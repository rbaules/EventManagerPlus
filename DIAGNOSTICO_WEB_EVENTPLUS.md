# Diagnóstico técnico para migración web de EventPlus

Fecha de auditoría: 25 de julio de 2026  
Repositorio auditado: `C:\WORKSPACE\EVENTPLUS`  
Entorno validado: Python 3.14.6, Flet 0.85.3, Supabase 2.31.0  
Alcance: auditoría estática y pruebas controladas, sin modificar código, configuración ni dependencias.

## 1. Resumen ejecutivo

EventPlus es una aplicación Flet funcional y modular, con dos modos de ejecución (`FULL` y `CHECKIN`), autenticación Google OAuth mediante Supabase, selección de cuenta/evento, Dashboard, consulta y mantenimiento de invitados y registro/reversión de llegadas. La aplicación ya puede levantarse localmente como sitio web dinámico con el CLI de Flet.

Sin embargo, **no debe desplegarse todavía como aplicación web multiusuario**. El bloqueo principal es que `db.py` crea y conserva un único `supabase.Client` global mediante `@lru_cache(maxsize=1)`. El estado de autenticación (access token y refresh token mantenidos internamente por `supabase-py`) queda ligado a ese cliente compartido por todo el proceso. En un servidor web, el login o logout de una persona puede sustituir o invalidar la sesión de otra y todas las consultas podrían ejecutarse con la identidad equivocada.

El segundo bloqueo es el flujo OAuth actual. Para escritorio inicia un `HTTPServer` local en `127.0.0.1:8765`, abre el navegador del sistema con `webbrowser.open()` y entrega el resultado mediante una cola estática de proceso. Este diseño no es apto para Internet, contenedores, varios workers, varios usuarios ni múltiples intentos simultáneos. En navegador, `localhost` identifica el dispositivo del usuario, no necesariamente el servidor desplegado.

Flet 0.85.3 sí ofrece exportación ASGI directamente: `ft.run(..., export_asgi_app=True)` devuelve una aplicación FastAPI. El repositorio aún no exporta ese objeto y `requirements.txt` no declara explícitamente un servidor ASGI. El entorno local auditado sí contiene `fastapi` y `uvicorn` como dependencias transitivas, pero para despliegue reproducible deben declararse según la estrategia elegida.

La interfaz tiene una buena base responsive (`ResponsiveRow`, columnas por breakpoint, `ListView`, `SafeArea`, navegación inferior y controles expansibles), aunque requiere validación real en anchos móviles. El ancho fijo de 460 px en login, los encabezados y algunos grupos de acciones merecen ajustes o pruebas específicas. Las dimensiones de `page.window` son exclusivas del modo escritorio y deben aplicarse condicionalmente o eliminarse para web.

La seguridad depende hoy en gran medida de filtros y comprobaciones de Python/UI. Los documentos del proyecto indican expresamente que RLS no está activado. Aunque las consultas incluyen `cuenta_id` y `evento_id`, sin RLS una publishable key permite que un cliente autenticado intente consultar o modificar directamente tablas fuera de la aplicación. Este riesgo es crítico antes de exponer el sistema a Internet.

## 2. Arquitectura actual

### 2.1 Capas

- **Entrada y configuración:** `app.py`, `main_checkin.py`, `config.py`, `db.py`.
- **Presentación:** `views/` y `components/`.
- **Servicios y acceso a datos:** `services/`.
- **Pruebas de regresión:** scripts ejecutables en `scripts/`; no existe una suite formal bajo `tests/` ni configuración visible de pytest.
- **Documentación funcional y de esquema:** archivos `EVENTPLUS_*.md` y `docs/`.
- **Activos:** logos e imágenes en `assets/`.

### 2.2 Archivos de entrada

1. `app.py`
   - Entrada principal.
   - Define `main(page: ft.Page)`.
   - Configura título, dimensiones de ventana, scroll y modo adaptativo.
   - Construye directamente la vista de login.
   - Ejecuta `ft.run(main, assets_dir="assets")` dentro del guard `if __name__ == "__main__"`.
   - Por defecto usa `EVENTPLUS_MODE=FULL`.

2. `main_checkin.py`
   - Entrada alternativa para el modo operativo de check-in.
   - Fija `EVENTPLUS_MODE=CHECKIN` antes de importar `main` desde `app.py`.
   - Ejecuta igualmente `ft.run(main, assets_dir="assets")`.

3. `app_publishable_key_v4.py`
   - Prototipo/diagnóstico OAuth autónomo, no integrado en la entrada productiva.
   - Duplica configuración, cliente Supabase, servidor callback y una UI de prueba.
   - Ejecuta `ft.run(main)` sin `assets_dir`.
   - No debería tratarse como entrada de producción.

### 2.3 Inicio de Flet

Se usa la API vigente `ft.run()` de Flet 0.85.3. En esta versión su firma incluye `view`, `host`, `port`, `assets_dir` y `export_asgi_app`. `ft.app()` existe por compatibilidad, pero el proyecto no lo usa.

Sin `view` explícito, ejecutar `env\Scripts\python.exe app.py` solicita la vista `FLET_APP`, normalmente escritorio. El CLI `flet run --web` cambia la presentación a sitio dinámico.

### 2.4 Navegación

La navegación no está modelada como rutas URL salvo el listener de deep links Android:

- `app.py` muestra login.
- `views/login_view.py` limpia la página y monta `build_home_view()` después del login.
- `views/home_view.py` conserva la pestaña activa en un diccionario local `state`.
- `components/bottom_navigation.py` selecciona Dashboard, Invitados o Registrar llegadas.
- En modo `CHECKIN` solo muestra Invitados y Registrar llegadas.
- `page.clean()` y reconstrucción de controles sustituyen la vista actual.
- `page.on_route_change` se usa únicamente para detectar el callback Android `eventplusbeta://auth-callback`.

No hay rutas web como `/login`, `/dashboard` o `/auth/callback`, historial de navegador, guards de ruta ni soporte explícito para deep links web. Recargar la página no reconstruye una ruta funcional autenticada.

### 2.5 Estado y sesiones

Hay tres niveles de estado:

- **Estado de UI por página:** el diccionario `state` se crea dentro de `build_home_view()`. Por estar dentro del handler de una página, se aísla razonablemente entre conexiones Flet mientras la página permanezca activa.
- **Store de sesión Flet:** `page.session.store` guarda `usuario_contexto`, `eventos_disponibles` y `diagnostico_login`. Se limpia en logout. Su alcance es la sesión Flet del servidor; no constituye por sí mismo persistencia segura tras recarga, nueva pestaña, reinicio o cambio de worker.
- **Estado Supabase global:** `get_supabase_client()` está cacheado globalmente. Es el problema crítico: Auth, tokens, cabeceras y cliente Realtime pertenecen a un único objeto compartido por el proceso.

No se encontró recuperación de sesión al iniciar la página (`auth.get_session()`, restauración de refresh token o equivalente). Cada nueva conexión vuelve al login. Una pestaña nueva crea otra sesión Flet, pero reutiliza el mismo cliente Supabase global. El logout llama `supabase.auth.sign_out()` sobre ese cliente y puede afectar a todas las pestañas y usuarios del proceso.

## 3. Inventario de archivos relevantes

| Archivo/directorio | Responsabilidad | Observaciones |
|---|---|---|
| `app.py` | Entrada principal FULL | Usa `ft.run`; aplica propiedades de ventana de escritorio; no exporta ASGI. |
| `main_checkin.py` | Entrada CHECKIN | Modifica una variable de entorno al importar; no exporta ASGI. |
| `app_publishable_key_v4.py` | Prototipo OAuth | Código duplicado, cliente y callback globales; no es apto para producción. |
| `config.py` | Configuración, modos y URLs OAuth | Lee `.env` y configuración pública empaquetada; callback web/local por defecto en `localhost:8765`. |
| `db.py` | Creación de cliente Supabase | Cliente global cacheado; riesgo crítico multiusuario. |
| `.env` | Valores locales | Ignorado por Git; contiene las tres variables esperadas. No se revelaron valores durante la auditoría. |
| `app_public_config.py` | Configuración pública empaquetada | Ignorado por Git; pensado para Android. Una publishable key no es secreto, pero RLS debe proteger los datos. |
| `app_public_config.example.py` | Plantilla pública | Correctamente advierte no usar service role ni secretos. |
| `requirements.txt` | Dependencias directas | Solo fija Flet, Supabase y python-dotenv. |
| `services/auth_service.py` | OAuth, sesión y logout | HTTP callback local, cola global, intercambio de code y acceso al cliente global. |
| `services/usuario_service.py` | Usuario, cuentas, eventos y roles | Construye el contexto operativo desde tablas Supabase. |
| `services/evento_context_service.py` | Contexto y store de sesión | Selección/limpieza de evento y persistencia en `page.session.store`. |
| `services/evento_service.py` | Consulta de eventos | Restringe consultas según el contexto calculado. |
| `services/invitado_service.py` | Invitados, invitaciones y llegadas | Núcleo de reglas, paginación, búsquedas, altas, edición, llegadas, reversión e imprevistos. |
| `services/response_utils.py` | Normalización de respuestas | Utilidades robustas para objetos/diccionarios de Supabase. |
| `views/login_view.py` | Login y transición al Home | Usa hilos, callback local, deep link Android y session store. |
| `views/home_view.py` | Orquestación de módulos | Estado por página, navegación, workers, contexto y logout. |
| `views/dashboard_view.py` | Dashboard y selección de evento | Estados loading/empty/error y layout responsive. |
| `views/invitados_view.py` | Consulta y formularios de invitados | Responsive, filtros, paginación, detalle y acciones según permisos. |
| `views/arrivals_view.py` | Registro de llegadas | Búsqueda, selección grupal, confirmación y reversión. |
| `components/app_shell.py` | Estructura visual común | `SafeArea`, header y contenido expandible. |
| `components/bottom_navigation.py` | Navegación principal | Permisos visuales y variantes FULL/CHECKIN. |
| `components/event_header.py` | Encabezado y menú | Usa `ResponsiveRow`; logout/cambio de evento. |
| `components/stat_card.py` | Tarjeta estadística | Componente del Dashboard. |
| `scripts/*.py` | Pruebas y verificaciones | Pruebas con dobles/mocks, smoke imports y baseline del entorno. |
| `scripts/build_android_checkin.ps1` | Build Android | Específico de Windows/desarrollo; no forma parte del runtime web. |
| `docs/ANDROID_*.md` | Guías Android | Relevantes al modo móvil empaquetado, no al despliegue web. |
| `EVENTPLUS_SCHEMA_CONTEXT_v1_1.md` | Contrato de esquema | Confirma que RLS aún no está activado y describe Realtime futuro. |

