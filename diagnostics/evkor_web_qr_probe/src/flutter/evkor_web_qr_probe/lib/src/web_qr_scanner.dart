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
  external factory _VideoConstraints({required String facingMode, required int width, required int height, required int frameRate});
}

class WebQrScanner extends StatefulWidget {
  const WebQrScanner({super.key, this.active = true, this.detectorEnabled = true, this.previewVisible = true, required this.facingMode, this.generation = 0, required this.onState, required this.onMetrics, required this.onQrDetected, required this.onError});
  final bool active;
  final bool detectorEnabled;
  final bool previewVisible;
  final String facingMode;
  final int generation;
  final ValueChanged<String> onState;
  final ValueChanged<String> onMetrics;
  final ValueChanged<String> onQrDetected;
  final ValueChanged<String> onError;
  @override State<WebQrScanner> createState() => _WebQrScannerState();
}

class _WebQrScannerState extends State<WebQrScanner> {
  static int _nextView = 0;
  late final web.HTMLVideoElement _video;
  late final String _viewType;
  web.MediaStream? _stream;
  _BarcodeDetector? _detector;
  Timer? _loop;
  var _cameraActive = false;
  var _detectorAvailable = false;
  var _cameraReused = false;
  var _getUserMediaCount = 0;
  var _attempts = 0;
  var _startedAt = 0;
  var _lastValue = "";
  var _lastEmitAt = 0;

  @override void initState() {
    super.initState();
    _viewType = "evkor-web-qr-video-${_nextView++}";
    _video = web.HTMLVideoElement()..autoplay = true..muted = true..playsInline = true..style.width = "100%"..style.height = "100%"..style.objectFit = "cover";
    ui_web.platformViewRegistry.registerViewFactory(_viewType, (_) => _video);
    unawaited(_syncLifecycle());
  }

  @override void didUpdateWidget(covariant WebQrScanner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_cameraActive && oldWidget.facingMode != widget.facingMode) { unawaited(_restartCamera()); return; }
    if (oldWidget.active != widget.active || oldWidget.detectorEnabled != widget.detectorEnabled) {
      unawaited(_syncLifecycle());
    } else if (oldWidget.previewVisible != widget.previewVisible) {
      _reportMetrics();
    }
  }

  bool get _streamLive {
    final stream = _stream;
    if (stream == null) return false;
    return stream.getVideoTracks().toDart.any((track) => track.readyState == "live");
  }
  Future<void> _restartCamera() async { await _stopCamera(emitState: false); await _syncLifecycle(); }

  Future<void> _syncLifecycle() async {
    if (!widget.active) { await _stopCamera(); return; }
    await _ensureCamera();
    if (!mounted || !_cameraActive) return;
    if (widget.detectorEnabled) { await _resumeDetector(); } else { _pauseDetector(); }
  }

  Future<void> _ensureCamera() async {
    if (_streamLive) { _cameraActive = true; _cameraReused = true; _reportMetrics(); return; }
    widget.onState("requesting_camera");
    final started = DateTime.now().millisecondsSinceEpoch;
    try {
      _stream = await web.window.navigator.mediaDevices.getUserMedia(web.MediaStreamConstraints(audio: false.toJS, video: _VideoConstraints(facingMode: widget.facingMode, width: 1280, height: 720, frameRate: 30))).toDart;
      _video.srcObject = _stream;
      await _video.play().toDart;
      _cameraActive = true;
      _cameraReused = false;
      _getUserMediaCount++;
      _startedAt = DateTime.now().millisecondsSinceEpoch;
      widget.onState("camera_active");
      _reportMetrics(cameraReused: false, started: started);
    } catch (error) { _fail(_cameraErrorCode(error)); }
  }

  Future<void> _resumeDetector() async {
    if (!_cameraActive || !widget.detectorEnabled || _loop != null) return;
    if (!globalContext.has("BarcodeDetector")) { _reportDetectorCapability("unavailable"); return; }
    try {
      if (_detector == null) {
        final formats = await _BarcodeDetector.getSupportedFormats().toDart;
        if (!formats.toDart.map((format) => format.toDart).contains("qr_code")) { _reportDetectorCapability("qr_code_not_supported"); return; }
        _detector = _BarcodeDetector(_BarcodeDetectorOptions(formats: ["qr_code".toJS].toJS));
        _detectorAvailable = true;
      }
      _reportMetrics(detector: "ready");
      widget.onState("detector_ready");
      _loop = Timer.periodic(const Duration(milliseconds: 180), (_) => _detect());
    } catch (_) { _reportDetectorCapability("initialization_failed"); }
  }

  void _pauseDetector() {
    _loop?.cancel();
    _loop = null;
    if (_cameraActive) widget.onState("detector_paused");
    _reportMetrics();
  }
  void _reportDetectorCapability(String value) { _detectorAvailable = false; _reportMetrics(detector: value); }

  Future<void> _detect() async {
    if (!_cameraActive || !widget.detectorEnabled || _detector == null || _video.readyState < 2) return;
    try {
      _attempts++;
      final matches = await _detector!.detect(_video).toDart;
      if (matches.toDart.isEmpty) return;
      final value = matches.toDart.first.rawValue.trim();
      final now = DateTime.now().millisecondsSinceEpoch;
      if (value.isEmpty || (value == _lastValue && now - _lastEmitAt < 1800)) return;
      _lastValue = value; _lastEmitAt = now;
      widget.onQrDetected(value);
      widget.onState("qr_detected");
      _pauseDetector();
      _reportMetrics(qrLatencyMs: now - _startedAt);
    } catch (_) { _fail("detector_failure"); }
  }

  void _reportMetrics({bool? cameraReused, String? detector, int? qrLatencyMs, int? started}) => widget.onMetrics(jsonEncode({
    "camera_reused": cameraReused ?? _cameraReused, "getUserMedia_count": _getUserMediaCount, "generation": widget.generation,
    "stream_live": _streamLive, "detector_enabled": widget.detectorEnabled, "preview_visible": widget.previewVisible,
    "videoWidth": _video.videoWidth, "videoHeight": _video.videoHeight, "facingMode": widget.facingMode,
    "barcodeDetector": globalContext.has("BarcodeDetector"), "detector": detector ?? (_detectorAvailable ? "ready" : "unavailable"),
    "getUserMediaMs": started == null ? null : _startedAt - started, "qrLatencyMs": qrLatencyMs, "attempts": _attempts,
  }));

  void _fail(String code) { _pauseDetector(); _cameraActive = false; widget.onState("error"); widget.onError(code); }
  String _cameraErrorCode(Object error) { final text = error.toString(); if (text.contains("NotAllowedError")) return "permission_denied"; if (text.contains("NotFoundError")) return "camera_not_found"; if (text.contains("NotReadableError")) return "camera_busy"; if (text.contains("mediaDevices")) return "get_user_media_unavailable"; return "camera_or_detector_failure"; }

  Future<void> _stopCamera({bool emitState = true}) async {
    _loop?.cancel(); _loop = null;
    for (final track in _stream?.getTracks().toDart ?? <web.MediaStreamTrack>[]) { track.stop(); }
    _stream = null; _video.srcObject = null; _detector = null; _detectorAvailable = false; _cameraActive = false; _cameraReused = false;
    if (emitState) widget.onState("stopped");
    _reportMetrics();
  }

  @override void dispose() { unawaited(_stopCamera()); super.dispose(); }
  @override Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Opacity(opacity: widget.previewVisible ? 1 : 0, child: SizedBox(height: 260, width: 360, child: HtmlElementView(viewType: _viewType)))]);
}
