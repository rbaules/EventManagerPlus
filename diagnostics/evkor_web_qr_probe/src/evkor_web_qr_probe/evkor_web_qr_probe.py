"""Python wrapper for the isolated EVKOR custom Flet Web control."""

from typing import Optional

import flet as ft


@ft.control("EvkorWebQrProbe")
class EvkorWebQrProbe(ft.LayoutControl):
    """Isolated browser-side camera and QR diagnostic control."""

    label: str = "EVKOR Web QR Control"
    on_qr_detected: Optional[ft.ControlEventHandler["EvkorWebQrProbe"]] = None
    on_scanner_state: Optional[ft.ControlEventHandler["EvkorWebQrProbe"]] = None
    on_scanner_metrics: Optional[ft.ControlEventHandler["EvkorWebQrProbe"]] = None
    on_scanner_error: Optional[ft.ControlEventHandler["EvkorWebQrProbe"]] = None


@ft.control("EvkorServerWebQrProbe")
class EvkorServerWebQrProbe(ft.LayoutControl):
    """Minimal browser control used to verify the server-side Flet transport."""

    on_test_event: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
