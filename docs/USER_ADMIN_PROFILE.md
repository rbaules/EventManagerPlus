# Perfil administrativo de usuarios — Tarea 8C

> El cierre definitivo de promoción/retiro de Master y cambio de rol está en `USER_ROLE_TRANSITIONS.md`. La antigua RPC booleana deja de ser una ruta autorizada tras aplicar la migración 202608100002.

## Alcance implementado

8C agrega creación del perfil interno `evp_usr_usuario`, edición de nombre/correo con alcance controlado, cambio de estado por Master y cambio de condición Master por Master. No crea identidades en Supabase Auth. Cuando actúa un Administrador, el preregistro incluye obligatoriamente la relación inicial `evp_ucu_usuario_cuenta`; al crear un Operador/Consulta con evento predeterminado, la misma RPC crea también `evp_uev_usuario_evento`. La administración general posterior de relaciones corresponde a 8D.

La migración `202608060001_user_admin_profile_rpc.sql`, con rollback homónimo, ya fue aplicada satisfactoriamente en Supabase mediante el proceso manual del proyecto.

## Esquema auditado

La tabla usa PK UUID `usr_usuario_id` con `gen_random_uuid()`. Nombre tiene 50 caracteres, abreviatura 12, email 254 y un índice único `lower(trim(usr_email))`. `usr_usuario_auth_uuid` es UUID único y FK a `auth.users(id)` con `ON DELETE SET NULL`. Master es booleano `NOT NULL DEFAULT false`; estado es varchar(15) `NOT NULL DEFAULT 'Preregistrado'`. El CHECK real permite `Preregistrado`, `Activo`, `Inactivo` y `Suspendido`, aunque 8C deliberadamente solo acepta los tres primeros. Cuenta/evento predeterminados son enteros anulables; evento requiere cuenta y cuenta tiene FK. Hay timestamps, teléfono, trigger de modificación y dos setters de defaults.

Los triggers reales de `esquema.sql` son:

- `trg_evp_ucu_set_default`, `AFTER INSERT` sobre `evp_ucu_usuario_cuenta`, ejecuta `evp_fn_set_usuario_cuenta_default()`. Solo si la relación nueva está `Activa`, establece su cuenta como default cuando el usuario todavía tiene `usr_cuenta_id_default IS NULL`.
- `trg_evp_uev_set_default`, `AFTER INSERT` sobre `evp_uev_usuario_evento`, ejecuta `evp_fn_set_usuario_evento_default()`. Solo si la asignación nueva está `Activa`, completa la cuenta si está nula y completa el evento si está nulo y la cuenta existente es nula o coincide.

No son triggers de rechazo: proponen defaults implícitos tras insertar relaciones. La RPC incremental inserta primero el perfil con ambos defaults `NULL`, crea las relaciones y finalmente actualiza ambos campos con los parámetros explícitos. Ese `UPDATE` final también escribe `NULL` cuando no se eligió una preferencia, por lo que neutraliza el valor propuesto por los setters. Las FK y el CHECK de defaults se evalúan con las relaciones ya creadas. Todo ocurre en una sola llamada/transacción; cualquier fallo del `UPDATE` final revierte perfil y relaciones.

`evp_fn_vincular_usuario_auth()` compara correo normalizado, vincula el UUID Auth y cambia `Preregistrado` a `Activo`; si no encuentra perfil crea uno no Master `Inactivo`. Por esto 8C no activa manualmente un perfil sin UUID Auth.

## RPC y seguridad

- `evp_admin_crear_usuario(p_nombre text, p_email text, p_es_master boolean default false, p_cuenta_id integer default null, p_rol text default null, p_cuenta_default_id integer default null, p_evento_default_id integer default null)`.
- `evp_admin_actualizar_usuario(p_usuario_id uuid, p_nombre text, p_email text)`.
- `evp_admin_cambiar_estado_usuario(p_usuario_id uuid, p_estado text)`.
- `evp_admin_cambiar_master(p_usuario_id uuid, p_es_master boolean)`.

Todas son `SECURITY DEFINER`, usan `search_path=''`, nombres calificados y `auth.uid()`. Se revoca `PUBLIC`/`anon` y solo se concede ejecución pública de negocio a `authenticated`. No se concede escritura directa ni se usa `service_role` en el cliente.

