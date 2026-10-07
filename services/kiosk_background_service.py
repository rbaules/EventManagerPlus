from __future__ import annotations

import re
from typing import Any


KIOSK_BACKGROUNDS_BUCKET = "kiosk-backgrounds"
KIOSK_BACKGROUND_SIGNED_URL_TTL_SECONDS = 3600


def _safe_error_detail(error: Exception) -> str:
    """Keep diagnostic messages useful without emitting URLs or credentials."""
    message = str(error).replace("\n", " ").replace("\r", " ")
    message = re.sub(r"https?://\S+", "<url>", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)(access[_-]?token|refresh[_-]?token|token|apikey|authorization)"
        r"\s*[:=]\s*\S+",
        r"\1=<redacted>",
        message,
    )
    return message[:240] or "<sin detalle>"


def kiosk_background_object_path(cuenta_id: int, evento_id: int) -> str:
    """Return the deterministic Storage path for one Kiosk event background."""
    return f"{int(cuenta_id)}/{int(evento_id)}.jpg"


def resolve_kiosk_background_url(
    supabase: Any,
    cuenta_id: int,
    evento_id: int,
) -> str | None:
    """Resolve a short-lived URL with the already-authenticated Supabase client.

    The bucket is intentionally treated as private: the caller can upload the
    conventional object without exposing every event image publicly.
    """
    object_path = kiosk_background_object_path(cuenta_id, evento_id)
    print(
        "[KIOSK-BG] lookup "
        f"account_id={cuenta_id} event_id={evento_id} "
        f"bucket={KIOSK_BACKGROUNDS_BUCKET} path={object_path}"
    )
    try:
        response = (
            supabase.storage
            .from_(KIOSK_BACKGROUNDS_BUCKET)
            .create_signed_url(object_path, KIOSK_BACKGROUND_SIGNED_URL_TTL_SECONDS)
        )
    except Exception as ex:
        print(
            "[KIOSK-BG] signed_url failed "
            f"account_id={cuenta_id} event_id={evento_id} "
            f"type={type(ex).__name__} message={_safe_error_detail(ex)}"
        )
        return None
    if isinstance(response, dict):
        url = response.get("signedURL") or response.get("signed_url")
    else:
        url = getattr(response, "signedURL", None) or getattr(response, "signed_url", None)
    if not isinstance(url, str) or not url.strip():
        response_type = type(response).__name__
        response_fields = sorted(response) if isinstance(response, dict) else []
        print(
            "[KIOSK-BG] signed_url missing "
            f"account_id={cuenta_id} event_id={evento_id} "
            f"response_type={response_type} fields={response_fields}"
        )
        return None
    print(f"[KIOSK-BG] signed_url success account_id={cuenta_id} event_id={evento_id}")
    return url
