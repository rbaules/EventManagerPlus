import "package:flet/flet.dart";
import "package:flutter/material.dart";

import "web_qr_scanner.dart";

class EvkorWebQrProbeControl extends StatefulWidget {
  const EvkorWebQrProbeControl({super.key, required this.control});

  final Control control;

  @override
  State<EvkorWebQrProbeControl> createState() => _EvkorWebQrProbeControlState();
}

class _EvkorWebQrProbeControlState extends State<EvkorWebQrProbeControl> {
  String _facingMode = "user";

  void _event(String name, String data) => widget.control.triggerEvent(name, data);

  @override
  Widget build(BuildContext context) {
    final label = widget.control.getString("label", "EVKOR Web QR Control")!;

    return LayoutControl(
      control: widget.control,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label),
          const SizedBox(height: 12),
          WebQrScanner(
            facingMode: _facingMode,
            onState: (value) => _event("scanner_state", value),
            onMetrics: (value) => _event("scanner_metrics", value),
            onQrDetected: (value) => _event("qr_detected", value),
            onError: (value) => _event("scanner_error", value),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: () => setState(() {
              _facingMode = _facingMode == "user" ? "environment" : "user";
            }),
            child: Text("Cambiar cámara ($_facingMode)"),
          ),
        ],
      ),
    );
  }
}
