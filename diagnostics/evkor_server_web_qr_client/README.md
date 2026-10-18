# EVKOR server-side custom web client

Cliente Flet aislado para compilar `EvkorServerWebQrProbe` dentro del
bundle Flutter que usa una aplicacion Flet server-side.

## Build local

Desde este directorio, usar el Flet instalado en el entorno del proyecto:

```powershell
..\..\env\Scripts\flet.exe build --no-rich-output web .
```

El resultado intermedio queda en `build/web/`. Para preparar el bundle final
que sirve Flet en modo server-side, ejecutar desde la raíz del repositorio:

```powershell
.\diagnostics\evkor_server_web_qr_client\prepare_server_web_client.ps1
```

El script copia el resultado a `deploy/server_web/`, cambia el índice a
`pyodide: false`, conserva `webSocketEndpoint: "/ws"` y elimina los recursos
de Pyodide y `assets/app/app.zip`. Ese directorio final se versiona para evitar
instalar Flutter durante cada build de Render.

## Prueba server-side

Con el bundle final versionado, iniciar el ASGI desde una sesión limpia:

```powershell
env\Scripts\python.exe -m uvicorn asgi:app --host 127.0.0.1 --port 8095
```

`asgi.py` define automáticamente `FLET_WEB_PATH` a
`<raíz-del-repositorio>/diagnostics/evkor_server_web_qr_client/deploy/server_web`
antes de inicializar Flet. En Render, mantener explícitamente la misma ruta
absoluta de su checkout:

```text
FLET_WEB_PATH=/opt/render/project/src/diagnostics/evkor_server_web_qr_client/deploy/server_web
```

El índice servido por Flet conserva `pyodide: false` y
`webSocketEndpoint: "/ws"`; no contiene ni requiere `assets/app/app.zip` ni
el runtime Python de Pyodide. `requirements.txt` instala el wrapper Python
local `evkor-web-qr-probe`; por ello tampoco se requiere `PYTHONPATH` manual
en Render.

Abrir `/diagnostics/server-web-qr-control` y pulsar el control para verificar
el evento `SERVER_WEB_QR_TEST` sobre el WebSocket existente.