## 4. Inventario funcional

| Módulo/capacidad | Estado | Archivo principal | Observaciones y riesgos |
|---|---|---|---|
| Arranque FULL | Implementado | `app.py` | Orientado por defecto a escritorio. |
| Arranque CHECKIN | Implementado | `main_checkin.py` | Modo decidido mediante variable global de entorno al importar. |
| Login Google OAuth/Supabase | Parcialmente implementado para web | `views/login_view.py`, `services/auth_service.py` | Funciona en escritorio/Android; callback local y cliente global impiden uso web concurrente. |
| Logout | Implementado, no aislado | `views/home_view.py`, `services/auth_service.py` | Limpia store Flet, pero hace sign-out sobre cliente global. |
| Recuperación de sesión | No implementado | — | No se encontró restauración de tokens o sesión al reconectar. |
| Contexto de usuario/cuenta/evento | Implementado | `services/usuario_service.py` | Buena validación en aplicación; depende de RLS para seguridad real. |
| Selección/cambio de evento | Implementado | `services/evento_context_service.py`, `views/home_view.py` | Estado por sesión Flet; no persistente entre pestañas/recargas. |
| Dashboard | Implementado | `views/dashboard_view.py` | Estados y tarjetas responsive; verificar datos reales y móviles. |
| Navegación | Implementado | `views/home_view.py`, `components/bottom_navigation.py` | Navegación interna por estado, sin rutas URL web. |
| Consulta paginada de invitados | Implementado | `services/invitado_service.py`, `views/invitados_view.py` | Usa filtros de cuenta/evento y `INVITADOS_PAGE_SIZE`; sin RLS el aislamiento no es garantizado. |
| Búsqueda por invitado | Implementado | `services/invitado_service.py` | Normalización y búsqueda parcial. |
| Búsqueda por mesa | Implementado | `services/invitado_service.py` | Consulta mesas coincidentes y filtra invitados. |
| Detalle de invitado | Implementado | `views/invitados_view.py`, `services/invitado_service.py` | Incluye clave compuesta de cuenta/evento/invitación/invitado. |
| Crear invitado planificado | Implementado | `services/invitado_service.py` | Control Master/Administrador en Python; requiere política DB. |
| Editar invitado planificado | Implementado | `services/invitado_service.py` | Revalida evento y existencia antes de actualizar. |
| Invitado imprevisto | Implementado en FULL | `services/invitado_service.py` | Bloqueado en CHECKIN por código; permisos de DB no verificados. |
| Eliminar invitado imprevisto | Implementado en FULL | `services/invitado_service.py` | Operación sensible protegida solo por contexto de app sin evidencia de RLS. |
| Registro de llegada individual | Implementado | `services/invitado_service.py` | Revalida rol/fase y claves del evento. |
| Registro grupal por invitación | Implementado | `services/invitado_service.py`, `views/arrivals_view.py` | Tiene pruebas con dobles; no se observó transacción/RPC atómica. |
| Reversión de llegada | Implementado | `services/invitado_service.py` | Permite Master/Administrador/Operador según reglas actuales. |
| Permisos por rol | Implementado en app | Servicios y vistas | Master, Administrador y Operador; no equivalen a autorización server-side sin RLS. |
| Preferencias | No implementado | `views/home_view.py` | Muestra placeholder en FULL. |
| Realtime | No implementado en código | — | Documentación lo contempla, pero no hay `channel()`, `subscribe()` ni lifecycle de WebSocket. |
| Rutas web/deep links web | No implementado | — | Solo callback Android en `on_route_change`. |
| ASGI exportable | Parcialmente disponible | `app.py` | La versión instalada lo soporta, pero el repositorio no exporta un objeto ASGI. |
| Responsive | Parcialmente implementado | Vistas y componentes | Buena base; faltan pruebas sistemáticas y ajustes de anchos/acciones. |
| Pruebas automatizadas | Parcialmente implementado | `scripts/` | Scripts directos, sin runner unificado, cobertura ni pruebas de concurrencia/OAuth web. |

## 5. Situación actual de ejecución web

### 5.1 ¿Puede ejecutarse hoy como web?

**Sí, localmente como sitio dinámico de Flet**, porque Flet 0.85.3 incluye el servidor web dinámico y el CLI reconoce `--web`. Esto permite renderizar y usar la UI desde un navegador.

No significa que sea segura o funcionalmente correcta para varios usuarios. El flujo OAuth actual puede funcionar en una prueba local de un solo usuario porque navegador y callback comparten la misma máquina, pero presenta colisiones y problemas de sesión aun en varias pestañas.

### 5.2 Comando actual de escritorio

Modo completo:

```powershell
env\Scripts\python.exe app.py
```

Modo check-in:

```powershell
env\Scripts\python.exe main_checkin.py
```

### 5.3 Comando exacto para prueba web local actual

Modo completo, en un puerto determinista:

```powershell
env\Scripts\flet.exe run --web --host 127.0.0.1 --port 8550 app.py
```

Modo check-in:

```powershell
env\Scripts\flet.exe run --web --host 127.0.0.1 --port 8550 main_checkin.py
```

Abrir `http://127.0.0.1:8550`. Para probar desde otro dispositivo de la LAN se puede usar `--host "*"`, sujeto al firewall, pero no se recomienda exponerlo a Internet en el estado actual.

### 5.4 ASGI actual

No existe hoy una variable de módulo como `asgi_app` o `app` que un servidor ASGI pueda importar. Flet 0.85.3 permite crearla conceptualmente así:

```python
asgi_app = ft.run(
    main,
    assets_dir="assets",
    export_asgi_app=True,
)
```

Después podría servirse, por ejemplo, con:

```powershell
env\Scripts\python.exe -m uvicorn app:asgi_app --host 0.0.0.0 --port 8000
```

Ese es el **comando web ASGI recomendado como objetivo**, no un comando operativo todavía: fallará mientras `app.py` no exporte `asgi_app`, y no debe añadirse antes de resolver el aislamiento de sesión y OAuth.

## 6. Dependencias y compatibilidad

### 6.1 Dependencias directas

```text
flet==0.85.3
supabase==2.31.0
python-dotenv==1.2.2
```

Las versiones instaladas coinciden con el baseline del proyecto. `flet-web`, `fastapi` y `uvicorn` están presentes en el entorno auditado, pero no todos están declarados directamente en `requirements.txt`. Depender de paquetes transitivos hace menos reproducible un despliegue Linux/ASGI.

### 6.2 Compatibilidad Flet 0.85.3 validada

Se comprobó en la instalación real:

- `ft.run()` existe.
- `ft.run(..., export_asgi_app=True)` está soportado y devuelve una aplicación FastAPI.
- `page.session`, `page.launch_url()` y `page.run_thread()` existen.
- Los controles importan y se construyen en las pruebas existentes.

`page.window.width` y `page.window.height` están orientados a una ventana nativa. En web no aportan control del viewport y deben evitarse o protegerse por plataforma. La API se resuelve en la instancia de Page, aunque no aparece como atributo de clase en la introspección simple.

### 6.3 Linux y servidor web

El runtime principal usa módulos estándar portables y clientes HTTP de Supabase. No se encontraron lecturas/escrituras de archivos de negocio, rutas absolutas Windows ni dependencias `win32` en el código de ejecución.

Elementos no adecuados para servidor:

