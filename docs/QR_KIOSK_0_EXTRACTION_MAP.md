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

## Initialization decomposition

`inicializar` permanece en `views/home_view.py` y actualmente agrupa estos bloques, que aún no se han movido:

1. Preparación: define `recovery_from_resume`, cede un turno al navegador y valida la sesión por `qr_runtime.is_scanner_session_current(...)`.
2. Resume/recovery: si `reuse_initialized_camera`, toma `qr_runtime.lifecycle_lock`, intenta `camera.resume_preview()` y reinicia captura. Si el plugin informa controller perdido, marca `controller_initialized=False`, `preview_paused=False` y activa `recovery_from_resume`.
3. Precondiciones de discovery: espera 0.3 s, vuelve a validar sesión y exige que Camera esté montada.
4. Discovery/selección: adquiere el mismo lifecycle lock, decide entre caché y `enumerate_cameras_with_retry`, selecciona descripción y actualiza `qr_runtime.camera_description`.
5. Inicialización nativa: ejecuta `camera.initialize(...)` con hasta tres intentos para errores transitorios.
6. Estado y captura: actualiza initialized/paused/camera_state, verifica nuevamente generation/sesión y llama `iniciar_captura(...)`.
7. Error terminal: los transitorios agotados dejan el panel abierto en estado `error` para retry/cancel; los no transitorios cierran por la ruta existente.

## Controller lost / recovery

Al abrir una nueva sesión, Home captura `reuse_initialized_camera = qr_runtime.controller_initialized` y después crea una generation nueva con `qr_runtime.invalidate()`. Si ese cache previo era verdadero, valida sesión y montaje, toma `qr_runtime.lifecycle_lock` e intenta `await camera.resume_preview()`. Un resume exitoso libera el lock, limpia `qr_runtime.preview_paused`, reutiliza la estrategia de captura ya guardada (`stream` o `snapshot`) e inicia captura sin discovery ni initialize.

Controller lost se detecta únicamente por excepción cuyo texto contiene, sin distinguir mayúsculas, `Camera is not initialized. Call initialize() first.`. Esa respuesta real del plugin prevalece sobre el cache Python: Home libera primero el lock de resume y después fija `qr_runtime.controller_initialized=False`, `qr_runtime.preview_paused=False`, `camera_state="uninitialized"` y `recovery_from_resume=True`. El panel sigue abierto; `camera_description` no se borra y generation permanece siendo la creada para esta apertura.

Luego la ruta normal vuelve a validar sesión y adquiere el mismo lock para initialize. Con `recovery_from_resume=True` y `qr_runtime.camera_description` no nula, usa la caché directamente, no enumera ni selecciona, y converge en `initialize_camera_with_retry`. Si la caché es `None`, usa discovery → selección → cache → el mismo helper. Una sesión invalidada durante la espera o dentro del helper retorna sin fijar controller ni iniciar captura; después de éxito Home vuelve a validar y sólo entonces llama `iniciar_captura`.

Un error de `resume_preview()` distinto del texto controller-lost no activa recovery: sale al `except` exterior. Si es `cameraNotReadable` o `cameraAbort`, conserva el panel en estado `error` con retry/cancel; cualquier otro se delega a `cerrar_scanner_qr(...)`. Esos transient errors no reciben retry automático en resume. Teardown es separado: nunca intenta resume, discovery, initialize ni recovery; durante `pause_preview()` reconoce el mismo texto como benigno, deja controller no inicializado y continúa cleanup sin abrir retry.

### Resume outcome classification — extracted

`services.qr_scanner_service.classify_camera_resume_outcome(error: Exception | None) -> Literal["resumed", "controller_lost", "error"]` es un helper puro. `None` devuelve `resumed`; sólo el texto case-insensitive `Camera is not initialized. Call initialize() first.` contenido en el error devuelve `controller_lost`; todo otro error, incluidos `cameraNotReadable` y `cameraAbort`, devuelve `error`.

Home conserva `await camera.resume_preview()` bajo `qr_runtime.lifecycle_lock`, clasifica el éxito con `None` y clasifica la excepción después de liberar el lock. Por tanto, el orden real es acquire → resume → release → classify/reaccionar → recovery → acquire de initialize, sin reentrancia. El plugin prevalece sobre el cache `controller_initialized`: `controller_lost` conserva en Home los cambios de runtime/UI y activa recovery; `error` conserva la clasificación transient y cierre existentes. El servicio no conoce runtime, lock, Camera, UI, recovery, discovery, initialize ni negocio.

