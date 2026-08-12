# Acceso de usuarios y preferencias — modelo definitivo

El cambio de rol de una UCU existente está implementado: Master usa Administrador/Operador/Consulta y Administrador solo Operador↔Consulta dentro de su cuenta administrada. Agregar cuentas o mantener asignaciones UEV de forma general queda pendiente para el bloque posterior a la Tarea 8.

El grid administrativo muestra alcance configurado para `Activo` y `Preregistrado`; `Inactivo` y `Suspendido` muestran 0/0. Esta presentación no concede sesión: `evp_priv_usuario_tiene_acceso` continúa exigiendo `Activo`. La corrección incremental posterior está en `202608110001_user_admin_task8_final_fixes.sql`.

> Las transiciones finales de Master y roles de cuenta se documentan en `USER_ROLE_TRANSITIONS.md`; la migración incremental `202608100002_user_role_transition_finalization.sql` está pendiente de aplicación.

Este documento sustituye cualquier regla anterior que contradiga la matriz siguiente. La migración incremental correspondiente es `202608100001_user_access_defaults_preferences.sql`; 8C y 8C-Fix permanecen como historial aplicado. La administración posterior UCU/UEV está en `USER_ACCESS_MANAGEMENT.md`; agregar o reactivar accesos nunca asigna defaults.

| Rol nuevo | Creador permitido | Default cuenta/evento | UCU inicial | UEV inicial |
|---|---|---|---|---|
| Master | Master | contexto activo, obligatorio | No | No |
| Administrador | Master | contexto activo, obligatorio | Administrador/Activa | No |
| Operador | Master o Administrador | contexto activo, obligatorio | Operador/Activa | evento activo/Activa |
| Consulta | Master o Administrador | contexto activo, obligatorio | Consulta/Activa | evento activo/Activa |

Los defaults son preferencias de inicio, no autorización. La cuenta y evento del modal son informativos y no editables. Tanto Python como la RPC pasan el contexto actual, y SQL vuelve a validar `auth.uid()`, estado, pertenencia cuenta-evento y alcance del actor.

## Acceso efectivo

- Master: toda cuenta activa y todo evento activo, sin UCU/UEV.
- Administrador: UCU Administrador Activa en cuenta Activa; hereda sus eventos activos.
- Operador/Consulta: usuario Activo, cuenta Activa, UCU Activa, evento Activo y UEV Activa.
- Una UEV almacenada no concede acceso cuando su UCU está Inactiva.
- `evp_priv_usuario_tiene_acceso` representa exclusivamente acceso efectivo y exige usuario Activo. `evp_priv_usuario_puede_tener_default` admite Activo/Preregistrado para preservar defaults válidos durante el preregistro; no concede acceso operativo.

## Administración

Master puede editar datos globales y administrar roles de cuenta. Administrador puede editar nombre/correo de Operador o Consulta con UCU Activa compartida en una cuenta que administra, sin depender de `usr_creado_por`. Este último se conserva exclusivamente como auditoría.

Administrador solo cambia Operador ↔ Consulta e inactiva/reactiva el vínculo de esos roles en su cuenta. Master puede administrar el estado de cualquier UCU de un objetivo no Master sin necesitar una UCU propia. Solo Master inactiva el perfil global. Retirar acceso limpia defaults que hayan dejado de ser elegibles; no se borran UEV históricas. Al degradar Administrador a Operador/Consulta no se inventan asignaciones de evento.

## Preferencias

`evp_usuario_actualizar_preferencias(cuenta, evento)` deriva la identidad exclusivamente de `auth.uid()` y modifica solo al usuario autenticado. Master elige cualquier contexto activo; Administrador, eventos activos de cuentas administradas; Operador/Consulta, únicamente contextos con UCU y UEV activas. Guardar preferencias no cambia el contexto activo de la sesión.

Un default nulo o inválido no se sustituye por el primer elemento disponible. La aplicación muestra el selector/Preferencias con el mensaje: “Seleccione una cuenta y un evento para continuar.”

## Seguridad y concurrencia

Las RPC son `SECURITY DEFINER`, usan `search_path=''`, nombres calificados, `auth.uid()`, revocación a PUBLIC/anon y concesión mínima a authenticated. Los helpers son privados. El orden uniforme de bloqueo es actor, objetivo, cuenta, relación de cuenta, evento y relación de evento.

## Guion manual pendiente

1. Como Master, seleccionar contexto activo y crear consecutivamente Master, Administrador, Operador y Consulta; verificar defaults y matriz UCU/UEV.
2. Como Administrador, crear Operador/Consulta; rechazar Master/Administrador; editar un usuario creado por otro actor en la cuenta compartida.
3. Cambiar Operador ↔ Consulta; inactivar/reactivar su UCU; confirmar que otra cuenta y las UEV almacenadas no se alteran y que el default perdido queda nulo.
4. Con cada rol, guardar preferencias válidas, reiniciar sesión y verificar inicio automático. Probar cuenta/evento inactivos, otra cuenta y evento no asignado.
5. Inactivar globalmente desde Master y comprobar el cierre mediante el refresco de sesión vigente.

La tarea no se considera cerrada hasta aplicar la migración en el entorno autorizado y completar este guion manual.
