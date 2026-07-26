from __future__ import annotations

import asyncio
import contextlib
import io
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services.auth_service as auth_service
import views.login_view as login_view


class FakeAuth:
    def __init__(self, name: str) -> None:
        self.name = name
        self.redirect_urls: list[str] = []
        self.exchanged_codes: list[str] = []
        self.user_id = f"auth-{name}"
        self.session: Any = None
        self.sign_out_scopes: list[str] = []
        self.exchange_delay = 0.0
        self.exchange_started = threading.Event()
        self.oauth_credentials: list[dict[str, Any]] = []

    def sign_in_with_oauth(self, credentials: dict[str, Any]) -> Any:
        self.oauth_credentials.append(credentials)
        self.session = None
        redirect_url = credentials["options"]["redirect_to"]
        self.redirect_urls.append(redirect_url)
        return SimpleNamespace(
            url=f"https://supabase.example/authorize?session={self.name}"
        )

    def exchange_code_for_session(self, params: dict[str, str]) -> Any:
        self.exchange_started.set()
        if self.exchange_delay:
            time.sleep(self.exchange_delay)
        self.exchanged_codes.append(params["auth_code"])
        self.session = SimpleNamespace(
            user=SimpleNamespace(id=self.user_id),
            access_token=f"access-{self.name}",
            refresh_token=f"refresh-{self.name}",
        )
        return SimpleNamespace(session=self.session)

    def get_session(self) -> Any:
        return self.session

    def get_user(self) -> Any:
        return SimpleNamespace(
            user=SimpleNamespace(id=self.user_id, email=f"{self.name}@example.com")
        )

    def sign_out(self, options: dict[str, str] | None = None) -> None:
        self.sign_out_scopes.append((options or {}).get("scope", "global"))
        self.session = None


class FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.auth = FakeAuth(name)


