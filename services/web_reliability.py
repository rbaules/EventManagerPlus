from __future__ import annotations

import logging
import os
import re
import secrets
import time
from typing import Any, Callable


LOGGER = logging.getLogger("eventplus.web")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _formatter.converter = time.gmtime
    _handler.setFormatter(_formatter)
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def _technical_id(value: Any) -> str:
    if value is None or value == "":
        return "none"
    return re.sub(r"[^A-Za-z0-9_./:-]", "_", str(value))[:64]


class PageWebTelemetry:
    """Per-Page, PII-free lifecycle measurements for Flet Web."""

    def __init__(
        self,
        page: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        logger: logging.Logger = LOGGER,
        page_id: str | None = None,
    ) -> None:
        self.page = page
        self.page_id = (page_id or secrets.token_hex(4)).upper()
        self.connect_count = 0
        self.disconnect_count = 0
        self._clock = clock
        self._logger = logger
        self._created_at = clock()
        self._ready_started_at = self._created_at
        self._disconnected_at: float | None = None
        self._authenticated: Callable[[], bool] = lambda: False
        self._context: Callable[[], dict[str, Any] | None] = lambda: None
        self.render_instance = os.environ.get("RENDER_INSTANCE_ID") or "local"
        self.git_commit = os.environ.get("RENDER_GIT_COMMIT") or "local"

    def bind_session(
        self,
        authenticated: Callable[[], bool],
        context: Callable[[], dict[str, Any] | None],
    ) -> None:
        self._authenticated = authenticated
        self._context = context

    def _fields(self) -> str:
        context = self._context() or {}
        account = context.get("cuenta_actual") or {}
        event = context.get("evento_actual") or {}
        route = str(getattr(self.page, "route", None) or "/").split("?", 1)[0]
        return " ".join(
            (
                f"page_id={self.page_id}",
                f"web={str(bool(getattr(self.page, 'web', False))).lower()}",
                f"platform={_technical_id(getattr(self.page, 'platform', None))}",
                f"width={_technical_id(getattr(self.page, 'width', None))}",
                f"height={_technical_id(getattr(self.page, 'height', None))}",
                f"authenticated={'yes' if self._authenticated() else 'no'}",
                f"account_id={_technical_id(account.get('cuenta_id'))}",
                f"event_id={_technical_id(event.get('evento_id'))}",
                f"route={_technical_id(route)}",
                f"render_instance={_technical_id(self.render_instance)}",
                f"git_commit={_technical_id(self.git_commit)}",
            )
        )

    def page_created(self) -> None:
        self._logger.info("[WEB][PAGE_CREATED] %s", self._fields())

    def connect(self) -> None:
        now = self._clock()
        self.connect_count += 1
        disconnected_for = (
            max(0.0, now - self._disconnected_at)
            if self._disconnected_at is not None
            else None
        )
        self._ready_started_at = now
        extra = (
            f" reconnect=true disconnected_for={disconnected_for:.1f}"
            if disconnected_for is not None
            else " reconnect=false disconnected_for=none"
        )
        self._disconnected_at = None
        self._logger.info(
            "[WEB][CONNECT] %s connect_count=%d%s",
            self._fields(),
            self.connect_count,
            extra,
        )

    def disconnect(self) -> None:
        self.disconnect_count += 1
        self._disconnected_at = self._clock()
        self._logger.info(
            "[WEB][DISCONNECT] %s disconnect_count=%d",
            self._fields(),
            self.disconnect_count,
        )

    def close(self) -> None:
        self._logger.info("[WEB][CLOSE] %s", self._fields())

    def error(self, _event: Any) -> None:
        # Event payloads can contain user-entered data. Deliberately log only a
        # stable technical classification; Flet keeps its normal error handling.
        self._logger.error(
            "[WEB][ERROR] %s error_type=PageError summary=unhandled_page_error",
            self._fields(),
        )

    def restore_start(self) -> float:
        started = self._clock()
        self._logger.info("[SESSION][RESTORE_START] %s", self._fields())
        return started

    def restore_result(self, outcome: str, started: float) -> None:
        normalized = outcome if outcome in {"OK", "NONE", "FAILED"} else "FAILED"
        context = self._context() or {}
        self._logger.info(
            "[SESSION][RESTORE_%s] %s duration_seconds=%.3f user=%s context=%s event=%s",
            normalized,
            self._fields(),
            max(0.0, self._clock() - started),
            "yes" if self._authenticated() else "no",
            "yes" if context else "no",
            "yes" if context.get("evento_actual") else "no",
        )

    def ready(self, *, restored_session: bool) -> None:
        self._logger.info(
            "[WEB][READY] %s ready_after_seconds=%.3f restored_session=%s",
            self._fields(),
            max(0.0, self._clock() - self._ready_started_at),
            str(restored_session).lower(),
        )
