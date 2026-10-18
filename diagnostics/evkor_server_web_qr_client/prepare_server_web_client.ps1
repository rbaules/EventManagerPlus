param(
    [string]$BuildDirectory = (Join-Path $PSScriptRoot "build\\web"),
    [string]$DeployDirectory = (Join-Path $PSScriptRoot "deploy\\server_web")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath (Join-Path $BuildDirectory "index.html"))) {
    throw "No existe el build web esperado: $BuildDirectory"
}

if (Test-Path -LiteralPath $DeployDirectory) {
    Remove-Item -LiteralPath $DeployDirectory -Recurse -Force
}

New-Item -ItemType Directory -Path $DeployDirectory -Force | Out-Null
Copy-Item -Path (Join-Path $BuildDirectory "*") -Destination $DeployDirectory -Recurse -Force

$indexPath = Join-Path $DeployDirectory "index.html"
$index = Get-Content -LiteralPath $indexPath -Raw
$index = $index.Replace("pyodide: true", "pyodide: false")
$index = $index -replace '(?m)^\s*pythonModuleName: "main",\r?\n', ""
$index = $index.Replace('appPackageUrl: "assets/app/app.zip"', 'appPackageUrl: "app.tar.gz"')
$index = $index -replace '(?m)^\s*<script src="python.js"></script>\r?\n', ""
[System.IO.File]::WriteAllText($indexPath, $index, [System.Text.UTF8Encoding]::new($false))

@(
    "python.js",
    "python-worker.js",
    "pyodide",
    ".last_build_id",
    "assets\\app\\app.zip",
    "assets\\app\\app.zip.hash"
) | ForEach-Object {
    $path = Join-Path $DeployDirectory $_
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$finalIndex = Get-Content -LiteralPath $indexPath -Raw
if ($finalIndex -notmatch "pyodide:\s*false") {
    throw "El índice final no desactiva Pyodide."
}
if ($finalIndex -notmatch 'webSocketEndpoint:\s*"/ws"') {
    throw "El índice final no conserva el WebSocket /ws."
}
if ($finalIndex -match "assets/app/app\.zip") {
    throw "El índice final conserva una referencia a app.zip."
}
if ($finalIndex -match "python(ModuleName|\.js)") {
    throw "El índice final conserva una referencia al runtime Python."
}

Write-Output "Prepared server-side Flet client: $DeployDirectory"