Teardown conserva su helper independiente para tratar el mismo texto durante `pause_preview()` como benigno; no usa este clasificador ni inicia recovery.

Estado: QR-KIOSK-0B4B-7A ✅; QR-KIOSK-0B4B-7B ✅; QR-KIOSK-0B4B-7C ✅.

## Close / QR finalizer

`cerrar_scanner_qr(mensaje="", *, reason="cancel", codigo_qr=None)` captura el estado nativo antes de invalidar generation: Camera, `controller_initialized`, stream activo y la referencia actual de `qr_runtime.snapshot_task`. Después ejecuta `qr_runtime.invalidate()` y marca `closing` sólo si Camera está montada e inicializada. No borra `qr_runtime.camera_description`; la caché sobrevive al cierre normal del Home/runtime.

| Responsabilidad | Ruta manual/cancel/error | Ruta QR aceptado |
|---|---|---|
| Scanner técnico | `_restaurar_estado_interaccion_qr()` y `detener()` llaman `_limpiar_camera_scanner(..., wait_for_polling=True)`: cancela/espera polling, luego stop stream y pause. | Invalida gate/sesión y agenda `finalizar_qr()`, que espera polling antes de `_limpiar_camera_scanner(..., wait_for_polling=False)`. |
| UI | Restaura interacción, oculta chrome/host mediante `_actualizar_visibilidad_scanner(False)`, aplica mensaje y renderiza. | Restaura interacción y renderiza después del cleanup; no entrega un mensaje de error por esta ruta. |
| Business handoff | Ninguno. | Sólo al final de `finalizar_qr()`: `buscar_qr_llegadas(codigo_qr)`. |

### Orden técnico actual

La ruta manual ejecuta invalidate → restauración inicial de UI/gate → tarea `detener` → acquire `qr_runtime.lifecycle_lock` → (si existe y no es la tarea actual) cancel + await de polling → `stop_image_stream()` si stream estaba activo → `pause_preview()` si el controller previo y el cache actual dicen initialized → release → restauración final/UI. Por tanto, polling termina antes de las operaciones Camera incompatibles. `run_qr_snapshot_polling` es dueño de limpiar `qr_runtime.snapshot_task` en su `finally`, sólo si la referencia sigue siendo su propia tarea; close no la limpia directamente.

En QR aceptado, `_on_qr_detected(codigo, generation, active_key)` valida sesión, guarda el código y llama a close. La rama QR no cancela/espera su propia tarea: `finalizar_qr`, creado con `page.run_task`, comprueba identidad contra `asyncio.current_task()`, espera la tarea de polling si sigue viva, limpia Camera con `wait_for_polling=False`, restaura UI y recién entonces llama negocio. Así scanner termina exactamente en `buscar_qr_llegadas(codigo_qr)`; polling, decode worker, el lock y cleanup no ejecutan negocio.

`_limpiar_camera_scanner` toma el único `qr_runtime.lifecycle_lock`. Dentro de él coordina cancel/await, stop stream y pause. Los errores de stop stream se registran y continúan. Un fallo de `pause_preview()` en el cierre ordinario se registra, deja `controller_initialized=False` y `camera_state="error"`, sin recovery ni propagación fuera de la tarea; el manejo específicamente benigno del mensaje controller-lost durante pause corresponde sólo a `_desmontar_scanner_overlay()` de teardown/logout, que además retira el overlay de Page. Close ordinario conserva el host/overlay persistentes, sólo los oculta y libera sus interacciones.

No hay un guard interno explícito de doble invocación dentro de `cerrar_scanner_qr`; la apertura bloquea cuando `qr_scanner_closing` está activo y cada cierre invalida la generation y reutiliza el cleanup actual. Esto queda caracterizado, no se rediseña en esta fase. Logout llama `_desmontar_scanner_overlay()`: comparte invalidate, gate stop, cancel/await, stream stop y pause bajo el mismo lock, pero no entrega negocio, elimina el overlay de Page y trata controller-lost de pause como benigno.

Funciones mezcladas actuales: `cerrar_scanner_qr` combina decisión de ruta, estado UI y programación de tareas; `finalizar_qr` combina cleanup/UI con el handoff de negocio; `_limpiar_camera_scanner` es la porción más técnica, aunque aún depende de Camera, lock, montado y estado textual de Home.