class FakePage:
    def __init__(self, *, web: bool, platform: str) -> None:
        self.web = web
        self.platform = platform
        self.login_calls = 0
        self.authorization: auth_service.SupabaseWebAuthorization | None = None
        self.added_controls: list[Any] = []
        self.background_tasks: list[asyncio.Task[Any]] = []
        self.update_calls = 0
        self.navigation_bar = None
        self.on_login: Any = None
        self.on_login_was_set_at_login = False

    async def login(
        self,
        provider: Any,
        *,
        fetch_user: bool,
        fetch_groups: bool,
        authorization: type[auth_service.SupabaseWebAuthorization],
    ) -> Any:
        self.login_calls += 1
        self.on_login_was_set_at_login = self.on_login is not None
        self.authorization = authorization(
            provider,
            fetch_user=fetch_user,
            fetch_groups=fetch_groups,
        )
        self.authorization.get_authorization_data()
        return self.authorization

    def add(self, *controls: Any) -> None:
        self.added_controls.extend(controls)

    def update(self) -> None:
        self.update_calls += 1

    def run_task(self, handler: Any, *args: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(handler(*args))
        self.background_tasks.append(task)
        return task


def find_control(root: Any, *, content: str) -> Any:
    visited: set[int] = set()

    def visit(control: Any) -> Any:
        if control is None or id(control) in visited:
            return None
        visited.add(id(control))
        if getattr(control, "content", None) == content:
            return control
        nested = []
        controls = getattr(control, "controls", None)
        if controls:
            nested.extend(controls)
        child = getattr(control, "content", None)
        if child is not None and not isinstance(child, str):
            nested.append(child)
        for item in nested:
            found = visit(item)
            if found is not None:
                return found
        return None

    return visit(root)


def assert_platform_strategies() -> None:
    web = FakePage(web=True, platform="windows")
    desktop = FakePage(web=False, platform="windows")
    android = FakePage(web=False, platform="android")
    assert auth_service.detect_oauth_strategy(web) == auth_service.OAUTH_STRATEGY_WEB
    assert (
        auth_service.detect_oauth_strategy(desktop)
        == auth_service.OAUTH_STRATEGY_DESKTOP
    )
    assert (
        auth_service.detect_oauth_strategy(android)
        == auth_service.OAUTH_STRATEGY_ANDROID
    )


async def create_web_attempt(
    name: str,
) -> tuple[FakePage, FakeClient, auth_service.SupabaseWebAuthorization]:
    page = FakePage(web=True, platform="windows")
    client = FakeClient(name)
    authorization = await auth_service.start_web_oauth(
        page,
        client,
        redirect_url="http://127.0.0.1:8550/auth/callback",
    )
    assert page.login_calls == 1
    assert authorization is page.authorization
    return page, client, authorization


async def create_managed_web_attempt(
    name: str,
) -> tuple[
    FakePage,
    FakeClient,
    auth_service.WebOAuthAttempt,
    auth_service.SupabaseWebAuthorization,
]:
    page = FakePage(web=True, platform="windows")
    client = FakeClient(name)
    attempt = auth_service.WebOAuthAttempt(page)
    authorization = await auth_service.start_web_oauth(
        page,
        client,
        redirect_url="http://127.0.0.1:8550/auth/callback",
        attempt=attempt,
    )
    return page, client, attempt, authorization


async def assert_web_does_not_use_desktop_callback_resources() -> None:
    original_http_server = auth_service.HTTPServer
    original_queue = auth_service.OAuthCallbackHandler.result_queue
    original_webbrowser_open = login_view.webbrowser.open
    http_server_calls = 0
    webbrowser_calls = 0

    def forbidden_http_server(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        nonlocal http_server_calls
        http_server_calls += 1
        raise AssertionError("Web no debe iniciar HTTPServer")

    class ForbiddenQueue:
        def get(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            raise AssertionError("Web no debe consultar result_queue")

        def put(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            raise AssertionError("Web no debe escribir result_queue")

    def forbidden_webbrowser_open(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        nonlocal webbrowser_calls
        webbrowser_calls += 1
        raise AssertionError("Web no debe usar webbrowser.open")

    try:
        auth_service.HTTPServer = forbidden_http_server
        auth_service.OAuthCallbackHandler.result_queue = ForbiddenQueue()
        login_view.webbrowser.open = forbidden_webbrowser_open
        await create_web_attempt("A")
    finally:
        auth_service.HTTPServer = original_http_server
        auth_service.OAuthCallbackHandler.result_queue = original_queue
        login_view.webbrowser.open = original_webbrowser_open

    assert http_server_calls == 0
    assert webbrowser_calls == 0


async def assert_state_session_and_client_isolation() -> None:
    _, client_a, auth_a = await create_web_attempt("A")
    _, client_b, auth_b = await create_web_attempt("B")
    assert auth_a.state
    assert auth_b.state
    assert auth_a.state != auth_b.state

    redirect_a = client_a.auth.redirect_urls[0]
    redirect_b = client_b.auth.redirect_urls[0]
    assert parse_qs(urlparse(redirect_a).query)["state"] == [auth_a.state]
    assert parse_qs(urlparse(redirect_b).query)["state"] == [auth_b.state]
    assert client_a.auth.oauth_credentials[0]["options"]["query_params"] == {
        "prompt": "select_account"
    }

    auth_a.validate_callback_state(auth_a.state)
    auth_b.validate_callback_state(auth_b.state)

    try:
        auth_b.validate_callback_state(auth_a.state)
    except ValueError as ex:
        assert "no corresponde" in str(ex)
    else:
        raise AssertionError("El state de A no debe ser aceptado por B")

    await auth_a.request_token("code-A")
    assert client_a.auth.exchanged_codes == ["code-A"]
    assert client_b.auth.exchanged_codes == []

    await auth_b.request_token("code-B")
    assert client_a.auth.exchanged_codes == ["code-A"]
    assert client_b.auth.exchanged_codes == ["code-B"]

    try:
        auth_a.validate_callback_state(auth_a.state)
    except ValueError as ex:
        assert "procesado" in str(ex)
    else:
        raise AssertionError("Un callback repetido debe rechazarse")

    try:
        await auth_a.request_token("code-A-repeat")
    except ValueError as ex:
        assert "procesado" in str(ex)
    else:
        raise AssertionError("Un code repetido debe rechazarse")
    assert client_a.auth.exchanged_codes == ["code-A"]


async def assert_expired_invalid_and_provider_error_callbacks() -> None:
    _, _, expired = await create_web_attempt("expired")
    assert expired.expires_at is not None
    after_expiry = expired.expires_at + timedelta(seconds=1)
    try:
        expired.validate_callback_state(expired.state, now=after_expiry)
    except ValueError as ex:
        assert "expirado" in str(ex)
    else:
        raise AssertionError("Un callback expirado debe rechazarse")

    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    try:
        await expired.request_token("expired-code")
    except ValueError as ex:
        assert "expirado" in str(ex)
    else:
        raise AssertionError("Un code expirado no debe intercambiarse")

    _, _, missing = await create_web_attempt("missing")
    try:
        await missing.request_token("")
    except ValueError as ex:
        assert "sin codigo" in str(ex)
    else:
        raise AssertionError("Un callback sin code debe rechazarse")

    message = auth_service.web_oauth_error_message(
        "access_denied",
        "The user cancelled",
    )
    assert "cancelado" in message
    generic = auth_service.web_oauth_error_message("provider_error", "failure")
    assert "proveedor" in generic


async def assert_context_after_login_and_no_sensitive_logs() -> None:
    _, client, authorization = await create_web_attempt("context")
    code = "sensitive-auth-code"
    token = "sensitive-access-token"
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        await authorization.request_token(code)
        user = auth_service.get_current_user(client)
        context = {
            "usr_usuario_auth_uuid": user.id,
            "cuenta_actual": {"cuenta_id": 7},
            "evento_actual": {"cuenta_id": 7, "evento_id": 70},
        }

    assert context["usr_usuario_auth_uuid"] == "auth-context"
    assert context["cuenta_actual"]["cuenta_id"] == 7
    assert context["evento_actual"]["evento_id"] == 70
    captured = output.getvalue()
    assert code not in captured
    assert token not in captured


async def assert_attempt_lifecycle_and_late_callbacks() -> None:
    page, client, attempt, authorization = await create_managed_web_attempt("lifecycle")
    assert attempt.page is page
    assert attempt.attempt_id
    assert attempt.created_at.tzinfo is not None
    assert attempt.pending
    assert attempt.authorization is authorization

    timeout_task = asyncio.create_task(asyncio.sleep(60))
    attempt.set_timeout_task(timeout_task)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_CANCELLED)
    attempt.cancel_timeout()
    await asyncio.sleep(0)
    assert timeout_task.cancelled()
    assert authorization.consumed
    try:
        await authorization.request_token("late-after-cancel")
    except ValueError as ex:
        assert "no esta activo" in str(ex)
    else:
        raise AssertionError("Callback tardio tras Cancelar debe rechazarse")
    assert client.auth.exchanged_codes == []

    _, expired_client, expired_attempt, expired_auth = (
        await create_managed_web_attempt("late-expired")
    )
    assert expired_attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    try:
        await expired_auth.request_token("late-after-timeout")
    except ValueError as ex:
        assert "no esta activo" in str(ex)
    else:
        raise AssertionError("Callback tardio tras timeout debe rechazarse")
    assert expired_client.auth.exchanged_codes == []


async def assert_success_cancels_timeout_exactly_once() -> None:
    _, client, attempt, authorization = await create_managed_web_attempt("success")
    timeout_task = asyncio.create_task(asyncio.sleep(60))
    attempt.set_timeout_task(timeout_task)
    await authorization.request_token("success-code")
    await asyncio.sleep(0)
    assert (
        attempt.status
        == auth_service.WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING
    )
    assert timeout_task.cancelled()
    assert client.auth.exchanged_codes == ["success-code"]
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_HOME_BUILDING)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_COMPLETED)
    assert not attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    try:
        await authorization.request_token("second-code")
    except ValueError as ex:
        assert "no esta activo" in str(ex)
    else:
        raise AssertionError("Solo un callback puede completar el intento")
    assert client.auth.exchanged_codes == ["success-code"]


async def assert_page_ui_pending_cancel_timeout_and_retry() -> None:
    original_timeout = login_view.EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS
    login_view.EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS = 0.02
    try:
        page = FakePage(web=True, platform="windows")
        client = FakeClient("ui")
        login_view.build_login_view(page, client)
        root = page.added_controls[0]
        login_button = find_control(root, content="Continuar con Google")
        cancel_button = find_control(root, content="Cancelar")
        assert login_button is not None
        assert cancel_button is not None

        await login_button.on_click(SimpleNamespace())
        first_authorization = page.authorization
        assert page.login_calls == 1
        assert page.on_login_was_set_at_login
        assert login_button.disabled
        assert cancel_button.visible

        await login_button.on_click(SimpleNamespace())
        assert page.login_calls == 1
        assert page.authorization is first_authorization

        await cancel_button.on_click(SimpleNamespace())
        assert not login_button.disabled
        assert not cancel_button.visible
        assert first_authorization is not None and first_authorization.consumed
        assert any(
            getattr(control, "value", "") == "Inicio de sesion cancelado."
            for control in root.content.content.content.controls
        )

        await login_button.on_click(SimpleNamespace())
        second_authorization = page.authorization
        assert page.login_calls == 2
        assert second_authorization is not first_authorization
        assert second_authorization is not None
        assert second_authorization.state != first_authorization.state
        await asyncio.sleep(0.04)
        assert not login_button.disabled
        assert not cancel_button.visible
        status_values = [
            getattr(control, "value", "")
            for control in root.content.content.content.controls
        ]
        assert any("No se completo la autenticacion" in value for value in status_values)

        await login_button.on_click(SimpleNamespace())
        assert page.login_calls == 3
        await cancel_button.on_click(SimpleNamespace())
    finally:
        login_view.EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS = original_timeout


async def assert_two_pages_and_race_isolation() -> None:
    page_a, client_a, attempt_a, auth_a = await create_managed_web_attempt("page-A")
    page_b, client_b, attempt_b, auth_b = await create_managed_web_attempt("page-B")
    task_a = asyncio.create_task(asyncio.sleep(60))
    task_b = asyncio.create_task(asyncio.sleep(60))
    attempt_a.set_timeout_task(task_a)
    attempt_b.set_timeout_task(task_b)

    assert attempt_a.transition(auth_service.WEB_OAUTH_ATTEMPT_CANCELLED)
    attempt_a.cancel_timeout()
    await auth_b.request_token("code-B")
    assert attempt_b.transition(auth_service.WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING)
    assert attempt_b.transition(auth_service.WEB_OAUTH_ATTEMPT_HOME_BUILDING)
    assert attempt_b.transition(auth_service.WEB_OAUTH_ATTEMPT_COMPLETED)
    await asyncio.sleep(0)
    assert task_a.cancelled()
    assert task_b.cancelled()
    assert client_a.auth.exchanged_codes == []
    assert client_b.auth.exchanged_codes == ["code-B"]
    assert attempt_a.page is page_a
    assert attempt_b.page is page_b

    _, race_client, race_attempt, race_auth = await create_managed_web_attempt("race")
    results = await asyncio.gather(
        asyncio.to_thread(
            race_attempt.transition,
            auth_service.WEB_OAUTH_ATTEMPT_EXPIRED,
        ),
        race_auth.request_token("race-code"),
        return_exceptions=True,
    )
    assert race_attempt.status in {
        auth_service.WEB_OAUTH_ATTEMPT_EXPIRED,
        auth_service.WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING,
    }
    assert len(race_client.auth.exchanged_codes) <= 1
    if race_attempt.status == auth_service.WEB_OAUTH_ATTEMPT_EXPIRED:
        assert any(isinstance(result, ValueError) for result in results)
        if race_client.auth.exchanged_codes:
            assert race_client.auth.exchanged_codes == ["race-code"]
            assert race_client.auth.sign_out_scopes == ["local"]
            assert race_client.auth.get_session() is None
    else:
        assert race_client.auth.exchanged_codes == ["race-code"]
        assert results[0] is False


async def assert_late_exchange_is_cleaned_after_timeout_or_cancel() -> None:
    _, expired_client, expired_attempt, expired_auth = (
        await create_managed_web_attempt("late-expired")
    )
    expired_attempt.mark_waiting_callback()
    assert expired_attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    result = await asyncio.gather(
        expired_auth.request_token("code-expired"),
        return_exceptions=True,
    )
    assert isinstance(result[0], ValueError)
    assert expired_client.auth.exchanged_codes == []

    _, client, attempt, authorization = await create_managed_web_attempt(
        "late-cancelled"
    )
    client.auth.exchange_delay = 0.04
    request_task = asyncio.create_task(
        authorization.request_token("code-cancelled")
    )
    await asyncio.to_thread(client.auth.exchange_started.wait, 1)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_CANCELLED)
    result = await asyncio.gather(request_task, return_exceptions=True)
    assert isinstance(result[0], ValueError)
    assert client.auth.exchanged_codes == ["code-cancelled"]
    assert client.auth.sign_out_scopes == ["local"]
    assert client.auth.get_session() is None


async def assert_callback_neutralizes_timeout_during_slow_phases() -> None:
    _, client, attempt, authorization = await create_managed_web_attempt(
        "callback-before-timeout"
    )
    attempt.mark_waiting_callback()
    timeout_task = asyncio.create_task(asyncio.sleep(60))
    attempt.set_timeout_task(timeout_task)
    await authorization.request_token("first-login-code")
    await asyncio.sleep(0)
    assert timeout_task.cancelled()
    assert (
        attempt.status
        == auth_service.WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING
    )
    assert not attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING)
    await asyncio.sleep(0.02)
    assert not attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_HOME_BUILDING)
    assert not attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_EXPIRED)
    assert attempt.transition(auth_service.WEB_OAUTH_ATTEMPT_COMPLETED)
    assert client.auth.exchanged_codes == ["first-login-code"]

    waiting = auth_service.WebOAuthAttempt(FakePage(web=True, platform="windows"))
    assert waiting.timeout_eligible
    assert waiting.mark_waiting_callback()
    assert waiting.timeout_eligible
    assert waiting.mark_callback_received(has_error=False)
    assert not waiting.timeout_eligible


async def main_async() -> None:
    assert_platform_strategies()
    await assert_web_does_not_use_desktop_callback_resources()
    await assert_state_session_and_client_isolation()
    await assert_expired_invalid_and_provider_error_callbacks()
    await assert_context_after_login_and_no_sensitive_logs()
    await assert_attempt_lifecycle_and_late_callbacks()
    await assert_success_cancels_timeout_exactly_once()
    await assert_page_ui_pending_cancel_timeout_and_retry()
    await assert_two_pages_and_race_isolation()
    await assert_late_exchange_is_cleaned_after_timeout_or_cancel()
    await assert_callback_neutralizes_timeout_during_slow_phases()


def main() -> int:
    asyncio.run(main_async())
    print(
        "OK - web OAuth strategies, state correlation, replay/expiry controls, "
        "attempt timeout/cancel/races, client isolation, and safe logging tests passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
