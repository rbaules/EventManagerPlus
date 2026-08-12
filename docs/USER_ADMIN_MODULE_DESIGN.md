# Administración de usuarios — auditoría y diseño (Tarea 8A)

> La matriz vigente de transiciones está en `USER_ROLE_TRANSITIONS.md`. La administración general UCU/UEV, sin escrituras directas desde Python, está en `USER_ACCESS_MANAGEMENT.md`.

> Estado 8C (2026-08-06): escrituras del perfil implementadas mediante cuatro RPC; la creación por Administrador incluye la relación inicial atómica aprobada. La administración general de relaciones, eventos, defaults e invitación Auth sigue pendiente. Véase `USER_ADMIN_PROFILE.md`.

Estado: diseño aprobado. 8B implementó listado/detalle y 8C implementó localmente las escrituras seguras del perfil mediante RPC, incluida la relación inicial al preregistrar como Administrador. Quedan pendientes aplicar/probar SQL, validar RLS SELECT, el alta Auth y la administración general de relaciones de cuenta/evento. Este documento usa como autoridad `esquema.sql` y el código productivo actual.

## 1. Esquema auditado

### `public.evp_usr_usuario`

Perfil interno. Columnas: `usr_usuario_id uuid NOT NULL DEFAULT extensions.gen_random_uuid()`; `usr_nombre_usuario varchar(50) NOT NULL`; `usr_nombre_usuario_abrev varchar(12) NOT NULL`; `usr_usuario_auth_uuid uuid NULL`; `usr_es_usuario_master boolean NOT NULL DEFAULT false`; `usr_email varchar(254) NOT NULL`; `usr_cuenta_id_default integer NULL`; `usr_evento_id_default integer NULL`; `usr_telefono varchar(20) NULL`; `usr_creado timestamptz NOT NULL DEFAULT now()`; `usr_modificado timestamptz NULL`; `usr_estado varchar(15) NOT NULL DEFAULT 'Preregistrado'`.

- PK: `usr_usuario_id`.
- UNIQUE: `usr_usuario_auth_uuid`; índice único `ux_evp_usr_email_norm` sobre `lower(trim(usr_email))` (no parcial).
- FK: Auth UUID a `auth.users(id) ON DELETE SET NULL`; cuenta predeterminada a cuenta; `(usr_cuenta_id_default, usr_evento_id_default)` a la PK compuesta del evento.
- CHECK: un evento predeterminado exige cuenta; estados `Preregistrado`, `Activo`, `Inactivo`, `Suspendido`.
- Trigger: `trg_evp_usr_touch` actualiza `usr_modificado` antes de UPDATE mediante `evp_fn_touch_usuario`.
- No hay columnas `creado_por`/`modificado_por`; solo timestamps. El UUID interno no es el UUID Auth.
- Auditoría 8C-FIX: `usr_creado` es `timestamptz NOT NULL DEFAULT now()`, sin FK ni trigger de identidad. Su semántica es instante de creación. No sustituye al `usr_creado_por uuid` propuesto para autoría verificable.

### `public.evp_ucu_usuario_cuenta`

Relación y rol por cuenta: `ucu_cuenta_id integer NOT NULL`, `ucu_usuario_id uuid NOT NULL`, `ucu_rol varchar(20) NOT NULL`, `ucu_estado varchar(15) NOT NULL DEFAULT 'Activo'`.

- PK `(ucu_cuenta_id, ucu_usuario_id)`: impide duplicados incluso inactivos; una fila se reactiva.
- FK a cuenta y usuario.
- CHECK rol: `Administrador`, `Operador`, `Consulta`; estado: `Activo`, `Suspendido`, `Inactivo`.
- Trigger AFTER INSERT `trg_evp_ucu_set_default`: si la relación nace activa y el usuario no tiene cuenta predeterminada, la establece.
- No tiene ID artificial, fechas ni auditoría. No garantiza que una cuenta predeterminada siga activa o vinculada después de cambios.

### `public.evp_uev_usuario_evento`

Asignación directa: `uev_cuenta_id integer NOT NULL`, `uev_evento_id integer NOT NULL`, `uev_usuario_id uuid NOT NULL`, `uev_estado varchar(15) NOT NULL DEFAULT 'Activo'`.