Nombre y correo se normalizan y validan en PostgreSQL y Python. `unique_violation` se transforma en `USER_EMAIL_EXISTS`. Tanto el cambio de estado como el cambio de condición Master usan exactamente el mismo orden: (1) `pg_advisory_xact_lock(817301)`, (2) `SELECT` de la fila objetivo `FOR UPDATE`, (3) validaciones, (4) conteo de Masters activos cuando aplica y (5) `UPDATE`. El advisory lock se toma para todos los cambios de estado, eliminando la inversión de locks. No se permite auto-inactivación ni retirar el propio Master.

## Creación por Administrador: opción B aprobada e implementada

Cuando actúa un Administrador, una sola llamada a `evp_admin_crear_usuario` crea dentro de la misma transacción:

- el perfil `evp_usr_usuario` no Master en estado `Preregistrado`;
- la relación inicial `evp_ucu_usuario_cuenta` en estado `Activo`;
- dentro de una cuenta `Activa` que el actor administre mediante una relación `Administrador/Activo`;
- con rol inicial exclusivamente `Operador` o `Consulta`.

El actor se obtiene mediante `auth.uid()`. Si falla una validación, la inserción del perfil, la inserción de la relación o un constraint, PostgreSQL revierte la operación completa. No se crea primero el perfil para vincularlo mediante una segunda RPC. La relación inicial hace que el usuario quede visible inmediatamente en el listado del Administrador.

Master conserva flexibilidad: puede crear perfiles Master o no Master sin cuenta inicial. La firma admite opcionalmente cuenta activa y rol `Administrador`, `Operador` o `Consulta`, aunque la UI 8C mantiene el flujo Master sin vínculo para evitar complejidad innecesaria.

La administración general de relaciones usuario-cuenta —agregar otras cuentas, cambiar roles, reactivar o inactivar relaciones y administrar defaults— sigue pendiente para 8D. Esto no incluye la relación inicial obligatoria del preregistro por Administrador, que forma parte de 8C.

## Rollback y verificación previa

El rollback contiene únicamente `DROP FUNCTION IF EXISTS` en orden inverso de dependencia, por lo que puede ejecutarse dos veces. La prueba SQL verifica `SECURITY DEFINER`, `search_path`, propietario, ACL de las RPC y helpers, además del orden de los locks. También documenta pasos exactos para errores funcionales, rollback doble y concurrencia en dos sesiones.

## UI y servicio

Master y Administrador ven “Nuevo usuario”; solo Master ve el checkbox Master. Para un Administrador, el modal muestra `Cuenta` y `Rol inicial` como campos obligatorios, limita el rol a `Operador` o `Consulta` e informa que el usuario quedará vinculado a la cuenta seleccionada. Ya no indica que la vinculación se realizará en un paso posterior. Master ve edición global y acciones de estado/Master; Administrador solo ve la edición limitada por creador y alcance descrita abajo. Un preregistro sin Auth muestra la advertencia y no ofrece Activar. Los formularios bloquean doble envío, conservan datos ante error y refrescan tras éxito.

Cada operación del servicio llama exactamente una RPC, preautoriza localmente y convierte códigos controlados en mensajes sin SQL ni traceback. La base sigue siendo la autoridad final.

### Navegación y acciones posteriores a 8C

La causa del defecto original fue una doble carga: `page.go()` activaba el manejador de ruta y `abrir_detalle_usuario()` volvía a solicitar el mismo detalle; `loading=True` se interpretaba erróneamente como denegación y una respuesta asíncrona anterior podía sobrescribir el ID vigente. La carga manual de detalle conserva un número de solicitud y descarta respuestas obsoletas. Master puede abrir perfiles Master y no Master sin relación de cuenta.

El detalle diferencia autorización denegada, usuario inexistente y error de carga. Master dispone de edición y acciones globales según sus protecciones. Administrador puede editar nombre/correo de un objetivo no Master cuando comparte una cuenta Activa donde el actor tiene UCU Administrador/Activa y el objetivo UCU Operador/Consulta Activa; `usr_creado_por` no participa en esta decisión y se conserva para auditoría. Master puede inactivar Activo o Preregistrado; Inactivo solo puede reactivarse con Auth vinculada.

La navegación automática post-creación fue eliminada por decisión funcional. Tras crear, el modal se cierra, el detalle/selección anterior se limpia, el listado se consulta nuevamente y se muestra `Usuario creado correctamente.`. El `usuario_id` retornado se conserva solo para verificar/localizar el alta; el usuario abre después `Ver detalle` manualmente.

