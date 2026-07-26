from __future__ import annotations

import asyncio
import queue
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from config import (
    CALLBACK_HOST,
    CALLBACK_PATH,
    CALLBACK_PORT,
    EVENTPLUS_WEB_OAUTH_REDIRECT_URL,
    EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS,
    EVENTPLUS_AUTH_DEBUG,
    SUPABASE_OAUTH_REDIRECT_URL,
    get_oauth_redirect_url,
    is_android_platform,
)
from services.response_utils import pretty, safe_get, to_dict


OAUTH_STRATEGY_WEB = "web"
OAUTH_STRATEGY_DESKTOP = "desktop"
OAUTH_STRATEGY_ANDROID = "android"
WEB_OAUTH_ATTEMPT_CREATED = "CREATED"
WEB_OAUTH_ATTEMPT_WAITING_CALLBACK = "WAITING_CALLBACK"
WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING = "SESSION_EXCHANGING"
WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING = "CONTEXT_BUILDING"
WEB_OAUTH_ATTEMPT_HOME_BUILDING = "HOME_BUILDING"
WEB_OAUTH_ATTEMPT_COMPLETED = "COMPLETED"
WEB_OAUTH_ATTEMPT_CANCELLED = "CANCELLED"
WEB_OAUTH_ATTEMPT_EXPIRED = "EXPIRED"
WEB_OAUTH_ATTEMPT_FAILED = "FAILED"
WEB_OAUTH_ATTEMPT_PENDING = WEB_OAUTH_ATTEMPT_WAITING_CALLBACK

WEB_OAUTH_TERMINAL_STATES = {
    WEB_OAUTH_ATTEMPT_COMPLETED,
    WEB_OAUTH_ATTEMPT_CANCELLED,
    WEB_OAUTH_ATTEMPT_EXPIRED,
    WEB_OAUTH_ATTEMPT_FAILED,
}

