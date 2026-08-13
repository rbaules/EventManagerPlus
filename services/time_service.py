from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


PANAMA_TIMEZONE = ZoneInfo("America/Panama")


def parse_instant(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value not in (None, ""):
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def instante_panama(value: Any) -> datetime | None:
    parsed = parse_instant(value)
    return parsed.astimezone(PANAMA_TIMEZONE) if parsed is not None else None


def hora_panama(value: Any) -> str | None:
    local = instante_panama(value)
    return local.strftime("%I:%M %p") if local is not None else None


def fecha_hora_panama(value: Any) -> str | None:
    local = instante_panama(value)
    return local.strftime("%d/%m/%Y %I:%M %p") if local is not None else None
