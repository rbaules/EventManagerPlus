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
from views.kiosk_view import KIOSK_IVORY, KIOSK_PANEL_FLORAL_ASSET, build_kiosk_view


class FakePage:
    """Page mínima: conserva tareas programadas sin iniciar Camera física."""

    def __init__(self) -> None:
        self.route = "/app/kiosk"
        self.scroll = ft.ScrollMode.AUTO
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
    host = scanner.host
    camera = scanner.camera
    scanner.set_preview_visible(False)
    assert scanner.host is host
    assert scanner.host.content is camera
    assert scanner.host.visible is True
    assert scanner.host.opacity == 0
    assert scanner.host.width == 1 and scanner.host.height == 1
    scanner.set_preview_visible(True)
    assert scanner.host is host
    assert scanner.host.content is camera
    assert scanner.host.visible is True
    assert scanner.host.opacity == 1

    root = build_kiosk_view(page=page, contexto_usuario={})
    assert isinstance(root, ft.Container)
    assert root.expand is True
    assert root.bgcolor == ft.Colors.SURFACE
    assert page.scroll is None
    assert isinstance(root.data["kiosk_scanner"], KioskQrScanner)
    kiosk_scanner = root.data["kiosk_scanner"]
    assert root.data["kiosk_root"] is root
    assert root.image is None
    foreground = root.content
    assert isinstance(foreground, ft.Container)
    assert foreground.expand is True
    assert foreground.alignment == ft.Alignment.CENTER
    assert foreground.bgcolor is None
    content_box = root.data["kiosk_content_box"]
    assert isinstance(content_box, ft.Container)
    assert content_box.width == 680
    assert content_box.bgcolor == KIOSK_IVORY
    assert (content_box.padding.left, content_box.padding.top, content_box.padding.right, content_box.padding.bottom) == (
        32,
        64,
        32,
        32,
    )
    assert isinstance(content_box.image, ft.DecorationImage)
    assert content_box.image.src == KIOSK_PANEL_FLORAL_ASSET
    assert content_box.image.fit == ft.BoxFit.COVER
    assert content_box.image.alignment == ft.Alignment.CENTER
    content = content_box.content
    camera_stage = root.data["kiosk_camera_stage"]
    assert isinstance(camera_stage, ft.Stack)
    assert camera_stage.controls[0] is kiosk_scanner.host
    assert camera_stage.controls[1] is root.data["kiosk_qr_guide"]
    assert content.controls[-1] is camera_stage
    assert kiosk_scanner.host.content is kiosk_scanner.camera
    guide = root.data["kiosk_qr_guide"]
    assert guide.ignore_interactions and guide.content.width == 200 and guide.content.height == 200
    assert len(page.tasks) == 1


def test_installed_flet_constructs_decoration_image_background() -> None:
    """Validates the production background mechanism without requiring a browser."""
    background = ft.Container(
        expand=True,
        bgcolor=ft.Colors.SURFACE,
        image=ft.DecorationImage(
            src="https://example.invalid/kiosk-background.jpg",
            fit=ft.BoxFit.CONTAIN,
            alignment=ft.Alignment.CENTER,
        ),
    )

    assert isinstance(background.image, ft.DecorationImage)
    assert background.image.src == "https://example.invalid/kiosk-background.jpg"
    assert background.image.fit == ft.BoxFit.CONTAIN
    assert background.image.alignment == ft.Alignment.CENTER


def main() -> None:
    test_kiosk_controls_build_with_installed_flet()
    test_installed_flet_constructs_decoration_image_background()
    print("Kiosk Flet construction smoke test passed.")


if __name__ == "__main__":
    main()