WEB_OAUTH_ALLOWED_TRANSITIONS = {
    WEB_OAUTH_ATTEMPT_CREATED: {
        WEB_OAUTH_ATTEMPT_WAITING_CALLBACK,
        WEB_OAUTH_ATTEMPT_CANCELLED,
        WEB_OAUTH_ATTEMPT_EXPIRED,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
    WEB_OAUTH_ATTEMPT_WAITING_CALLBACK: {
        WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED,
        WEB_OAUTH_ATTEMPT_CANCELLED,
        WEB_OAUTH_ATTEMPT_EXPIRED,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
    WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED: {
        WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING,
        WEB_OAUTH_ATTEMPT_CANCELLED,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
    WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING: {
        WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING,
        WEB_OAUTH_ATTEMPT_CANCELLED,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
    WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING: {
        WEB_OAUTH_ATTEMPT_HOME_BUILDING,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
    WEB_OAUTH_ATTEMPT_HOME_BUILDING: {
        WEB_OAUTH_ATTEMPT_COMPLETED,
        WEB_OAUTH_ATTEMPT_FAILED,
    },
}


class WebOAuthAttempt:
    """One atomic OAuth lifecycle owned by a single Flet Page."""

    def __init__(self, page: Any) -> None:
        self.attempt_id = secrets.token_urlsafe(24)
        self.created_at = datetime.now(timezone.utc)
        self.started_monotonic = time.monotonic()
        self.status = WEB_OAUTH_ATTEMPT_CREATED
        self.page = page
        self.authorization: SupabaseWebAuthorization | None = None
        self.timeout_task: Any = None
        self.exchange_started = False
        self.connected = True
        self._transition_lock = threading.Lock()
        self.trace("attempt_created")

    @property
    def pending(self) -> bool:
        with self._transition_lock:
            return self.status not in WEB_OAUTH_TERMINAL_STATES

    @property
    def timeout_eligible(self) -> bool:
        with self._transition_lock:
            return self.status in {
                WEB_OAUTH_ATTEMPT_CREATED,
                WEB_OAUTH_ATTEMPT_WAITING_CALLBACK,
            }

    def trace(self, phase: str, **flags: Any) -> None:
        if not EVENTPLUS_AUTH_DEBUG:
            return
        allowed_flags = {
            "on_login",
            "has_error",
            "session_present",
            "home_claimed",
            "timeout_cancelled",
            "timeout_fired",
            "connected",
        }
        safe_flags = " ".join(
            f"{key}={bool(value)}"
            for key, value in flags.items()
            if key in allowed_flags
        )
        elapsed = time.monotonic() - self.started_monotonic
        page_ref = hex(id(self.page))[-6:]
        platform = str(getattr(self.page, "platform", "unknown"))
        web = bool(getattr(self.page, "web", False))
        suffix = f" {safe_flags}" if safe_flags else ""
        print(
            "[AUTH_FLOW]",
            f"cid={self.attempt_id[:8]}",
            f"page={page_ref}",
            f"phase={phase}",
            f"t={elapsed:.3f}",
            f"state={self.status}",
            f"connected={self.connected}",
            f"platform={platform}",
            f"web={web}{suffix}",
        )

    def set_connected(self, connected: bool) -> None:
        self.connected = connected

    def bind_authorization(self, authorization: SupabaseWebAuthorization) -> None:
        with self._transition_lock:
            self.authorization = authorization
            should_invalidate = self.status in {
                WEB_OAUTH_ATTEMPT_CANCELLED,
                WEB_OAUTH_ATTEMPT_EXPIRED,
            }
        if should_invalidate:
            authorization.invalidate()

    def set_timeout_task(self, timeout_task: Any) -> None:
        with self._transition_lock:
            self.timeout_task = timeout_task

    def transition(self, target_status: str) -> bool:
        with self._transition_lock:
            allowed = WEB_OAUTH_ALLOWED_TRANSITIONS.get(self.status, set())
            if target_status not in allowed:
                return False
            self.status = target_status
            authorization = self.authorization

        if (
            target_status
            in {
                WEB_OAUTH_ATTEMPT_CANCELLED,
                WEB_OAUTH_ATTEMPT_EXPIRED,
                WEB_OAUTH_ATTEMPT_FAILED,
            }
            and authorization is not None
        ):
            authorization.invalidate()
        self.trace("attempt_terminal_state" if target_status in WEB_OAUTH_TERMINAL_STATES else target_status.lower())
        return True

    def begin_exchange(self) -> bool:
        with self._transition_lock:
            if self.status not in {
                WEB_OAUTH_ATTEMPT_CREATED,
                WEB_OAUTH_ATTEMPT_WAITING_CALLBACK,
            } or self.exchange_started:
                return False
            self.status = WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED
            self.exchange_started = True
        self.trace("on_login_success_or_error", on_login=False, has_error=False)
        self.cancel_timeout()
        with self._transition_lock:
            if self.status != WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED:
                return False
            self.status = WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING
        self.trace("session_exchanging")
        return True

    def mark_waiting_callback(self) -> bool:
        return self.transition(WEB_OAUTH_ATTEMPT_WAITING_CALLBACK)

    def mark_callback_received(self, *, has_error: bool) -> bool:
        with self._transition_lock:
            if self.status in WEB_OAUTH_TERMINAL_STATES:
                return False
            if self.status in {
                WEB_OAUTH_ATTEMPT_CREATED,
                WEB_OAUTH_ATTEMPT_WAITING_CALLBACK,
            }:
                self.status = WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED
        self.trace("on_login_enter", on_login=True, has_error=has_error)
        self.cancel_timeout()
        return True

    def cancel_timeout(self) -> None:
        with self._transition_lock:
            timeout_task = self.timeout_task
            self.timeout_task = None
        if timeout_task is not None and not timeout_task.done():
            self.trace("timeout_cancel_requested")
            timeout_task.cancel()
            self.trace("timeout_cancelled", timeout_cancelled=True)


def detect_oauth_strategy(page: Any) -> str:
    if is_android_platform(getattr(page, "platform", None)):
        return OAUTH_STRATEGY_ANDROID
    if bool(getattr(page, "web", False)):
        return OAUTH_STRATEGY_WEB
    return OAUTH_STRATEGY_DESKTOP


def web_oauth_error_message(
    error: str | None,
    error_description: str | None = None,
) -> str:
    error_text = str(error or "")
    description = str(error_description or "")
    if error_text == "access_denied":
        return "El inicio de sesion fue cancelado. Puedes intentarlo nuevamente."
    if "expir" in error_text.lower() or "expir" in description.lower():
        return "El intento de inicio de sesion expiro. Inicia uno nuevo."
    return "El proveedor rechazo o no pudo completar el inicio de sesion."


def _redirect_url_with_state(redirect_url: str, state: str) -> str:
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["state"] = [state]
    query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=query))


class SupabaseWebOAuthProvider:
    """Per-Page dependencies consumed by the Flet OAuth adapter."""

    def __init__(
        self,
        supabase: Any,
        redirect_url: str,
        attempt: WebOAuthAttempt | None = None,
    ) -> None:
        self.supabase = supabase
        self.redirect_url = redirect_url
        self.attempt = attempt


class SupabaseWebAuthorization:
    """Bridge Flet's correlated callback to one Page-scoped Supabase client."""

    def __init__(
        self,
        provider: SupabaseWebOAuthProvider,
        fetch_user: bool,
        fetch_groups: bool,
        scope: list[str] | None = None,
    ) -> None:
        del fetch_user, fetch_groups, scope
        self.provider = provider
        self.state = ""
        self.expires_at: datetime | None = None
        self.consumed = False
        if self.provider.attempt is not None:
            self.provider.attempt.bind_authorization(self)

    def get_authorization_data(self) -> tuple[str, str]:
        self.state = secrets.token_urlsafe(32)
        self.expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS
        )
        redirect_url = _redirect_url_with_state(
            self.provider.redirect_url,
            self.state,
        )
        authorization_url = get_oauth_url(
            self.provider.supabase,
            redirect_url=redirect_url,
            select_account=True,
        )
        return authorization_url, self.state

    def validate_callback_state(self, state: str, now: datetime | None = None) -> None:
        current_time = now or datetime.now(timezone.utc)
        if not self.state or not secrets.compare_digest(state, self.state):
            raise ValueError("Callback OAuth no corresponde a esta sesion.")
        if self.consumed:
            raise ValueError("Callback OAuth ya fue procesado.")
        if self.expires_at is None or current_time > self.expires_at:
            raise ValueError("Callback OAuth expirado.")

    def invalidate(self) -> None:
        self.consumed = True
        self.expires_at = datetime.now(timezone.utc)

    async def request_token(self, code: str) -> None:
        attempt = self.provider.attempt
        if attempt is not None and not attempt.begin_exchange():
            raise ValueError("Intento OAuth web ya no esta activo.")
        if self.consumed:
            raise ValueError("Callback OAuth ya fue procesado.")
        if self.expires_at is None or datetime.now(timezone.utc) > self.expires_at:
            raise ValueError("Callback OAuth expirado.")
        if not code:
            raise ValueError("Callback OAuth sin codigo.")
        self.consumed = True
        exchange_task = asyncio.create_task(
            asyncio.to_thread(
                exchange_code_for_session,
                self.provider.supabase,
                code,
            )
        )
        try:
            await asyncio.shield(exchange_task)
        except asyncio.CancelledError:
            await exchange_task
            if attempt is not None and not attempt.pending:
                await asyncio.to_thread(
                    sign_out_local_session,
                    self.provider.supabase,
                )
            raise
        except Exception:
            if attempt is not None:
                attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
                attempt.cancel_timeout()
            await asyncio.to_thread(
                sign_out_local_session,
                self.provider.supabase,
            )
            raise

        if attempt is not None:
            if attempt.status != WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING:
                await asyncio.to_thread(
                    sign_out_local_session,
                    self.provider.supabase,
                )
                attempt.trace("late_event_rejected")
                raise ValueError("Intento OAuth web ya no esta activo.")
            try:
                session_present = (
                    self.provider.supabase.auth.get_session() is not None
                )
            except Exception:
                session_present = False
            attempt.trace(
                "supabase_session_present",
                session_present=session_present,
            )

    async def dehydrate_token(self, saved_token: str) -> None:
        del saved_token
        raise NotImplementedError("La recuperacion de sesion web no pertenece a esta tarea.")

    async def get_token(self) -> None:
        return None


async def start_web_oauth(
    page: Any,
    supabase: Any,
    redirect_url: str = EVENTPLUS_WEB_OAUTH_REDIRECT_URL,
    attempt: WebOAuthAttempt | None = None,
) -> Any:
    if detect_oauth_strategy(page) != OAUTH_STRATEGY_WEB:
        raise ValueError("La estrategia OAuth web requiere una Page web.")
    provider = SupabaseWebOAuthProvider(supabase, redirect_url, attempt)
    return await page.login(
        provider,
        fetch_user=False,
        fetch_groups=False,
        authorization=SupabaseWebAuthorization,
    )


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Ruta no encontrada.")
            return

        params = parse_qs(parsed.query)

        result = {
            "code": params["code"][0] if "code" in params and params["code"] else None,
            "error": params["error"][0] if "error" in params and params["error"] else None,
            "error_description": (
                params["error_description"][0]
                if "error_description" in params and params["error_description"]
                else None
            ),
            "raw_path": self.path,
        }

        OAuthCallbackHandler.result_queue.put(result)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        html = """
        <!doctype html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <title>EventPlus - Login completado</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; color: #222; }
                .box {
                    max-width: 640px;
                    border: 1px solid #ddd;
                    border-radius: 12px;
                    padding: 24px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                }
                h1 { margin-top: 0; }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>Login completado</h1>
                <p>Ya puedes cerrar esta pestana y volver a EventPlus.</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))


def wait_for_oauth_callback(timeout_seconds: int = 180) -> dict[str, Any]:
    OAuthCallbackHandler.result_queue = queue.Queue()

    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        return OAuthCallbackHandler.result_queue.get(timeout=timeout_seconds)
    finally:
        server.shutdown()
        server.server_close()


def parse_oauth_callback_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {
        "code": params["code"][0] if "code" in params and params["code"] else None,
        "error": params["error"][0] if "error" in params and params["error"] else None,
        "error_description": (
            params["error_description"][0]
            if "error_description" in params and params["error_description"]
            else None
        ),
    }


def get_oauth_url(
    supabase: Any,
    redirect_url: str | None = None,
    *,
    select_account: bool = False,
) -> str:
    redirect_to = redirect_url or get_oauth_redirect_url()
    options: dict[str, Any] = {"redirect_to": redirect_to}
    if select_account:
        options["query_params"] = {"prompt": "select_account"}
    response = supabase.auth.sign_in_with_oauth(
        {
            "provider": "google",
            "options": options,
        }
    )

    url = safe_get(response, "url")

    if not url and isinstance(response, str):
        # Algunas versiones podrian devolver directamente la URL.
        url = response

    if not url:
        raise RuntimeError(
            "Supabase no devolvio una URL OAuth.\n"
            f"Respuesta recibida:\n{pretty(to_dict(response) or str(response))}"
        )

    return str(url)


def exchange_code_for_session(supabase: Any, code: str) -> Any:
    if not hasattr(supabase.auth, "exchange_code_for_session"):
        raise RuntimeError(
            "Tu version de supabase-py no tiene exchange_code_for_session(). "
            "Actualiza con: pip install --upgrade supabase"
        )

    return supabase.auth.exchange_code_for_session({"auth_code": code})


def get_current_user(supabase: Any) -> Any:
    response = supabase.auth.get_user()
    return safe_get(response, "user")


def sign_out_local_session(supabase: Any) -> None:
    supabase.auth.sign_out({"scope": "local"})


def sign_out_global_session(supabase: Any) -> None:
    """Revoke all refresh tokens for the user; reserved for a future UI."""
    supabase.auth.sign_out({"scope": "global"})
