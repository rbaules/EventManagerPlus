# QR-2A: resolucion segura

La RPC `evp_oper_resolver_invitacion_qr(cuenta, evento, codigo)` exige un usuario autenticado y limita toda busqueda por cuenta, evento y codigo normalizado. Master y Administrador pueden resolver en su alcance; Operador y Consulta requieren asignacion UEV activa. Consulta sigue siendo solo lectura: la RPC no modifica datos y devuelve solo metadatos de la invitacion, no invitados ni UUIDs.

La fase permitida es exclusivamente `En_proceso`, consistente con las operaciones actuales de llegada. La respuesta permite a QR-2B reutilizar el servicio existente de grupo de invitacion sin duplicar invitados en la RPC. Los codigos externos de cuatro caracteres no son secretos criptograficos; no hay acceso `anon` y QR-2A no es un lookup publico. QR Revocado devuelve `QR_REVOKED`; los demas estados no disponibles se agrupan para reducir revelacion de estado.
