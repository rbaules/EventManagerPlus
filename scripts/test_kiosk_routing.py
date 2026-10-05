from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from views.authenticated_router import AuthenticatedViewRouter, authenticated_route_target


class FakePage:
    def __init__(self, route: str) -> None:
        self.route = route
        self.controls: list[object] = []
        self.clean_calls = 0
        self.update_calls = 0

    def clean(self) -> None:
        self.clean_calls += 1
        self.controls.clear()

    def add(self, control: object) -> None:
        self.controls.append(control)

    def update(self) -> None:
        self.update_calls += 1


def _builders(calls: list[tuple[str, dict[str, Any]]]):
    def home_builder(**kwargs: Any) -> object:
        calls.append(("home", kwargs))
        return SimpleNamespace(data={"start_eventos": lambda: calls.append(("start_eventos", {}))})

    def kiosk_builder(**kwargs: Any) -> object:
        calls.append(("kiosk", kwargs))
        return SimpleNamespace(data={})

    return home_builder, kiosk_builder


def test_authenticated_target_selection() -> None:
    assert authenticated_route_target("/app/kiosk") == "kiosk"
    assert authenticated_route_target("/app/kiosk?refresh=1") == "kiosk"
    assert authenticated_route_target("/app/dashboard") == "home"
    assert authenticated_route_target("/") == "home"


def test_direct_entry_and_refresh_mount_kiosk() -> None:
    for route in ("/app/kiosk", "/app/kiosk?refresh=1"):
        calls: list[tuple[str, dict[str, Any]]] = []
        page = FakePage(route)
        home_builder, kiosk_builder = _builders(calls)
        router = AuthenticatedViewRouter(
            page=page,
            contexto_usuario={"usr_usuario_id": "test"},
            supabase=object(),
            session_controller=object(),
            home_builder=home_builder,
            kiosk_builder=kiosk_builder,
        )
        router.mount_current_route()
        assert calls[0][0] == "kiosk"
        assert page.clean_calls == 1 and page.update_calls == 1


def test_home_remains_default_and_route_callback_switches_views() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    page = FakePage("/app/dashboard")
    home_builder, kiosk_builder = _builders(calls)
    router = AuthenticatedViewRouter(
        page=page,
        contexto_usuario={"usr_usuario_id": "test"},
        supabase=object(),
        session_controller=object(),
        home_builder=home_builder,
        kiosk_builder=kiosk_builder,
    )
    router.mount_current_route()
    assert [name for name, _kwargs in calls] == ["home", "start_eventos"]

    page.route = "/app/kiosk"
    calls[0][1]["on_authenticated_route_change"]()
    assert calls[-1][0] == "kiosk"

    page.route = "/app/dashboard"
    calls[-1][1]["on_authenticated_route_change"]()
    assert calls[-2][0] == "home"
    assert calls[-1][0] == "start_eventos"


def test_route_cleanup_and_login_use_the_shared_router() -> None:
    kiosk_source = (ROOT / "views" / "kiosk_view.py").read_text(encoding="utf-8")
    home_source = (ROOT / "views" / "home_view.py").read_text(encoding="utf-8")
    login_source = (ROOT / "views" / "login_view.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "await scanner.stop_scan()" in kiosk_source
    assert "on_authenticated_route_change()" in kiosk_source
    # Page.clean() no limpia Page.overlay: Home debe terminar su Camera antes
    # de entregar la ruta al builder de Kiosk.
    assert "_desmontar_scanner_overlay(on_complete=on_authenticated_route_change)" in home_source
    assert "if on_complete is not None:\n                        on_complete()" in home_source
    assert "AuthenticatedViewRouter" in login_source
    assert "AuthenticatedViewRouter" in app_source


def main() -> None:
    test_authenticated_target_selection()
    test_direct_entry_and_refresh_mount_kiosk()
    test_home_remains_default_and_route_callback_switches_views()
    test_route_cleanup_and_login_use_the_shared_router()
    print("Kiosk routing tests passed.")


if __name__ == "__main__":
    main()