- `webbrowser.open()` intenta abrir un navegador en la máquina del servidor.
- `HTTPServer(("127.0.0.1", 8765), ...)` crea un listener adicional por intento.
- Threads manuales y una cola estática complican el lifecycle y la concurrencia.
- `scripts/build_android_checkin.ps1` es exclusivo de Windows, pero no participa en runtime.
- `.env` se lee desde el directorio de trabajo; en producción conviene inyección de variables del entorno/plataforma.

No hay escritura local de usuarios o uploads. Los únicos artefactos locales observados son assets, documentación, scripts y logs de build Android.

## 7. Análisis de sesiones

### 7.1 Aislamiento Flet

Cada conexión a `main(page)` recibe un `Page`. El estado cerrado dentro de `build_home_view()` se crea por página. `page.session.store` también está asociado a la sesión Flet. Esta parte es compatible con sesiones independientes mientras no se introduzcan objetos globales mutables.

### 7.2 Ruptura por cliente Supabase global

`db.get_supabase_client()` devuelve siempre el mismo objeto. `exchange_code_for_session()`, `get_current_user()` y `sign_out()` actúan sobre él. Consecuencias:

1. Usuario A inicia sesión y el cliente guarda sus tokens.
2. Usuario B inicia sesión y sobrescribe la sesión Auth del mismo cliente.
3. Una acción posterior de A puede ejecutarse con la identidad de B.
4. El logout de cualquier usuario invalida/borra la sesión compartida.
5. Si se activa Realtime sobre el mismo cliente, canales y JWT también quedarían mezclados.

Este riesgo existe incluso con un solo worker. Varios workers no lo solucionan: solo crean grupos de usuarios que comparten un cliente por proceso.

### 7.3 Tokens

No se encontraron tokens impresos ni guardados explícitamente en archivos, globals o `page.session.store`. Los tokens quedan dentro del objeto Auth de `supabase-py`. Eso reduce exposición accidental, pero el objeto global vuelve inseguro su alcance.

Para web debe existir un cliente Supabase por sesión de usuario o un diseño explícito stateless que aplique el JWT de cada sesión en cada operación. Los refresh tokens deben persistirse con una estrategia segura, nunca en logs ni en un diccionario global. Si se usan cookies, deben ser `Secure`, `HttpOnly` y con `SameSite` apropiado, y el callback debe validar `state`/PKCE según lo provisto por Supabase.

### 7.4 Recarga, pestañas y desconexión

- Una recarga o nueva pestaña no restaura el contexto operativo.
- Dos pestañas tienen stores Flet distintos, pero comparten Auth global.
- No hay sincronización de logout entre pestañas.
- No hay manejo explícito de expiración/refresco de sesión.
- No hay callback de desconexión que cierre potenciales suscripciones Realtime.

## 8. Análisis de autenticación

### 8.1 Flujo actual

1. `get_oauth_url()` pide a Supabase una URL Google OAuth.
2. Escritorio usa `webbrowser.open()`.
3. Android usa `page.launch_url()` con deep link `eventplusbeta://auth-callback`.
4. Escritorio inicia un `HTTPServer` en `127.0.0.1:8765`.
5. El callback coloca `code/error` en una cola estática.
6. `exchange_code_for_session({"auth_code": code})` establece la sesión en el cliente global.
7. Se consulta el usuario Auth y se construye su contexto EventPlus.
8. Se guarda contexto en `page.session.store` y se monta Home.

El uso de `{"auth_code": code}` es compatible con Supabase 2.31.0 según el propio baseline del proyecto.

### 8.2 Problemas web

- `SUPABASE_OAUTH_REDIRECT_URL` por defecto es `http://localhost:8765/auth/callback`, no una URL HTTPS pública.
- En producción, Google/Supabase redirigirían al `localhost` del usuario.
- El callback no es una ruta del ASGI/Flet principal.
- Todos los intentos compiten por el mismo puerto 8765.
- `OAuthCallbackHandler.result_queue` es compartida: un callback puede entregarse al flujo equivocado.
- No hay correlación visible entre intento, Page y callback más allá de lo que pueda manejar internamente Supabase.
- `webbrowser.open()` es incorrecto en un servidor remoto.
- No existe navegación web post-login basada en URL.

### 8.3 Diseño requerido

- Callback público HTTPS, por ejemplo `https://app.example.com/auth/callback`, registrado en Supabase.
- El navegador cliente debe navegar a la URL OAuth; el servidor no debe abrir su propio navegador.
- Ruta ASGI de callback o flujo compatible con las rutas de Flet que asocie de manera segura el `code` con la sesión original.
- Cliente Supabase por sesión.
- Restauración/refresco de sesión.
- Logout de la sesión concreta y limpieza de contexto.
- Pruebas con dos navegadores, dos pestañas, callback cancelado, callback duplicado y expiración.

## 9. Uso de WebSockets y Realtime

Flet dinámico usa una conexión persistente entre navegador y servidor (normalmente WebSocket), por lo que el proxy/reverse proxy debe permitir upgrades WebSocket, timeouts largos y afinidad si el backend de Flet la requiere.

Supabase Realtime está descrito en la documentación y la tabla de invitados aparece preparada, pero no se encontró código que cree canales, se suscriba o desuscriba. Por tanto:

- No existe actualización automática entre operadores hoy.
- No hay riesgo actual de fuga por canales, pero debe diseñarse con filtros por cuenta/evento.
- Cada sesión deberá tener su propio canal/JWT.
- Toda suscripción debe cerrarse al cambiar evento, hacer logout o desconectarse.
- RLS y políticas Realtime deben estar activas antes de confiar en filtros del cliente.

## 10. Análisis responsive

### Fortalezas

- `page.adaptive = True`.
- `SafeArea` en login y shell.
- `ResponsiveRow` con breakpoints `xs`, `sm`, `md`, `lg` y `xl`.
- `ListView(expand=True)` para contenido largo.
- Barra de navegación inferior apropiada para móvil.
- Tarjetas y formularios pasan a una columna en anchos pequeños.
- Textos importantes usan ellipsis.

### Riesgos y pruebas pendientes

- Login fija `width=460`; debe comprobarse overflow en viewport menor que 460 px más padding.
- `page.window.width/height` no tiene sentido operativo en navegador.
- El header coloca logo, evento y usuario en varias filas en móvil; puede ocupar demasiado alto.
- Filas de botones y diálogos pueden desbordarse con textos largos o accesibilidad/font scaling.
- No se encontraron handlers de resize ni pruebas visuales automatizadas.
- Deben probarse 320, 360, 390, 768, 1024 y 1440 px, orientación vertical/horizontal, teclado móvil y zoom 200%.
- Deben probarse touch targets, scroll anidado y mantenimiento del foco después de re-render completo.

## 11. Análisis de seguridad

### 11.1 Claves y secretos

- `.env` está ignorado por Git.
- `app_public_config.py` está ignorado por Git.
- No se encontró `SUPABASE_SERVICE_ROLE_KEY`, `service_role`, bearer token ni secreto real versionado.
- Solo se usa `SUPABASE_PUBLISHABLE_KEY`, que es apropiada para cliente público **si y solo si RLS protege todas las tablas y operaciones**.
- La auditoría no reveló ni copió valores de `.env`.

### 11.2 RLS

Los documentos `EVENTPLUS_CONTEXT.md` y `EVENTPLUS_SCHEMA_CONTEXT_v1_1.md` indican explícitamente que RLS no está activado. Para una aplicación accesible por Internet, esto es crítico. Los roles y filtros Python no impiden que alguien use la publishable key y su JWT para llamar directamente a la API REST de Supabase.

Debe verificarse y activar RLS en todas las tablas expuestas, como mínimo:

- usuarios;
- cuentas y relaciones usuario-cuenta;
- eventos y relaciones usuario-evento;
- invitados;
- invitaciones;
- mesas y entidades relacionadas;
- cualquier tabla publicada a Realtime.

Las políticas deben derivar acceso desde `auth.uid()` y las relaciones internas, no desde IDs enviados por la interfaz.

### 11.3 Autorización

Los servicios realizan buenas defensas locales:

- verifican rol;
- verifican evento activo;
- comparan claves de cuenta/evento del registro;
- reconsultan fase/estado antes de operaciones;
- filtran updates por clave compuesta.

Estas defensas son útiles para UX y defensa en profundidad, pero no sustituyen autorización en la base. Un contexto es un diccionario mutable en memoria y no debe considerarse una credencial.

### 11.4 Aislamiento entre cuentas/eventos

Las consultas auditadas suelen incluir `cuenta_id` y `evento_id`, lo que reduce errores accidentales. Persisten riesgos:

- ausencia de RLS;
- cliente Auth compartido;
- contextos mutables;
- políticas no verificadas desde el repositorio;
- potencial falta de atomicidad en confirmación grupal.

### 11.5 Logs y errores

No se encontraron tokens impresos. Sí se imprimen:

