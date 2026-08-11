# Diseño de seguridad RLS de EventPlus

> Extensión 8C: RPC `SECURITY DEFINER` con actor derivado de `auth.uid()`, sin `service_role` ni escritura directa; migración pendiente de aplicación y prueba.

## Importación Excel — diseño futuro, no aplicado

La importación no usará INSERT directos desde Python. Una única RPC futura
recibirá selectores de cuenta/evento no confiables y un payload JSON sin IDs de
tenant; derivará al usuario desde `auth.uid()`, exigirá usuario Activo y rol
Master o Administrador dentro del alcance, y revalidará evento `Activo` en
`Pre_evento` y ausencia total de mesas, invitaciones e invitados. Operador,
Consulta y `anon` no tendrán EXECUTE.

La función deberá ser `SECURITY DEFINER` con `search_path` fijo, límites de
payload, locks contra concurrencia y rollback natural ante cualquier excepción.
Debe omitir IDs internos para usar los triggers vigentes, revocar EXECUTE de
`public`/`anon` y concederlo únicamente a `authenticated`. Su diseño SQL,
políticas y pruebas transaccionales siguen pendientes; nada de esto fue aplicado
remotamente. Véase `docs/EXCEL_IMPORT_DESIGN.md`.

## Administración de eventos — diseño futuro

Master/Administrador: SELECT, INSERT y UPDATE solo dentro del alcance y con
`WITH CHECK` que conserve `eve_cuenta_id`. Operador/Consulta: SELECT únicamente
de eventos asignados; ninguna escritura administrativa. Anon: sin acceso.
DELETE directo no se concede.

Fuente autoritativa: `C:\WORKSPACE\EVENTPLUS\esquema.sql`. `eve_tipo_evento`
debe ser `Boda`, `Cumpleaños`, `Quinceaños`, `Corporativo` u `Otro`.

Crear, cambiar ubicación/estado, iniciar y cerrar deben migrar a RPC
`SECURITY DEFINER` endurecidas antes de activar RLS. Cada RPC debe resolver
`auth.uid()`, validar rol/tenant, bloquear columnas protegidas y comparar
fase/estado actual para concurrencia. El predeterminado debe actualizar
exclusivamente la fila propia de `evp_usr_usuario`. Este diseño no ha sido
aplicado remotamente.

Estado: **diseñado, no aplicado**. Fecha: 27 de julio de 2026.

## Alcance, evidencia y limitaciones

Se revisaron los documentos de contexto y esquema, configuración, cliente
Supabase, todos los servicios, vistas y scripts funcionales, y todos los
archivos SQL/migraciones presentes. El repositorio no contenía DDL ni
migraciones previas: `EVENTPLUS_SCHEMA_CONTEXT_v1_1.md` es la única fuente
local de estructura y se declara como contrato del SQL v1.1. Antes de aplicar
la propuesta debe ejecutarse `scripts/supabase_rls_diagnostics.sql`, comparar
el resultado con este documento y guardar los grants/políticas como respaldo.

No se inventaron columnas. No puede confirmarse localmente: nombres y acciones
exactas de todas las FK, propietarios, grants actuales, definiciones reales de
funciones/vistas, políticas existentes, `security_invoker` de vistas, ni
publicaciones Realtime. El diagnóstico de solo lectura obtiene esos faltantes.

## Modelo de amenazas

El adversario es un usuario anónimo o autenticado que usa la publishable key y
REST/PostgREST directamente, altera `cuenta_id`, `evento_id`, rol o payload,
intenta autoasignarse, mover filas entre tenants, modificar columnas de
auditoría o ejecutar una operación fuera de fase. También se consideran errores
de UI/Python, concurrencia de llegadas, vistas que eludan RLS y una futura
suscripción Realtime. La cookie opaca y `usuario_contexto` no son autoridades.

La raíz única de autorización es:

`auth.uid()` → `evp_usr_usuario.usr_usuario_auth_uuid` (usuario Activo) →
`usr_usuario_id` → relación activa de cuenta → relación activa de evento.