**Siguiente micro-paso propuesto — QR-KIOSK-0B4B-8B:** extraer sólo el bloque interno de `_limpiar_camera_scanner` que, con polling ya coordinado y lock ya adquirido por Home, ejecuta stop stream/pause y reporta el resultado técnico por callbacks. No mover `cerrar_scanner_qr`, `finalizar_qr`, business handoff, lock, polling ownership ni UI.

### Camera capture stop — extracted

`services.qr_scanner_service.stop_camera_capture(stop_stream, pause_preview, stream_active, should_pause)` recibe únicamente callbacks nativos y flags técnicos. Devuelve `CameraCaptureStopResult` con los intentos y errores originales de stream/pause. No conoce runtime, lock, polling, UI, Camera, códigos QR ni negocio; tampoco captura `CancelledError`, que conserva su propagación natural.

Home sigue cancelando/esperando polling y adquiriendo `qr_runtime.lifecycle_lock` antes de llamar al helper desde `_limpiar_camera_scanner`. El helper intenta stop sólo con stream activo y, incluso si éste falla, intenta pause cuando Home lo solicitó. Home registra errores y conserva los estados: pause exitoso marca preview pausado/estado `paused`; pause fallido deja controller falso/estado `error`, sin recovery. Teardown mantiene sus llamadas directas porque su semántica para controller-lost es distinta.

Estado: QR-KIOSK-0B4B-8A ✅; QR-KIOSK-0B4B-8B ✅; QR-KIOSK-0B4B-8C ✅ si la batería completa pasa.

## Camera discovery / selection — extracted

`services/qr_scanner_service.py` contiene la infraestructura reutilizable: `enumerate_cameras_with_retry(enumerate_cameras, is_active, on_transient_error, *, max_attempts=3, retry_delays=(0.4, 0.8))` y `select_camera_description(cameras, preferred_lens) -> CameraDescription | None`.

Discovery conserva un máximo de tres intentos y considera transitorios exclusivamente `cameraNotReadable` y `cameraAbort`. Si la sesión deja de ser vigente durante el backoff, devuelve `None`; los errores terminales se propagan a Home. `select_camera_description` devuelve la primera cámara BACK, o `cameras[0]` si no hay BACK, o `None` para una lista vacía; no ordena ni muta la lista.

Home conserva el lifecycle lock, la decisión cache vs. discovery, el mensaje para lista vacía, los logs, y el único ownership de `qr_runtime.camera_description`. La apertura normal siempre usa discovery; recovery desde `resume_preview` con caché no nula reutiliza directamente la descripción y omite discovery/selección. Recovery sin caché vuelve a discovery. `camera.initialize(...)`, sus retries, recovery y UI permanecen en Home.

### Camera initialize retry — extracted

El adapter Flet permanece en `views/home_view.py`: `initialize_once()` ejecuta `await camera.initialize(description, fcam.ResolutionPreset.LOW, enable_audio=False, image_format_group=fcam.ImageFormatGroup.JPEG)`. `description` es la `CameraDescription` local: en apertura normal y recovery sin caché llega de discovery/selección y Home la guarda antes en `qr_runtime.camera_description`; recovery desde `resume_preview` con caché no nula reutiliza directamente esa misma caché.

El retry técnico vive en `qr_scanner_service.initialize_camera_with_retry(initialize_once, is_active, on_transient_error=None, *, max_attempts=3, retry_delays=(0.25, 0.5), sleep=asyncio.sleep) -> int | None`. Éxito devuelve el intento usado; sesión inactiva devuelve `None`; el error terminal original se relanza. Sólo `is_camera_transient(ex)` —`cameraNotReadable` o `cameraAbort`— vuelve a intentar, con delays exactos de 0.25 y 0.5 tras los dos primeros fallos. Un error no transitorio, incluido `Camera is not initialized. Call initialize() first.` si lo emitiera initialize, o el tercer fallo transitorio se propaga al `except` exterior. `asyncio.CancelledError` no se intercepta ni se convierte en retry o `None`.

