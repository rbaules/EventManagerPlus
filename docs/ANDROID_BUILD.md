# Android Build - EventPlus Check-in

## Requisitos

- Windows PowerShell.
- Python del proyecto: `.\env\Scripts\python.exe`.
- Flet CLI del entorno: `.\env\Scripts\flet.exe`.
- Java 17 disponible.
- Conexion a Internet para descargar/usar componentes de Flutter, Android SDK y dependencias si no estan en cache.

## Entorno confirmado

- Python: 3.14.6 en `C:\WORKSPACE\EVENTPLUS\env\Scripts\python.exe`.
- Flet: 0.85.3.
- Flutter reportado por Flet: 3.41.7.

## Configuracion publica

El APK no debe empaquetar `.env`. Para una build local se usa `app_public_config.py`, ignorado por Git, con solo:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`

No incluir `service_role`, secretos de Google ni tokens.

## Generar `app_public_config.py`

Desde la raiz:

```powershell
$pairs = @{}
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        $pairs[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$url = $pairs['SUPABASE_URL']
$key = $pairs['SUPABASE_PUBLISHABLE_KEY']
if (-not $url -or -not $key) { throw 'Faltan variables publicas' }
@(
    "# Generated public client config for Android build. Do not commit.",
    "SUPABASE_URL = '$url'",
    "SUPABASE_PUBLISHABLE_KEY = '$key'"
) | Set-Content -Encoding UTF8 app_public_config.py
```

## Build

```powershell
cd C:\WORKSPACE\EVENTPLUS
.\scripts\build_android_checkin.ps1
```

Comando base equivalente:

```powershell
.\env\Scripts\flet.exe build apk . --module-name main_checkin --bundle-id com.eventplus.beta.checkin --product "EventPlus Beta" --build-version 0.1.0 --build-number 1 --deep-linking-scheme eventplusbeta --deep-linking-host auth-callback --yes
```

## Ubicacion del APK

Flet genera artefactos bajo `build\apk` por defecto. Si se copia una version final, usar:

```text
dist\EventPlus-Checkin-0.1.0-beta.apk
```

## Instalacion con ADB

```powershell
adb devices
adb install -r "RUTA_REAL_DEL_APK"
```

Si `adb` no esta disponible, instalar Android Platform Tools o transferir el APK al dispositivo y habilitar temporalmente instalacion desde origenes desconocidos. Deshabilitar ese permiso al terminar.

## Logs

```powershell
adb logcat
adb logcat | Select-String -Pattern "EventPlus|CHECKIN|LOGIN|OAuth|Flet|Python|Exception"
```

## Errores frecuentes

- `adb` no encontrado: Android Platform Tools no esta en PATH.
- Descarga bloqueada: revisar proxy/firewall/Netskope y reintentar sin desactivar controles de seguridad.
- OAuth no vuelve al APK: falta configurar `eventplusbeta://auth-callback` en Supabase.
- Variables faltantes: regenerar `app_public_config.py`.
