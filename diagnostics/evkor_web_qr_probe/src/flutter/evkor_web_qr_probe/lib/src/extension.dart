import "package:flet/flet.dart";
import "package:flutter/widgets.dart";

import "evkor_web_qr_probe_control.dart";
import "server_web_qr_probe_control.dart";

class Extension extends FletExtension {
  @override
  Widget? createWidget(Key? key, Control control) {
    switch (control.type) {
      case "EvkorWebQrProbe":
        return EvkorWebQrProbeControl(key: key, control: control);
      case "EvkorServerWebQrProbe":
        return EvkorServerWebQrProbeControl(key: key, control: control);
      default:
        return null;
    }
  }
}
