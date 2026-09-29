# QR-3A — integración Flet de check-in QR manual

QR-3A incorpora al inicio de **Registrar llegadas** un campo manual de cuatro caracteres y el botón **Consultar QR**. Enter y el botón usan el mismo manejador; no incluye cámara, escáner, JavaScript, paquetes adicionales ni cambios de base de datos.

El adaptador `resolver_invitacion_qr()` llama una vez a `evp_oper_resolver_invitacion_qr(cuenta, evento, codigo)`. Una respuesta `QR_RESOLVED` debe coincidir con el contexto activo y luego carga el grupo mediante el flujo común `cargar_grupo_invitacion()`. La vista no consulta invitados directamente.

Los perfiles Master, Administrador y Operador pueden resolver, cargar y confirmar. Consulta puede resolver y cargar en modo solo lectura; los controles de selección y confirmación se deshabilitan. Los errores QR se traducen a mensajes seguros y los logs no registran el código QR completo.

El cambio de evento reinicia el estado de llegadas, incluido el código QR y el grupo cargado. La confirmación continúa usando la RPC común de QR-2B y refresca el grupo; no se agregaron llamadas SQL ni migraciones.