- IDs de cuenta/evento;
- IDs/cantidades de invitados;
- mensajes de excepciones Supabase;
- tracebacks completos durante login;
- diagnóstico de usuario Auth (ID y email) en la UI/prototipo.

En producción deben usarse logs estructurados con redacción. Los mensajes de excepciones de proveedores pueden contener datos sensibles. `diagnostico_login` guarda traceback en el store de sesión y el prototipo muestra email/UUID; esto debe deshabilitarse o limitarse fuera de desarrollo.

## 12. Riesgos clasificados

### Críticos

1. **Cliente Supabase autenticado global compartido entre sesiones.**
   - Impacto: suplantación o mezcla de identidades y logout cruzado.
2. **RLS documentada como desactivada.**
   - Impacto: acceso directo a datos entre cuentas/eventos con la API pública.

### Altos

1. **OAuth basado en callback localhost, puerto y cola globales.**
   - Impacto: login no funcional en Internet y callbacks cruzados/concurrentes.
2. **No existe recuperación/aislamiento persistente de tokens por sesión.**
   - Impacto: recargas fallidas, pestañas inconsistentes y expiración no controlada.
3. **Autorización crítica principalmente en Python/UI.**
   - Impacto: bypass llamando directamente a Supabase.
4. **No hay ruta ASGI exportada ni estrategia de workers/WebSocket.**
   - Impacto: despliegue no reproducible y fallos de conexión.
5. **Diagnósticos y tracebacks demasiado detallados para producción.**
   - Impacto: exposición de PII o detalles internos.

### Medios

1. Navegación sin rutas URL ni guards.
2. Multi-pestaña y logout sincronizado no implementados.
3. Dependencias ASGI no declaradas directamente.
4. Realtime todavía no implementado.
5. Confirmaciones grupales aparentemente compuestas por varias operaciones, sin evidencia de transacción atómica.
6. Hilos manuales y re-render de página completa requieren pruebas de concurrencia/desconexión.
7. Prototipo OAuth duplicado puede confundirse con código productivo.
8. Falta una suite de integración contra un entorno Supabase de pruebas.

### Bajos

1. Dimensiones `page.window` específicas de escritorio.
2. Ancho fijo del login y posibles overflows móviles.
3. Logs de IDs y cantidades demasiado verbosos.
4. Scripts de prueba no integrados a un runner estándar.
5. `EVENTPLUS_MODE` se decide globalmente al importar, impidiendo servir FULL y CHECKIN desde el mismo proceso sin separar módulos/apps.

## 13. Pruebas existentes

| Script | Cobertura principal |
|---|---|
| `scripts/verify_environment.py` | Python exacto, versiones instaladas, imports y APIs Flet básicas. |
| `scripts/smoke_imports.py` | Importación de módulos y construcción de controles. |
| `scripts/test_session_initialization.py` | Contexto con cero/uno/varios eventos y errores controlados. |
| `scripts/test_event_selection.py` | Selección y sincronización de evento. |
| `scripts/test_guest_readonly.py` | Consulta, filtros, búsqueda, paginación y UI de solo lectura. |
| `scripts/test_guest_write.py` | Creación/edición planificada, autorización, validación y duplicados. |
| `scripts/test_guest_arrival_operations.py` | Llegadas, reversión e invitados imprevistos. |
| `scripts/test_arrivals_by_invitation.py` | Flujo grupal por invitación. |

Son pruebas valiosas con dobles locales. Faltan pruebas de:

- dos sesiones simultáneas;
- OAuth web real;
- recuperación/refresh de sesión;
- logout entre pestañas;
- RLS/políticas con usuarios de cuentas distintas;
- ASGI y WebSocket detrás de proxy;
- responsive visual;
- Realtime y limpieza de suscripciones.

## 14. Plan incremental propuesto

### Tarea 1. Aislar el cliente Supabase por sesión Flet

**Objetivo:** eliminar el singleton autenticado y hacer explícita la dependencia de un cliente por `Page`/sesión.

**Archivos probables:** `db.py`, `services/auth_service.py`, `views/login_view.py`, `views/home_view.py`, servicios que hoy llaman `get_supabase_client()`, y nuevos tests bajo `scripts/`.

**Criterios de aceptación:**

- Dos páginas simuladas reciben instancias diferentes de `supabase.Client`.
- Login/logout de una no cambia `auth.get_session()` de la otra.
- Ningún cliente autenticado queda en un global, caché de módulo o clase estática.
- Todos los servicios reciben explícitamente el cliente de la sesión o un contexto tipado equivalente.
- Las funciones actuales de invitados/eventos siguen pasando.

**Regresión:** ejecutar todos los scripts existentes, `pip check`, compilación y smoke controlado.

### Tarea 2. Añadir pruebas de concurrencia y aislamiento

**Objetivo:** fijar contractualmente el comportamiento multiusuario antes de tocar OAuth.

**Archivos probables:** nuevos `scripts/test_multi_session_isolation.py` y utilidades de dobles.

**Criterios de aceptación:**

- Dos sesiones con usuarios/cuentas distintos no comparten cliente, contexto ni tokens.
- Logout A no altera B.
- Cambiar evento en A no altera B.
- Una operación con registro de otro evento se rechaza.

**Regresión:** suite existente completa.

### Tarea 3. Diseñar callback OAuth web sobre HTTPS/ASGI

**Objetivo:** sustituir `HTTPServer`, cola global y `webbrowser.open()` en modo web por un callback público asociado a sesión.

**Archivos probables:** `services/auth_service.py`, `views/login_view.py`, `config.py`, nuevo módulo ASGI/rutas y documentación de entorno.

**Criterios de aceptación:**

- Redirect URL configurable como HTTPS pública.
- No se abre navegador en el servidor.
- Dos logins simultáneos reciben su propio callback.
- Callback cancelado/duplicado/expirado se maneja sin filtrar datos.
- Escritorio y Android conservan su flujo mediante adaptadores separados.

**Regresión:** login escritorio controlado, deep link Android simulado y flujos funcionales existentes.

### Tarea 4. Recuperación, refresco y logout de sesión

**Objetivo:** definir ciclo de vida completo de Auth por sesión/pestaña.

**Archivos probables:** `services/auth_service.py`, `views/login_view.py`, módulo de sesión y tests.

**Criterios de aceptación:**

- Recarga restaura una sesión válida según estrategia aprobada.
- Token expirado se refresca o conduce a login seguro.
- Logout elimina tokens/contexto solo de la sesión correspondiente.
- Cookies/almacenamiento no exponen refresh tokens a JavaScript si se adopta backend session.

**Regresión:** navegación y operaciones después de sesión restaurada.

### Tarea 5. Implementar y probar RLS antes de Internet

**Objetivo:** mover la autoridad real a Supabase.

**Archivos probables:** migraciones SQL nuevas (no existen actualmente en el repo), documentación y pruebas de integración.

**Criterios de aceptación:**

- RLS activa en todas las tablas expuestas.
- Usuario de cuenta A no puede leer/escribir cuenta B usando REST directo.
- Operador no puede realizar acciones de Administrador/Master.
- Policies usan `auth.uid()` y relaciones activas.
- Realtime respeta las mismas políticas.

**Regresión:** casos positivos de cada rol y función vigente.

### Tarea 6. Exportar la aplicación ASGI

**Objetivo:** publicar una factoría/variable ASGI sin cambiar la entrada local actual.

**Archivos probables:** `app.py` o nuevo `asgi.py`, `requirements.txt`, configuración de despliegue.

**Criterios de aceptación:**

- `uvicorn ...` inicia sin ejecutar una ventana desktop.
- `/` carga assets y establece WebSocket.
- Health check separado no crea una sesión Flet innecesaria.
- Apagado limpia recursos.
- Entrada desktop sigue funcionando.

**Regresión:** arranque desktop, CLI web y ASGI.

### Tarea 7. Rutas y navegación web

**Objetivo:** soportar login/callback/home, recargas y guards coherentes.

**Archivos probables:** `app.py`, `views/login_view.py`, `views/home_view.py`, nuevo router.

**Criterios de aceptación:**

- Recargar Dashboard no deja pantalla vacía.
- Usuario no autenticado vuelve a login.
- Callback navega al destino correcto.
- Back/forward no rompe el estado.

**Regresión:** navegación inferior y selección de evento.

### Tarea 8. Hardening de logs y errores

**Objetivo:** retirar PII, tracebacks y detalles del proveedor de la UI/producción.

**Archivos probables:** `views/login_view.py`, servicios y configuración de logging.

**Criterios de aceptación:**

- Ningún log contiene tokens, códigos OAuth, email completo o payload sensible.
- Usuario recibe mensaje corto con ID de correlación.
- Tracebacks quedan solo en logging protegido de servidor.

**Regresión:** errores controlados siguen siendo accionables.

### Tarea 9. Validación responsive

**Objetivo:** asegurar usabilidad real en móvil y escritorio.

**Archivos probables:** vistas/componentes; pruebas visuales.

**Criterios de aceptación:**

- Sin overflow a 320/360/390 px.
- Login, formularios, diálogos y navegación utilizables con touch.
- Zoom 200% y teclado móvil no ocultan acciones críticas.
- Desktop conserva densidad y legibilidad.

