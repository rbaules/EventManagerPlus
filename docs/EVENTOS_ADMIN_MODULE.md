# Administración de eventos

## Alcance

Módulo exclusivo de FULL para Master y Administrador, siempre limitado a la cuenta
activa validada. Operador y Consulta conservan la selección de eventos asignados,
pero no ven esta administración ni pueden escribir. El 2 de agosto de 2026 se
aplicó manualmente en Supabase el default `Otro` de `eve_tipo_evento`.

## Inventario real

Tabla: `evp_eve_evento`. PK compuesta: `eve_cuenta_id, eve_evento_id`.
El ID relativo se omite en INSERT porque `trg_evp_eve_set_id` ejecuta
`evp_fn_set_evento_id()`.

| Columna | Tipo/regla |
|---|---|
| `eve_cuenta_id` | integer, requerido, protegido |
| `eve_evento_id` | integer, requerido, generado por trigger, protegido |
| `eve_nombre_evento` | varchar(50), requerido |
| `eve_nombre_evento_abrev` | varchar(20), opcional |
| `eve_fase_evento` | varchar(20), requerido, default `Pre_evento` |
| `eve_tipo_evento` | varchar(15), requerido, default `Otro`; valores completos del CHECK |
| `eve_lugar_id` / `eve_salon_id` | integer, requeridos |
| `eve_cant_mesas` | integer, opcional |
| `eve_fecha_hora_inicio` / `eve_fecha_hora_fin` | timestamptz; fin posterior a inicio |
| `eve_estado` | varchar(15), requerido, default `Activo` |

No existen en el inventario documentado descripción, país directo, zona horaria
separada, observaciones, imagen, capacidad de invitados, creador ni timestamps de
auditoría. País pertenece al lugar y capacidades máximas al salón.

Valores: fase `Pre_evento`, `En_proceso`, `Post_evento`, `Cerrado`; estado
`Activo`, `Suspendido`, `Inactivo`; tipo `Boda`, `Cumpleaños`, `Quinceaños`, `Corporativo`, `Otro`.

## Esquema autoritativo

`C:\WORKSPACE\EVENTPLUS\esquema.sql` es la exportación autoritativa actual. El
default `Otro` de `eve_tipo_evento` pertenece al CHECK y ambos son compatibles.
Las relaciones dependientes son `evp_mes_mesa`, `evp_inv_invitacion`,
`evp_ivt_invitado` y `evp_uev_usuario_evento`. El script
`scripts/eventos_schema_diagnostics.sql` confirma CHECK, UNIQUE, FK, índices,
vistas, funciones y triggers en Supabase sin mutarla.

## Permisos y ciclo de vida

`authorization_service.Capacidades` expone nueve capacidades de eventos. Master y
Administrador las reciben; Operador y Consulta reciben `false`.

| Fase actual | Transición | Edición ordinaria | Ubicación | Llegadas |
|---|---|---|---|---|
| `Pre_evento` | `En_proceso` | sí | sí, si no hay dependencias | no |
| `En_proceso` | `Post_evento` | no | no | sí si estado Activo y rol operativo |
| `Post_evento` | ninguna | no | no | no |
| `Cerrado` | ninguna | no | no | no |

No hay salto, retroceso ni reapertura. “Cerrar” usa `Post_evento`, la fase
operativa de cierre vigente. `Cerrado` se respeta como valor terminal legado.

## Validaciones y dependencias

La cuenta viene exclusivamente del contexto. El servicio valida nombre, fecha/hora
ISO, fin posterior, tipo, fase/estado inicial, pertenencia y actividad de
lugar/salón. Solo acepta una lista blanca de campos. Los cambios de ubicación solo
ocurren en `Pre_evento` y se bloquean si existe al menos una mesa, invitación o
invitado, pues no existe una operación transaccional para reconciliarlos.

Las actualizaciones de fase y estado vuelven a leer la fila y agregan fase/estado
anterior a los filtros del UPDATE para detectar conflictos razonables.

## Contexto y predeterminado

Cuando cambia el evento activo, `establecer_evento_activo()` recalcula llegadas y
capacidades, actualiza la sesión Page y reinicia Invitados/Llegadas. Desactivar el
activo limpia la selección. El predeterminado actualiza únicamente
`evp_usr_usuario.usr_cuenta_id_default` y `usr_evento_id_default`, filtrando por
`usr_usuario_id`; no altera preferencias ajenas.

## UI

La entrada vive en el menú administrativo del encabezado de FULL. Incluye loading,
vacío, error, sin cuenta, denegado y guardando; búsqueda y filtros; tarjetas
responsive; formulario con lugares activos y salones filtrados; confirmaciones
para iniciar, cerrar y cambiar estado. Las fechas se capturan como ISO 8601 con
offset para conservar `timestamptz`. CHECKIN nunca muestra la entrada.

## RPC futuras y preparación RLS

Antes de habilitar RLS deben convertirse en RPC transaccionales crear, cambiar
ubicación/estado, iniciar, cerrar y establecer predeterminado. Deben validar
`auth.uid()`, rol, tenant, fila actual, máquina de estados, ubicación,
dependencias y columnas protegidas. RLS futura: Master/Administrador
SELECT/INSERT/UPDATE dentro de alcance con `WITH CHECK` que preserve tenant;
transiciones sensibles solo por RPC. Operador/Consulta SELECT de asignados y
ninguna mutación. Anon sin acceso. Nunca DELETE directo.

## Pruebas y guion manual

`scripts/test_eventos_admin.py` cubre capacidades, aislamiento, validaciones,
campos protegidos, fases, dependencias, estado, predeterminado, UI y CHECKIN.

Pruebas funcionales manuales completadas satisfactoriamente el 2 de agosto de
2026: creación y edición de eventos, uso de todos los tipos configurados y
ausencia de nuevas violaciones de `chk_eve_tipo_evento`.

Guion: entrar como Administrador; abrir el módulo; crear un evento de prueba en
`Pre_evento`; elegir lugar/salón; editarlo; hacerlo predeterminado; seleccionarlo
y comprobar Invitados; iniciarlo y comprobar llegadas; verificar que ubicación
queda bloqueada; cerrarlo y comprobar que no admite llegadas; verificar ausencia
del menú como Operador, Consulta y en CHECKIN. No usar el evento habitual.

## Limitaciones

No hay borrado, reapertura, clonación, mesas/invitaciones/usuarios, estadísticas,
Realtime, publicación, RPC aplicada ni RLS aplicada. Los conteos no se muestran
para evitar consultas costosas. El diagnóstico real de restricciones debe
ejecutarse manualmente como lectura antes de una migración/RLS.