Master es `usr_es_usuario_master=true` en un usuario activo. Administrador,
Operador y Consulta proceden exclusivamente de `ucu_rol`. Administrador ve
todos los eventos activos de una cuenta activa; Operador y Consulta requieren
además `evp_uev_usuario_evento` activo. Operar llegadas exige evento Activo en
`En_proceso`, y Consulta queda excluido aunque tenga asignación. Consulta es un
rol de cuenta estrictamente de lectura: no es Master ni equivale a inactividad.

## Inventario real

| Tabla | PK documentada | FK/tenant documentado | Estado/rol | Operaciones del código |
|---|---|---|---|---|
| `evp_cta_cuenta` | `cta_cuenta_id` | raíz de cuenta | `cta_estado` | SELECT |
| `evp_usr_usuario` | `usr_usuario_id` | Auth UUID; defaults a cuenta/evento | `usr_estado`, master | SELECT |
| `evp_ucu_usuario_cuenta` | cuenta + usuario | cuenta, usuario | `ucu_estado`, `ucu_rol` | SELECT |
| `evp_pai_pais` | `pai_pais_id` | ninguna; catálogo | — | no usada |
| `evp_lug_lugar` | cuenta + lugar | cuenta, país | `lug_estado` | módulo FULL Master/Admin |
| `evp_sal_salon` | cuenta + lugar + salón | cuenta/lugar | `sal_estado` | módulo FULL Master/Admin |
| `evp_eve_evento` | cuenta + evento | cuenta, lugar/salón | `eve_estado`, `eve_fase_evento` | SELECT |
| `evp_uev_usuario_evento` | cuenta + evento + usuario | cuenta/evento/usuario | `uev_estado` | SELECT |
| `evp_mes_mesa` | cuenta + evento + mesa | cuenta/evento | `mes_estado` | no usada directamente |
| `evp_inv_invitacion` | cuenta + evento + invitación | cuenta/evento | `inv_estado` | SELECT |
| `evp_ivt_invitado` | cuenta + evento + invitación + invitado | cuenta/evento/invitación, usuarios auditoría | `ivt_estado` | SELECT, INSERT, UPDATE; sin DELETE físico |

Vistas documentadas: `evp_vw_mesa_resumen` y `evp_vw_evento_resumen`; el código
actual no las consulta. Deben ser `security_invoker=true` en PostgreSQL 15+ o
revocarse de `anon/authenticated` hasta verificar que no eluden RLS.

Funciones documentadas: `evp_normalizar_texto`, seis asignadores de ID,
`evp_fn_touch_usuario`, `evp_fn_touch_invitado`, dos setters de defaults,
`evp_fn_vincular_usuario_auth`, `evp_usuario_id_actual`,
`evp_es_usuario_master`, `evp_tiene_acceso_cuenta` y
`evp_puede_ver_evento`. Ninguna es llamada por RPC desde Python.

Triggers documentados: asignación de IDs para lugar, salón, evento, mesa,
invitación e invitado; touch de usuario/invitado; defaults de cuenta/evento; y
vinculación de `auth.users` con usuario EventPlus. Se requiere auditar sus
definiciones y privilegios reales.

Inconsistencias: la solicitud menciona “mesas/tipos/estados/catálogos” de modo
genérico; el contrato solo define `evp_mes_mesa` y `evp_pai_pais`, y tipos y
estados son columnas con `CHECK`, no tablas documentadas. “Master,
Administrador, Operador” omite `Consulta`. Los helpers existentes tienen
nombres distintos de los nuevos `evp_rls_*`. La app obtiene mesas leyendo
`ivt_mesa_id`, no `evp_mes_mesa`.

## Funciones auxiliares

La propuesta crea `evp_rls_usuario_id`, `evp_rls_es_master`,
`evp_rls_rol_cuenta`, `evp_rls_tiene_cuenta`, `evp_rls_tiene_evento`,
`evp_rls_puede_administrar_evento` y `evp_rls_puede_operar_evento`.