**Regresión:** smoke de construcción y capturas comparativas.

### Tarea 10. Realtime por evento

**Objetivo:** actualizar llegadas entre operadores conectados.

**Archivos probables:** nuevo servicio Realtime, `views/home_view.py`, tests.

**Criterios de aceptación:**

- Suscripción filtrada al evento autorizado.
- Cambio de evento y logout cancelan la suscripción anterior.
- Dos operadores ven la llegada sin recarga.
- Reconexión no duplica eventos.

**Regresión:** búsquedas, paginación y operaciones manuales siguen funcionando.

### Tarea 11. Empaquetado y despliegue Linux

**Objetivo:** definir build reproducible, reverse proxy, variables y observabilidad.

**Archivos probables:** `requirements.txt`, manifiesto/contenedor, documentación y CI.

**Criterios de aceptación:**

- Instalación limpia con Python 3.14.6.
- `pip check`, compilación y suite completa pasan.
- WebSocket funciona detrás de HTTPS.
- Secrets se inyectan, no se empaquetan.
- Reinicio/escala no mezcla sesiones.

**Regresión:** arranque local FULL/CHECKIN y ASGI.

## 15. Primera modificación recomendada

La primera modificación debe ser **eliminar el cliente Supabase autenticado global y establecer un cliente aislado por sesión Flet**.

No se recomienda empezar exportando ASGI: hacerlo haría accesible una aplicación cuyo estado Auth se comparte entre usuarios. El aislamiento es una precondición de seguridad y también simplifica el rediseño posterior del callback OAuth.

### Contenido preciso de la primera tarea

1. Reemplazar el `@lru_cache(maxsize=1)` de `db.py` por una factoría que cree clientes independientes.
2. Crear un contenedor/contexto de sesión que pertenezca a una sola `Page`.
3. Crear el cliente cuando se inicializa esa página.
4. Inyectar ese cliente en Auth, usuario, evento e invitado; no recuperarlo desde globals.
5. Mantener el contexto operativo en el store Flet, pero no almacenar ahí un objeto cliente no serializable.
6. Hacer logout únicamente sobre el cliente de esa Page.
7. Añadir una prueba específica con dos sesiones/clientes y usuarios distintos.
8. Mantener compatibilidad funcional con FULL y CHECKIN.

### Criterios de aceptación de la primera tarea

- No existe un `supabase.Client` autenticado en scope global ni cacheado.
- Cada invocación de `main(page)` obtiene un cliente exclusivo.
- Dos sesiones concurrentes mantienen usuarios y tokens diferentes.
- Logout de A no cambia la sesión de B.
- Todos los accesos a Supabase usan el cliente inyectado de la sesión.
- Contexto, evento seleccionado y estado UI siguen aislados.
- Pasan `scripts/verify_environment.py`, todos los `scripts/test_*.py`, `scripts/smoke_imports.py`, `pip check`, compilación y una prueba controlada FULL/CHECKIN.
- No se cambia todavía el flujo OAuth, las URLs, RLS ni el comportamiento funcional visible salvo lo indispensable para inyección de dependencias.

## 16. Conclusión

EventPlus no necesita reconstruirse. La separación entre vistas, componentes y servicios permite una migración incremental. La interfaz y la lógica funcional existente pueden conservarse. El orden seguro es: aislamiento de cliente/sesión, pruebas concurrentes, OAuth web, recuperación/logout, RLS, exportación ASGI, rutas, hardening, responsive y Realtime.

La aplicación puede probarse hoy en navegador local con el CLI de Flet, pero **no está lista para exponerse a Internet** hasta resolver los dos riesgos críticos: cliente Supabase global y ausencia de RLS.

## Resultado de la Tarea 1 — Aislamiento del cliente Supabase

**Fecha:** 25 de julio de 2026.

### Archivos modificados

- `app.py`
- `app_publishable_key_v4.py`
- `db.py`
- `services/auth_service.py`
- `services/evento_service.py`
- `services/invitado_service.py`
- `services/usuario_service.py`
- `views/login_view.py`
- `views/home_view.py`
- `scripts/test_session_initialization.py`
- `DIAGNOSTICO_WEB_EVENTPLUS.md`

### Archivo creado

- `scripts/test_multi_session_isolation.py`

### Arquitectura adoptada

`db.py` expone `create_supabase_client()` como factoría sin caché. Cada invocación de `main(page)` crea exactamente una instancia nueva de `supabase.Client`. Esa instancia pertenece a la Page y acompaña su ciclo de vida mediante closures e inyección explícita por parámetros.

La función `get_supabase_client()` se conserva únicamente como factoría de compatibilidad: no usa caché, no guarda referencias y devuelve una instancia nueva en cada llamada. Ningún servicio productivo la importa o utiliza.

El cliente no se guarda en `page.session.store`. El store conserva solamente contexto y datos serializables de la sesión. Auth, usuario, eventos, invitados, Home y logout reciben el cliente de la Page actual.

El prototipo `app_publishable_key_v4.py` también crea su cliente dentro de `main(page)` para que no quede un cliente autenticable global, sin alterar su callback ni su flujo OAuth.

### Mecanismo de inyección

- `app.main(page)` crea el cliente.
- `build_login_view(page, supabase)` lo captura durante login.
- Las funciones de `auth_service` reciben `supabase` explícitamente.
- `usuario_service` recibe y propaga el cliente a todas sus consultas auxiliares.
- `build_home_view(..., supabase)` conserva el mismo cliente en sus closures.
- `evento_service` e `invitado_service` requieren el cliente inyectado antes de acceder a datos.
- Logout ejecuta `sign_out()` solo en el cliente recibido por la Page actual.

### Prueba de aislamiento creada

`scripts/test_multi_session_isolation.py` valida con dobles, sin login real:

- un cliente distinto por cada Page;
- exactamente una creación por ejecución de `main(page)`;
- identidades y tokens simulados independientes;
- logout aislado;
- contextos de cuenta/evento independientes;
- uso del cliente correcto por `usuario_service`;
- factoría sin caché;
- ausencia de clientes autenticados globales en los módulos auditados.

### Validaciones ejecutadas y resultados

| Validación | Resultado |
|---|---|
| `env\Scripts\python.exe -m pip check` | OK — no hay dependencias rotas. |
| `env\Scripts\python.exe -m compileall app.py main_checkin.py config.py db.py services views components scripts` | OK. |
| `scripts/verify_environment.py` | OK — Python 3.14.6, Flet 0.85.3 y Supabase 2.31.0. |
| `scripts/smoke_imports.py` | OK — imports y construcción de controles. |
| `scripts/test_session_initialization.py` | OK. |
| `scripts/test_event_selection.py` | OK. |
| `scripts/test_guest_readonly.py` | OK. |
| `scripts/test_guest_write.py` | OK. |
| `scripts/test_guest_arrival_operations.py` | OK. |
| `scripts/test_arrivals_by_invitation.py` | OK. |
| `scripts/test_multi_session_isolation.py` | OK. |
| FULL escritorio: `env\Scripts\python.exe app.py` | OK — inicio controlado sin salida inmediata ni traceback. |
| CHECKIN escritorio: `env\Scripts\python.exe main_checkin.py` | OK — inicio controlado sin salida inmediata ni traceback. |
| FULL web: puerto 8550 | OK — servidor disponible en `http://127.0.0.1:8550`, detenido de forma controlada. |
| CHECKIN web: puerto 8551 | OK — servidor disponible en `http://127.0.0.1:8551`, detenido de forma controlada. |

### Resultado

No queda `@lru_cache` en la creación del cliente ni un `supabase.Client` autenticable global en las entradas o servicios de EventPlus. Cada Page obtiene una instancia independiente y logout actúa solamente sobre esa instancia. FULL, CHECKIN, escritorio y web local conservan su arranque y no se modificó el comportamiento visual.

### Limitaciones pendientes

- El callback OAuth local, `HTTPServer`, deep link Android y sus mecanismos de concurrencia no se cambiaron.
- No se implementó recuperación de sesión ni OAuth web.
- No se exportó ASGI.
- RLS continúa pendiente.
- Realtime continúa pendiente.
- La función de compatibilidad `get_supabase_client()` debe retirarse cuando no existan consumidores externos; actualmente siempre crea un cliente nuevo y no es usada por los servicios productivos.

## Resultado de la Tarea 2 — Separación del flujo OAuth web

**Fecha:** 25 de julio de 2026.

### Arquitectura aplicada

El login selecciona una de tres estrategias explícitas:

- **Web:** usa `Page.login()` y el callback OAuth integrado en el servidor de Flet 0.85.3.
- **Escritorio:** conserva temporalmente `webbrowser.open()`, `HTTPServer` local y la espera del callback en `127.0.0.1:8765`.
- **Android:** conserva el redirect `eventplusbeta://auth-callback`, abre el navegador mediante la API de Flet y procesa el deep link existente.

