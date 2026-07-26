from __future__ import annotations

import asyncio
import contextlib
import io
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.session_service import (  # noqa: E402
    PageSessionController,
    SESSION_INVALID_MESSAGE,
)
from services.auth_service import (  # noqa: E402
    WEB_OAUTH_ATTEMPT_FAILED,
    WEB_OAUTH_ATTEMPT_WAITING_CALLBACK,
    WebOAuthAttempt,
)
from views.login_view import wait_for_supabase_session  # noqa: E402


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)


class FakePage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.session = SimpleNamespace(store=FakeStore())
        self.tasks: list[asyncio.Task[Any]] = []

    def run_task(self, handler: Any, *args: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(handler(*args))
        self.tasks.append(task)
        return task


class FakeSession:
    def __init__(self, user_id: str, *, expired: bool = False) -> None:
        self.user = SimpleNamespace(id=user_id, email=f"{user_id}@example.com")
        self.access_token = f"access-{user_id}"
        self.refresh_token = f"refresh-{user_id}"
        self.expired = expired


class FakeAuth:
    def __init__(
        self,
        name: str,
        session: FakeSession | None,
        *,
        refresh_fails: bool = False,
        refresh_delay: float = 0,
        peers: list["FakeAuth"] | None = None,
    ) -> None:
        self.name = name
        self.session = session
        self.refresh_fails = refresh_fails
        self.refresh_delay = refresh_delay
        self.refresh_calls = 0
        self.get_session_calls = 0
        self.sign_out_calls = 0
        self.sign_out_scopes: list[str] = []
        self.refresh_started = threading.Event()
        self.peers = peers
        if peers is not None:
            peers.append(self)

    def get_session(self) -> FakeSession | None:
        self.get_session_calls += 1
        if self.session is None:
            return None
        if self.session.expired:
            self.refresh_calls += 1
            self.refresh_started.set()
            if self.refresh_delay:
                time.sleep(self.refresh_delay)
            if self.refresh_fails:
                raise RuntimeError("invalid refresh token")
            self.session = FakeSession(self.session.user.id, expired=False)
        return self.session

    def get_user(self) -> Any:
        if self.session is None:
            return SimpleNamespace(user=None)
        return SimpleNamespace(user=self.session.user)

    def sign_out(self, options: dict[str, str] | None = None) -> None:
        self.sign_out_calls += 1
        scope = (options or {}).get("scope", "global")
        self.sign_out_scopes.append(scope)
        if scope == "global" and self.session is not None and self.peers is not None:
            user_id = self.session.user.id
            for peer in self.peers:
                if peer.session is not None and peer.session.user.id == user_id:
                    peer.session = None
        else:
            self.session = None


class FakeClient:
    def __init__(self, name: str, auth: FakeAuth) -> None:
        self.name = name
        self.auth = auth


def valid_context(user_id: str) -> dict[str, Any]:
    return {
        "usr_usuario_auth_uuid": user_id,
        "usr_usuario_id": f"internal-{user_id}",
        "usr_estado": "Activo",
        "cuentas_permitidas": [{"cuenta_id": 1, "estado": "Activo"}],
        "eventos_permitidos": [
            {"cuenta_id": 1, "evento_id": 10, "estado": "Activo"}
        ],
        "cuenta_actual": {"cuenta_id": 1, "estado": "Activo"},
        "evento_actual": {"cuenta_id": 1, "evento_id": 10, "estado": "Activo"},
    }


def make_controller(
    name: str,
    *,
    session: FakeSession | None,
    refresh_fails: bool = False,
    refresh_delay: float = 0,
    context: dict[str, Any] | None = None,
    peers: list[FakeAuth] | None = None,
) -> tuple[FakePage, FakeClient, PageSessionController]:
    page = FakePage(name)
    auth = FakeAuth(
        name,
        session,
        refresh_fails=refresh_fails,
        refresh_delay=refresh_delay,
        peers=peers,
    )
    client = FakeClient(name, auth)
    selected_context = context

    def load_context(_client: Any, user_id: str) -> dict[str, Any]:
        return selected_context if selected_context is not None else valid_context(user_id)

    return page, client, PageSessionController(
        page,
        client,
        context_loader=load_context,
    )


def assert_valid_and_missing_sessions() -> None:
    page, _, controller = make_controller(
        "valid",
        session=FakeSession("user-valid"),
    )
    result = controller.validate_current_session(claim_home=True)
    assert result.ok and result.should_build_home
    assert result.user.id == "user-valid"
    assert page.session.store.values["usuario_contexto"]["usr_estado"] == "Activo"

    missing_page, _, missing = make_controller("missing", session=None)
    missing_result = missing.validate_current_session(claim_home=True)
    assert not missing_result.ok
    assert not missing.authenticated
    assert "usuario_contexto" not in missing_page.session.store.values


def assert_refresh_behavior() -> None:
    _, client, controller = make_controller(
        "fresh",
        session=FakeSession("user-fresh"),
    )
    assert controller.validate_current_session().ok
    assert client.auth.refresh_calls == 0

    _, expired_client, expired = make_controller(
        "expired",
        session=FakeSession("user-expired", expired=True),
    )
    result = expired.validate_current_session(claim_home=True)
    assert result.ok and result.user.id == "user-expired"
    assert result.should_build_home
    assert expired_client.auth.refresh_calls == 1

    invalid_page, invalid_client, invalid = make_controller(
        "invalid-refresh",
        session=FakeSession("user-invalid", expired=True),
        refresh_fails=True,
    )
    invalid_page.session.store.set("usuario_contexto", {"stale": True})
    invalid_result = invalid.validate_current_session(claim_home=True)
    assert not invalid_result.ok
    assert invalid_result.message == SESSION_INVALID_MESSAGE
    assert invalid_client.auth.refresh_calls == 1
    assert "usuario_contexto" not in invalid_page.session.store.values


async def assert_refresh_concurrency_and_page_isolation() -> None:
    _, client, controller = make_controller(
        "concurrent",
        session=FakeSession("user-concurrent", expired=True),
        refresh_delay=0.03,
    )
    results = await asyncio.gather(
        *[
            asyncio.to_thread(controller.validate_current_session)
            for _ in range(4)
        ]
    )
    assert all(result.ok for result in results)
    assert client.auth.refresh_calls == 1

    _, client_a, controller_a = make_controller(
        "A",
        session=FakeSession("user-A", expired=True),
    )
    _, client_b, controller_b = make_controller(
        "B",
        session=FakeSession("user-B", expired=True),
    )
    result_a, result_b = await asyncio.gather(
        asyncio.to_thread(controller_a.validate_current_session),
        asyncio.to_thread(controller_b.validate_current_session),
    )
    assert result_a.user.id == "user-A"
    assert result_b.user.id == "user-B"
    assert client_a.auth.refresh_calls == 1
    assert client_b.auth.refresh_calls == 1


async def assert_logout_and_late_refresh() -> None:
    shared_auths: list[FakeAuth] = []
    _, client_a, controller_a = make_controller(
        "logout-A",
        session=FakeSession("same-user"),
        peers=shared_auths,
    )
    _, client_b, controller_b = make_controller(
        "logout-B",
        session=FakeSession("same-user"),
        peers=shared_auths,
    )
    assert controller_a.validate_current_session().ok
    assert controller_b.validate_current_session().ok
    controller_a.logout()
    assert client_a.auth.sign_out_calls == 1
    assert client_a.auth.sign_out_scopes == ["local"]
    assert client_b.auth.sign_out_calls == 0
    assert controller_b.authenticated
    assert controller_b.validate_current_session(load_context=False).ok

    global_auths: list[FakeAuth] = []
    _, global_client_a, global_a = make_controller(
        "global-A",
        session=FakeSession("global-user"),
        peers=global_auths,
    )
    _, global_client_b, global_b = make_controller(
        "global-B",
        session=FakeSession("global-user"),
        peers=global_auths,
    )
    assert global_a.validate_current_session().ok
    assert global_b.validate_current_session().ok
    global_a.logout_global()
    assert global_client_a.auth.sign_out_scopes == ["global"]
    assert global_client_b.auth.session is None
    assert not global_b.validate_current_session(load_context=False).ok

    _, late_client, late = make_controller(
        "late",
        session=FakeSession("user-late", expired=True),
        refresh_delay=0.05,
    )
    validation_task = asyncio.create_task(
        asyncio.to_thread(
            late.validate_current_session,
            claim_home=True,
        )
    )
    await asyncio.to_thread(late_client.auth.refresh_started.wait, 1)
    logout_task = asyncio.create_task(asyncio.to_thread(late.logout))
    result = await validation_task
    await logout_task
    assert not result.ok
    assert not result.should_build_home
    assert not late.authenticated


async def assert_single_home_claim_and_invalid_contexts() -> None:
    _, _, controller = make_controller(
        "claim",
        session=FakeSession("user-claim"),
    )
    first, second = await asyncio.gather(
        asyncio.to_thread(
            controller.validate_current_session,
            claim_home=True,
        ),
        asyncio.to_thread(
            controller.validate_current_session,
            claim_home=True,
        ),
    )
    assert sum(result.should_build_home for result in (first, second)) == 1

    wrong_context = valid_context("another-user")
    _, _, wrong = make_controller(
        "wrong",
        session=FakeSession("real-user"),
        context=wrong_context,
    )
    assert not wrong.validate_current_session(claim_home=True).ok

    inactive_context = valid_context("inactive-user")
    inactive_context["usr_estado"] = "Inactivo"
    _, _, inactive = make_controller(
        "inactive",
        session=FakeSession("inactive-user"),
        context=inactive_context,
    )
    inactive_result = inactive.validate_current_session(claim_home=True)
    assert not inactive_result.ok
    assert "contexto" in inactive_result.message


async def assert_no_client_storage_tokens_logs_and_task_cleanup() -> None:
    page, _, controller = make_controller(
        "secure",
        session=FakeSession("user-secure"),
    )
    access_token = "access-user-secure"
    refresh_token = "refresh-user-secure"
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        assert controller.validate_current_session().ok
    serialized_store = repr(page.session.store.values)
    assert access_token not in serialized_store
    assert refresh_token not in serialized_store
    assert access_token not in output.getvalue()
    assert refresh_token not in output.getvalue()
    assert not hasattr(page, "client_storage")

    controller.start_refresh_monitor(lambda _message: None, interval_seconds=60)
    assert page.tasks and not page.tasks[0].done()
    controller.logout()
    await asyncio.sleep(0)
    assert page.tasks[0].cancelled()

    close_page, _, close_controller = make_controller(
        "close",
        session=FakeSession("user-close"),
    )
    close_controller.validate_current_session()
    close_controller.start_refresh_monitor(
        lambda _message: None,
        interval_seconds=60,
    )
    close_controller.close()
    await asyncio.sleep(0)
    assert close_page.tasks[0].cancelled()


def assert_no_cross_page_restoration() -> None:
    _, _, controller_a = make_controller(
        "restore-A",
        session=FakeSession("user-A"),
    )
    _, _, controller_b = make_controller("restore-B", session=None)
    assert controller_a.validate_current_session().user.id == "user-A"
    assert not controller_b.validate_current_session().ok
    assert controller_b.user is None


def assert_residual_session_cleanup() -> None:
    page, client, controller = make_controller(
        "residual",
        session=FakeSession("residual-user"),
    )
    page.session.store.set("usuario_contexto", {"stale": True})
    assert not controller.authenticated
    assert controller.clear_residual_session()
    assert client.auth.session is None
    assert client.auth.sign_out_scopes == ["local"]
    assert "usuario_contexto" not in page.session.store.values

    invalid_context = valid_context("context-user")
    invalid_context["usr_estado"] = "Inactivo"
    _, invalid_client, invalid = make_controller(
        "context-failure",
        session=FakeSession("context-user"),
        context=invalid_context,
    )
    result = invalid.validate_current_session(claim_home=True)
    assert not result.ok
    invalid.logout()
    assert invalid_client.auth.session is None
    assert invalid_client.auth.sign_out_scopes == ["local"]


async def assert_short_session_retry_and_oauth_reconnection() -> None:
    page, client, controller = make_controller("delayed", session=None)
    checks = 0

    def delayed_get_session() -> FakeSession | None:
        nonlocal checks
        checks += 1
        if checks == 3:
            client.auth.session = FakeSession("delayed-user")
        return client.auth.session

    client.auth.get_session = delayed_get_session  # type: ignore[method-assign]
    attempt = WebOAuthAttempt(page)
    attempt.mark_waiting_callback()
    attempt.mark_callback_received(has_error=False)
    assert await wait_for_supabase_session(
        controller,
        attempt,
        retries=4,
        delay_seconds=0.001,
    )
    assert checks == 3

    missing_page, _, missing_controller = make_controller(
        "still-missing",
        session=None,
    )
    missing_attempt = WebOAuthAttempt(missing_page)
    missing_attempt.mark_waiting_callback()
    missing_attempt.mark_callback_received(has_error=False)
    assert not await wait_for_supabase_session(
        missing_controller,
        missing_attempt,
        retries=3,
        delay_seconds=0.001,
    )
    assert missing_attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
    assert missing_attempt.status == WEB_OAUTH_ATTEMPT_FAILED
    assert missing_attempt.status != WEB_OAUTH_ATTEMPT_WAITING_CALLBACK

    reconnect_page, _, reconnect_controller = make_controller(
        "reconnect-oauth",
        session=None,
    )
    reconnect_attempt = WebOAuthAttempt(reconnect_page)
    reconnect_controller.register_oauth_attempt(reconnect_attempt)
    reconnect_controller.set_connected(False)
    reconnect_controller.set_connected(True)
    assert reconnect_controller.current_oauth_attempt is reconnect_attempt


async def main_async() -> None:
    assert_valid_and_missing_sessions()
    assert_refresh_behavior()
    await assert_refresh_concurrency_and_page_isolation()
    await assert_logout_and_late_refresh()
    await assert_single_home_claim_and_invalid_contexts()
    await assert_no_client_storage_tokens_logs_and_task_cleanup()
    assert_no_cross_page_restoration()
    assert_residual_session_cleanup()
    await assert_short_session_retry_and_oauth_reconnection()


def main() -> int:
    asyncio.run(main_async())
    print(
        "OK - web session validation, refresh, logout, concurrency, "
        "task cleanup, and Page isolation tests passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
