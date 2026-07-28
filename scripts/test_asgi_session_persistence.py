from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import sys
import threading
import time
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=StarletteDeprecationWarning,
)
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asgi  # noqa: E402
from config import (  # noqa: E402
    EVENTPLUS_SESSION_COOKIE_NAME,
    EVENTPLUS_SESSION_COOKIE_SAMESITE,
    EVENTPLUS_SESSION_COOKIE_SECURE,
)
from services.server_session_service import (  # noqa: E402
    EventPlusSessionMiddleware,
    InMemorySessionRepository,
    ServerSessionBinding,
    create_server_session_binding,
)
from services.session_service import PageSessionController  # noqa: E402
from views import home_view  # noqa: E402


class FakeSession:
    def __init__(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.access_token = access_token
        self.refresh_token = refresh_token


class FakeAuth:
    def __init__(self, session: FakeSession | None = None) -> None:
        self.session = session
        self.set_session_calls = 0
        self.get_session_calls = 0
        self.sign_out_calls: list[dict[str, str] | None] = []
        self.delay = 0.0

    def get_session(self) -> FakeSession | None:
        self.get_session_calls += 1
        return self.session

    def set_session(self, access_token: str, refresh_token: str) -> Any:
        self.set_session_calls += 1
        if self.delay:
            time.sleep(self.delay)
        user_id = access_token.split("-", 1)[0]
        self.session = FakeSession(user_id, access_token, refresh_token)
        return SimpleNamespace(session=self.session)

    def get_user(self) -> Any:
        return SimpleNamespace(
            user=self.session.user if self.session is not None else None
        )

    def sign_out(self, options: dict[str, str] | None = None) -> None:
        self.sign_out_calls.append(options)
        self.session = None


class FakeClient:
    def __init__(self, session: FakeSession | None = None) -> None:
        self.auth = FakeAuth(session)


class FakePage:
    def __init__(self) -> None:
        self.web = True


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)