La estrategia web no invoca funciones de la estrategia desktop. No inicia un servidor adicional, no usa `webbrowser.open()`, no consulta `OAuthCallbackHandler.result_queue` y no bloquea un thread esperando el retorno.

### Detección de plataforma

`detect_oauth_strategy(page)` aplica este orden:

1. `page.platform` Android → estrategia Android.
2. `page.web is True` → estrategia web.
3. Cualquier otro caso → estrategia desktop.

El orden evita clasificar una aplicación Android como web por características incidentales del runtime.

### Flujo web

1. La Page crea `SupabaseWebOAuthProvider` con su cliente Supabase exclusivo.
2. `SupabaseWebAuthorization` genera un `state` criptográficamente aleatorio y una expiración.
3. El `state` se incorpora al `redirect_to` configurado.
4. `supabase.auth.sign_in_with_oauth()` genera la URL Google/Supabase y conserva el verificador PKCE dentro del cliente de esa Page.
5. `Page.login()` registra el state en el administrador OAuth de Flet, asociado al identificador interno de la sesión.
6. Flet abre la URL en el navegador cliente.
7. Supabase retorna a `/auth/callback`.
8. El handler HTTP integrado de Flet consume el state, recupera exclusivamente la Page original y entrega el code a su autorización.
9. `SupabaseWebAuthorization.request_token()` intercambia el code mediante el cliente Supabase de esa Page.
10. `page.on_login` continúa con `get_current_user()`, contexto EventPlus y Home.

Se verificó contra el código instalado de Flet 0.85.3 que el servidor dinámico ya incluye un endpoint OAuth, almacenamiento temporal de state, asociación a la sesión Flet, expiración y consumo de un solo uso. No fue necesario exportar ASGI ni crear una ruta HTTP paralela.

### Flujo desktop

El flujo desktop permanece encapsulado en `run_desktop_login_flow()` y conserva:

- `SUPABASE_OAUTH_REDIRECT_URL`;
- navegador del sistema;
- callback `http://localhost:8765/auth/callback`;
- `HTTPServer` local;
- intercambio mediante el cliente de la Page.

Este mecanismo no es utilizado cuando `page.web` es verdadero.

### Flujo Android

Android conserva:

- `eventplusbeta://auth-callback`;
- `page.on_route_change`;
- parseo del deep link;
- cliente Supabase aislado por Page.

La apertura de URL ahora espera correctamente la API asíncrona `page.launch_url()` de Flet 0.85.3. No se modificaron package ID, scheme, host ni configuración del proveedor.

### Correlación y protección del callback

La protección combina:

- state aleatorio de 256 bits aproximados generado con `secrets.token_urlsafe(32)`;
- validación defensiva del state en el adaptador de autorización;
- state interno de Flet asociado al identificador de sesión/Page;
- expiración configurable;
- consumo de un solo uso en Flet;
- marca `consumed` antes del intercambio Supabase;
- PKCE generado y conservado por el cliente `supabase-py` de esa Page.

Un state desconocido, cruzado, repetido o expirado no puede intercambiar un code con otro cliente. El endpoint real fue probado con un state inválido y respondió HTTP 400.

No se registran auth codes, access tokens o refresh tokens. Los mensajes de error web no muestran `error_description` del proveedor.

### Variables de entorno nuevas

```text
EVENTPLUS_WEB_OAUTH_REDIRECT_URL=http://127.0.0.1:8550/auth/callback
EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS=600
EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS=120
```

La primera define el callback local completo. La segunda controla la vida máxima del state de Flet y nunca puede ser menor de 30 segundos. La tercera controla cuánto espera la UI por un callback antes de expirar el intento y restaurar el login.

`config.py` deriva de la ruta configurada:

```text
FLET_OAUTH_CALLBACK_HANDLER_ENDPOINT=auth/callback
```

También alinea `FLET_OAUTH_STATE_TIMEOUT` con el TTL configurado. `SUPABASE_OAUTH_REDIRECT_URL` continúa reservado para escritorio.

### Prueba creada

`scripts/test_web_oauth_flow.py` valida con dobles:

- selección web/desktop/Android;
- ausencia de `HTTPServer`, `webbrowser.open()` y cola desktop en web;
- states diferentes para dos sesiones;
- aislamiento A/B;
- rechazo de state cruzado;
- rechazo de callback repetido, expirado o sin code;
- manejo controlado de error del proveedor;
- intercambio únicamente con el cliente de la Page correspondiente;
- construcción del contexto posterior;
- ausencia de codes/tokens en stdout y stderr.

`scripts/verify_environment.py` valida además la existencia en Flet 0.85.3 de `Page.web`, `Page.login`, `Page.on_login`, `LoginEvent` y el parámetro `authorization`.

### Validaciones

Todas las verificaciones obligatorias pasaron:

- `pip check`;
- `compileall`;
- `verify_environment.py`;
- `smoke_imports.py`;
- inicialización de sesión;
- selección de evento;
- invitados read-only;
- escritura de invitados;
- operaciones de llegada;
- llegadas por invitación;
- aislamiento multisesión;
- flujo OAuth web.

Los arranques FULL escritorio, CHECKIN escritorio, FULL web en 8550 y CHECKIN web en 8551 iniciaron sin traceback inmediato y fueron detenidos de forma controlada.

### Configuración manual requerida en Supabase

Para FULL web local:

1. Abrir Supabase Dashboard.
2. Ir a **Authentication → URL Configuration → Redirect URLs**.
3. Agregar para desarrollo local:

```text
http://127.0.0.1:8550/auth/callback**
```

El sufijo `**` se necesita en desarrollo porque el state de correlación viaja como query parameter dentro de `redirect_to`. No usar un wildcard amplio en producción.

4. Conservar:

```text
http://localhost:8765/auth/callback
eventplusbeta://auth-callback
```

5. En `.env`, agregar:

```text
EVENTPLUS_WEB_OAUTH_REDIRECT_URL=http://127.0.0.1:8550/auth/callback
```

6. Reiniciar EventPlus y ejecutar:

```powershell
env\Scripts\flet.exe run --web --host 127.0.0.1 --port 8550 app.py
```

7. Abrir `http://127.0.0.1:8550`, iniciar con Google y confirmar que vuelve a Home.

Para probar CHECKIN web en el puerto 8551, registrar también:

```text
http://127.0.0.1:8551/auth/callback**
```

y arrancar el proceso con:

```powershell
$env:EVENTPLUS_WEB_OAUTH_REDIRECT_URL="http://127.0.0.1:8551/auth/callback"
env\Scripts\flet.exe run --web --host 127.0.0.1 --port 8551 main_checkin.py
```

Google Cloud debe continuar usando como redirect autorizado el callback del proyecto Supabase:

```text
https://<project-ref>.supabase.co/auth/v1/callback
```

No se realizaron cambios automáticos en Supabase o Google Cloud.

### Limitaciones

- El cierre manual del popup no produce un evento en Flet ni en Google. La corrección de la Tarea 2 mantiene ahora un intento OAuth por `Page` y aplica un timeout controlado, sin intentar inspeccionar el popup mediante JavaScript o polling.
- Cada intento contiene un identificador aleatorio, fecha de creación, estado terminal atómico (`pending`, `completed`, `cancelled` o `expired`), referencia a su `Page`, autorización y tarea de timeout. No existe timer, cola ni estado global para el flujo web.
- `Page.run_task()` ejecuta el timeout no bloqueante en el bucle asociado a esa Page. La variable `EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS` permite configurarlo y su valor predeterminado es `120`.
- Mientras el intento está pendiente, la vista muestra “Esperando autenticación”, deshabilita el login, muestra progreso y ofrece **Cancelar**. Cancelar marca el intento como `cancelled`, invalida inmediatamente la autorización/state en la capa EventPlus, cancela la tarea y permite reintentar con un state nuevo.
- Al vencer el timeout, el intento pasa una sola vez a `expired`, se invalida su autorización, se restaura el login y se presenta un mensaje controlado. El state correlacionado que Flet mantiene internamente continúa sujeto a su expiración propia, pero ya no puede intercambiar un code en EventPlus.
- `SupabaseWebAuthorization.request_token()` exige ganar la transición atómica a `completed` antes de intercambiar el code. Un callback posterior a cancelación o expiración se rechaza antes de `exchange_code_for_session()`; un intento antiguo tampoco puede modificar un intento nuevo ni otra Page.
- Un callback válido cancela la tarea de timeout antes de continuar el login normal. Las carreras callback/timeout y callback/Cancelar admiten una sola transición terminal.
- Las pruebas con dobles añadidas a `scripts/test_web_oauth_flow.py` cubren UI pendiente, bloqueo de doble clic, cancelación, timeout, reintento con state nuevo, éxito único, callback tardío sin intercambio, aislamiento de dos Pages, carrera concurrente y ausencia de credenciales en logs.

