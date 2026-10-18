# EVKOR server-side custom web client

Cliente Flet aislado para compilar `EvkorServerWebQrProbe` dentro del
bundle Flutter que usa una aplicacion Flet server-side.

## Build local

Desde este directorio, usar el Flet instalado en el entorno del proyecto:

```powershell
..\..\env\Scripts\flet.exe build --no-rich-output web .
```

El resultado generado queda en `build/flutter/build/web/` y no se versiona.

## Prueba server-side

Copiar el contenido del resultado a un directorio temporal de deploy y usar
esa ruta solamente en la sesion local:

```powershell
$env:FLET_WEB_PATH = "C:\ruta\a\server_web"
$env:PYTHONPATH = "C:\WORKSPACE\EVENTPLUS\diagnostics\evkor_web_qr_probe\src"
env\Scripts\python.exe -m uvicorn asgi:app --host 127.0.0.1 --port 8095
```

El indice servido por Flet debe conservar `pyodide: false` y
`webSocketEndpoint: "/ws"`; el indice de `assets/` es la configuracion
server-side que Flet aplica al servir la aplicacion.

Abrir `/diagnostics/server-web-qr-control` y pulsar el control para verificar
el evento `SERVER_WEB_QR_TEST` sobre el WebSocket existente.
