# EVKOR Web QR Probe

This is an isolated Flet 0.85.3 extension spike. Its Dart/Flutter custom
control uses browser `getUserMedia` for a camera preview and optionally uses
`BarcodeDetector` to emit QR events to the Python Flet diagnostic UI. It has no
Kiosk integration and no changes to the principal Flet application routes.

## Local validation

The extension must be installed before Flet can package its Flutter portion:

```powershell
Set-Location examples\evkor_web_qr_probe_example
..\..\..\..\env\Scripts\flet.exe build --base-url /diagnostics/flet-web-qr-probe/ web .
```

The example's Flet `dev_packages` setting resolves the local extension during
the build. `flet build web` packages the Python extension and copies its
`src/flutter/evkor_web_qr_probe` package into the generated Flet Flutter
shell. The generated web output, not this source directory, is what a static
web server would serve.

The `src/flutter/evkor_web_qr_probe` package has no third-party Dart
dependencies. Its only Flutter dependency is Flet itself.

## Diagnostic deployment artifact

`deploy/web` is the versioned output served only at
`/diagnostics/flet-web-qr-probe/` by `asgi.py`. It is versioned because this
repository has no Render build configuration for Flutter/Pyodide and compiling
the main service during deployment would not be reproducible. Flet 0.85.3
applies `--base-url` to the document and app assets but leaves the CanvasKit and
Pyodide URLs rooted at `/`; the deployed `index.html` adjusts only those two
generated URLs to the same diagnostic prefix.
