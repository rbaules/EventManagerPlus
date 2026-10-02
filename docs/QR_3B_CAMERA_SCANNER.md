# QR-3B — escáner de cámara

QR-3B añade una entrada de cámara al flujo QR-3A sin crear una ruta de negocio nueva:

```text
Cámara -> cv2.QRCodeDetector -> código normalizado -> buscar_qr_llegadas()
       -> resolver_invitacion_qr() (QR-2A) -> cargar_grupo_invitacion() (QR-2B)
```

## Dependencias

- `flet-camera==0.85.3`, alineado con Flet 0.85.3.
- `opencv-python-headless==4.14.0.94`, con wheel compatible con Python 3.14.

No se usa `pyzbar`, no hay extensiones Flutter propias, JavaScript, almacenamiento de imágenes ni cambios SQL.

## Cámara y ciclo de vida

La cámara tiene identidad estable por Home/Page: se construye una sola vez y se monta en un `page.overlay` persistente. El shell de Llegadas se reconstruye con `render()`, pero el overlay no; por eso abrir o cerrar el scanner sólo alterna `visible` y actualiza la página, sin desmontar, reparentar ni crear otra `Camera`. El acceso físico (listar cámaras, inicializar, stream o snapshot) sigue ocurriendo exclusivamente después de pulsar **Escanear QR**.

El wrapper Python instalado expone `initialize()`, `pause_preview()` y `resume_preview()`, pero no expone `dispose()`. El wheel no contiene la implementación Flutter que permitiría confirmar que retirar el control del árbol libera los tracks Web; por eso EventPlus no depende de un unmount para liberar el dispositivo ni usa métodos privados. La máquina de estados es `mounted → initialized → scanning → closing → paused`; la primera apertura enumera e inicializa, Cancelar detiene la lectura y pausa el preview, y las reaperturas usan `resume_preview()` con la estrategia ya seleccionada. No se vuelve a enumerar ni se llama `initialize()` mientras el controller permanezca sano. Un error real de estado/pause invalida ese estado y permite la inicialización normal posterior.

Si `resume_preview()` informa exactamente que el controller no está inicializado, el panel permanece abierto y realiza una recuperación en el mismo clic: invalida el estado local y reinicializa primero con la `CameraDescription` ya seleccionada. No hay una enumeración innecesaria ni un loop ilimitado.

El polling snapshot conserva una referencia explícita a su tarea. Cancelar, navegación y error la cancelan y esperan antes de pausar el preview. Para un QR válido, que se detecta desde la propia tarea de polling, un finalizador externo espera primero que esa tarea retorne; sólo entonces adquiere el lock, limpia físicamente Camera, oculta el scanner y llama a la resolución QR. Así no se puede cancelar o esperar una tarea desde sí misma, ni se solapan `take_picture()` con `pause_preview()`, `resume_preview()` o `initialize()`. Un `asyncio.Lock` serializa dichas operaciones nativas. Una recuperación de controller perdido reutiliza la `CameraDescription` ya enumerada; sólo la primera inicialización enumera dispositivos.

En Web, después de mostrar el overlay se espera 300 ms antes de enumerar. `cameraNotReadable` y `cameraAbort` se tratan como transitorios tanto al enumerar como al inicializar: se reintentan como máximo tres veces. La enumeración usa 400 y 800 ms; la inicialización usa 250 y 500 ms. Tras agotar esos intentos el scanner no se cierra: permanece visible con **Reintentar cámara** y **Cancelar**. Es una mitigación acotada, no una garantía general del navegador: permisos, seguridad, cámara ausente y cualquier otro error no se reintentan. Si se cancela, cambia el evento o se navega durante el backoff, la generación invalida la operación sin mostrar un error tardío.

El control `Camera` se crea una sola vez por Home/Page. Su host persistente y todos sus ancestros permanecen con `visible=True`; cuando el scanner está cerrado se reduce a 1×1, usa `opacity=0` e ignora interacciones. El chrome (título, instrucciones y Cancelar) es hermano del host y sí puede usar `visible=False`. Así el widget Web no se desmonta al ocultar el panel. Al abrir, el host pasa a tamaño de preview y `opacity=1`, EventPlus cede un turno al loop y confirma `camera.page` antes de invocar cualquier método del plugin.

Después del montaje, consulta las cámaras, prefiere `CameraLensDirection.BACK` y usa la primera disponible como fallback. Inicializa `ResolutionPreset.LOW`, JPEG y audio desactivado. La resolución baja es suficiente para un QR de cuatro caracteres a distancia de lectura y reduce transferencia, CPU, memoria y latencia. El stream se detiene y el preview se pausa al detectar un código, cancelar, cambiar de evento o abandonar Registrar llegadas; estas operaciones sólo se intentan para una cámara montada e inicializada.

Hay dos estrategias, con el mismo preview y el mismo destino de negocio:

- Nativo compatible: si `supports_image_streaming()` es verdadero, usa `start_image_stream()` y `on_stream_image`.
- Web: `camera_web` no soporta image streaming; si la consulta devuelve falso, el preview permanece abierto y se ejecuta polling secuencial con `take_picture()` cada 650 ms.

El polling nunca solapa capturas. Después de tres errores consecutivos de captura se cierra de forma segura y queda disponible la entrada manual. Un error aislado se registra sin traceback y se reintenta.

`QrFrameGate` limita el decode a un intento cada 250 ms, permite un solo decode concurrente y bloquea cualquier detección posterior a la primera válida. Un token de generación y la clave cuenta/evento invalidan frames o snapshots tardíos después de cancelar, cambiar de evento o salir de Llegadas. Los frames se procesan exclusivamente en memoria; no se registran ni persisten bytes o imágenes. Los logs sólo indican el largo del código válido.

## Decoder y fallback

`decode_qr_frame()` acepta bytes codificados, usa `cv2.imdecode()` y `cv2.QRCodeDetector.detectAndDecode()`, y sólo entrega `^[A-Z0-9]{4}$` tras trim y mayúsculas. QR inválidos se ignoran y no alcanzan Supabase. Permisos denegados, cámara ausente, stream no soportado e inicialización fallida conservan el campo manual QR disponible.

Consulta puede escanear y cargar el grupo en modo lectura; QR-3A sigue impidiendo selección y confirmación.

## Web móvil

Los navegadores requieren un contexto seguro para acceder a cámara. `localhost` y `127.0.0.1` son aptos para pruebas en la misma máquina. Una URL LAN HTTP como `http://192.168.x.x:8550` no debe considerarse apta para cámara móvil: la prueba real en teléfono/tablet requiere HTTPS. No se desactiva seguridad del navegador ni se recomiendan flags inseguros.

## Pruebas

`scripts/test_qr_camera_lifecycle.py` verifica que renders de ruta, apertura y cierre conservan una sola construcción de cámara y un solo overlay por Page.

`scripts/test_qr_scanner_service.py` cubre decoder válido/sin QR/inválido/bytes inválidos/excepción, selección stream/snapshot, polling sin QR, detección única, cancelación/evento tardío y errores temporales o persistentes. Las pruebas QR y responsive verifican los controles Escanear/Cancelar, el campo compartido y los tres tamaños de layout. El hardware y permisos requieren una prueba manual posterior con cámara real.

Para aislar el plugin de EVENTPLUS y del decoder, ejecute el spike manual:

```powershell
env\Scripts\python.exe -m flet run --web scripts\test_camera_web_spike.py
```

Pulse **Inicializar** y luego **Foto**. El spike comprueba montaje, lista cámaras, inicializa LOW/JPEG/sin audio y muestra únicamente la longitud de bytes recibidos en memoria.
