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
    """Server-driven diagnostic probe with independent stream, detector and preview."""

    label: str = "EVKOR Server Web QR Control"
    active: bool = False
    detector_enabled: bool = False
    preview_visible: bool = True
    facing_mode: str = "user"
    generation: int = 0
    diagnostic: bool = False
    preview_width: int = 560
    preview_height: int = 300
    on_test_event: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
    on_lifecycle_action: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
    on_qr_detected: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
    on_scanner_state: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
    on_scanner_metrics: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
    on_scanner_error: Optional[ft.ControlEventHandler["EvkorServerWebQrProbe"]] = None
