# Módulo administrativo de lugares y salones

Estado: implementado localmente el 29 de julio de 2026. No se ejecutó SQL
remoto, no se activó RLS y no se modificaron dependencias.

## Alcance entregado

El módulo aparece únicamente en modo FULL y solo para Master o Administrador.
Permite listar, crear, editar, activar, suspender e inactivar lugares de la
cuenta activa y sus salones. No contiene eliminación física, operaciones
masivas, Realtime ni administración de países.

El servicio recibe explícitamente el cliente Supabase y el contexto. Obtiene la
cuenta desde el contexto autorizado, filtra todas las consultas por tenant,
rechaza IDs sensibles enviados en los datos y omite los IDs relativos durante
el alta para que los triggers existentes los generen.

Operador y Consulta no ven el acceso administrativo ni pueden llamar las
mutaciones del servicio. CHECKIN no expone el módulo. La navegación inferior no
cambió; el acceso se añadió al menú de usuario para no saturar la barra.

## Contrato de datos usado

- `evp_pai_pais`: catálogo de países de solo lectura.
- `evp_lug_lugar`: PK `(lug_cuenta_id, lug_lugar_id)`; nombre, dirección,
  ciudad, país, tipo y estado.
- `evp_sal_salon`: PK `(sal_cuenta_id, sal_lugar_id, sal_salon_id)`; nombre,
  ubicación, máximos de mesas/invitados y estado.
- Estados reales: `Activo`, `Suspendido`, `Inactivo`.
- Tipos reales de lugar: `Hotel`, `Sala de eventos`, `Otro`.
- `trg_evp_lug_set_id` y `trg_evp_sal_set_id` generan los consecutivos.

El esquema documentado no declara abreviatura, observaciones ni columnas de
auditoría para estas tablas; la UI no las inventa. Tampoco documenta una
restricción única para nombres. La aplicación detecta duplicados normalizando
espacios, mayúsculas y acentos dentro de cuenta, y dentro de cuenta/lugar para
salones. Esa comprobación no sustituye una restricción única concurrente. Antes
de proponerla debe validarse la metadata remota y acordarse la regla de negocio.

## Dependencias y baja lógica

Al cambiar un lugar o salón desde `Activo` se consultan eventos que lo usan. La
operación se bloquea si existe un evento no cerrado; no se borra ninguna fila.
Los eventos cerrados conservan la referencia histórica.

No se implementó transición automática de eventos, cascada ni RPC. Estas reglas
deben permanecer explícitas cuando se construya el módulo de eventos.

## Diseño RLS propuesto, no aplicado

La migración local propuesta separa las políticas:

- SELECT Master/Administrador: lugares y salones de sus cuentas.
- SELECT Operador/Consulta: solo los vinculados a eventos asignados.
- INSERT/UPDATE: únicamente Master/Administrador de la cuenta.
- DELETE: sin grant y sin política.
- País: SELECT autenticado; sin mantenimiento desde este módulo.

La aplicación sigue protegiendo tenant y rol aunque RLS remota todavía no esté
confirmada. La migración debe contrastarse con metadata/grants reales, dividirse
por etapas y probarse con JWT de cada rol en staging antes de aplicarse.

## Prueba manual recomendada

1. En FULL como Master, cambiar de cuenta y verificar aislamiento del catálogo.
2. Como Administrador, crear un lugar y un salón sin proporcionar IDs.
3. Editar nombre, dirección, ubicación y capacidades; recargar y comprobarlos.
4. Intentar duplicar nombres con diferencias de espacios, acentos o mayúsculas.
5. Suspender/reactivar un salón y un lugar sin eventos abiertos.
6. Confirmar que un evento no cerrado bloquea la inactivación correspondiente.
7. Abrir FULL como Operador y Consulta: no debe aparecer el acceso.
8. Abrir CHECKIN con cualquier rol: no debe aparecer el módulo.
9. Simular error de red: la vista debe conservar un error controlado y reintento.
10. Validar en Supabase que no hubo DELETE y que los IDs provinieron del trigger.

## Próximos módulos sugeridos

El siguiente bloque funcional es administración de cuentas para Master o
creación/configuración de eventos. Este último ya puede reutilizar el catálogo
de lugar/salón, pero requiere definir máquina de fases, cierre y RPC.