class ControllerPage(FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.session = SimpleNamespace(store=FakeStore())


class FakeServerBinding:
    def __init__(self) -> None:
        self.opaque_id = "opaque-test"
        self.delete_calls = 0

    def restore_and_run(self, _client: Any, operation: Any) -> Any:
        return operation()

    def persist_login(self, _client: Any) -> bool:
        return True

    def delete(self) -> None:
        self.delete_calls += 1
        self.opaque_id = None

    def close(self) -> None:
        return


def make_cookie_app(
    repository: InMemorySessionRepository,
    login_client: FakeClient,
) -> FastAPI:
    app = FastAPI()

    @app.get("/login-test")
    async def login_test() -> dict[str, bool]:
        binding = create_server_session_binding(repository, FakePage())
        return {"created": binding.persist_login(login_client)}

    @app.get("/restore-test")
    async def restore_test(request: Request) -> dict[str, Any]:
        del request
        client = FakeClient()
        binding = create_server_session_binding(repository, FakePage())
        restored = (
            binding.restore_and_run(
                client,
                lambda: SimpleNamespace(ok=True),
            )
            if binding.opaque_id
            else None
        )
        return {
            "restored": restored is not None,
            "client": id(client),
            "set_session_calls": client.auth.set_session_calls,
        }

    @app.get("/logout-test")
    async def logout_test() -> JSONResponse:
        binding = create_server_session_binding(repository, FakePage())
        binding.delete()
        return JSONResponse({"logged_out": True})

    app.add_middleware(EventPlusSessionMiddleware, repository=repository)
    return app


def assert_asgi_health_and_routes() -> None:
    with TestClient(asgi.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    outer_paths = {getattr(route, "path", "") for route in asgi.app.routes}
    assert "/health" in outer_paths
    assert "/session/logout" in outer_paths
    flet_outer_mount = next(
        route for route in asgi.app.routes if getattr(route, "path", None) == ""
    )
    exported_paths = {
        getattr(route, "path", "") for route in flet_outer_mount.app.routes
    }
    assert "" in exported_paths
    inner_mount = next(
        route
        for route in flet_outer_mount.app.routes
        if getattr(route, "path", None) == ""
    )
    inner_paths = {getattr(route, "path", "") for route in inner_mount.app.routes}
    assert "/ws" in inner_paths
    assert "/auth/callback" in inner_paths


def assert_cookie_creation_properties_and_rotation() -> str:
    repository = InMemorySessionRepository()
    access_token = "access-userA-sensitive"
    refresh_token = "refresh-userA-sensitive"
    login_client = FakeClient(
        FakeSession("userA", access_token, refresh_token)
    )
    cookie_app = make_cookie_app(repository, login_client)
    with TestClient(cookie_app) as client:
        response = client.get("/login-test")
        assert response.status_code == 200
        set_cookie = response.headers["set-cookie"]
        opaque_id = client.cookies.get(EVENTPLUS_SESSION_COOKIE_NAME)
        assert opaque_id
        assert "HttpOnly" in set_cookie
        assert "Path=/" in set_cookie
        assert f"SameSite={EVENTPLUS_SESSION_COOKIE_SAMESITE}" in set_cookie
        assert ("Secure" in set_cookie) is EVENTPLUS_SESSION_COOKIE_SECURE
        for sensitive in (
            access_token,
            refresh_token,
            "userA",
            "example.com",
        ):
            assert sensitive not in opaque_id
            assert sensitive not in set_cookie

        old_id = opaque_id
        rotated = repository.rotate(old_id)
        assert rotated is not None
        assert rotated.opaque_id != old_id
        assert repository.get(old_id) is None
        assert repository.get(rotated.opaque_id) is not None
        return rotated.opaque_id


def assert_restore_pages_logout_and_unknown_cookie() -> None:
    repository = InMemorySessionRepository()
    login_client = FakeClient(
        FakeSession("shared", "shared-access", "shared-refresh")
    )
    cookie_app = make_cookie_app(repository, login_client)
    with TestClient(cookie_app) as browser:
        browser.get("/login-test")
        opaque_id = browser.cookies.get(EVENTPLUS_SESSION_COOKIE_NAME)
        assert opaque_id
        first = browser.get("/restore-test").json()
        second = browser.get("/restore-test").json()
        assert first["restored"] and second["restored"]
        assert first["set_session_calls"] == 1
        assert second["set_session_calls"] == 1
        assert first["client"] != second["client"]
        record = repository.get(opaque_id)
        assert record is not None
        assert len(record.bound_pages) >= 2

        logout_response = browser.get("/logout-test")
        assert logout_response.status_code == 200
        assert repository.get(opaque_id) is None
        assert EVENTPLUS_SESSION_COOKIE_NAME not in browser.cookies

    with TestClient(cookie_app) as anonymous:
        anonymous.cookies.set(EVENTPLUS_SESSION_COOKIE_NAME, "unknown")
        response = anonymous.get("/restore-test")
        assert not response.json()["restored"]
        assert "Max-Age=0" in response.headers["set-cookie"]


def assert_expiry_revocation_and_repository_restart() -> None:
    now = [1000.0]
    repository = InMemorySessionRepository(clock=lambda: now[0])
    record = repository.create(
        access_token="access-expiring",
        refresh_token="refresh-expiring",
        auth_user_id="expiring",
        ttl_seconds=60,
    )
    now[0] += 61
    assert repository.get(record.opaque_id) is None

    revoked = repository.create(
        access_token="access-revoked",
        refresh_token="refresh-revoked",
        auth_user_id="revoked",
        ttl_seconds=60,
    )
    repository.delete(revoked.opaque_id)
    assert repository.get(revoked.opaque_id) is None

    old_repository = InMemorySessionRepository()
    existing = old_repository.create(
        access_token="access-restart",
        refresh_token="refresh-restart",
        auth_user_id="restart",
        ttl_seconds=60,
    )
    restarted_repository = InMemorySessionRepository()
    restarted_app = make_cookie_app(restarted_repository, FakeClient())
    with TestClient(restarted_app) as browser:
        browser.cookies.set(
            EVENTPLUS_SESSION_COOKIE_NAME,
            existing.opaque_id,
        )
        response = browser.get("/restore-test")
        assert not response.json()["restored"]
        assert "Max-Age=0" in response.headers["set-cookie"]


async def assert_concurrent_refresh_and_stale_write_protection() -> None:
    repository = InMemorySessionRepository()
    record = repository.create(
        access_token="shared-v1",
        refresh_token="refresh-v1",
        auth_user_id="shared",
        ttl_seconds=300,
    )
    clients = [FakeClient(), FakeClient()]
    for client in clients:
        client.auth.delay = 0.02
    bindings = [
        ServerSessionBinding(repository, FakePage(), record.opaque_id)
        for _ in clients
    ]
    active = 0
    max_active = 0
    active_lock = threading.Lock()

    def operation(index: int) -> SimpleNamespace:
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            current = clients[index].auth.session
            assert current is not None
            clients[index].auth.session = FakeSession(
                "shared",
                f"shared-v{index + 2}",
                f"refresh-v{index + 2}",
            )
            time.sleep(0.02)
            return SimpleNamespace(ok=True)
        finally:
            with active_lock:
                active -= 1

    results = await asyncio.gather(
        *[
            asyncio.to_thread(
                bindings[index].restore_and_run,
                clients[index],
                lambda index=index: operation(index),
            )
            for index in range(2)
        ]
    )
    assert all(result is not None for result in results)
    assert max_active == 1
    latest = repository.get(record.opaque_id)
    assert latest is not None and latest.version == 3
    stale = repository.update(
        record.opaque_id,
        access_token="stale-access",
        refresh_token="stale-refresh",
        auth_user_id="shared",
        expected_version=1,
    )
    assert stale is None
    assert repository.get(record.opaque_id).access_token != "stale-access"


def assert_distinct_sessions_and_safe_logs() -> None:
    repository = InMemorySessionRepository()
    first = repository.create(
        access_token="secret-access-A",
        refresh_token="secret-refresh-A",
        auth_user_id="A",
        ttl_seconds=300,
    )
    second = repository.create(
        access_token="secret-access-B",
        refresh_token="secret-refresh-B",
        auth_user_id="B",
        ttl_seconds=300,
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        repository.delete(first.opaque_id)
    assert repository.get(first.opaque_id) is None
    assert repository.get(second.opaque_id) is not None
    captured = output.getvalue()
    assert "secret-access" not in captured
    assert "secret-refresh" not in captured

    sources = "\n".join(
        [
            (ROOT / "app.py").read_text(encoding="utf-8"),
            (ROOT / "asgi.py").read_text(encoding="utf-8"),
            (ROOT / "services" / "server_session_service.py").read_text(
                encoding="utf-8"
            ),
        ]
    )
    for forbidden in ("client_storage", "localStorage", "sessionStorage"):
        assert forbidden not in sources


def assert_logout_endpoint() -> None:
    record = asgi.session_repository.create(
        access_token="endpoint-access",
        refresh_token="endpoint-refresh",
        auth_user_id="endpoint-user",
        ttl_seconds=300,
    )
    with TestClient(asgi.app) as client:
        client.cookies.set(EVENTPLUS_SESSION_COOKIE_NAME, record.opaque_id)
        response = client.get("/session/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "Max-Age=0" in response.headers["set-cookie"]
    assert asgi.session_repository.get(record.opaque_id) is None


def assert_controller_logout_is_terminal_local_and_idempotent() -> None:
    page = ControllerPage()
    session = FakeSession("local-user", "local-access", "local-refresh")
    client = FakeClient(session)
    binding = FakeServerBinding()
    context = {
        "usr_usuario_auth_uuid": "local-user",
        "usr_estado": "Activo",
        "cuentas_permitidas": [{"cuenta_id": 1}],
        "cuenta_actual": {"cuenta_id": 1},
        "eventos_permitidos": [],
        "evento_actual": None,
    }
    controller = PageSessionController(
        page,
        client,
        context_loader=lambda _client, _user_id: context,
        server_session_binding=binding,
    )
    assert controller.validate_current_session().ok
    page.session.store.set("diagnostico_login", "stale")
    assert controller.logout()
    assert not controller.authenticated
    assert not controller.logging_out
    assert binding.delete_calls == 1
    assert client.auth.sign_out_calls == [{"scope": "local"}]
    assert page.session.store.values == {}
    assert not controller.logout()
    assert binding.delete_calls == 1
    assert client.auth.sign_out_calls == [{"scope": "local"}]


async def assert_same_page_home_unmounted_and_self_navigation() -> None:
    source = inspect.getsource(home_view.build_home_view)
    assert "page.launch_url" not in source
    assert "web_only_window_name=ft.UrlTarget.SELF" in source

    class UiPage(ControllerPage):
        def __init__(self) -> None:
            super().__init__()
            self.platform = "windows"
            self.navigation_bar: Any = None
            self.clean_calls = 0
            self.added: list[Any] = []
            self.tasks: list[asyncio.Task[Any]] = []

        def clean(self) -> None:
            self.clean_calls += 1
            self.added.clear()

        def add(self, *controls: Any) -> None:
            self.added.extend(controls)

        def update(self) -> None:
            return

        def run_task(self, handler: Any, *args: Any) -> asyncio.Task[Any]:
            task = asyncio.create_task(handler(*args))
            self.tasks.append(task)
            return task

    class UiController:
        def __init__(self) -> None:
            self.has_server_session = True
            self.authenticated = True
            self.logout_calls = 0

        def logout(self) -> bool:
            self.logout_calls += 1
            self.authenticated = False
            return self.logout_calls == 1

    launches: list[tuple[str, Any]] = []

    class FakeUrlLauncher:
        async def launch_url(
            self,
            url: str,
            *,
            web_only_window_name: Any = None,
            **_kwargs: Any,
        ) -> None:
            launches.append((url, web_only_window_name))

    page = UiPage()
    controller = UiController()
    context = {
        "usr_nombre_usuario": "Usuario",
        "rol_global_calculado": "Administrador",
        "cuenta_actual": {"cuenta_id": 1, "nombre_cuenta": "Cuenta"},
        "evento_actual": None,
        "cuentas_permitidas": [{"cuenta_id": 1}],
        "eventos_permitidos": [],
        "puede_registrar_llegadas": False,
    }
    original_launcher = home_view.ft.UrlLauncher
    try:
        home_view.ft.UrlLauncher = FakeUrlLauncher
        home = home_view.build_home_view(
            page,
            context,
            supabase=FakeClient(),
            session_controller=controller,  # type: ignore[arg-type]
        )
        page.add(home)

        def find_logout(control: Any) -> Any:
            items = getattr(control, "items", None) or []
            for item in items:
                if getattr(item, "content", None) == "Salir":
                    return item
            children: list[Any] = []
            content = getattr(control, "content", None)
            if content is not None and not isinstance(content, str):
                children.append(content)
            children.extend(getattr(control, "controls", None) or [])
            children.extend(items)
            for child in children:
                found = find_logout(child)
                if found is not None:
                    return found
            return None

        logout_item = find_logout(home)
        assert logout_item is not None
        logout_item.on_click(SimpleNamespace())
        assert controller.logout_calls == 1
        assert not controller.authenticated
        assert page.clean_calls >= 1
        assert page.added
        assert page.added[-1] is not home
        await asyncio.gather(*page.tasks)
    finally:
        home_view.ft.UrlLauncher = original_launcher

    assert launches == [("/session/logout", home_view.ft.UrlTarget.SELF)]


async def assert_logout_wins_shared_cookie_races() -> None:
    repository = InMemorySessionRepository()
    shared = repository.create(
        access_token="shared-access",
        refresh_token="shared-refresh",
        auth_user_id="shared",
        ttl_seconds=300,
    )
    page_a = FakePage()
    page_b = FakePage()
    binding_a = ServerSessionBinding(repository, page_a, shared.opaque_id)
    binding_b = ServerSessionBinding(repository, page_b, shared.opaque_id)
    client_b = FakeClient()
    client_b.auth.delay = 0.03
    started = threading.Event()

    def slow_restore() -> SimpleNamespace:
        started.set()
        time.sleep(0.03)
        return SimpleNamespace(ok=True)

    restore_task = asyncio.create_task(
        asyncio.to_thread(
            binding_b.restore_and_run,
            client_b,
            slow_restore,
        )
    )
    await asyncio.to_thread(started.wait, 1)
    logout_task = asyncio.create_task(asyncio.to_thread(binding_a.delete))
    await asyncio.gather(restore_task, logout_task)
    assert repository.get(shared.opaque_id) is None
    assert binding_b.restore_and_run(
        client_b,
        lambda: SimpleNamespace(ok=True),
    ) is None
    assert repository.get(shared.opaque_id) is None

    independent = repository.create(
        access_token="other-access",
        refresh_token="other-refresh",
        auth_user_id="other",
        ttl_seconds=300,
    )
    binding_a.delete()
    assert repository.get(independent.opaque_id) is not None


async def main_async() -> None:
    assert_asgi_health_and_routes()
    assert_cookie_creation_properties_and_rotation()
    assert_restore_pages_logout_and_unknown_cookie()
    assert_expiry_revocation_and_repository_restart()
    await assert_concurrent_refresh_and_stale_write_protection()
    assert_distinct_sessions_and_safe_logs()
    assert_logout_endpoint()
    assert_controller_logout_is_terminal_local_and_idempotent()
    await assert_same_page_home_unmounted_and_self_navigation()
    await assert_logout_wins_shared_cookie_races()


def main() -> int:
    asyncio.run(main_async())
    print(
        "OK - ASGI health/routes, opaque HttpOnly cookies, server sessions, "
        "restore, rotation, concurrency, logout, restart, and safe logs passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