- PK `(cuenta, evento, usuario)`: impide duplicados y permite reactivación.
- FK `(cuenta, evento)` al evento: evita evento de otra cuenta.
- FK `(cuenta, usuario)` a `evp_ucu_usuario_cuenta`: impide asignación sin una fila usuario-cuenta, aunque no exige que esa fila esté activa.
- CHECK estado: `Activo`, `Suspendido`, `Inactivo`.
- Trigger AFTER INSERT `trg_evp_uev_set_default`: para relación activa completa defaults nulos de cuenta/evento bajo condiciones de coherencia.
- No tiene fechas/auditoría ni limita la asignación a Operador/Consulta.

### `public.evp_cta_cuenta`

Cuenta: ID `integer GENERATED ALWAYS AS IDENTITY`, nombre `varchar(100)`, abreviatura `varchar(15)`, contacto `varchar(80)`, teléfono `varchar(20)`, email `varchar(254)`, suscripción `varchar(15) DEFAULT Demo`, vencimiento `date`, estado `varchar(15) DEFAULT Activo`. PK por ID. Checks: suscripción `Premium/Estandar/Demo`; estado `Activo/Inactivo/Suspendido`. Sin UNIQUE de nombre/email, timestamps ni auditoría.

### `public.evp_eve_evento`

PK `(eve_cuenta_id, eve_evento_id)`. Nombre `varchar(50)`, abreviatura `varchar(20)`, fase `varchar(20) DEFAULT Pre_evento`, tipo `varchar(15) DEFAULT Otro`, lugar/salón obligatorios, capacidad de mesas opcional, inicio/fin `timestamptz`, estado `varchar(15) DEFAULT Activo`. Checks de capacidad no negativa, fechas, fases `Pre_evento/En_proceso/Post_evento/Cerrado`, tipos y estados `Activo/Suspendido/Inactivo`. FK compuesta a salón. `trg_evp_eve_set_id` genera MAX+1 por cuenta bajo advisory lock. Sin auditoría.

### Debilidades y garantías

Las PK evitan relaciones duplicadas; las FK compuestas garantizan coherencia cuenta-evento y existencia de usuario-cuenta. Persisten riesgos: la FK usuario-evento acepta una relación de cuenta inactiva; una asignación directa puede existir para Master/Admin; los defaults pueden apuntar a relaciones o entidades inactivas y no prueban acceso efectivo; no hay protección del último Master; no hay auditoría de relaciones; no hay constraint que prohíba autoelevación ni múltiples Master (múltiples son válidos); el estado `Suspendido` existe en las tres entidades y no debe ser sustituido silenciosamente por un modelo binario. Un Master sin relaciones sigue siendo coherente con el acceso global actual, pero la UI debe representarlo como heredado.

## 2. Supabase Auth frente a EventPlus

Supabase Auth conserva identidad externa, credenciales/OAuth, correo Auth, sesión, refresh, recuperación e invitación, y es la autoridad de autenticación. `evp_usr_usuario` conserva perfil, correo administrativo EventPlus, estado, flag Master, defaults y relaciones. Ninguna capa debe usar el UUID Auth como PK interna ni sincronizar automáticamente los correos si divergen.

`evp_fn_vincular_usuario_auth()` procesa un `NEW` de Auth: por email normalizado actualiza solo un perfil cuyo Auth UUID sea NULL; enlaza `NEW.id` y cambia `Preregistrado` a `Activo`. Si no encuentra perfil, crea uno no Master en estado `Inactivo`, usando metadata/nombre/email. No crea cuentas ni eventos. Si el perfil ya tiene otro UUID no lo toma. La función existe en el volcado, pero la sentencia que instala el trigger sobre `auth.users` no aparece en `esquema.sql`; su existencia remota es **verificación pendiente**.

Consecuencias: el perfil puede preregistrarse antes del primer login, pero Auth-first también crea un perfil inactivo si el trigger está instalado. Un Auth sin perfil no pasa `cargar_contexto_usuario`; un perfil sin Auth queda pendiente. Borrar Auth pone el UUID interno en NULL. Cambiar correo en Auth no sincroniza el perfil porque la función descrita actúa en alta y la relación posterior es por UUID; cambiar el correo interno no cambia Auth. El índice normalizado impide correos internos duplicados. El comportamiento ante dos altas concurrentes por el mismo email debe probarse. Inactivar/suspender el perfil bloquea la reconstrucción del contexto, pero no revoca por sí solo tokens Auth.

