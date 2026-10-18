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
  String _facingMode = "user";

  void _event(String name, String data) => widget.control.triggerEvent(name, data);

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
              facingMode: _facingMode,
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
                  onPressed: () => setState(() {
                    _facingMode = _facingMode == "user" ? "environment" : "user";
                  }),
                  child: Text("Cambiar camara ($_facingMode)"),
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
