# QR-KIOSK-0A: mapa de extracción

## Estado actual

`home_view` contiene router/shell, negocio de Llegadas y el lifecycle QR-3B. El bloque QR ocupa aproximadamente las líneas 1430--2105.

| Elemento | Tipo | Dependencias | Destino 0B |
|---|---|---|---|
| `generation`, `snapshot_task`, `lifecycle_lock` | estado técnico en `QrCameraRuntime` | polling/finalizador | runtime parcial |
| `qr_scanner_camera` | control nativo | Flet Camera | permanece Home |
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
| lifecycle lock | `QrCameraRuntime` | exclusión mutua de operaciones nativas de lifecycle |
| camera description cacheada | `QrCameraRuntime` | selección de cámara para initialize/recovery |
| camera state textual | `state["qr_scanner_camera_state"]` en `home_view` | representación para UI/logs |

`_scanner_state_change(event: CameraStateEvent)` recibe la fuente nativa y actualiza los caches `runtime.controller_initialized` y `runtime.preview_paused` desde `event.is_initialized` y `event.is_preview_paused`; ante `event.has_error` invalida el controller y deja `camera_state` en error.

Tras initialize se marca initialized y se limpia preview paused; pause marca paused; resume limpia preview paused. El runtime conserva caches locales, pero una respuesta real del plugin tiene autoridad final: si el cache dice initialized y `resume_preview()` devuelve `Camera is not initialized...`, se invalida controller initialized y se activa recovery. En teardown el mismo error es benigno, deja initialized falso y no recupera. `preview_paused=True` nunca prueba validez si `controller_initialized` es falso.

### Lifecycle lock

El único lock actual es `qr_runtime.lifecycle_lock`, creado como `asyncio.Lock()` por instancia de `QrCameraRuntime`. No se comparte entre instancias/Home y no es reentrante: cada operación libera el lock antes de iniciar una operación posterior que pueda necesitarlo.

Lo adquieren estas rutas:

- `desmontar()` de `_desmontar_scanner_overlay`: cancela y espera polling, detiene stream y pausa preview durante teardown.
- `_limpiar_camera_scanner()`: serializa stop de stream y `pause_preview()` para close/cancel y para el finalizador QR.
- `inicializar()` al reutilizar la cámara: serializa `resume_preview()`.
- `inicializar()` normal o tras controller lost: serializa enumeración, selección de descripción e `initialize()`; la recuperación ocurre después de que el lock de resume fue liberado.

Retry entra por `_reintentar_scanner_qr()` y vuelve a `abrir_scanner_qr()`, por lo que reutiliza la misma ruta protegida. `take_picture()` y polling no toman el lock: antes de pausar, cerrar o desmontar, las rutas protegidas cancelan y esperan la tarea de polling para evitar solaparla con operaciones nativas excluyentes. No deben ejecutarse simultáneamente initialize, resume, pause, stop de stream ni teardown.

El lock ya vive en `QrCameraRuntime`; las funciones lifecycle permanecen en Home y sólo consumen esa misma instancia.

### Cached CameraDescription

La caché actual es `qr_runtime.camera_description`, inicializada en `None` por instancia de `QrCameraRuntime`. La primera inicialización enumera mediante `enumerate_cameras_with_retry`, selecciona la cámara trasera si existe y guarda la descripción. Dentro de la vida de ese Home/runtime no se invalida explícitamente; se reinicia al crear un nuevo runtime.

Es una caché técnica, no autoridad sobre el estado actual del dispositivo. Ante controller lost durante `resume_preview()`, el flujo marca `recovery_from_resume=True`; si existe descripción cacheada, `initialize()` la reutiliza sin reenumerar. Si no existe caché —o la apertura es normal— se vuelve a enumerar. Los errores transitorios `cameraNotReadable` y `cameraAbort` conservan la estrategia actual de retry para enumeración e initialize; no borran por sí mismos la descripción cacheada. Teardown no intenta recovery ni consume la caché.

La caché sólo transporta `CameraDescription` hacia `camera.initialize()` y no contiene lógica de negocio. Permanecen en Home el control `Camera`, las funciones lifecycle, overlay y `qr_scanner_camera_state` textual/UI.