No existe en el código productivo un cliente administrativo Auth, invitación por correo ni uso seguro de `service_role`. Fase inicial: preregistro interno en `Preregistrado` y alta Auth manual/controlada. Fase futura: invitación desde backend privilegiado; nunca `service_role` en navegador.

## 3. Autorización efectiva actual

`cargar_contexto_usuario` exige perfil Activo. Master carga todas las cuentas, incluso no activas según la consulta actual, y todos sus eventos, incluso no activos (`solo_activos=False`); se aprueba conservar esa visibilidad para administración, sin implicar que una entidad inactiva pueda usarse operativamente. No Master solo conserva relaciones de cuenta activas cuya cuenta esté Activa. Administrador recibe hoy todos los eventos Activos de su cuenta; el diseño aprobado además le permitirá ver, con presentación no operativa, las cuentas y los eventos inactivos pertenecientes a sus cuentas administradas. Operador y Consulta reciben únicamente cuentas activas y eventos activos con asignación activa. `evento_autorizado` exige que el evento actual esté en `eventos_permitidos`.

La matriz `Capacidades` concede hoy administración general a Master y Administrador; no implementa todavía las reglas granulares aprobadas de administración de usuarios. Estas decisiones son contrato funcional para la implementación futura, no permisos ya vigentes en el código productivo.

| Capacidad operativa actual | Master | Administrador | Operador | Consulta |
|---|---|---|---|---|
| Cuentas/eventos visibles | global | cuentas Admin; todos sus eventos activos | cuentas activas; eventos activos asignados | igual que Operador |
| Administración general declarada | sí | sí, contextual | no | no |
| Operar evento | sí | sí | sí si `En_proceso` y asignado | no |
| Lectura | sí | sí | sí | sí si asignado |
| Módulo usuarios productivo | no existe | no existe | no | no |

## 4. Modelo funcional y UI

Navegación FULL: `Administración > Usuarios`; nunca CHECKIN. Lista con búsqueda por nombre/email, filtros de estado/Master/cuenta/rol, total de eventos, paginación server-side y detalle. Escritorio: tabla compacta y acciones contextuales. Móvil: tarjetas con nombre, email, estado, rol/alcance, cuentas y “Administrar”.

Detalle por pestañas: Datos generales; Cuentas; Eventos; Acceso efectivo; Auditoría. Eventos debe distinguir `Heredado global` (Master), `Heredado por cuenta` (Administrador), `Asignado` (Operador/Consulta) y `Sin acceso efectivo`. No crear filas `uev` redundantes para Master/Admin. Modales coherentes con Administración de eventos, confirmación reforzada para estado/Master/propio usuario y resultados accesibles.

Estados visuales compatibles: `Preregistrado` como pendiente de Auth, `Activo`, `Suspendido`, `Inactivo`; relaciones también muestran sus tres estados reales. Acceso efectivo requiere usuario Activo, cuenta y relación Activas y, salvo Master/Admin de esa cuenta, asignación de evento Activa y evento Activo.

## 5. Permisos funcionales aprobados

`A(cuenta)` significa únicamente usuarios/relaciones de una cuenta donde el actor conserva una relación activa Administrador.

