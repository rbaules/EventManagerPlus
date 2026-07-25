$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
chcp 65001 | Out-Null

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:EVENTPLUS_MODE = "CHECKIN"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:LANG = "en_US.UTF-8"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

if (-not (Test-Path ".\app_public_config.py")) {
    throw "Falta app_public_config.py. Genera la configuracion publica desde .env antes de compilar."
}

.\env\Scripts\flet.exe build apk . `
    --module-name main_checkin `
    --project eventplus_checkin `
    --product "EventPlus Beta" `
    --description "Control de acceso y consulta de invitados" `
    --bundle-id "com.eventplus.beta.checkin" `
    --build-version "0.1.0" `
    --build-number "1" `
    --deep-linking-scheme eventplusbeta `
    --deep-linking-host auth-callback `
    --android-adaptive-icon-background "#FFFFFF" `
    --splash-color "#FFFFFF" `
    --splash-dark-color "#FFFFFF" `
    --exclude ".env" `
    --exclude "env" `
    --exclude ".git" `
    --exclude "__pycache__" `
    --exclude "app_publishable_key_v4.py" `
    --exclude "build" `
    --exclude "dist" `
    --exclude "*.pyc" `
    --no-rich-output `
    --yes