Todas requieren `SECURITY DEFINER` porque consultan tablas que ellas mismas
ayudan a proteger; `SECURITY INVOKER` produciría recursión o decisiones
dependientes de políticas intermedias. Mitigaciones: cuerpo SQL simple,
identidad solo desde `auth.uid()`, parámetros escalares tipados, `STABLE`,
objetos calificados, `search_path = pg_catalog, public, auth`, ejecución
revocada a `PUBLIC/anon` y concedida solo a `authenticated`. Debe confirmarse
que el propietario no es un rol de login y que nadie salvo migraciones puede
reemplazarlas. No usan `service_role`.

## Matriz de roles

| Recurso/acción | Master | Administrador | Operador asignado | Consulta | Sin relación/anónimo |
|---|---:|---:|---:|---:|---:|
| Propio usuario | Sí | Sí | Sí | Sí | No |
| Cuentas autorizadas | todas (modelo actual) | leer | leer | leer | No |
| Eventos autorizados | todos | cuenta | asignados | asignados/leer | No |
| Invitaciones/invitados SELECT | Sí | Sí | asignados | asignados/leer | No |
| Administrar evento/invitación/invitado | Sí | Sí | No | No | No |
| Confirmar/revertir llegada en proceso | Sí | Sí | Sí | No | No |
| Gestionar asignaciones | Sí; solo Master asigna/retira Admin | cuenta propia; solo Operador/Consulta | No | No | No |

## Matriz de políticas y pruebas

`U` es `USING`, `C` es `WITH CHECK`; “admin-evento” y “operar-evento” son los
helpers anteriores.

| Tabla | Op. | Autorizado | U / C | Riesgo y prueba positiva/negativa |
|---|---|---|---|---|
| usuario | SELECT | propio; Master justificado para administración | Auth UUID / — | Master global expone PII; A ve A, operador no ve B |
| usuario | I/U/D | ninguno directo | — | trigger Auth debe seguir funcionando; cliente no eleva master/estado |
| usuario-cuenta | SELECT | propio, Master/Admin cuenta | pertenencia / — | A ve relaciones A, no B |
| usuario-cuenta | I/U | Master; Admin de cuenta solo para Operador/Consulta | rol cuenta / rol permitido y misma cuenta activa | solo Master asigna/retira Admin; Admin asigna operador/consulta; operador no se autoasigna ni eleva rol |
| usuario-cuenta | DELETE/baja | Master; Admin solo relación Operador/Consulta de su cuenta, no sí mismo | rol y usuario distinto / — | Admin inactiva relación de tercero; no elimina su propia autoridad ni afecta perfil global |
| usuario-evento | SELECT | propio, Master/Admin cuenta | pertenencia/rol / — | operador ve su asignación, no A2 |
| usuario-evento | I/U/D | Master/Admin cuenta | rol / misma cuenta | Admin asigna A1; operador no se autoasigna |
| cuenta | SELECT | relación activa o Master | tiene-cuenta / — | A lee A; no B |
| cuenta | UPDATE | solo Master | master / master | no cambiar ID; grants deben limitar columnas |
| cuenta | I/D | ninguno directo | — | API directa denegada |
| evento | SELECT | evento autorizado | tiene-evento / — | operador A1 lee A1; no A2/B |
| evento | INSERT/UPDATE | Master/Admin | rol/admin-evento / misma cuenta | Admin crea/edita en A; no mueve a B |
| evento | DELETE | Master | master / — | Admin no borra; preferir baja lógica |
| lugar/salón | SELECT | cuenta autorizada | tiene-cuenta / — | aislamiento A/B |
| lugar/salón | I/U/D | Master/Admin | rol / misma cuenta | operador denegado; FK/IDs inmutables |
| mesa | SELECT | evento autorizado | tiene-evento / — | A1 sí, A2 no |
| mesa | I/U/D | Master/Admin | admin-evento / mismo evento | operador denegado |
| invitación | SELECT | evento autorizado | tiene-evento / — | A1 sí, B no |
| invitación | I/U/D | Master/Admin | admin-evento / mismo evento | operador denegado; fase debe añadirse al helper antes de activar |
| invitado | SELECT | evento autorizado | tiene-evento / — | evento/tenant aislado |
| invitado | INSERT/UPDATE | Master/Admin directo | admin-evento / mismo evento | IDs no se mueven; UPDATE directo revocado inicialmente |
| invitado | DELETE | Master, excepcional | master / — | app usa baja lógica, no DELETE |
| país | SELECT | autenticado | `true` justificado / — | anónimo no; autenticado sí |
| país | I/U/D | ninguno cliente | — | catálogo inmutable por API |

