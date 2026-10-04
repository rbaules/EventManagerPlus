from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import flet as ft
import flet_camera as fcam

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.kiosk_qr_scanner import KioskQrScanner
from views.kiosk_view import build_kiosk_view


class FakePage:
    """Page mínima: conserva tareas programadas sin iniciar Camera física."""

    def __init__(self) -> None:
        self.route = "/app/kiosk"
        self.on_route_change: Any = None
        self.tasks: list[Any] = []
        self.updated = 0

    def run_task(self, task_factory: Any) -> None:
        self.tasks.append(task_factory)

    def update(self) -> None:
        self.updated += 1


def test_kiosk_controls_build_with_installed_flet() -> None:
    page = FakePage()
    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=lambda _code: None,
        on_camera_error=lambda _message: None,
    )
    assert isinstance(scanner.camera, fcam.Camera)
    assert isinstance(scanner.host, ft.Container)
    assert isinstance(scanner.camera.content, ft.Container)
    assert isinstance(scanner.camera.content.border, ft.Border)
    assert scanner.camera.content.border.top.width == 2
    assert scanner.camera.content.border.top.color == ft.Colors.PRIMARY

    root = build_kiosk_view(page=page, contexto_usuario={})
    assert isinstance(root, ft.Container)
    assert isinstance(root.data["kiosk_scanner"], KioskQrScanner)
    assert len(page.tasks) == 1


def main() -> None:
    test_kiosk_controls_build_with_installed_flet()
    print("Kiosk Flet construction smoke test passed.")


if __name__ == "__main__":
    main()