- La correlación integrada de Flet 0.85.3 reside en memoria del proceso. Esta implementación es adecuada para desarrollo web local con un proceso; una futura topología multiworker deberá definir afinidad o un almacén de state compartido.
- La sesión Supabase todavía no se recupera después de reiniciar el proceso.
- No se sincroniza logout entre pestañas.
- El callback público HTTPS, reverse proxy y cookies endurecidas pertenecen al despliegue posterior.
- Desktop conserva temporalmente su cola global y servidor local, encapsulados fuera de web.
- Flet rechaza antes del intercambio un callback que tenga state válido pero no incluya ni `code` ni `error`; en ese caso anómalo el endpoint puede mostrar una respuesta HTTP de error en vez de un mensaje dentro de EventPlus. Los errores normales del proveedor, incluida cancelación, sí llegan como mensajes controlados a la Page.
- RLS continúa pendiente y sigue siendo obligatoria antes de exposición pública.

### Siguiente tarea recomendada

Antes de despliegue público, definir el ciclo de vida de sesión web —recuperación, refresh, expiración y logout— y después integrar la aplicación en la topología ASGI/HTTPS definitiva con una estrategia explícita para state y sesiones en múltiples workers. No se implementó ninguna de esas tareas en este incremento.

## Resultado de la Tarea 3 — Ciclo de vida y recuperación de sesión web

**Fecha:** 26 de julio de 2026.

### Comportamiento anterior

Cada `Page` ya recibía un cliente Supabase exclusivo, pero la aplicación no tenía un controlador explícito para coordinar sesión, refresh, contexto, logout y tareas tardías. Después del OAuth se consultaba directamente el usuario y se construía Home. El logout limpiaba el contexto y llamaba `sign_out()`, pero no coordinaba tareas de refresh ni intentos OAuth.

No existía restauración segura entre una nueva Page y otra. Los tokens permanecían solamente en la memoria interna del cliente `supabase-py` de la Page.

### Auditoría de Flet 0.85.3

La inspección del código instalado confirmó:

- Flet conserva una `Session` y su `Page` en memoria después de una desconexión durante `FLET_SESSION_TIMEOUT`; el valor predeterminado es 3600 segundos.
- El cliente puede solicitar reconexión enviando el identificador de sesión Flet. Si la sesión sigue en memoria y no tiene otra conexión, Flet adjunta el nuevo WebSocket a la misma Page.
- Existen `page.on_disconnect`, `page.on_connect` y `page.on_close`.
- `on_disconnect` no destruye inmediatamente la Page; `on_close` ocurre cuando Flet elimina la sesión expirada.
- La entrada dinámica actual no recibe objetos FastAPI `Request`/`Response` ni ofrece una API general para emitir una cookie de sesión propia.
- Flet usa una cookie `flet_oauth_state` HttpOnly, SameSite Strict y temporal solamente para una variante de retorno OAuth. En 0.85.3 aparece con `Secure=False` y no representa una sesión EventPlus ni puede reutilizarse para persistir Supabase Auth.
- El identificador de sesión Flet no es una cookie de autenticación EventPlus y no sustituye una cookie opaca, HttpOnly y Secure respaldada por un repositorio server-side.

Por estas limitaciones no se guardaron access tokens ni refresh tokens en almacenamiento accesible al navegador y no se simuló persistencia entre Pages.

### Arquitectura implementada

`services/session_service.py` incorpora `PageSessionController`. Cada instancia pertenece a exactamente una Page y contiene:

- el cliente Supabase exclusivo de esa Page;
- usuario Auth y contexto EventPlus actuales;
- estado autenticado, conectado y cerrado;
- lock exclusivo de refresh;
- generación de sesión para invalidar resultados tardíos;
- reclamación única de Home por generación;
- tareas de monitorización pertenecientes a la Page;
- referencia al intento OAuth pendiente;
- limpieza coordinada.

No existe controlador autenticado global.

La interfaz `SessionRepository` deja preparado el límite futuro para crear, restaurar y eliminar sesiones server-side mediante identificadores opacos. No se implementó un repositorio en memoria porque la entrada dinámica actual no puede entregar de forma segura el identificador mediante una cookie HttpOnly propia. Tampoco se añadieron Redis, archivos o tablas.

### Validación previa a Home

Antes de reclamar Home se verifica:

1. `supabase.auth.get_session()` devuelve una sesión válida.
2. `supabase.auth.get_user()` devuelve un usuario Auth identificable.
3. `cargar_contexto_usuario()` acepta el usuario.
4. `usr_usuario_auth_uuid` coincide con Auth.
5. El usuario EventPlus está activo.
6. Existen cuentas permitidas y la cuenta actual pertenece a ellas.
7. Si hay evento actual, pertenece a los eventos permitidos.
8. La generación no cambió por logout mientras se realizaban consultas.

Una sola operación puede reclamar la construcción de Home. Esto evita dos Homes si restauración y callback OAuth coinciden.

### Manejo de refresh

En `supabase-py` 2.31.0, `auth.get_session()` comprueba la expiración y llama internamente al refresh usando el refresh token guardado en el propio cliente cuando la sesión está vencida o próxima a vencer.

EventPlus ejecuta esa operación bajo un lock por Page. Dos comprobaciones simultáneas de la misma Page producen como máximo un refresh efectivo: la segunda observa la sesión ya renovada. Dos Pages usan locks y clientes diferentes.

Después del login se inicia mediante `Page.run_task()` una comprobación periódica no bloqueante. Durante desconexión queda pausada lógicamente; al reconectar, `on_connect` vuelve a validar la misma sesión retenida por Flet.

Si refresh o validación Auth falla:

- se invalida el estado autenticado de esa Page;
- se elimina el contexto del store;
- se ejecuta logout controlado;
- se cancela la monitorización;
- se reconstruye Login con el mensaje “Tu sesión venció o dejó de ser válida. Inicia sesión nuevamente.”;
- una tarea tardía no puede reclamar Home porque su generación ya no coincide.

No se imprimen tokens.

### Manejo de logout y cierre

Logout:

- incrementa la generación antes de esperar operaciones de red;
- marca la Page como no autenticada;
- limpia usuario y contexto;
- elimina `usuario_contexto`, eventos y diagnóstico del store;
- cancela las tareas registradas;
- cancela e invalida el intento OAuth pendiente;
- ejecuta `sign_out()` solamente sobre el cliente de esa Page;
- reconstruye Login.

`on_close` cancela tareas y limpia estado local sin compartir datos con otras Pages. `on_disconnect` no destruye la sesión, porque Flet puede reconectarla durante su ventana server-side.

### Almacenamiento utilizado

- Tokens Supabase: únicamente dentro del cliente `supabase-py` de la Page, en memoria del proceso.
- Contexto EventPlus: `page.session.store`, sin access token ni refresh token.
- Navegador: no se escriben tokens en localStorage, sessionStorage, client storage, shared preferences, controles, URLs ni cookies propias.
- Archivos y logs: no se escriben tokens.
- Globals: no existen clientes, tokens ni controladores autenticados globales.

### Comportamiento ante recarga y nuevas Pages

| Escenario | Resultado diseñado | Evidencia |
|---|---|---|
| Corte temporal y reconexión de la misma sesión Flet | Conserva la Page/client en memoria dentro del timeout; `on_connect` revalida Auth | API/código instalado de Flet; lógica automatizada del controlador. Requiere prueba manual de navegador. |
| F5 que Flet reconecte a la misma Session | Puede conservar Home y revalidar | Depende del identificador que envíe el cliente Flet; no se afirma como prueba manual completada. |
| F5 que cree una Page nueva | Vuelve a Login | No hay persistencia insegura de tokens. |
| Pestaña nueva | Vuelve a Login si crea otra Page | No hay restauración entre Pages. |
| Duplicar pestaña | Comportamiento del identificador cliente debe comprobarse manualmente; no se comparte identidad mediante EventPlus | No probado manualmente. |
| Cerrar y reabrir pestaña | Normalmente nueva Page y Login | No hay cookie EventPlus. |
| Reiniciar navegador | Login | No hay persistencia de Auth en navegador. |
| Reiniciar servidor | Login | Cliente y sesión Flet estaban en memoria del proceso. |
| Access token vencido dentro de Page activa | Refresh serializado mediante el cliente de esa Page | Prueba automatizada. |
| Refresh token inválido/revocado | Limpieza y retorno controlado a Login | Prueba automatizada. |

### Pruebas automatizadas

`scripts/test_web_session_lifecycle.py` usa dobles y valida:

- sesión válida y sesión ausente;
- ausencia de refresh innecesario;
- refresh válido de sesión vencida;
- refresh inválido y limpieza;
- refresh concurrente único;
- refresh aislado en dos Pages;
- logout aislado;
- resultado tardío después de logout;
- reclamación única de Home;
- rechazo de contexto cruzado;
- rechazo de usuario inactivo;
- ausencia de tokens en client storage, store y logs;
- cancelación de tareas en logout y cierre;
- imposibilidad de restaurar A dentro de B sin sesión propia.

Son pruebas automatizadas; no equivalen a OAuth real, F5 real ni dos navegadores reales.

### Pruebas manuales pendientes

Para FULL web deben ejecutarse y registrar por separado:

