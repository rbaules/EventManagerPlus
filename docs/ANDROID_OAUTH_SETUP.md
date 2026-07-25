# Android OAuth Setup

## Deep link final

```text
eventplusbeta://auth-callback
```

- Scheme: `eventplusbeta`
- Host: `auth-callback`

## En Supabase

En el proyecto de Supabase, agregar la Redirect URL:

```text
eventplusbeta://auth-callback
```

Conservar tambien la URL usada en escritorio:

```text
http://localhost:8765/auth/callback
```

No eliminar las URLs actuales que ya funcionan en Windows.

## En Google Cloud

Conservar el proveedor Google ya usado por Supabase. Para pruebas internas con deep link personalizado, verificar que Supabase siga siendo el intermediario OAuth.

Si se configura un cliente Android nativo posteriormente, se necesitara:

- Package name: `com.eventplus.beta.checkin`
- SHA-1 o SHA-256 del certificado usado para firmar.

No incluir client secrets dentro del APK.

## Diferencia Windows vs Android

- Windows usa callback local: `http://localhost:8765/auth/callback`.
- Android usa deep link: `eventplusbeta://auth-callback`.

La funcion central en codigo resuelve el redirect segun plataforma.

## Procedimiento de prueba

1. Instalar APK.
2. Abrir EventPlus Beta.
3. Tocar `Continuar con Google`.
4. Completar login en navegador.
5. Confirmar que vuelve al APK.
6. Confirmar que se carga el contexto y abre Check-in.

## Problemas comunes

- Supabase rechaza redirect: falta registrar exactamente `eventplusbeta://auth-callback`.
- La app no vuelve desde navegador: revisar que el APK tenga deep linking configurado con scheme/host correctos.
- Callback incompleto: reintentar login; no reutilizar enlaces antiguos.
