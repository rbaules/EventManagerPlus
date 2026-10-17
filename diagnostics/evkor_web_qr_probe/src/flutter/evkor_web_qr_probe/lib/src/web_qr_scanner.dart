import "dart:async";
import "dart:convert";
import "dart:js_interop";
import "dart:js_interop_unsafe";
import "dart:ui_web" as ui_web;

import "package:flutter/material.dart";
import "package:web/web.dart" as web;

@JS("BarcodeDetector")
extension type _BarcodeDetector._(JSObject _) implements JSObject {
  external factory _BarcodeDetector(_BarcodeDetectorOptions options);
  external JSPromise<JSArray<_Barcode>> detect(web.HTMLVideoElement source);
  external static JSPromise<JSArray<JSString>> getSupportedFormats();
}

@anonymous
extension type _BarcodeDetectorOptions._(JSObject _) implements JSObject {
  external factory _BarcodeDetectorOptions({required JSArray<JSString> formats});
}

@anonymous
extension type _Barcode._(JSObject _) implements JSObject {
  external String get rawValue;
}

@anonymous
extension type _VideoConstraints._(JSObject _) implements JSObject {
  external factory _VideoConstraints({
    required String facingMode,
    required int width,
    required int height,
    required int frameRate,
  });
}

class WebQrScanner extends StatefulWidget {
  const WebQrScanner({
    super.key,
    required this.facingMode,
    required this.onState,
    required this.onMetrics,
    required this.onQrDetected,
    required this.onError,
  });

  final String facingMode;
  final ValueChanged<String> onState;
  final ValueChanged<String> onMetrics;
  final ValueChanged<String> onQrDetected;
  final ValueChanged<String> onError;

  @override
  State<WebQrScanner> createState() => _WebQrScannerState();
}

class _WebQrScannerState extends State<WebQrScanner> {
  static int _nextView = 0;
  late final web.HTMLVideoElement _video;
  late final String _viewType;
  web.MediaStream? _stream;
  _BarcodeDetector? _detector;
  Timer? _loop;
  var _running = false;
  var _attempts = 0;
  var _startedAt = 0;
  var _lastValue = "";
  var _lastEmitAt = 0;

  @override
  void initState() {
    super.initState();
    _viewType = "evkor-web-qr-video-${_nextView++}";
    _video = web.HTMLVideoElement()
      ..autoplay = true
      ..muted = true
      ..playsInline = true
      ..style.width = "100%"
      ..style.height = "100%"
      ..style.objectFit = "cover";
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (_) => _video);
  }

  @override
  void didUpdateWidget(covariant WebQrScanner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_running && oldWidget.facingMode != widget.facingMode) {
      unawaited(_restart());
    }
  }

  Future<void> _restart() async {
    await _stop();
    await _start();
  }

  Future<void> _start() async {
    if (_running) return;
    widget.onState("requesting_camera");
    final started = DateTime.now().millisecondsSinceEpoch;
    try {
      final constraints = web.MediaStreamConstraints(
        audio: false.toJS,
        video: _VideoConstraints(
          facingMode: widget.facingMode,
          width: 1280,
          height: 720,
          frameRate: 30,
        ),
      );
      _stream = await web.window.navigator.mediaDevices.getUserMedia(constraints).toDart;
      _video.srcObject = _stream;
      await _video.play().toDart;
      _running = true;
      _startedAt = DateTime.now().millisecondsSinceEpoch;
      widget.onState("camera_active");
      widget.onMetrics(jsonEncode({
        "getUserMediaMs": _startedAt - started,
        "videoReadyMs": _startedAt - started,
        "videoWidth": _video.videoWidth,
        "videoHeight": _video.videoHeight,
        "facingMode": widget.facingMode,
        "barcodeDetector": globalContext.has("BarcodeDetector"),
      }));
      await _startDetector(started);
    } catch (error) {
      _fail(_cameraErrorCode(error));
    }
  }

  Future<void> _startDetector(int started) async {
    if (!globalContext.has("BarcodeDetector")) {
      _reportDetectorCapability("unavailable");
      return;
    }
    try {
      final formats = await _BarcodeDetector.getSupportedFormats().toDart;
      if (!formats.toDart.map((format) => format.toDart).contains("qr_code")) {
        _reportDetectorCapability("qr_code_not_supported");
        return;
      }
      _detector = _BarcodeDetector(_BarcodeDetectorOptions(
        formats: ["qr_code".toJS].toJS,
      ));
      widget.onMetrics(jsonEncode({
        "detector": "ready",
        "detectorReadyMs": DateTime.now().millisecondsSinceEpoch - started,
        "qrCodeSupported": true,
      }));
      widget.onState("detector_ready");
      _loop = Timer.periodic(const Duration(milliseconds: 180), (_) => _detect());
    } catch (_) {
      _reportDetectorCapability("initialization_failed");
    }
  }

  void _reportDetectorCapability(String value) {
    widget.onMetrics(jsonEncode({"detector": value, "qrCodeSupported": false}));
  }

  Future<void> _detect() async {
    if (!_running || _detector == null || _video.readyState < 2) return;
    try {
      _attempts++;
      final matches = await _detector!.detect(_video).toDart;
      if (matches.toDart.isEmpty) return;
      final value = matches.toDart.first.rawValue.trim();
      final now = DateTime.now().millisecondsSinceEpoch;
      if (value.isEmpty || (value == _lastValue && now - _lastEmitAt < 1800)) return;
      _lastValue = value;
      _lastEmitAt = now;
      widget.onQrDetected(value);
      widget.onState("qr_detected");
      widget.onMetrics(jsonEncode({
        "attempts": _attempts,
        "qrLatencyMs": now - _startedAt,
        "videoWidth": _video.videoWidth,
        "videoHeight": _video.videoHeight,
      }));
    } catch (_) {
      _fail("detector_failure");
    }
  }

  void _fail(String code) {
    _loop?.cancel();
    _loop = null;
    _running = false;
    widget.onState("error");
    widget.onError(code);
  }

  String _cameraErrorCode(Object error) {
    final text = error.toString();
    if (text.contains("NotAllowedError")) return "permission_denied";
    if (text.contains("NotFoundError")) return "camera_not_found";
    if (text.contains("NotReadableError")) return "camera_busy";
    if (text.contains("mediaDevices")) return "get_user_media_unavailable";
    return "camera_or_detector_failure";
  }

  Future<void> _stop() async {
    _loop?.cancel();
    _loop = null;
    for (final track in _stream?.getTracks().toDart ?? <web.MediaStreamTrack>[]) {
      track.stop();
    }
    _stream = null;
    _video.srcObject = null;
    _detector = null;
    _running = false;
    widget.onState("stopped");
  }

  @override
  void dispose() {
    unawaited(_stop());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(height: 260, width: 360, child: HtmlElementView(viewType: _viewType)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, children: [
            ElevatedButton(onPressed: _start, child: const Text("Iniciar cámara")),
            OutlinedButton(onPressed: _stop, child: const Text("Detener cámara")),
          ]),
        ],
      );
}