Todas las tablas quedan con RLS en el SQL integral, pero el orden de activación
posterior debe separar los bloques. No debe ejecutarse la migración integral
sin dividirla y validar cada etapa.

## Protección de columnas y RPC

RLS decide filas, no columnas. Son inmutables desde clientes:
`*_cuenta_id`, `*_evento_id`, IDs relativos, `usr_usuario_auth_uuid`,
`usr_es_usuario_master`, roles/estados de autorización y campos de auditoría.
Los grants globales de `authenticated` no pueden dar a Administrador columnas
de perfil y simultáneamente dar a Operador solo columnas de llegada. Por ello
la propuesta revoca todas las mutaciones directas de `evp_ivt_invitado`.

RPC recomendadas, todas transaccionales, `SECURITY DEFINER` endurecidas y sin
aceptar cuenta, evento, usuario ni timestamp como autoridad:

- `evp_confirmar_llegada(p_invitado_uuid uuid)`.
- `evp_reversar_llegada(p_invitado_uuid uuid)`.
- `evp_confirmar_llegadas(p_invitado_uuids uuid[])`: bloquea/valida todo el
  grupo y actualiza todo o nada.
- `evp_crear_invitado_imprevisto(...)` y
  `evp_desactivar_invitado_imprevisto(uuid)`.
- RPC administrativas de crear/editar invitado planificado si se desea evitar
  grants amplios; son la opción recomendada.

La operación grupal actual puede confirmar unas filas y omitir otras; no es
atómica. Los timestamps y `ivt_usuario_conf_llegada` proceden hoy de Python y
deben establecerse con `clock_timestamp()` y `evp_rls_usuario_id()` en SQL.

## Plan de pruebas de seguridad

Preparar ocho identidades separadas: Master A, Admin A, Operador A1, Operador
A2, Consulta A1, usuario B, usuario autenticado sin relación y usuario
inactivo; añadir cliente anónimo. Usar sus JWT reales en staging, nunca
`service_role`, y ejecutar tanto cliente Supabase como REST directo.

Pruebas obligatorias: A no lee cuenta/evento B; A1 no lee A2; Consulta A1 lee
solo A1 y no puede mutar ni ejecutar RPC de escritura; adulterar cuenta
o evento no amplía acceso; no hay autoasignación de cuenta/evento; Operador no
eleva rol ni administra; Operador confirma/revierte solo en evento activo y
fase válida; Admin sí administra lo permitido; inactivo/anónimo no acceden;
UPDATE no mueve tenant ni cambia auditoría; DELETE respeta rol; consultas
legítimas actuales siguen funcionando; publishable key sin JWT no basta; REST
y futura Realtime producen el mismo aislamiento. Para cada SELECT/INSERT/
UPDATE/DELETE comprobar caso permitido y denegado, respuesta y estado final.

## Activación gradual y rollback

| Etapa | Cambio | Riesgo/validación | Respaldo y criterio de rollback |
|---|---|---|---|
| 1 | helpers | owner/search_path/recursión | exportar definiciones; rollback ante resultado incorrecto por identidad |
| 2 | usuario y relaciones | bloquear login/contexto | exportar grants/policies; rollback si falla cualquier identidad válida |
| 3 | cuenta y evento | bloquear selección | probar matriz A/A1/A2/B; rollback por fuga o falso rechazo |
| 4 | invitación/invitado SELECT | romper listas/dashboard | comparar consultas actuales; rollback por fuga o UI ilegítimamente vacía |
| 5 | escrituras | pérdida funcional | snapshot y staging; rollback ante columna mutable o flujo roto |
| 6 | RPC sensibles | concurrencia/atomicidad | pruebas transaccionales y carga; rollback si hay actualización parcial |
| 7 | Realtime | fuga por suscripción | staging y dos tenants; retirar publicación ante evento cruzado |

