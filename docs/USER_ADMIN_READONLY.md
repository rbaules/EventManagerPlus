# Administración de usuarios en solo lectura (Tarea 8B)

Estado: implementada localmente y preparada para prueba manual. La integración
remota depende de que las políticas SELECT vigentes permitan el alcance
documentado. No se añadieron migraciones, RPC, RLS ni operaciones de escritura.

## Alcance

El módulo existe únicamente en FULL bajo `Administración > Usuarios`. Master y
Administrador disponen de las rutas `/app/admin/usuarios` y
`/app/admin/usuarios/<usuario_id>`. Operador y Consulta no ven la opción y las
rutas directas se rechazan tanto en la vista como en el servicio. CHECKIN no
expone ni carga el módulo.

Master consulta todos los usuarios, cuentas y eventos, incluidos estados
inactivos, y ve el acceso heredado global. Administrador deriva su alcance de
sus relaciones `evp_ucu_usuario_cuenta` activas con rol `Administrador` y de
cuentas activas; solo ve usuarios que comparten esas cuentas. En el detalle se
eliminan cuentas, roles, eventos y defaults ajenos.

## Implementación

- `models/usuario_admin_models.py`: modelos congelados de resumen, detalle,
  cuentas, eventos, acceso efectivo y paginación.
- `services/usuario_admin_service.py`: autorización, búsqueda, filtros,
  ordenamiento, paginación y detalle. Usa únicamente el cliente Supabase de la
  Page y consultas SELECT.
- `views/user_admin_view.py`: tabla para escritorio, tarjetas responsive para
  móvil, filtros, actualización, paginación y detalle por secciones.
- `services/authorization_service.py`: cuatro capacidades exclusivas de
  lectura; no contiene capacidades de escritura de usuarios.
- `services/navigation_service.py`, `components/app_shell.py`,
  `components/event_header.py` y `views/home_view.py`: rutas e integración FULL.

El listado pagina `evp_usr_usuario` con tamaño inicial 20 y enriquece únicamente
la página visible con relaciones de cuenta y asignaciones de evento. Los filtros
de rol/cuenta se resuelven primero dentro del alcance autorizado para evitar
duplicar usuarios vinculados a varias cuentas.

## Acceso efectivo y advertencias

- Master: `Global`, sin requerir relaciones de evento.
- Administrador objetivo: `Heredado` en todos los eventos visibles de sus
  relaciones administrativas activas.
- Operador/Consulta: `Asignado`; exige usuario, cuenta, relación de cuenta,
  evento y asignación activos.

Se muestran advertencias para preregistro sin Auth, usuario activo sin UUID
Auth, defaults fuera del acceso efectivo, usuario sin cuentas, usuario activo
sin eventos efectivos y asignación activa con relación de cuenta inactiva. No
se consulta el correo de Auth ni se presume divergencia sin evidencia segura.
Solo se exponen presencia del UUID Auth, estado interno y correo administrativo.

## Pruebas

`scripts/test_user_admin_readonly.py` cubre 56 comprobaciones: roles, aislamiento
Master/Admin, usuario compartido, manipulación de IDs, acceso efectivo,
advertencias, filtros, paginación, rutas, tabla, tarjetas, detalle y ausencia de
INSERT/UPDATE/DELETE o `service_role`.

La prueba manual del usuario continúa pendiente. También debe validarse con el
RLS SELECT real antes de declarar 8B cerrada. Las escrituras seguras de perfil
de 8C ya existen; la administración general de relaciones, roles, eventos,
predeterminados y Auth continúa en sus fases posteriores.

## Integración con escrituras 8C

El detalle recibe explícitamente el `usuario_id` seleccionado o devuelto por la RPC de creación; no lo infiere de la posición del listado ni reutiliza una selección anterior. Master consulta perfiles globalmente, incluidos Master nuevos y no Master sin cuenta. La navegación descarta respuestas de detalle obsoletas y diferencia `Usuario no encontrado`, `No tiene acceso` y error de carga.

Las acciones globales de estado y condición Master aparecen solamente cuando el actor es Master. Con la migración incremental pendiente, Administrador podrá ver `Editar datos` exclusivamente cuando `usr_creado_por` demuestre su autoría y conserve alcance activo; SQL sigue siendo la autoridad. La validación automatizada está implementada; la prueba manual dirigida en FULL sigue pendiente.
# Alcance vigente

La consulta de usuarios conserva este diseño. Las acciones y su autorización se rigen por `USER_ACCESS_AND_PREFERENCES.md`; Administrador puede editar Operador/Consulta de su cuenta aunque no los haya creado.
