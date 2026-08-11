# Transiciones finales de roles

La columna Roles muestra exclusivamente roles vigentes: Master prevalece sobre cualquier UCU histórica; para no Master solo se incluyen roles distintos de UCU Activas. El cambio de rol sobre una UCU existente está implementado mediante `evp_admin_cambiar_rol_cuenta`. La administración general para agregar, inactivar o reactivar libremente UCU/UEV permanece pendiente.

La migraciÃ³n incremental pendiente `202608100002_user_role_transition_finalization.sql` sustituye el cambio booleano de Master por operaciones transaccionales. El nombre fÃ­sico vigente de la columna es `usr_es_usuario_master`; representa exclusivamente la condiciÃ³n Master.

| TransiciÃ³n | Perfil | UCU | UEV | Defaults |
|---|---|---|---|---|
| Administrador/Operador/Consulta â†’ Master | `usr_es_usuario_master=true` | Todas Inactivas | Se conservan | Se mantienen si cuenta y evento estÃ¡n activos |
| Master â†’ Administrador | `false` | Solo la seleccionada Activa/Administrador | Todas Inactivas; no se crea UEV | Cuenta y evento predeterminados obligatorios y activos |
| Master â†’ Operador/Consulta | `false` | Solo la seleccionada Activa con el rol elegido | Solo el evento seleccionado queda Activo | Cuenta y evento seleccionados |
| Administrador â†’ Operador/Consulta | Sin cambio global | Cambia rol | Todas las UEV de la cuenta se inactivan; solo se activa el evento obligatorio elegido | Se alinean con cuenta/evento elegidos |
| Operador/Consulta â†’ Administrador | Sin cambio global | Cambia rol | Las filas se conservan como histÃ³rico, en estado Inactivo | Se mantienen si siguen siendo vÃ¡lidos por acceso heredado |
| Operador â†” Consulta | Sin cambio global | Solo cambia rol | Se conserva | Se mantienen si siguen siendo vÃ¡lidos |

La promociÃ³n, el retiro y las protecciones del Ãºltimo Master usan el advisory lock `817301`. El orden es lock global, actor, objetivo, cuenta, UCU, evento y UEV. Las RPC son `SECURITY DEFINER`, fijan `search_path=''`, derivan identidad de `auth.uid()` y solo conceden ejecuciÃ³n a `authenticated`.

La inactivaciÃ³n global sigue siendo exclusiva de Master, conserva UCU/UEV y produce acceso efectivo 0/0. La reactivaciÃ³n exige UUID Auth; un Preregistrado sin Auth permanece pendiente de autenticaciÃ³n. Administrador solo puede inactivar o reactivar relaciones UCU dentro de sus cuentas.

Las columnas del grid representan alcance configurado. Activo y Preregistrado muestran permisos configurados; Inactivo y Suspendido muestran 0/0. El acceso operativo continúa exigiendo estado Activo.

“HistÃ³rico” significa que la fila UEV no se elimina. Al pasar a Administrador, todas las UEV de esa cuenta quedan Inactivas. Si posteriormente vuelve a Operador/Consulta, no se reactivan permisos anteriores en bloque: solamente queda Activo el evento seleccionado explÃ­citamente durante esa transiciÃ³n. Operador â†” Consulta no altera las UEV actuales.

CorrecciÃ³n final: las columnas del grid representan alcance configurado. Activo y Preregistrado muestran las cuentas/eventos permitidos por Master, UCU y UEV; Inactivo y Suspendido muestran 0/0. Esto no altera `evp_priv_usuario_tiene_acceso`, que continÃºa exigiendo estado Activo para acceso operativo.
