from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from views.kiosk_router import (
    KIOSK_STANDALONE_LOGIN_ROUTE,
    KIOSK_STANDALONE_ROUTE,
    KioskStandaloneRouter,
    is_kiosk_standalone_route,
    kiosk_standalone_access_message,
)


class FakePage:
    def __init__(self, route: str) -> None:
        self.route = route
        self.controls: list[object] = []
        self.navigation_bar: object | None = object()
        self.clean_calls = 0
        self.update_calls = 0
        self.scheduled_routes: list[str] = []

    def go(self, route: str) -> None:
        raise AssertionError(f"unsafe page.go() was called for {route}")

    async def push_route(self, route: str) -> None:
        self.scheduled_routes.append(route)
        self.route = route

    def run_task(self, handler: Any, *args: Any) -> object:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(handler(*args))
        return loop.create_task(handler(*args))

    def clean(self) -> None:
        self.clean_calls += 1
        self.controls.clear()

    def add(self, control: object) -> None:
        self.controls.append(control)

    def update(self) -> None:
        self.update_calls += 1


class FakeSession:
    def __init__(self, *, authenticated: bool, context: dict[str, Any] | None = None) -> None:
        self.authenticated = authenticated
        self.context = context
        self.logout_calls = 0

    def logout(self) -> None:
        self.logout_calls += 1
        self.authenticated = False
        self.context = None


def operative_context(role: str = "Operador") -> dict[str, Any]:
    event = {"cuenta_id": 2, "evento_id": 10, "rol": role, "estado": "Activo"}
    return {
        "usr_usuario_id": "user-1",
        "evento_actual": event,
        "eventos_permitidos": [dict(event)],
        "rol_global_calculado": role,
    }


def test_routes_are_explicit_and_do_not_claim_app_kiosk() -> None:
    assert is_kiosk_standalone_route("/kiosk")
    assert is_kiosk_standalone_route("/kiosk/login?next=/kiosk")
    assert not is_kiosk_standalone_route("/app/kiosk")


def test_unauthenticated_kiosk_redirects_to_dedicated_login() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    page = FakePage(KIOSK_STANDALONE_ROUTE)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=False),
        kiosk_login_builder=lambda **kwargs: calls.append(("login", kwargs)),
    )
    router.mount_current_route()
    assert page.route == KIOSK_STANDALONE_LOGIN_ROUTE
    assert page.scheduled_routes == [KIOSK_STANDALONE_LOGIN_ROUTE]
    assert calls and calls[0][0] == "login"
    assert calls[0][1]["on_authenticated"] == router.on_login_authenticated


def test_kiosk_login_without_session_stays_on_dedicated_login() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    page = FakePage(KIOSK_STANDALONE_LOGIN_ROUTE)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=False),
        kiosk_login_builder=lambda **kwargs: calls.append(("login", kwargs)),
    )
    router.mount_current_route()
    assert page.route == KIOSK_STANDALONE_LOGIN_ROUTE
    assert [name for name, _kwargs in calls] == ["login"]


def test_authenticated_kiosk_mounts_without_home_shell() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    page = FakePage(KIOSK_STANDALONE_ROUTE)
    context = operative_context()
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=True, context=context),
        kiosk_builder=lambda **kwargs: calls.append(("kiosk", kwargs)) or SimpleNamespace(data={}),
    )
    router.mount_current_route()
    assert [name for name, _kwargs in calls] == ["kiosk"]
    assert calls[0][1]["on_kiosk_logout"] == router.logout
    assert page.navigation_bar is None


def test_master_administrator_and_operator_can_mount_kiosk() -> None:
    for role in ("Master", "Administrador", "Operador"):
        calls: list[str] = []
        context = operative_context(role)
        if role == "Master":
            context["usr_es_usuario_master"] = True
        router = KioskStandaloneRouter(
            page=FakePage(KIOSK_STANDALONE_ROUTE),
            supabase=object(),
            session_controller=FakeSession(authenticated=True, context=context),
            kiosk_builder=lambda **kwargs: calls.append("kiosk") or SimpleNamespace(data={}),
        )
        router.mount_current_route()
        assert calls == ["kiosk"], role


def test_login_route_with_session_returns_to_kiosk() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    page = FakePage(KIOSK_STANDALONE_LOGIN_ROUTE)
    context = operative_context("Administrador")
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=True, context=context),
        kiosk_builder=lambda **kwargs: calls.append(("kiosk", kwargs)) or SimpleNamespace(data={}),
    )
    router.mount_current_route()
    assert page.route == KIOSK_STANDALONE_ROUTE
    assert page.scheduled_routes == [KIOSK_STANDALONE_ROUTE]
    assert [name for name, _kwargs in calls] == ["kiosk"]


def test_oauth_callback_returns_to_kiosk_without_dashboard() -> None:
    calls: list[str] = []
    page = FakePage(KIOSK_STANDALONE_LOGIN_ROUTE)
    session = FakeSession(authenticated=True)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=session,
        kiosk_builder=lambda **kwargs: calls.append("kiosk") or SimpleNamespace(data={}),
    )
    router.on_login_authenticated(operative_context())
    assert page.route == KIOSK_STANDALONE_ROUTE
    assert page.scheduled_routes == [KIOSK_STANDALONE_ROUTE]
    assert calls == ["kiosk"]