La corrección cuenta con pruebas automatizadas locales. La verificación manual dirigida con usuarios reales en FULL permanece pendiente antes de declarar cerrado el hallazgo funcional.

## Corrección incremental 8C pendiente de aplicación

El esquema aplicado no contiene creador auditable en `evp_usr_usuario`; compartir cuenta, fecha o correo no demuestra autoría. La migración incremental `202608080001_user_admin_profile_8c_fix.sql` propone `usr_creado_por uuid`, FK autorreferenciada, y hace que la RPC derive y guarde el actor mediante `auth.uid()`. Master conserva edición global. Administrador solo puede editar nombre/correo si es el creador real, el objetivo no es Master y ambos mantienen una relación Activa dentro de una cuenta Activa que el actor administra. Filas anteriores quedan con creador NULL y no son editables por Administrador.

### Auditoría inequívoca de `usr_creado`

En `esquema.sql`, `public.evp_usr_usuario.usr_creado` está definido exactamente como `timestamp with time zone DEFAULT now() NOT NULL`. Es una fecha/hora de creación, no un UUID. No tiene FK, tabla/columna referenciada ni trigger que le asigne identidad. `trg_evp_usr_touch` ejecuta `evp_fn_touch_usuario()` solamente en UPDATE y establece `NEW.usr_modificado = now()`; no toca `usr_creado`. Las inserciones omiten normalmente la columna y PostgreSQL aplica `now()`. Python la lee exclusivamente para mostrar auditoría temporal y no la escribe ni la usa para autorizar.

La búsqueda global confirma que el esquema sí usa el patrón `*_creado_por uuid` cuando representa identidad: por ejemplo `ivt_invitado_creado_por` tiene FK a `evp_usr_usuario(usr_usuario_id)`. `usr_creado` no sigue ese patrón ni puede compararse con `usr_usuario_id`. Por ello `usr_creado_por` no es redundante y permanece en la migración incremental. El cliente nunca envía su valor: la RPC resuelve `auth.uid()` a `v_actor_id` y lo persiste server-side.

La misma migración amplía `evp_admin_crear_usuario` con `p_cuenta_default_id` y `p_evento_default_id`. Master puede asignar cuenta/rol inicial a no Master (`Administrador`, `Operador`, `Consulta`) y defaults válidos; al crear otro Master no se exige relación redundante y los defaults se autorizan por acceso global. En no Master, la cuenta default debe coincidir con la relación inicial. Si el rol es Operador/Consulta y hay evento default, también se crea atómicamente la asignación activa al evento. Evento y cuenta se validan en PostgreSQL. Cuenta inicial y cuenta predeterminada son conceptos independientes: no se asignan defaults implícitamente. La respuesta JSON devuelve los valores leídos mediante `UPDATE ... RETURNING`; si solo existe cuenta inicial, `cuenta_default_id` es `null`, y `evento_default_id` refleja igualmente el valor persistido.

La UI Master es un superconjunto de la UI Administrador: ofrece cuenta inicial, rol, cuenta predeterminada y evento dependiente. Cambiar cuenta limpia el evento anterior. Administrador mantiene cuenta inicial y roles Operador/Consulta, sin defaults de terceros.

### Guion manual posterior a la migración

En FULL, como Master: (A) crear otro Master con cuenta/evento predeterminados; (B) crear Administrador con cuenta, cuenta/evento predeterminados; (C) crear Operador con cuenta y evento predeterminado; (D) crear Consulta con cuenta y evento predeterminado. En cada caso debe permanecer en el listado, aparecer el registro nuevo y abrirse su detalle solo mediante `Ver detalle`. Luego: (E) editar nombre/correo; (F) inactivar otro usuario; (G) reactivar uno Inactivo con Auth.

Como Administrador: (H) crear Operador; (I) crear Consulta; (J) confirmar permanencia y visibilidad en el listado; (K) editar solamente un usuario creado por ese mismo Administrador. Repetir con un usuario creado por otro actor para confirmar `USER_EDIT_FORBIDDEN`.

## Pendiente

Quedan: administración general de vínculos y roles por cuenta en 8D, asignación por evento, defaults, invitación/creación Auth automática, contraseñas, verificación RLS y eliminación física. La validación manual dirigida FULL continúa pendiente.
# Consolidación vigente

Este perfil se complementa y, donde exista contradicción, es sustituido por `USER_ACCESS_AND_PREFERENCES.md`. Cuenta y evento son el contexto activo obligatorio, no selectores del formulario.
