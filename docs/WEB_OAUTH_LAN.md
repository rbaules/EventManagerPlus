# OAuth web de EventPlus en LAN y producción

## Flujo real

EventPlus web usa el adaptador OAuth de Flet. La aplicación llama a Supabase
con `redirect_to=<origen>/auth/callback`; Flet atiende esa ruta, correlaciona el
`state` y entrega el `code` a `SupabaseWebAuthorization.request_token()`, que
ejecuta el intercambio PKCE sobre el cliente Supabase de esa Page.

La decisión de transporte usa primero `page.web`. Por ello Chrome en Android
(`platform=ANDROID`, `web=True`) entra en el mismo OAuth web que un navegador
Windows. Solo una Page Android con `web=False` utiliza el deep link nativo.

La resolución del origen tiene esta prioridad:

1. `EVENTPLUS_PUBLIC_BASE_URL`, si está configurada y es HTTP(S) válida.
2. El origen de `page.url`, únicamente para localhost, loopback o una IP LAN
   privada.
3. El fallback local de `EVENTPLUS_WEB_OAUTH_REDIRECT_URL`.

En Flet 0.85.3 sobre ASGI, `page.url` procede del WebSocket y contiene un origen
`ws://host:puerto` o `wss://host`. EventPlus lo transforma explícitamente a
`http://` o `https://`; tratarlo como una URL HTTP directa fue la causa del error
temprano “No se pudo determinar la dirección de retorno”.

Flet genera el state que correlaciona el popup con la Page, lo almacena en el
`FletAppManager` en memoria junto al ID de sesión y lo consume una sola vez en
`/auth/callback`. Si la sesión continúa retenida, el callback llama a la misma
Page; no crea una nueva. Supabase genera además su propio state para el tramo
Google→Supabase. Un `bad_oauth_state` emitido en una URL de Supabase/Site URL
ocurre antes de que el callback de EventPlus sea ejecutado.

No se acepta un dominio público tomado solamente del Host de la petición. Para
un dominio público debe configurarse `EVENTPLUS_PUBLIC_BASE_URL`; esto evita que
un Host arbitrario convierta el login en un open redirect. La URL se conserva
por intento y nunca se guarda como estado global mutable de la última sesión.

## Desarrollo local y LAN

La ejecución no cambia:

```powershell
env\Scripts\python.exe -m uvicorn asgi:app --host 0.0.0.0 --port 8560 --timeout-graceful-shutdown 5
```

Si el navegador abre `http://127.0.0.1:8560`, el callback es
`http://127.0.0.1:8560/auth/callback`. Si Android abre
`http://192.168.1.45:8560`, vuelve a
`http://192.168.1.45:8560/auth/callback`. Un cambio DHCP se incorpora
automáticamente porque se usa el origen de esa Page.

Como alternativa explícita para una prueba LAN:

```powershell
$env:EVENTPLUS_PUBLIC_BASE_URL="http://192.168.0.27:8560"
env\Scripts\python.exe -m uvicorn asgi:app --host 0.0.0.0 --port 8560 --timeout-graceful-shutdown 5
```

## Supabase Authentication > URL Configuration

Cada `redirect_to` debe coincidir con la lista de Redirect URLs. Para desarrollo
se recomienda registrar URLs exactas, por ejemplo:

```text
http://127.0.0.1:8560/auth/callback
http://localhost:8560/auth/callback
http://192.168.1.45:8560/auth/callback
```

Supabase admite patrones glob. Para una red de desarrollo `192.168.0.0/16`, el
patrón restringido al puerto y callback de EventPlus puede ser:

```text
http://192.168.*.*:8560/auth/callback
```

Esta comodidad es solo para desarrollo. Producción debe usar una URL HTTPS
exacta. El Site URL es el retorno por defecto cuando no se proporciona o no se
acepta `redirect_to`. En la prueba contra el proyecto Supabase alojado fue
necesario establecer temporalmente el origen LAN como Site URL; con ello el
flujo real en laptop y Chrome Android completó correctamente. Esta medida se
limita al entorno LAN de desarrollo y debe retirarse al finalizar la prueba.

## Producción

Configure antes de arrancar:

```text
EVENTPLUS_PUBLIC_BASE_URL=https://eventplus.midominio.com
```

Y registre exactamente en Supabase:

```text
https://eventplus.midominio.com/auth/callback
```

El reverse proxy debe preservar el acceso a `/auth/callback`. EventPlus no
confía actualmente en `X-Forwarded-Host` ni `X-Forwarded-Proto`; la URL pública
explícita evita depender de headers de un proxy no declarado confiable.

## Google Cloud

Google redirige al callback del proveedor Supabase, normalmente
`https://<project-ref>.supabase.co/auth/v1/callback`. Supabase redirige después
a `redirect_to` de EventPlus. Por tanto, añadir cada IP LAN a Google Cloud no es
necesario mientras el callback de Supabase ya esté autorizado. No se modifica
Google Cloud automáticamente.

## Logs y validación manual

Antes del OAuth se registran únicamente `base_url`, `redirect_to` y la fuente
`config|request|fallback`. Nunca se registran code, tokens, JWT, verifier ni
secretos. El flujo OAuth real fue validado satisfactoriamente desde:

- laptop con `http://127.0.0.1:8560`;
- Chrome Android en tablet con `http://<IP-LAPTOP>:8560`.

Para producción queda pendiente definir el dominio público estable, configurar
`EVENTPLUS_PUBLIC_BASE_URL` con su origen HTTPS y registrar el callback exacto
en Supabase. No debe conservarse una IP privada como Site URL de producción.
