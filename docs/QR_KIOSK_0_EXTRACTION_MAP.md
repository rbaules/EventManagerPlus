# QR-KIOSK-0A: mapa de extracción

## Estado actual

`home_view` contiene router/shell, negocio de Llegadas y el lifecycle QR-3B. El bloque QR ocupa aproximadamente las líneas 1430--2105.

| Elemento | Tipo | Dependencias | Destino 0B |
|---|---|---|---|
| `qr_scanner_generation`, `qr_scanner_snapshot_task`, `qr_scanner_lifecycle_lock` | estado técnico | polling/finalizador | controller |
| `qr_scanner_camera`, `qr_scanner_description`, initialized/paused | estado técnico | Flet Camera | controller |
| `_obtener_camera_scanner`, `abrir_scanner_qr`, `cerrar_scanner_qr`, `_limpiar_camera_scanner`, `_desmontar_scanner_overlay` | lifecycle | Page/overlay | controller |
| `_on_qr_detected` | frontera | negocio Llegadas | callback `on_qr_detected(codigo)` |
| `buscar_qr_llegadas`, resolver/grupo/confirmación | negocio | Supabase/UI | permanece Home |

UI directa: Camera, `persistent_camera_host`, `scanner_overlay`, chrome y retry. 0B moverá estado/lifecycle/polling/finalizador, recibiendo temporalmente controles visuales; 0C moverá overlay. No hay imports de negocio previstos en controller.

## Initialized / Preview state

| Estado | Ubicación actual | Rol |
|---|---|---|
| generation | `QrCameraRuntime` | cache técnico de vigencia del scanner |
| snapshot task | `QrCameraRuntime` | referencia real de la tarea de polling |
| controller initialized | `QrCameraRuntime` | cache local de inicialización del controller nativo |
| preview paused | `QrCameraRuntime` | cache local del estado de preview |
| camera state textual | `state["qr_scanner_camera_state"]` en `home_view` | representación para UI/logs |

`_scanner_state_change(event: CameraStateEvent)` recibe la fuente nativa y actualiza los caches `runtime.controller_initialized` y `runtime.preview_paused` desde `event.is_initialized` y `event.is_preview_paused`; ante `event.has_error` invalida el controller y deja `camera_state` en error.

Tras initialize se marca initialized y se limpia preview paused; pause marca paused; resume limpia preview paused. El runtime conserva caches locales, pero una respuesta real del plugin tiene autoridad final: si el cache dice initialized y `resume_preview()` devuelve `Camera is not initialized...`, se invalida controller initialized y se activa recovery. En teardown el mismo error es benigno, deja initialized falso y no recupera. `preview_paused=True` nunca prueba validez si `controller_initialized` es falso.
