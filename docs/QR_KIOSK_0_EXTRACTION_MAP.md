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

## Lifecycle function dependency map

Ubicación real: las funciones scanner están en `views/home_view.py`, aproximadamente entre las líneas 1388 y 2101; `logout()` las dispara desde la línea 3740. Leyenda: **R** runtime, **C** Camera, **U** overlay/UI, **P** page, **T** estado textual/UI, **B** negocio Llegadas, **L** otra función lifecycle y **E** callback externo.

| Función/callback real | R | C | U | P | T | B | L / E | Dificultad |
|---|---|---|---|---|---|---|---|---|
| `_mensaje_error_scanner` | — | — | mensaje | — | — | — | E: error camera | BAJA |
| `_controller_camera_no_inicializado` | — | — | — | — | — | — | E: error plugin | BAJA |
| `_log_scanner_exception` | — | — | logs | — | — | — | E: excepción | BAJA |
| `_obtener_camera_scanner` | initialized | crea/configura | host, chrome, overlay | `page.overlay` | mounted/state | — | E: state/image callbacks | ALTA |
| `_actualizar_visibilidad_scanner` | — | — | host/chrome/retry/overlay | — | retry visible | — | — | ALTA |
| `_desmontar_scanner_overlay` / `desmontar` | generation, task, lock, initialized | stop/pause | elimina overlay | tarea/update | flags | — | L: mounted/log | ALTA |
| `_log_identidad_scanner` | generation/initialized | inspecciona | host/overlay | ruta | — | — | — | MEDIA |
| `_camera_esta_montada` | — | `camera.page` | — | page | mounted | — | — | MEDIA |
| `_restaurar_estado_interaccion_qr` | — | — | visibilidad | — | flags/gate | — | L: visibilidad | MEDIA |
| `_limpiar_camera_scanner` | lock/task/initialized/paused | stop/pause | — | — | estado error | — | L: mounted/log | MEDIA |
| `cerrar_scanner_qr` / `detener` / `finalizar_qr` | generation/task/initialized | cleanup indirecto | render | tareas | closing/mensajes | **sí**, finalizer | L: cleanup/restaurar | ALTA |
| `_scanner_state_change` | initialized/paused | evento nativo | — | — | `camera_state` | — | E: `CameraStateEvent`; L: close | MEDIA |
| `QrCameraRuntime.is_scanner_session_current` | generation | — | — | — | claves aportadas por Home | — | E: `evento_activo_key` desde Home | BAJA |
| `_on_qr_detected` | generation indirecta | — | — | — | código QR | puente | E: stream/poll; L: close | MEDIA |
| `QrCameraRuntime.accept_snapshot_code` | generation/vigencia | — | — | — | `QrFrameGate` aportado por Home | — | E: callback técnico Home | BAJA |
| `process_qr_camera_frame` / `_decode_and_accept_qr_frame` | vigencia aportada | bytes | — | scheduler aportado | `QrFrameGate` | — | E: callback técnico Home | MEDIA |
| `abrir_scanner_qr` | todos los campos | obtiene/inicia | visibilidad/render | update/tarea | opening/scanning | depende de evento activo | L: cámara/visibilidad | ALTA |
| `abrir_scanner_qr > iniciar_captura` | task/generation | stream/take picture | render | — | strategy/flags | — | E: polling; L: accept/close | ALTA |
| `abrir_scanner_qr > take_snapshot` | generation indirecta | `take_picture` | — | tarea actual | — | — | E: polling | BAJA |
| `abrir_scanner_qr > inicializar` | todos los campos | resume/enumerate/initialize | — | tarea/lock | error/scanning | — | L: vigente/close/capture | ALTA |
| `_reintentar_scanner_qr` | indirecto | — | retry button | — | error/closing | — | L: open | BAJA |
| `logout` | indirecto | teardown indirecto | `page.clean` | page/sesión | — | sesión | L: desmontar | ALTA |

### Frontera scanner / negocio

La infraestructura termina conceptualmente en `_on_qr_detected(codigo, generation, active_key)`: valida vigencia, guarda el código y solicita cierre. El callback no resuelve invitaciones. En la rama QR de `cerrar_scanner_qr`, el finalizador externo espera polling, ejecuta `_limpiar_camera_scanner`, restaura la interacción y sólo entonces llama `buscar_qr_llegadas(codigo_qr)`. Allí comienza el negocio EVKOR: resolver QR, cargar integrantes y mostrar/confirmar llegadas.

Por tanto, `cerrar_scanner_qr` mezcla infraestructura y negocio únicamente por su `finalizar_qr` anidado; `_on_qr_detected` es el puente de callback y `buscar_qr_llegadas` pertenece al lado de negocio. Polling, `take_snapshot` y decodificación no llaman negocio directamente.