El mismo `qr_runtime.lifecycle_lock` se adquiere después de las precondiciones de sesión/montado y contiene decisión caché vs. discovery, cacheo y la llamada al helper; el helper no adquiere lock. Se libera en el `finally` antes de actualizar el estado post-éxito. Después de éxito Home fija `qr_runtime.controller_initialized=True`, `qr_runtime.preview_paused=False` y `state["qr_scanner_camera_state"]="initialized"`, vuelve a validar navegación/sesión e inicia captura con `scanner_strategy(await camera.supports_image_streaming())`. `_scanner_state_change` también actualiza los caches desde el evento nativo; por tanto, el await exitoso permite el estado local de Home y el callback nativo sigue siendo la fuente de eventos del plugin.

El controller-lost se detecta antes, durante `resume_preview`, y permanece en Home. Apertura normal, recovery sin caché y recovery con caché convergen en la misma llamada al helper; sólo difiere cómo obtienen `description`. Ante agotamiento transitorio, el `except` exterior deja `controller_initialized=False`, `camera_state="error"`, mensaje de retry/cancel y panel abierto; no invoca negocio ni cleanup explícito en esa rama. Los errores no transitorios se delegan a `cerrar_scanner_qr(...)` por la ruta actual. Runtime state, UI, cache ownership, recovery y start capture siguen fuera del servicio.



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
| `abrir_scanner_qr > iniciar_captura` | adapters/generation | inicia stream | render | — | strategy/flags | — | E: polling; L: accept/close | MEDIA |
| `qr_scanner_service.run_qr_snapshot_polling` / `take_qr_snapshot` | `snapshot_task`/generation | callback `take_picture` | — | tarea actual | gate/callbacks aportados | — | E: polling | MEDIA |
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
4. **0B4B-4 — ✅ `run_qr_snapshot_polling` / `take_qr_snapshot`**: polling técnico migrado; Home conserva estrategia, estado visual y adapters.
5. **0B4B-5A — ✅ caracterización**: delimitó discovery/selección sin mover lifecycle.
6. **0B4B-5B — ✅ extracción**: `enumerate_cameras_with_retry` reutilizado y `select_camera_description` extraído a `qr_scanner_service`.
7. **0B4B-5C — ✅ validación**: cubre BACK/fallback, retry, ownership de caché y recovery cacheada.
8. **0B4B-6A — ✅ caracterización**: fija el contrato de `camera.initialize()` y su retry sin extraerlo.
9. **0B4B-6B — ✅ extracción**: retry técnico de initialize migrado; recovery permanece en Home.
10. **0B4B-6C — ✅ validación**: cubre retry, cancelación, lock y fronteras de estado.
11. **Siguiente candidato — controller-lost / recovery**: caracterizar y extraer por separado; no iniciado.
12. **0B4B-7 — `_limpiar_camera_scanner`**: primera operación nativa reutilizable; conserva lock, cancelación/espera de polling y callbacks mínimos de montado/log/UI.
13. **0B4B-8 — `cerrar_scanner_qr`**: separar primero el finalizador técnico de su callback `on_qr_detected(codigo)` antes de mover el coordinador de close.
14. **0B4B-9 — `_desmontar_scanner_overlay` y luego Camera/overlay**: mantenerlos al final por dependencia directa de Page y composición visual.

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

### Polling snapshot migrado

El loop técnico antes anidado en `iniciar_captura` y su `take_snapshot` local fueron migrados a `qr_scanner_service.run_qr_snapshot_polling(...)` y `take_qr_snapshot(...)`. Home conserva solamente la selección stream/snapshot, estado visual y adapters para `camera.take_picture`, vigencia, aceptación y error.

El servicio registra la tarea actual en `runtime.snapshot_task` y en su `finally` la limpia sólo si la referencia aún identifica esa misma tarea. Cleanup y el finalizador continúan invalidando generation, cancelando y esperando esa task antes de pausar la cámara; la cancelación se propaga al polling y `take_qr_snapshot` conserva el `finally` de logging. La ruta es `take_picture` → decode de polling → callback Home → `QrCameraRuntime.accept_snapshot_code` → gate → `_on_qr_detected`.

Stream y snapshot permanecen separados, pero reciben el mismo `QrFrameGate` de la sesión. No hay negocio en el servicio: el finalizador externo espera polling/captura, realiza cleanup y sólo después llama `buscar_qr_llegadas(codigo_qr)`.

0B4B-1, 0B4B-2, 0B4B-3 y 0B4B-4 quedan completados. El siguiente candidato, sin migrarlo todavía, es `inicializar / recovery` (0B4B-5).