| Operación | Master | Administrador | Operador | Consulta |
|---|---:|---:|---:|---:|
| Listar/ver detalle/auditoría | global | A(cuenta) | no | no |
| Preregistrar perfil no Master | sí | sí, atómicamente como Operador o Consulta en A(cuenta) activa | no | no |
| Editar nombre/correo globales | sí | no | no | no |
| Activar/inactivar perfil global | sí, con protecciones | no | no | no |
| Convertir/retirar Master | sí, nunca último ni propio | no | no | no |
| Vincular cuenta | sí | solo A(cuenta) activa y como Operador/Consulta | no | no |
| Asignar/retirar Administrador | sí | no | no | no |
| Asignar Operador/Consulta | sí | A(cuenta) | no | no |
| Cambiar rol/inactivar relación | sí | solo Operador↔Consulta de A(cuenta) | no | no |
| Asignar/inactivar evento | sí | Operador/Consulta de A(cuenta) | no | no |
| Cambiar predeterminados ajenos | sí, dentro del acceso efectivo del objetivo | no | no | no |
| Cambiar predeterminados propios | sí, dentro del acceso efectivo propio | sí, dentro del acceso efectivo propio | sí, dentro del acceso efectivo propio | sí, dentro del acceso efectivo propio |
| Modificar datos propios | básicos sí; no autoestado/auto-Master | sin nombre/correo global desde este módulo | no módulo | no módulo |
| Modificar otro Master | sí salvo último, con advertencia | no | no | no |

Protecciones aprobadas: sin DELETE físico; no cero Master activos; lock al contar Master; un Master no puede auto-inactivarse ni auto-retirar su flag; otro Master debe hacerlo; solo Master asigna o retira Administrador. Admin no crea/modifica Admin ni Master, no edita nombre ni correo global, no inactiva el perfil global y no cruza cuentas; solo puede inactivar relaciones de sus cuentas y eventos.

Decisión aprobada e implementada en 8C: la opción B crea atómicamente el perfil `Preregistrado` y una relación activa, solo con rol `Operador` o `Consulta`, dentro de una cuenta Activa que `auth.uid()` administra activamente. Nunca permite al Administrador asignar rol `Administrador` ni condición Master, y el vínculo inicial mantiene al usuario visible en su listado 8B.

## 6. Integridad y casos de borde

Toda escritura debe revalidar: email normalizado único; UUID Auth único y nunca aceptado libremente del cliente; reutilización de relaciones inactivas; pertenencia evento-cuenta; relación cuenta activa previa; asignación directa solo para Operador/Consulta; defaults accesibles y coherentes; actor vigente sin autoelevación; al menos un Master Activo; entidades objetivo bloqueadas.

- Usuario activo sin cuenta/todas inactivas: sin acceso; selector vacío. Hoy `cargar_contexto_usuario` rechaza al no Master sin cuentas.
- Auth inexistente/eliminado: `Preregistrado` o UUID NULL; sin login EventPlus. Auth eliminado deja UUID NULL por FK.
- Correos divergentes: `evp_usr_usuario.usr_email` es el correo administrativo EventPlus y Supabase Auth es la autoridad de autenticación. Mostrar ambos y una advertencia; no sincronizar automáticamente en ninguna dirección.
- Admin pierde rol: retirar inmediatamente alcance heredado y recalcular contexto.
- Asignación activa con cuenta/evento inactivos: sin acceso efectivo; conservar fila para trazabilidad.
- Default inválido/inactivo: seleccionar primer acceso válido hoy; futura escritura debe sanearlo explícitamente.
- Dos Master concurrentes: lock estable y validación del último dentro de la misma transacción.
- Dos Admin vinculan: PK + operación idempotente/reactivación; resultado controlado.
- Varias cuentas/roles: calcular por cuenta, nunca un “rol global” para autorizar una mutación.
- Sesión abierta tras reducción: una RPC siempre revalida servidor; la UI no basta.

## 7. Servicios y modelos futuros

`models/usuario_admin_models.py`: `UsuarioResumen`, `UsuarioDetalle`, `UsuarioCuenta`, `UsuarioEvento`, `AccesoEfectivo`, `ResultadoOperacion`, modelos congelados y sin objetos Supabase.

`usuario_admin_service.py`: listado/detalle, filtros/paginación, acceso efectivo, validación UX e invocación RPC. `usuario_cuenta_service.py`: relaciones, roles, reactivación y operaciones de cuenta. `usuario_evento_service.py`: asignaciones y validación cuenta-evento. Python compone vistas, mensajes y prevalidaciones; PostgreSQL revalida identidad, autorización, estado, integridad, concurrencia y atomicidad. Ningún INSERT/UPDATE/DELETE directo administrativo.

## 8. RPC futuras

Preferencia: RPC pequeñas y específicas; nunca una función de columnas arbitrarias. Todas `SECURITY DEFINER`, `search_path=pg_catalog`, objetos calificados, identidad exclusiva `auth.uid()`, REVOKE PUBLIC/anon, GRANT authenticated, locks y errores controlados.