def test_sync_oauth_callback_schedules_push_route_without_running_loop() -> None:
    """Regression: Flet Page.go() uses create_task and fails from OAuth workers."""
    page = FakePage(KIOSK_STANDALONE_LOGIN_ROUTE)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=True),
        kiosk_builder=lambda **kwargs: SimpleNamespace(data={}),
    )
    router.on_login_authenticated(operative_context())
    assert page.scheduled_routes == [KIOSK_STANDALONE_ROUTE]
    assert page.route == KIOSK_STANDALONE_ROUTE


def test_post_auth_navigation_error_stays_in_kiosk_controlled_view() -> None:
    page = FakePage(KIOSK_STANDALONE_LOGIN_ROUTE)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=FakeSession(authenticated=True, context=operative_context()),
    )
    router.on_post_authentication_error(RuntimeError("route unavailable"))
    assert getattr(router.active_control, "data", {}).get("kiosk") == "standalone_unavailable"


def test_no_event_and_consulta_are_controlled_without_mounting_kiosk() -> None:
    assert kiosk_standalone_access_message({"usr_usuario_id": "user-1"}) == (
        "No hay un evento seleccionado para operar el Kiosco."
    )
    assert "Consulta" in (kiosk_standalone_access_message(operative_context("Consulta")) or "")
    for context in ({"usr_usuario_id": "user-1"}, operative_context("Consulta")):
        calls: list[str] = []
        router = KioskStandaloneRouter(
            page=FakePage(KIOSK_STANDALONE_ROUTE),
            supabase=object(),
            session_controller=FakeSession(authenticated=True, context=context),
            kiosk_builder=lambda **kwargs: calls.append("kiosk") or SimpleNamespace(data={}),
        )
        control = router.mount_current_route()
        assert calls == []
        assert getattr(control, "data", {}).get("kiosk") == "standalone_unavailable"
        labels = [getattr(item, "content", None) for item in control.content.controls]
        assert "Cerrar sesión" not in labels


def test_logout_pauses_kiosk_and_returns_only_to_kiosk_login() -> None:
    calls: list[str] = []
    session = FakeSession(authenticated=True, context=operative_context())
    page = FakePage(KIOSK_STANDALONE_ROUTE)
    router = KioskStandaloneRouter(
        page=page,
        supabase=object(),
        session_controller=session,
        kiosk_login_builder=lambda **kwargs: calls.append("login"),
    )
    router.active_control = SimpleNamespace(data={"pause_dashboard": lambda: calls.append("pause")})
    router.logout()
    assert calls == ["pause", "login"]
    assert session.logout_calls == 1
    assert page.route == KIOSK_STANDALONE_LOGIN_ROUTE


def test_sources_keep_app_kiosk_and_shared_google_oauth() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    kiosk_login_source = (ROOT / "views" / "kiosk_login_view.py").read_text(encoding="utf-8")
    kiosk_source = (ROOT / "views" / "kiosk_view.py").read_text(encoding="utf-8")
    assert "AuthenticatedViewRouter" in app_source
    assert "KioskStandaloneRouter" in app_source
    assert "build_login_view" in kiosk_login_source
    assert "Ingresar con Google" in kiosk_login_source
    assert "on_kiosk_logout" in kiosk_source
    assert '"standalone_logout"' not in kiosk_source
    router_source = (ROOT / "views" / "kiosk_router.py").read_text(encoding="utf-8")
    login_source = (ROOT / "views" / "login_view.py").read_text(encoding="utf-8")
    mount = router_source.index("control = self._mount(")
    assert mount < router_source.index("self._start_asset_prefetch(context)", mount)
    callback = login_source.index("if on_authenticated is not None:")
    home_mount = login_source.index("authenticated_router.mount_current_route()")
    home_shown = login_source.index('print("[HOME] Home mostrado")')
    assert callback < home_mount < home_shown


def main() -> None:
    test_routes_are_explicit_and_do_not_claim_app_kiosk()
    test_unauthenticated_kiosk_redirects_to_dedicated_login()
    test_kiosk_login_without_session_stays_on_dedicated_login()
    test_authenticated_kiosk_mounts_without_home_shell()
    test_master_administrator_and_operator_can_mount_kiosk()
    test_login_route_with_session_returns_to_kiosk()
    test_oauth_callback_returns_to_kiosk_without_dashboard()
    test_sync_oauth_callback_schedules_push_route_without_running_loop()
    test_post_auth_navigation_error_stays_in_kiosk_controlled_view()
    test_no_event_and_consulta_are_controlled_without_mounting_kiosk()
    test_logout_pauses_kiosk_and_returns_only_to_kiosk_login()
    test_sources_keep_app_kiosk_and_shared_google_oauth()
    print("Kiosk standalone router tests passed.")


if __name__ == "__main__":
    main()