### Orden incremental recomendado

1. **0B4B-1 — ✅ `QrCameraRuntime.is_scanner_session_current`**: migrado desde `_scanner_sigue_vigente` sin arrastrar lifecycle grande.
2. **0B4B-2 — ✅ `QrCameraRuntime.accept_snapshot_code`**: migrado desde `_aceptar_codigo_snapshot`; conserva el gate como frontera de aceptación y recibe el callback técnico de Home.
3. **0B4B-3 — ✅ `process_qr_camera_frame` / `_decode_and_accept_qr_frame`**: migrados desde `_scanner_frame_received` / `decode_worker`; Home conserva sólo el adaptador Flet y el callback técnico.
4. **0B4B-4 — `iniciar_captura` y `take_snapshot`**: siguiente pareja; task/generation/gate/polling, sin moverla todavía.
5. **0B4B-5 — `_limpiar_camera_scanner`**: primera operación nativa reutilizable; conserva lock, cancelación/espera de polling y callbacks mínimos de montado/log/UI.
6. **0B4B-6 — `inicializar`**: resume, recovery, enumeración y retry; mover después de tener las primitivas anteriores.
7. **0B4B-7 — `cerrar_scanner_qr`**: separar primero el finalizador técnico de su callback `on_qr_detected(codigo)` antes de mover el coordinador de close.
8. **0B4B-8 — `_desmontar_scanner_overlay` y luego Camera/overlay**: mantenerlos al final por dependencia directa de Page y composición visual.

### Vigencia de sesión migrada

`_scanner_sigue_vigente` fue migrada a `QrCameraRuntime.is_scanner_session_current(generation, scanner_active, expected_key, session_key, current_key)`. La implementación compara `generation` con `runtime.generation`, exige scanner activo y exige que la clave esperada coincida tanto con la clave de sesión como con la clave actual.

Home suministra esos cuatro valores técnicos; el runtime no conoce `state`, UI, arrivals, invitaciones, overlay, rutas ni negocio. Los 8 call sites de Home —polling, decode, resume, enumeración e initialize— usan esa única implementación.

### Aceptación de snapshot migrada

`_aceptar_codigo_snapshot` fue migrada a `QrCameraRuntime.accept_snapshot_code(codigo, generation, scanner_active, expected_key, session_key, current_key, gate, on_code_accepted)`.

El método reutiliza `is_scanner_session_current(...)`; no duplica la comparación de generación ni claves. El orden real de efectos es: validar vigencia de sesión → `QrFrameGate.try_begin_decode()` → `QrFrameGate.finish_decode(codigo)` → `on_code_accepted(codigo, generation, expected_key)`. Por tanto, el callback sólo recibe un código ya aceptado técnicamente; el booleano final es `bool(codigo_aceptado y callback)`.

`QrFrameGate` conserva la única responsabilidad de control de concurrencia, throttle y deduplicación. Home aporta el gate, las claves técnicas y el callback `_on_qr_detected`; hay un único call site migrado. El runtime no conoce `state`, UI, arrivals, RPC, invitaciones ni negocio. La frontera se mantiene: frame/decode → aceptación técnica → callback Home → finalizador/lifecycle → cleanup → `buscar_qr_llegadas(codigo_qr)`.

### Procesamiento stream migrado

`_scanner_frame_received` y su `decode_worker` fueron migrados a `qr_scanner_service.process_qr_camera_frame(...)` y al helper privado `_decode_and_accept_qr_frame(...)`. El servicio conoce únicamente bytes, `decode_qr_frame`, `QrFrameGate` y callbacks técnicos; no conoce UI, arrivals, invitaciones, RPC, navegación ni negocio.

Home conserva `_on_scanner_stream_image(event)` porque Flet entrega un `CameraImageEvent`: el adapter extrae `event.bytes` y aporta la vigencia de sesión, gate de la sesión, `page.run_thread` y el callback `_on_qr_detected`. No decodifica ni manipula el gate. El flujo stream es `CameraImageEvent` → adapter → `process_qr_camera_frame` → gate → worker/decode → callback técnico.

La ruta snapshot permanece independiente: `take_picture` → decode de polling → `QrCameraRuntime.accept_snapshot_code` → gate → callback técnico. Ambas rutas reciben el mismo `QrFrameGate` de la sesión y por eso comparten throttle, exclusión de decode concurrente y deduplicación. Ninguna llama negocio: `_on_qr_detected` solicita el finalizador y `buscar_qr_llegadas(codigo_qr)` ocurre sólo después de polling/captura terminada y cleanup.

0B4B-1, 0B4B-2 y 0B4B-3 quedan completados. El siguiente candidato, sin migrarlo todavía, es `iniciar_captura` + `take_snapshot` (0B4B-4).