Cada etapa requiere inventario previo, backup lógico/point-in-time de la
plataforma, pruebas positivas y negativas, observación de logs sin datos
sensibles y aprobación explícita. El rollback incluido solo elimina objetos de
esta propuesta; deliberadamente no deshabilita RLS ni restaura grants
desconocidos. Los grants se restauran desde el inventario previo.

## Decisiones pendientes antes de aplicar

1. Comparar DDL remoto, FK, checks, owners, grants y políticas con el contrato.
2. Validar técnicamente la decisión aprobada: Master ve y administra cuentas/eventos inactivos; Admin los ve en sus cuentas sin uso operativo; Operador/Consulta no acceden.
3. Implementar la decisión aprobada de que solo Master asigna o retira Administrador; Admin solo gestiona relaciones Operador/Consulta de sus cuentas activas.
4. Definir fases permitidas para invitaciones, invitados y reversión.
5. Decidir si eliminación es siempre baja lógica.
6. Confirmar reglas de imprevistos en FULL frente a CHECKIN.
7. Auditar trigger de vinculación Auth para que RLS/grants no lo rompan.
8. Endurecer vistas como `security_invoker` o no exponerlas.
9. Diseñar e implementar RPC antes de habilitar escrituras.
10. Dividir la migración integral por etapas y probarla en staging.
# Importación Excel transaccional (7C)

La única ruta de escritura del importador es EXECUTE sobre
`public.evp_importar_evento_desde_json(integer,integer,jsonb,text)`. Es
`SECURITY DEFINER`, deriva identidad con `auth.uid()`, fija `search_path`, valida
tenant/rol/evento y mantiene `anon`/`PUBLIC` revocados. No requiere ni justifica
conceder INSERT directo. La sentencia es atómica y usa locks por evento. Esta
preparación no activa RLS; debe coordinarse con la fase RLS futura.

# Diseño del módulo de usuarios (8A)

`docs/USER_ADMIN_MODULE_DESIGN.md` concreta el alcance por cuenta, las
protecciones del último Master, las RPC específicas y la invalidación de
capacidades. Es diseño: no añade políticas, grants ni funciones. La existencia
del trigger Auth que invoca `evp_fn_vincular_usuario_auth` debe verificarse en
metadatos remotos antes de implementar altas.

La Tarea 8B añadió únicamente consultas SELECT desde
`services/usuario_admin_service.py`. El servicio vuelve a derivar las cuentas
administrativas activas del actor y recorta relaciones/detalle al alcance
visible; no usa `service_role`. Esto no sustituye RLS: antes de declarar la
integración cerrada deben probarse las políticas SELECT reales con Master,
Administrador, Operador, Consulta y dos tenants. No se aplicó SQL remoto.
### Decisión aprobada 8C-B: creación por Administrador

`evp_admin_crear_usuario` obtiene el actor exclusivamente con `auth.uid()`. Un Administrador solo puede crear un no Master `Preregistrado` dentro de una cuenta Activa donde tenga relación `Administrador/Activo`, con rol inicial `Operador` o `Consulta`. Perfil y relación se crean en una sola transacción `SECURITY DEFINER`, sin INSERT directo, `service_role` ni segunda RPC. Master puede omitir cuenta/rol o proporcionar una cuenta Activa y un rol válido.

La corrección incremental 8C propuesta agrega `usr_creado_por` porque el esquema aplicado no permite demostrar autoría. La edición por Admin exige simultáneamente creador exacto, objetivo no Master y alcance administrativo activo compartido. La creación con defaults valida cuenta/evento y acceso en la RPC; no acepta creador desde el cliente. Operador/Consulta recibe una asignación activa si se establece evento default. Master usa acceso global y no requiere relación redundante. No se modifica RLS.

`usr_creado` no es una identidad: es `timestamptz NOT NULL DEFAULT now()`, no tiene FK y solo registra el instante del alta. La identidad del creador requiere una columna UUID independiente. La RPC obtiene ese UUID interno exclusivamente desde `auth.uid()`; no existe parámetro de creador manipulable por el cliente.
# Consolidación de RPC de usuarios

Las RPC incrementales y el orden de locks se documentan en `USER_ACCESS_AND_PREFERENCES.md`. Los defaults son preferencias y nunca sustituyen la verificación de acceso efectivo.
