# Administración general de accesos de usuarios

Estado: implementación local preparada; migración y prueba manual pendientes. No declarar cerrado este bloque hasta aplicar `202608110003_user_access_management.sql` en el entorno autorizado.

## Modelo y matriz

Master tiene acceso global y nunca recibe UCU/UEV. Administrador hereda todos los eventos activos de cada UCU `Administrador/Activo` y no recibe UEV. Operador y Consulta requieren UCU activa y UEV activa.

“Un Administrador no administra personas globalmente; administra accesos dentro de las cuentas que tiene autorizadas.” Solo Master es una condición global. Administrador, Operador y Consulta son roles por cuenta, por lo que una persona puede ser Operador en A, Administrador en B y Consulta en C sin inconsistencia.

| Actor | Objetivo | UCU | Roles | UEV |
|---|---|---|---|---|
| Master | No Master Activo/Preregistrado | agregar, cambiar, inactivar, reactivar | Administrador, Operador, Consulta | administrar para Operador/Consulta |
| Administrador | No Master, evaluado solo en la cuenta administrada | agregar, cambiar, inactivar, reactivar | Operador, Consulta | administrar dentro de su cuenta |

Administrador no puede administrar una relación UCU cuyo rol en esa misma cuenta sea Administrador, esté activa o inactiva. Un rol Administrador del objetivo en otra cuenta no bloquea ni se revela. La autoridad exacta exige actor Activo con UCU `Administrador/Activo` sobre `p_cuenta_id`, cuenta Activa y objetivo no Master en estado Activo o Preregistrado.

Inactivo y Suspendido quedan bloqueados server-side. Preregistrado puede prepararse. No hay DELETE físico. Reactivar conserva historia y no establece defaults. Inactivar UCU/UEV llama la limpieza vigente; nunca se elige un default sustituto.

Reactivar una UCU con un rol diferente aplica las mismas reglas de transición que un cambio de rol sobre una UCU activa. Un helper privado común evita que ambas rutas diverjan:

- mismo rol Operador/Consulta: conserva las UEV históricas y garantiza el evento inicial activo;
- Operador ↔ Consulta: conserva todas las filas y estados históricos, y activa/reactiva el evento inicial;
- Operador/Consulta → Administrador: inactiva todas las UEV de esa cuenta sin borrarlas;
- Administrador → Operador/Consulta: inactiva primero todas las UEV y deja activo únicamente el evento inicial elegido.

La reactivación no asigna defaults. Primero restaura los valores anteriores para neutralizar setters automáticos y luego ejecuta `evp_priv_limpiar_defaults`: un default que todavía sea válido permanece y uno que perdió acceso queda `NULL`; nunca se elige un sustituto. Esto aplica al mismo rol y a todas las transiciones.

El helper de limpieza fue auditado en `202608100001_user_access_defaults_preferences.sql`: es `SECURITY DEFINER`, usa `search_path=''` y su ACL revoca `PUBLIC`, `anon` y `authenticated`. Evalúa Activo/Preregistrado mediante `evp_priv_usuario_puede_tener_default`; Administrador conserva un evento Activo por acceso heredado aunque la UEV esté Inactiva, mientras Operador/Consulta requieren UEV Activa.

## RPC

Se reutilizan `evp_admin_cambiar_rol_cuenta` y `evp_admin_cambiar_estado_cuenta`. Se agregan `evp_admin_agregar_cuenta_usuario`, `evp_admin_agregar_evento_usuario`, `evp_admin_cambiar_estado_evento_usuario` y la búsqueda mínima `evp_admin_buscar_usuario_para_cuenta`. `evp_priv_8d_aplicar_transicion_rol` centraliza la semántica UEV y no es ejecutable por roles cliente. Todas usan `SECURITY DEFINER`, `SET search_path=''`, `auth.uid()` en las entradas públicas, validación de alcance y locks actor → objetivo → cuenta → UCU → evento → UEV.

## Búsqueda controlada y privacidad

La incorporación de un usuario todavía no visible comienza seleccionando una cuenta autorizada y ejecutando una búsqueda explícita de al menos tres caracteres. Se devuelven como máximo 20 candidatos no Master en estado Activo o Preregistrado. Los únicos campos son ID técnico, nombre, email, estado y rol/estado de la UCU de la cuenta consultada. No se retornan otras cuentas, roles externos ni eventos. Un Master, Inactivo o Suspendido produce el mismo resultado genérico de ausencia de candidatos elegibles.

## UI y capabilities

El detalle muestra Cuentas y Eventos como cards utilizables en móvil y escritorio. Master objetivo muestra acceso global sin mantenimiento redundante. Las acciones usan capabilities explícitas de agregar/cambiar/inactivar/reactivar UCU/UEV; SQL sigue siendo autoridad. Cada éxito refresca detalle y grid mediante los request IDs existentes.

## Guion manual pendiente

1. Aplicar la migración en un entorno autorizado y ejecutar `scripts/test_user_access_management_rpc.sql` con fixtures aislados.
2. Como Master: alta Administrador sin UEV; altas Operador/Consulta con evento; duplicado y reactivación; transiciones de rol; inactivar/reactivar; rechazo de Master objetivo.
3. Como Administrador: altas Operador/Consulta propias; permitir objetivo Administrador en otra cuenta; rechazar únicamente UCU Administrador de la misma cuenta, cuenta ajena y Master; cambio Operador ↔ Consulta.
4. UEV: agregar/inactivar/reactivar, evento de otra cuenta, UCU inactiva, objetivo Administrador/Master y limpieza de evento default.
5. Estados: Activo y Preregistrado permitidos; Inactivo y Suspendido bloqueados.
6. Confirmar conteos inmediatos, ausencia de detalle obsoleto, experiencia FULL/CHECKIN y cards en viewport móvil.

Las pruebas Python usan una DB mock y validan servicio, contrato RPC y estructura SQL/UI; no son integración PostgreSQL. `scripts/test_user_access_management_rpc.sql` separa: A) auditoría read-only posterior a migración; B) prueba funcional autocontenida dentro de `BEGIN/ROLLBACK`; C) concurrencia manual en dos sesiones. La sección B usa únicamente los perfiles reales Master/Admin A como actores, sin modificarlos, y crea ocho targets `Preregistrado` sintéticos que desaparecen con el rollback. No inserta en `auth.users`: simula `auth.uid()` con el patrón validado `set_config('request.jwt.claim.sub', ..., true)` y comprueba inmediatamente el UUID. Los eventos se identifican siempre por `(cuenta_id, evento_id)`, porque `evento_id` no es global. Las pruebas funcional PostgreSQL y de concurrencia siguen pendientes de ejecución manual.
