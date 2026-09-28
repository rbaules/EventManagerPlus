# QR-2B: llegadas grupales comunes

`evp_oper_obtener_grupo_invitacion` carga el grupo activo de una invitación y
`evp_oper_confirmar_llegadas_invitacion` confirma una selección explícita. Son
RPC genéricas: check-in manual y QR consumen el mismo backend; QR-2A solo
provee una `invitacion_id` candidata y no es una autoridad para QR-2B.

La confirmación rechaza lista vacía (`ARRIVAL_EMPTY_SELECTION`), duplicados,
IDs ajenos, inexistentes o inactivos (`ARRIVAL_INVALID_SELECTION`) y cualquier
invitado ya confirmado (`ARRIVAL_ALREADY_CONFIRMED`). En esos casos no escribe
ninguna fila. `ARRIVAL_NOT_ALLOWED` cubre identidad o rol no autorizado;
`ARRIVAL_EVENT_NOT_ALLOWED` cubre cuenta/evento/fase no operativos;
`ARRIVAL_INVITATION_NOT_FOUND` cubre una invitación inexistente o inactiva;
`ARRIVAL_OPERATION_ERROR` evita exponer errores internos. Éxitos: 
`ARRIVAL_GROUP_LOADED` y `ARRIVAL_CONFIRMED`.

El lote bloquea la invitación y todos los invitados objetivo antes de validar y
usa un solo `UPDATE`. Captura una sola `clock_timestamp()` y almacena el
`usr_usuario_id` del actor activo, que coincide con la semántica actual de
`ivt_usuario_conf_llegada`. No implementa reversión.

`LEGACY_REVERSAL_REVIEW_PENDING`: la capa Python heredada permite reversar a
Operador; QR-2B no modifica esa decisión ni crea una RPC de reversión.
