import "package:flet/flet.dart";
import "package:flutter/material.dart";

import "web_qr_scanner.dart";

class EvkorServerWebQrProbeControl extends StatefulWidget {
  const EvkorServerWebQrProbeControl({super.key, required this.control});

  final Control control;

  @override
  State<EvkorServerWebQrProbeControl> createState() =>
      _EvkorServerWebQrProbeControlState();
}

class _EvkorServerWebQrProbeControlState
    extends State<EvkorServerWebQrProbeControl> {
  void _event(String name, String data) => widget.control.triggerEvent(name, data);

  bool _bool(String name, bool fallback) =>
      widget.control.getString(name, fallback.toString()) == "true";

  @override
  Widget build(BuildContext context) => LayoutControl(
        control: widget.control,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.control.getString("label", "EVKOR Server Web QR Control")!),
            const SizedBox(height: 12),
            WebQrScanner(
              active: _bool("active", false),
              detectorEnabled: _bool("detector_enabled", false),
              previewVisible: _bool("preview_visible", true),
              facingMode: widget.control.getString("facing_mode", "user")!,
              generation: int.tryParse(widget.control.getString("generation", "0")!) ?? 0,
              onState: (value) => _event("scanner_state", value),
              onMetrics: (value) => _event("scanner_metrics", value),
              onQrDetected: (value) => _event("qr_detected", value),
              onError: (value) => _event("scanner_error", value),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                TextButton(
                  onPressed: () => _event("lifecycle_action", "start"),
                  child: const Text("Iniciar camara"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "stop"),
                  child: const Text("Detener camara"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "activate_detector"),
                  child: const Text("Activar detector"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "pause_detector"),
                  child: const Text("Pausar detector"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "show_preview"),
                  child: const Text("Mostrar preview"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "hide_preview"),
                  child: const Text("Ocultar preview"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "next_guest"),
                  child: const Text("Siguiente invitado"),
                ),
                TextButton(
                  onPressed: () => _event("lifecycle_action", "switch_camera"),
                  child: const Text("Cambiar camara"),
                ),
                OutlinedButton(
                  onPressed: () => _event("test_event", "SERVER_WEB_QR_TEST"),
                  child: const Text("Enviar evento server-side"),
                ),
              ],
            ),
          ],
        ),
      );
}
