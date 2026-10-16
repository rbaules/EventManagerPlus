from __future__ import annotations

import logging
import os
import re
import sys
import time
from typing import Any

from services.web_reliability import page_correlation_id


LOGGER = logging.getLogger("eventplus.kiosk")
if not LOGGER.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _formatter.converter = time.gmtime
    _handler.setFormatter(_formatter)
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

_SENSITIVE_FIELD = re.compile(r"(?:token|cookie|authorization|password|pin|email|qr|name)", re.I)


def _safe_value(value: Any) -> str:
    if value is None:
        return "none"
    text = str(value)
    if re.search(r"(?:token|cookie|bearer|authorization|https?://)", text, re.I):
        return "<redacted>"
    return re.sub(r"[^A-Za-z0-9_./:=-]", "_", text)[:120] or "empty"


def kiosk_log(page: Any, family: str, event: str, **fields: Any) -> None:
    """Emit one PII-safe, stderr-backed Kiosk diagnostic record."""
    route = str(getattr(page, "route", None) or "/").split("?", 1)[0]
    values: dict[str, Any] = {
        "page_id": page_correlation_id(page),
        "render_instance": os.environ.get("RENDER_INSTANCE_ID") or "local",
        "git_commit": os.environ.get("RENDER_GIT_COMMIT") or "local",
        "route": route,
    }
    for key, value in fields.items():
        values[key] = "<redacted>" if _SENSITIVE_FIELD.search(key) else value
    detail = " ".join(f"{key}={_safe_value(value)}" for key, value in values.items())
    LOGGER.info("[%s][%s] %s", _safe_value(family), _safe_value(event), detail)
