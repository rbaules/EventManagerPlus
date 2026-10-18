import "package:flet/flet.dart";
import "package:flutter/material.dart";

class EvkorServerWebQrProbeControl extends StatelessWidget {
  const EvkorServerWebQrProbeControl({super.key, required this.control});

  final Control control;

  @override
  Widget build(BuildContext context) => LayoutControl(
        control: control,
        child: ElevatedButton(
          onPressed: () => control.triggerEvent("test_event", "SERVER_WEB_QR_TEST"),
          child: const Text("Enviar evento server-side"),
        ),
      );
}
