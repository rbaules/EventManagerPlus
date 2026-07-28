from __future__ import annotations

import contextvars
import secrets
import threading
import time
from dataclasses import dataclass, field, replace
from http.cookies import SimpleCookie
from typing import Any, Callable, Protocol

from starlette.datastructures import MutableHeaders

from config import (
    EVENTPLUS_SESSION_COOKIE_NAME,
    EVENTPLUS_SESSION_COOKIE_SAMESITE,
    EVENTPLUS_SESSION_COOKIE_SECURE,
    EVENTPLUS_SESSION_ROTATE_ON_RESTORE,
    EVENTPLUS_SESSION_TTL_SECONDS,
)
from services.response_utils import safe_get


@dataclass(frozen=True)
class ServerSession:
    opaque_id: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    auth_user_id: str
    created_at: float
    expires_at: float
    updated_at: float
    version: int = 1
    revoked: bool = False
    bound_pages: frozenset[str] = field(default_factory=frozenset)


class SessionRepository(Protocol):
    def create(
        self,
        *,
        access_token: str,
        refresh_token: str,
        auth_user_id: str,
        ttl_seconds: int,
    ) -> ServerSession: ...

    def get(self, opaque_id: str) -> ServerSession | None: ...

    def update(
        self,
        opaque_id: str,
        *,
        access_token: str,
        refresh_token: str,
        auth_user_id: str,
        expected_version: int | None = None,
        ttl_seconds: int | None = None,
    ) -> ServerSession | None: ...

    def rotate(self, opaque_id: str) -> ServerSession | None: ...

    def delete(self, opaque_id: str) -> None: ...

    def delete_expired(self) -> int: ...

    def bind_page(self, opaque_id: str, page_id: str) -> bool: ...

    def unbind_page(self, opaque_id: str, page_id: str) -> None: ...


