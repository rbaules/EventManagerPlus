"""Regresión QR-3B: la cámara no puede pertenecer al árbol reconstruido por render()."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from views import home_view


class Page:
    def __init__(self) -> None:
        self.width = 1024
        self.route = "/app/llegadas"
        self.overlay: list[Any] = []
        self.navigation_bar = None
        self.clean_calls = 0
        self.update_calls = 0
        self.tasks: list[Any] = []

    def clean(self) -> None:
        self.clean_calls += 1

    def add(self, _control: Any) -> None:
        pass

    def update(self) -> None:
        self.update_calls += 1

    def run_task(self, task: Any, *args: Any) -> None:
        self.tasks.append((task, args))

    def run_thread(self, _worker: Any, *_args: Any) -> None:
        pass

    def go(self, route: str) -> None:
        self.route = route


def context() -> dict[str, Any]:
    event = {"cuenta_id": 1, "evento_id": 10, "nombre_evento": "Prueba", "fase_evento": "En_proceso", "estado": "Activo", "rol": "Operador"}
    return {
        "usr_usuario_id": "operator-1", "usr_nombre_usuario": "Operador", "rol_global_calculado": "Operador",
        "cuenta_actual": {"cuenta_id": 1, "nombre_cuenta": "Cuenta", "rol": "Operador"},
        "cuentas_permitidas": [{"cuenta_id": 1, "nombre_cuenta": "Cuenta", "rol": "Operador"}],
        "evento_actual": event, "eventos_permitidos": [event], "puede_registrar_llegadas": True,
    }


def _walk(control: Any) -> list[Any]:
    result = [control]
    content = getattr(control, "content", None)
    if content is not None and content is not control:
        result.extend(_walk(content))
    for child in getattr(control, "controls", None) or []:
        result.extend(_walk(child))
    return result


def test_one_camera_survives_home_renders() -> None:
    original_camera = home_view.fcam.Camera
    original_checkin_mode = home_view.is_checkin_mode
    creations: list[Any] = []

    class CountingCamera(original_camera):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            creations.append(self)

    page = Page()
    try:
        home_view.fcam.Camera = CountingCamera
        home_view.is_checkin_mode = lambda: True
        home = home_view.build_home_view(page, context())
        state = home.data["state"]
        assert len(creations) == state["qr_scanner_camera_creations"] == 1
        assert state["qr_scanner_camera"] is creations[0]
        assert len(page.overlay) == 1

        # Simula navegación y cambio de evento: ambos ejecutan render().
        page.on_route_change(SimpleNamespace(route="/app/llegadas"))
        page.on_route_change(SimpleNamespace(route="/app/llegadas"))
        assert len(creations) == 1

        overlay = page.overlay[0]
        host = state["qr_scanner_camera_host"]
        chrome = state["qr_scanner_chrome"]
        assert overlay.visible is True and overlay.ignore_interactions is True
        assert host.visible is True and host.opacity == 0
        assert host.content is creations[0] and creations[0].visible is True
        assert chrome.visible is False
        scan = next(node for node in _walk(home) if getattr(node, "data", None) == {"arrivals_qr": "scan"})
        scan.on_click(SimpleNamespace())
        assert overlay.visible is True and overlay.ignore_interactions is False
        assert host.visible is True and host.opacity == 1
        assert host.width == 528 and host.height == 280 and chrome.visible is True
        assert len(creations) == 1
        # Simula cancelar después de initialize: el shell previo ya tenía los
        # controles QR construidos como disabled y debe reconstruirse liberado.
        state["qr_scanner_camera_initialized"] = True
        renders_before_cancel = page.clean_calls
        cancel = next(node for node in _walk(overlay) if getattr(node, "data", None) == {"arrivals_qr": "cancel"})
        cancel.on_click(SimpleNamespace())
        assert overlay.visible is True and overlay.ignore_interactions is True
        assert host.visible is True and host.opacity == 0
        assert host.width == 1 and host.height == 1 and chrome.visible is False
        assert len(creations) == 1
        assert state["qr_scanner_active"] is False
        assert state["qr_scanner_camera_initialized"] is True
        assert page.clean_calls > renders_before_cancel

        # Diez ciclos no crean ni montan una segunda cámara. En una Page real,
        # las nueve reaperturas usan resume_preview(), no initialize().
        for _ in range(9):
            scan.on_click(SimpleNamespace())
            assert state["qr_scanner_active"] is True
            cancel.on_click(SimpleNamespace())
            assert state["qr_scanner_active"] is False
        assert len(creations) == 1 and len(page.overlay) == 1
    finally:
        home_view.fcam.Camera = original_camera
        home_view.is_checkin_mode = original_checkin_mode


def main() -> int:
    test_one_camera_survives_home_renders()
    print("OK - QR camera is constructed once per Home/Page and survives shell renders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