| RPC | Parámetros principales | Actor/validaciones/lock | Resultado y errores |
|---|---|---|---|
| `evp_admin_crear_usuario` | nombre, abreviado, email, teléfono, estado inicial y relación inicial cuando actúa Admin | Master; Admin solo no Master, `Preregistrado`, Operador/Consulta y cuenta propia activa; operación atómica; email lock/advisory; no UUID/Auth/master desde Admin | ID, estado y relación; DUPLICATE_EMAIL/FORBIDDEN |
| `evp_admin_actualizar_usuario` | usuario, campos básicos, versión esperada | alcance vigente; lock usuario; no tocar seguridad | perfil/version; STALE_DATA |
| `evp_admin_cambiar_estado_usuario` | usuario, estado | Master; lock usuario+Master; no auto-inactivar/último | estado; LAST_MASTER/SELF_PROTECTED |
| `evp_admin_cambiar_condicion_master` | usuario, boolean | Master distinto; lock serializado de Master | flag; LAST_MASTER |
| `evp_admin_vincular_usuario_cuenta` | usuario, cuenta, rol | Master o Admin limitado si aprobado; reactivar; Admin sin rol Admin | relación; CROSS_ACCOUNT/ROLE_FORBIDDEN |
| `evp_admin_actualizar_usuario_cuenta` | usuario, cuenta, rol/estado | lock relación; proteger Admin/Master; sanear defaults | relación y accesos perdidos |
| `evp_admin_vincular_usuario_evento` | usuario, cuenta, evento | Master/Admin de cuenta; usuario-cuenta activo y rol Operador/Consulta | asignación; INVALID_SCOPE |
| `evp_admin_actualizar_usuario_evento` | claves, estado | mismo alcance; lock asignación | asignación/default afectado |
| `evp_admin_actualizar_predeterminados` | usuario, cuenta nullable, evento nullable | propio usuario o Master para terceros; verificar acceso efectivo y FK; Admin nunca modifica los de terceros | defaults; INVALID_DEFAULT |

Cada excepción revierte la sentencia completa. Errores inesperados deben conservar un código interno separado. Auditoría futura debe registrar actor, operación, objetivo y antes/después sin secretos.

## 9. Sesiones y capacidades

Actualmente el contexto se carga en login con `load_context=True`. El monitor cada 60 s y la reconexión usan `load_context=False`: validan Auth y el contexto cacheado, pero no vuelven a consultar estado/roles. La sesión web server-side guarda tokens en memoria por proceso, cookie opaca HttpOnly y serializa restore/refresh; no ofrece broadcast de cambios de autorización ni revocación por usuario.

Diseño requerido: cada RPC revalida siempre; después de una mutación propia recargar contexto. Para cambios externos, añadir versión de autorización o `usr_modificado`/registro de permisos consultado periódicamente y en cada navegación/mutación. Si el usuario deja de estar Activo, la recarga periódica debe detectarlo, borrar contexto y sesión server-side, y ejecutar logout. Si pierde cuenta/evento actual: limpiar evento y volver al selector. Si baja rol/Master: reconstruir menú/capacidades antes de continuar. Otra pestaña debe detectarlo por polling/versionado o canal seguro; no confiar en `Page.session`. Una revocación global inmediata de tokens Auth podrá requerir un mecanismo backend adicional, pero no sustituye la expulsión aprobada mediante recarga periódica de autorización y logout.

## 10. Pruebas futuras

Master: alcance global, alta, roles, eventos, segundo Master y protección último/propio. Admin: solo sus cuentas/usuarios compartidos, Operador/Consulta, sin Admin/Master ni cruce. Operador/Consulta: módulo ausente y RPC prohibidas. Aislamiento: usuario compartido, cuenta A/B, evento cruzado y parámetros manipulados. Concurrencia: rol, último Master, doble vínculo y reactivación. Sesiones: inactivación, reducción, retiro de evento/Master y otra pestaña. Auth: preregistro, Auth-first, correo divergente, UUID eliminado/duplicado y trigger ausente. Todas las RPC requieren pruebas de rollback y grants reales.