1. Login normal real.
2. F5 y confirmación de si Flet reconecta la misma Session.
3. Duplicar pestaña.
4. Abrir una pestaña nueva.
5. Cerrar y reabrir pestaña.
6. Logout y F5.
7. Dos navegadores con usuarios distintos.
8. Logout A mientras B permanece activo.
9. Invalidar/revocar refresh token real.
10. Cortar y recuperar temporalmente la conexión.

No se afirma que estos casos manuales hayan pasado en esta tarea.

### Necesidad de ASGI

La persistencia segura entre una nueva Page, reinicio del navegador o reinicio del proceso requiere la siguiente tarea de arquitectura ASGI:

- acceso controlado a request/response;
- cookie con identificador opaco, HttpOnly, Secure y SameSite apropiado;
- rotación y protección contra fijación;
- repositorio server-side con expiración y eliminación por logout;
- estrategia multiworker;
- protección CSRF según rutas y SameSite;
- ningún token Supabase expuesto al navegador.

La memoria del proceso no se presentará como solución productiva.

### Corrección posterior a las pruebas manuales

Las pruebas manuales de la Tarea 3 detectaron dos defectos:

1. `supabase.auth.sign_out()` sin opciones usa scope `global` en supabase-py 2.31.0. Logout en una Page podía revocar los refresh tokens de otras Pages del mismo usuario.
2. En determinadas condiciones del navegador, un exchange OAuth podía establecer una sesión Supabase aunque EventPlus ya hubiera cancelado o expirado el intento, dejando una sesión residual para el siguiente login.

#### Logout local

El logout normal usa ahora exactamente:

```python
supabase.auth.sign_out({"scope": "local"})
```

Esto revoca el refresh token de la sesión actual y elimina la sesión almacenada en el cliente de esa Page, sin revocar las demás sesiones del mismo usuario.

`sign_out_global_session()` y `PageSessionController.logout_global()` quedan como funciones internas separadas para una futura operación administrativa, sin opción visual actual. Utilizan:

```python
supabase.auth.sign_out({"scope": "global"})
```

El logout global revoca todos los refresh tokens del usuario. En ambos scopes, los access tokens JWT ya emitidos no pueden revocarse individualmente mediante esta API y siguen siendo técnicamente válidos hasta su expiración; por eso su duración debe mantenerse limitada y la autorización de datos seguirá dependiendo de RLS en la tarea correspondiente.

#### Selección explícita de cuenta Google

El flujo OAuth web agrega a `sign_in_with_oauth()`:

```python
"query_params": {"prompt": "select_account"}
```

Supabase incorpora `prompt=select_account` a la autorización Google. No se utiliza `prompt=consent`. La opción se aplica únicamente al adaptador web; los flujos desktop y Android conservan su construcción anterior.

#### Sesión residual y carrera callback/timeout

El intento permanece en estado `pending` mientras `exchange_code_for_session()` se ejecuta y registra internamente que el exchange ya comenzó. Solo un callback puede iniciar el intercambio.

Al finalizar:

- si el intento todavía está pendiente, gana la transición única a `completed`, cancela el timeout y continúa a Home;
- si timeout o Cancelar ya ganaron, la transición a `completed` se rechaza, se ejecuta logout local sobre el cliente que pudo haber recibido la sesión y no se construye Home;
- si el exchange falla después de modificar parcialmente Auth, también se ejecuta logout local;
- si la coroutine del callback se cancela mientras el trabajo síncrono continúa, EventPlus espera su terminación y limpia cualquier sesión creada antes de propagar la cancelación.

Antes de abrir un OAuth web nuevo, `PageSessionController.clear_residual_session()` consulta el cliente. Si EventPlus no está autenticado pero Supabase conserva una sesión, se clasifica como huérfana, se elimina con scope local y se limpia el contexto antes de generar un state nuevo.

Si Auth se completa pero falla la validación o construcción de `usuario_contexto`, EventPlus cierra localmente la sesión, invalida su generación, limpia el contexto y vuelve a Login. El siguiente intento no hereda esa sesión.

#### Pruebas agregadas

Las suites OAuth y lifecycle incluyen ahora:

- logout local A sin afectar B para el mismo usuario;
- función global interna que sí revoca las sesiones simuladas del usuario;
- `prompt=select_account` en OAuth web;
- state nuevo después de logout/reintento;
- un solo Home ante callback concurrente;
- exchange que termina después de timeout;
- exchange que termina después de Cancelar;
- logout local y cliente vacío tras una carrera perdida;
- limpieza de sesión residual antes de OAuth;
- limpieza posterior a contexto EventPlus inválido;
- revalidación de B después del logout local de A;
- aislamiento de usuarios distintos;
- ausencia de codes y tokens en logs.

El comportamiento esperado con dos Pages del mismo usuario es que logout local A devuelva A a Login, mientras B conserva su refresh token, sigue autenticada y supera F5/revalidación mientras su propia sesión continúe válida.

### Corrección del primer login en navegador invitado

#### Defecto y causa raíz

En una Page sin cookies ni sesión Google previa, el primer intercambio puede tardar más que en el segundo intento. En Flet 0.85.3, el callback integrado invoca `authorization.request_token(code)` y espera que termine antes de emitir `page.on_login`. EventPlus iniciaba el timeout alrededor de `Page.login()` y solo lo cancelaba después del intercambio o al entrar en `on_login`. Por tanto, el timeout podía expirar el intento mientras `exchange_code_for_session()` ya estaba procesando el primer callback. El segundo intento parecía resolverlo porque Google ya conservaba su propia sesión y el intercambio terminaba más rápido.

No existe doble intercambio: el mecanismo Auth de Flet delega el único intercambio a `SupabaseWebAuthorization.request_token()`, que usa el cliente Supabase exclusivo de esa Page. `page.on_login` permanece asignado antes de `page.login()` y no se reemplaza durante el popup.

#### Máquina de estados e instrumentación

Cada intento de la Page usa una sola máquina:

`CREATED → WAITING_CALLBACK → CALLBACK_RECEIVED → SESSION_EXCHANGING → CONTEXT_BUILDING → HOME_BUILDING → COMPLETED`

También puede terminar en `CANCELLED`, `EXPIRED` o `FAILED`. Solo `CREATED` y `WAITING_CALLBACK` pueden expirar. La referencia al intento vive en `PageSessionController`, además de la closure de la vista, por lo que una reconexión de la misma Page conserva el intento y su correlación.

`SupabaseWebAuthorization.request_token()` registra la recepción efectiva del callback y cancela el timeout **antes** de iniciar `exchange_code_for_session()`. Cuando luego llega `on_login`, el handler verifica la sesión mediante reintentos cortos y acotados, construye el contexto y reclama Home una sola vez. Un error de callback, intercambio, contexto o Home termina como `FAILED`, limpia localmente Auth y muestra un mensaje distinto del timeout sin callback.

Con `EVENTPLUS_AUTH_DEBUG=true` se emiten fases estructuradas seguras: creación y click, llamada a Page.login, recepción de callback/on_login, comprobación booleana de sesión, contexto, reclamación de Home, cancelación/vencimiento de timeout, estado terminal y rechazo tardío. Solo incluyen correlación y Page abreviadas, tiempo monotónico, estado, conexión, plataforma y booleanos permitidos. No incluyen code, tokens, email, payload ni secretos. El valor predeterminado es `false`.

#### Pruebas automatizadas

`scripts/test_web_oauth_flow.py` y `scripts/test_web_session_lifecycle.py` cubren el orden del handler, primer intento, callback próximo al timeout, intercambio/contexto lentos, estados no expirables, fallo limpio, reintento posterior, reconexión con el mismo intento, aparición tardía acotada de la sesión, ausencia permanente de sesión, reclamación única de Home y logs sin credenciales.

#### Pruebas manuales

La verificación real del primer login con credenciales en Edge Invitado y Chrome Incógnito requiere interacción del usuario y confirmar externamente que Netskope está detenido. No se considera aprobada hasta ejecutar ambos navegadores desde cero y observar Home en el primer intento. Los logs de diagnóstico deben habilitarse solo durante esa prueba y revisarse sin conservar información sensible.

### Limitaciones pendientes

- No existe persistencia Auth entre Pages nuevas.
- Un reinicio del proceso elimina las sesiones activas.
- La reconexión depende de la retención server-side de Flet y del identificador enviado por su cliente.
- No se sincroniza logout entre sesiones Flet distintas del mismo usuario.
- No se incorporó ASGI, cookie propia ni repositorio de sesiones.
- RLS continúa pendiente y sigue siendo obligatoria antes de exposición pública.
- Realtime, dominio público, proxy e infraestructura no fueron modificados.

### Siguiente tarea recomendada

Exportar e integrar EventPlus como aplicación ASGI y añadir una sesión server-side respaldada por identificador opaco en cookie HttpOnly/Secure/SameSite. Esa tarea debe definir expiración, rotación, invalidación, protección contra fijación, estrategia multiworker y pruebas reales de F5/nuevas pestañas antes de afirmar persistencia web completa.
