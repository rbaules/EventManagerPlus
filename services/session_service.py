from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from services.auth_service import (
    sign_out_global_session,
    sign_out_local_session,
)
from services.evento_context_service import (
    guardar_contexto_sesion,
    limpiar_contexto_sesion,
)
from services.response_utils import safe_get
from services.usuario_service import UsuarioContextoError, cargar_contexto_usuario


SESSION_INVALID_MESSAGE = (
    "Tu sesion vencio o dejo de ser valida. Inicia sesion nuevamente."
)


@dataclass(frozen=True)
class SessionValidationResult:
    ok: bool
    message: str = ""
    user: Any = None
    context: dict[str, Any] | None = None
    should_build_home: bool = False


class PageSessionController:
    """Own Supabase Auth and operational state for exactly one Flet Page."""

    def __init__(
        self,
        page: Any,
        supabase: Any,
        *,
        context_loader: Callable[[Any, str], dict[str, Any]] = cargar_contexto_usuario,
        server_session_binding: Any = None,
    ) -> None:
        self.page = page
        self.supabase = supabase
        self._context_loader = context_loader
        self._server_session_binding = server_session_binding
        self._refresh_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._tasks: set[Any] = set()
        self._oauth_attempt: Any = None
        self._generation = 0
        self._home_generation: int | None = None
        self._authenticated = False
        self._closed = False
        self._connected = True
        self._logging_out = False
        self._logout_complete = False
        self.user: Any = None
        self.context: dict[str, Any] | None = None

    @property
    def authenticated(self) -> bool:
        with self._state_lock:
            return self._authenticated and not self._closed

    @property
    def connected(self) -> bool:
        with self._state_lock:
            return self._connected and not self._closed

    @property
    def logging_out(self) -> bool:
        with self._state_lock:
            return self._logging_out

    @property
    def current_oauth_attempt(self) -> Any:
        with self._state_lock:
            return self._oauth_attempt

    def has_supabase_session(self) -> bool:
        try:
            with self._refresh_lock:
                return self.supabase.auth.get_session() is not None
        except Exception:
            return False

    def set_connected(self, connected: bool) -> None:
        with self._state_lock:
            if not self._closed:
                self._connected = connected
                attempt = self._oauth_attempt
            else:
                attempt = None
        if attempt is not None and hasattr(attempt, "set_connected"):
            attempt.set_connected(connected)

    def register_oauth_attempt(self, attempt: Any) -> None:
        with self._state_lock:
            if self._closed:
                cancel_immediately = True
            else:
                self._oauth_attempt = attempt
                cancel_immediately = False
        if cancel_immediately:
            self._cancel_oauth_attempt(attempt)

    def clear_oauth_attempt(self, attempt: Any) -> None:
        with self._state_lock:
            if self._oauth_attempt is attempt:
                self._oauth_attempt = None

    @staticmethod
    def _cancel_oauth_attempt(attempt: Any) -> None:
        if attempt is None:
            return
        try:
            from services.auth_service import WEB_OAUTH_ATTEMPT_CANCELLED

            attempt.transition(WEB_OAUTH_ATTEMPT_CANCELLED)
            attempt.cancel_timeout()
        except Exception:
            pass

    def _context_is_valid(self, context: dict[str, Any], auth_user_id: str) -> bool:
        if str(safe_get(context, "usr_usuario_auth_uuid", "")) != auth_user_id:
            return False
        if safe_get(context, "usr_estado") != "Activo":
            return False

        cuentas = safe_get(context, "cuentas_permitidas", []) or []
        cuenta_actual = safe_get(context, "cuenta_actual")
        if not cuentas or not cuenta_actual:
            return False
        cuenta_ids = {safe_get(cuenta, "cuenta_id") for cuenta in cuentas}
        if safe_get(cuenta_actual, "cuenta_id") not in cuenta_ids:
            return False

        evento_actual = safe_get(context, "evento_actual")
        if evento_actual:
            eventos = safe_get(context, "eventos_permitidos", []) or []
            evento_keys = {
                (safe_get(evento, "cuenta_id"), safe_get(evento, "evento_id"))
                for evento in eventos
            }
            current_key = (
                safe_get(evento_actual, "cuenta_id"),
                safe_get(evento_actual, "evento_id"),
            )
            if current_key not in evento_keys:
                return False
        return True

    def validate_current_session(
        self,
        *,
        load_context: bool = True,
        claim_home: bool = False,
    ) -> SessionValidationResult:
        if self._server_session_binding is not None:
            result = self._server_session_binding.restore_and_run(
                self.supabase,
                lambda: self._validate_current_session(
                    load_context=load_context,
                    claim_home=claim_home,
                ),
            )
            if isinstance(result, SessionValidationResult):
                return result
            return self._invalidate(SESSION_INVALID_MESSAGE)
        return self._validate_current_session(
            load_context=load_context,
            claim_home=claim_home,
        )

    def _validate_current_session(
        self,
        *,
        load_context: bool,
        claim_home: bool,
    ) -> SessionValidationResult:
        with self._state_lock:
            if self._closed:
                return SessionValidationResult(False, SESSION_INVALID_MESSAGE)
            generation = self._generation

        try:
            # supabase-py refreshes an expired/near-expiry session inside
            # get_session(). This lock guarantees one effective refresh per Page.
            with self._refresh_lock:
                session = self.supabase.auth.get_session()
                if not session:
                    return self._invalidate(SESSION_INVALID_MESSAGE)
                user_response = self.supabase.auth.get_user()
        except Exception:
            return self._invalidate(SESSION_INVALID_MESSAGE)

        user = safe_get(user_response, "user")
        auth_user_id = str(safe_get(user, "id", ""))
        if not user or not auth_user_id:
            return self._invalidate(SESSION_INVALID_MESSAGE)

        context = self.context
        if load_context or context is None:
            try:
                context = self._context_loader(self.supabase, auth_user_id)
            except UsuarioContextoError as ex:
                return self._invalidate(str(ex))
            except Exception:
                return self._invalidate(
                    "No fue posible validar tu acceso a EventPlus."
                )

        if not context or not self._context_is_valid(context, auth_user_id):
            return self._invalidate(
                "Tu sesion es valida, pero el contexto de EventPlus no es valido."
            )

        with self._state_lock:
            if self._closed or generation != self._generation:
                return SessionValidationResult(False, SESSION_INVALID_MESSAGE)
            self.user = user
            self.context = context
            self._authenticated = True
            self._logging_out = False
            self._logout_complete = False
            should_build_home = False
            if claim_home and self._home_generation != generation:
                self._home_generation = generation
                should_build_home = True

        guardar_contexto_sesion(self.page.session.store, context)
        return SessionValidationResult(
            True,
            user=user,
            context=context,
            should_build_home=should_build_home,
        )

    def persist_server_session(self) -> bool:
        if self._server_session_binding is None:
            return True
        return bool(
            self._server_session_binding.persist_login(self.supabase)
        )

    @property
    def has_server_session(self) -> bool:
        return bool(
            self._server_session_binding is not None
            and self._server_session_binding.opaque_id
        )

    def _invalidate(self, message: str) -> SessionValidationResult:
        with self._state_lock:
            self._generation += 1
            self._authenticated = False
            self.user = None
            self.context = None
            self._home_generation = None
        limpiar_contexto_sesion(self.page.session.store)
        return SessionValidationResult(False, message or SESSION_INVALID_MESSAGE)

    def add_task(self, task: Any) -> Any:
        with self._state_lock:
            if self._closed:
                task.cancel()
                return task
            self._tasks.add(task)

        def discard(_task: Any) -> None:
            with self._state_lock:
                self._tasks.discard(_task)

        task.add_done_callback(discard)
        return task

    def start_refresh_monitor(
        self,
        on_invalid: Callable[[str], Awaitable[None] | None],
        *,
        interval_seconds: float = 60.0,
    ) -> Any:
        async def monitor() -> None:
            while True:
                await asyncio.sleep(interval_seconds)
                if not self.connected or not self.authenticated:
                    continue
                result = await asyncio.to_thread(
                    self.validate_current_session,
                    load_context=False,
                )
                if result.ok:
                    continue
                callback_result = on_invalid(result.message or SESSION_INVALID_MESSAGE)
                if inspect.isawaitable(callback_result):
                    await callback_result
                return

        return self.add_task(self.page.run_task(monitor))

    async def validate_after_reconnect(self) -> SessionValidationResult:
        self.set_connected(True)
        if not self.authenticated:
            return SessionValidationResult(False, SESSION_INVALID_MESSAGE)
        return await asyncio.to_thread(
            self.validate_current_session,
            load_context=False,
        )

    def clear_residual_session(self) -> bool:
        """Remove Supabase Auth left behind while EventPlus is unauthenticated."""
        with self._state_lock:
            if self._authenticated or self._closed:
                return False
        found_session = False
        with self._refresh_lock:
            try:
                found_session = self.supabase.auth.get_session() is not None
            except Exception:
                found_session = True
            if found_session:
                sign_out_local_session(self.supabase)
        if found_session:
            self._invalidate(SESSION_INVALID_MESSAGE)
        return found_session

    def logout(
        self,
        *,
        remote: bool = True,
        cancel_tasks: bool = True,
        invalidate_server: bool = True,
    ) -> bool:
        with self._state_lock:
            if self._logging_out or self._logout_complete:
                return False
            self._logging_out = True
            self._generation += 1
            self._authenticated = False
            self._home_generation = None
            self.user = None
            self.context = None
            oauth_attempt = self._oauth_attempt
            self._oauth_attempt = None
            tasks = list(self._tasks)
            self._tasks.clear()

        self._cancel_oauth_attempt(oauth_attempt)
        if cancel_tasks:
            for task in tasks:
                if not task.done():
                    task.cancel()
        if remote:
            try:
                with self._refresh_lock:
                    sign_out_local_session(self.supabase)
            except Exception:
                pass
        try:
            if invalidate_server and self._server_session_binding is not None:
                self._server_session_binding.delete()
        finally:
            limpiar_contexto_sesion(self.page.session.store)
            with self._state_lock:
                self._logging_out = False
                self._logout_complete = True
        return True

    def logout_global(self) -> None:
        """Explicit future administrative logout; not exposed in the UI."""
        self.logout(remote=False)
        try:
            with self._refresh_lock:
                sign_out_global_session(self.supabase)
        except Exception:
            pass

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        self.logout(remote=False, invalidate_server=False)
        if self._server_session_binding is not None:
            self._server_session_binding.close()