class InMemorySessionRepository:
    """Single-process development repository.

    Tokens never leave this object. The implementation is intentionally
    process-local and is not suitable for restarts or multiple workers.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, ServerSession] = {}

    def _new_id(self) -> str:
        while True:
            opaque_id = secrets.token_urlsafe(32)
            if opaque_id not in self._sessions:
                return opaque_id

    def _valid_locked(self, opaque_id: str) -> ServerSession | None:
        record = self._sessions.get(opaque_id)
        if record is None:
            return None
        if record.revoked or record.expires_at <= self._clock():
            self._sessions.pop(opaque_id, None)
            return None
        return record

    def create(
        self,
        *,
        access_token: str,
        refresh_token: str,
        auth_user_id: str,
        ttl_seconds: int = EVENTPLUS_SESSION_TTL_SECONDS,
    ) -> ServerSession:
        if not access_token or not refresh_token or not auth_user_id:
            raise ValueError("La sesion server-side requiere Auth completa.")
        with self._lock:
            now = self._clock()
            opaque_id = self._new_id()
            record = ServerSession(
                opaque_id=opaque_id,
                access_token=access_token,
                refresh_token=refresh_token,
                auth_user_id=auth_user_id,
                created_at=now,
                updated_at=now,
                expires_at=now + max(60, int(ttl_seconds)),
            )
            self._sessions[opaque_id] = record
            return record

    def get(self, opaque_id: str) -> ServerSession | None:
        with self._lock:
            return self._valid_locked(opaque_id)

    def update(
        self,
        opaque_id: str,
        *,
        access_token: str,
        refresh_token: str,
        auth_user_id: str,
        expected_version: int | None = None,
        ttl_seconds: int | None = None,
    ) -> ServerSession | None:
        with self._lock:
            current = self._valid_locked(opaque_id)
            if current is None or current.auth_user_id != auth_user_id:
                return None
            if expected_version is not None and current.version != expected_version:
                return None
            now = self._clock()
            updated = replace(
                current,
                access_token=access_token,
                refresh_token=refresh_token,
                updated_at=now,
                expires_at=(
                    now + max(60, int(ttl_seconds))
                    if ttl_seconds is not None
                    else current.expires_at
                ),
                version=current.version + 1,
            )
            self._sessions[opaque_id] = updated
            return updated

    def rotate(self, opaque_id: str) -> ServerSession | None:
        with self._lock:
            current = self._valid_locked(opaque_id)
            if current is None:
                return None
            new_id = self._new_id()
            rotated = replace(
                current,
                opaque_id=new_id,
                updated_at=self._clock(),
                version=current.version + 1,
            )
            self._sessions.pop(opaque_id, None)
            self._sessions[new_id] = rotated
            return rotated

    def delete(self, opaque_id: str) -> None:
        with self._lock:
            record = self._sessions.pop(opaque_id, None)
            if record is not None:
                replace(
                    record,
                    access_token="",
                    refresh_token="",
                    revoked=True,
                )

    def delete_expired(self) -> int:
        with self._lock:
            expired = [
                key
                for key, value in self._sessions.items()
                if value.revoked or value.expires_at <= self._clock()
            ]
            for key in expired:
                self._sessions.pop(key, None)
            return len(expired)

    def bind_page(self, opaque_id: str, page_id: str) -> bool:
        with self._lock:
            current = self._valid_locked(opaque_id)
            if current is None:
                return False
            self._sessions[opaque_id] = replace(
                current,
                bound_pages=current.bound_pages | {page_id},
            )
            return True

    def unbind_page(self, opaque_id: str, page_id: str) -> None:
        with self._lock:
            current = self._valid_locked(opaque_id)
            if current is None:
                return
            self._sessions[opaque_id] = replace(
                current,
                bound_pages=current.bound_pages - {page_id},
            )

    def run_serialized(
        self,
        opaque_id: str,
        operation: Callable[[ServerSession], Any],
    ) -> Any:
        """Run restore/refresh under the repository lock for one process."""
        with self._lock:
            current = self._valid_locked(opaque_id)
            if current is None:
                return None
            return operation(current)


@dataclass
class RequestSessionContext:
    cookie_value: str | None
    set_cookie_value: str | None = None
    delete_cookie: bool = False


_request_session_context: contextvars.ContextVar[
    RequestSessionContext | None
] = contextvars.ContextVar("eventplus_request_session", default=None)


def current_request_session_context() -> RequestSessionContext | None:
    return _request_session_context.get()


def request_cookie_update(opaque_id: str) -> None:
    context = current_request_session_context()
    if context is not None:
        context.set_cookie_value = opaque_id
        context.delete_cookie = False


def request_cookie_delete() -> None:
    context = current_request_session_context()
    if context is not None:
        context.set_cookie_value = None
        context.delete_cookie = True


def _cookie_from_headers(headers: list[tuple[bytes, bytes]]) -> str | None:
    raw_cookie = ""
    for key, value in headers:
        if key.lower() == b"cookie":
            raw_cookie = value.decode("latin-1")
            break
    parsed = SimpleCookie()
    parsed.load(raw_cookie)
    morsel = parsed.get(EVENTPLUS_SESSION_COOKIE_NAME)
    return morsel.value if morsel is not None else None


def _set_cookie_header(opaque_id: str) -> str:
    cookie = SimpleCookie()
    cookie[EVENTPLUS_SESSION_COOKIE_NAME] = opaque_id
    morsel = cookie[EVENTPLUS_SESSION_COOKIE_NAME]
    morsel["path"] = "/"
    morsel["max-age"] = str(EVENTPLUS_SESSION_TTL_SECONDS)
    morsel["httponly"] = True
    morsel["samesite"] = EVENTPLUS_SESSION_COOKIE_SAMESITE
    if EVENTPLUS_SESSION_COOKIE_SECURE:
        morsel["secure"] = True
    return morsel.OutputString()


def _delete_cookie_header() -> str:
    cookie = SimpleCookie()
    cookie[EVENTPLUS_SESSION_COOKIE_NAME] = ""
    morsel = cookie[EVENTPLUS_SESSION_COOKIE_NAME]
    morsel["path"] = "/"
    morsel["max-age"] = "0"
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    morsel["httponly"] = True
    morsel["samesite"] = EVENTPLUS_SESSION_COOKIE_SAMESITE
    if EVENTPLUS_SESSION_COOKIE_SECURE:
        morsel["secure"] = True
    return morsel.OutputString()


class EventPlusSessionMiddleware:
    """Propagate the opaque cookie to HTTP callbacks and Flet WebSockets."""

    def __init__(self, app: Any, repository: InMemorySessionRepository) -> None:
        self.app = app
        self.repository = repository

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        cookie_value = _cookie_from_headers(scope.get("headers", []))
        context = RequestSessionContext(cookie_value=cookie_value)
        if cookie_value and self.repository.get(cookie_value) is None:
            context.cookie_value = None
            context.delete_cookie = True
        elif (
            cookie_value
            and EVENTPLUS_SESSION_ROTATE_ON_RESTORE
            and scope["type"] == "http"
            and scope.get("path") == "/"
        ):
            rotated = self.repository.rotate(cookie_value)
            if rotated is not None:
                context.cookie_value = rotated.opaque_id
                context.set_cookie_value = rotated.opaque_id
        token = _request_session_context.set(context)

        async def send_with_cookie(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if context.delete_cookie:
                    headers.append("set-cookie", _delete_cookie_header())
                elif context.set_cookie_value:
                    headers.append(
                        "set-cookie",
                        _set_cookie_header(context.set_cookie_value),
                    )
            await send(message)

        try:
            await self.app(scope, receive, send_with_cookie)
        finally:
            _request_session_context.reset(token)


class ServerSessionBinding:
    """Connect one Page/client to one opaque repository record."""

    def __init__(
        self,
        repository: InMemorySessionRepository,
        page: Any,
        opaque_id: str | None,
    ) -> None:
        self.repository = repository
        self.page_id = hex(id(page))
        self.opaque_id = opaque_id
        if opaque_id:
            self.repository.bind_page(opaque_id, self.page_id)

    @staticmethod
    def _session_values(client: Any) -> tuple[str, str, str] | None:
        session = client.auth.get_session()
        if session is None:
            return None
        access_token = str(safe_get(session, "access_token", "") or "")
        refresh_token = str(safe_get(session, "refresh_token", "") or "")
        user = safe_get(session, "user")
        auth_user_id = str(safe_get(user, "id", "") or "")
        if not access_token or not refresh_token or not auth_user_id:
            return None
        return access_token, refresh_token, auth_user_id

    def persist_login(self, client: Any) -> bool:
        values = self._session_values(client)
        if values is None:
            return False
        access_token, refresh_token, auth_user_id = values
        if self.opaque_id:
            self.repository.delete(self.opaque_id)
        record = self.repository.create(
            access_token=access_token,
            refresh_token=refresh_token,
            auth_user_id=auth_user_id,
            ttl_seconds=EVENTPLUS_SESSION_TTL_SECONDS,
        )
        self.opaque_id = record.opaque_id
        self.repository.bind_page(record.opaque_id, self.page_id)
        request_cookie_update(record.opaque_id)
        return True

    def restore_and_run(
        self,
        client: Any,
        operation: Callable[[], Any],
    ) -> Any:
        opaque_id = self.opaque_id
        if not opaque_id:
            return operation()

        def serialized(record: ServerSession) -> Any:
            try:
                response = client.auth.set_session(
                    record.access_token,
                    record.refresh_token,
                )
                restored = safe_get(response, "session") or client.auth.get_session()
                if restored is None:
                    raise RuntimeError("Sesion Supabase no restaurada.")
                result = operation()
                if getattr(result, "ok", True) is False:
                    raise RuntimeError("La revalidacion EventPlus fue rechazada.")
                values = self._session_values(client)
                if values is None:
                    raise RuntimeError("Sesion Supabase no disponible.")
                access_token, refresh_token, auth_user_id = values
                updated = self.repository.update(
                    opaque_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    auth_user_id=auth_user_id,
                    expected_version=record.version,
                    ttl_seconds=EVENTPLUS_SESSION_TTL_SECONDS,
                )
                if updated is None:
                    raise RuntimeError("La sesion fue invalidada durante refresh.")
                return result
            except Exception:
                self.repository.delete(opaque_id)
                request_cookie_delete()
                return None

        result = self.repository.run_serialized(opaque_id, serialized)
        if result is None:
            self.opaque_id = None
            request_cookie_delete()
            return None
        return result

    def delete(self) -> None:
        if self.opaque_id:
            opaque_id = self.opaque_id
            self.repository.unbind_page(opaque_id, self.page_id)
            self.repository.delete(opaque_id)
            self.opaque_id = None
        request_cookie_delete()

    def close(self) -> None:
        if self.opaque_id:
            self.repository.unbind_page(self.opaque_id, self.page_id)


def create_server_session_binding(
    repository: InMemorySessionRepository,
    page: Any,
) -> ServerSessionBinding:
    context = current_request_session_context()
    opaque_id = context.cookie_value if context is not None else None
    return ServerSessionBinding(repository, page, opaque_id)