## 11. Plan 8B–8G

| Tarea | Objetivo/archivos | Permisos y pruebas | SQL |
|---|---|---|---|
| 8B | implementada localmente: modelos, consultas paginadas y vista solo lectura | Master global, Admin limitado; 49 comprobaciones; prueba manual/RLS real pendientes | no; usa únicamente SELECT vigente |
| 8C | preregistro/edición básica | política aprobada; email/concurrencia/rollback | sí: RPC de perfil antes de UI de escritura |
| 8D | relaciones usuario-cuenta | inicialmente Master; reactivar/rol/default | sí: RPC cuenta |
| 8E | relaciones usuario-evento | Master/Admin limitado; solo Operador/Consulta | sí: RPC evento |
| 8F | estado, Master y defaults | último Master, propio usuario, defaults, concurrencia | sí: RPC específicas |
| 8G | endurecimiento integral, auditoría, sesiones y Auth futuro | grants, SQL real, aislamiento, dos sesiones/pestañas | sí; migraciones/rollback y backend Auth separado |

Dependencia ajustada: ninguna UI de escritura debe preceder a su RPC segura. 8B puede avanzar sin SQL si las lecturas actuales son suficientes; debe verificarse RLS real antes de declararla integrada.

## 12. Decisiones funcionales aprobadas

1. Solo Master puede asignar o retirar el rol Administrador.
2. Decisión aprobada e implementada (opción B): Administrador preregistra usuarios no Master únicamente como Operador o Consulta dentro de sus cuentas activas; perfil y relación inicial son atómicos. La administración posterior de relaciones permanece en 8D.
3. Administrador no puede editar el nombre ni el correo global del usuario.
4. Administrador solo puede inactivar relaciones de sus cuentas y eventos, nunca el usuario global.
5. Master no puede auto-retirarse como Master ni auto-inactivarse; la acción corresponde a otro Master y nunca puede dejar cero Master activos.
6. Auth se gestionará inicialmente de forma manual controlada.
7. El estado previo a la vinculación Auth es `Preregistrado`; no se crea un estado alternativo `Pendiente`.
8. **DECISIÓN APROBADA 8C-B:** el Administrador no puede crear un perfil aislado. Debe seleccionar una cuenta Activa que administre con relación Activa y asignar exclusivamente `Operador` o `Consulta`; perfil y relación se insertan en la misma RPC/transacción. Master puede crear sin cuenta inicial; la RPC también soporta cuenta/rol opcionales válidos.
9. `usr_creado_por` se conserva exclusivamente para auditoría. Admin puede corregir nombre/correo de Operador/Consulta con UCU Activa compartida en una cuenta Activa que administra, sin importar quién creó el perfil; Master edita globalmente.
10. Master dispone como mínimo de las capacidades de alta del Admin: cuenta/rol inicial, cuenta default y evento default. Para Master objetivo no se crea relación redundante. Para Operador/Consulta, un evento default implica asignación activa atómica.
11. Después de crear se permanece en el listado; no existe navegación automática al detalle.
8. Los accesos heredados se muestran calculados como `Heredado global` o `Heredado por cuenta`, sin crear relaciones `uev` redundantes.
9. Master administra predeterminados de terceros. Cada usuario puede cambiar los propios únicamente dentro de su acceso efectivo. Administrador no cambia predeterminados de terceros.
10. Un usuario inactivado debe ser expulsado mediante recarga periódica de autorización y logout.
11. Master puede ver y administrar cuentas y eventos inactivos, aunque estos no se habilitan para uso operativo por estar inactivos.
12. Administrador puede ver entidades inactivas de sus cuentas, pero no utilizarlas operativamente.
13. Operador y Consulta no acceden a cuentas ni eventos inactivos.
14. `evp_usr_usuario.usr_email` es el correo administrativo EventPlus y Supabase Auth es la autoridad de autenticación. Si divergen, se muestran ambos con una advertencia y no se sincronizan automáticamente.
# Consolidación vigente

Para creación, edición, roles por cuenta, inactivación y defaults prevalece `USER_ACCESS_AND_PREFERENCES.md`. La autorización de edición de Administrador ya no depende de `usr_creado_por`.
