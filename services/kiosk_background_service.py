from __future__ import annotations

from typing import Any

from services.kiosk_asset_service import (
    KIOSK_ASSET_SIGNED_URL_TTL_SECONDS,
    KIOSK_BACKGROUNDS_BUCKET,
    kiosk_asset_location,
    resolve_kiosk_background_url as _resolve_kiosk_background_url,
)

KIOSK_BACKGROUND_SIGNED_URL_TTL_SECONDS = KIOSK_ASSET_SIGNED_URL_TTL_SECONDS


def kiosk_background_object_path(cuenta_id: int, evento_id: int) -> str:
    """Return the deterministic Storage path for one Kiosk event background."""
    return kiosk_asset_location(cuenta_id, evento_id, "background").path


def resolve_kiosk_background_url(
    supabase: Any,
    cuenta_id: int,
    evento_id: int,
) -> str | None:
    """Resolve a short-lived URL with the already-authenticated Supabase client.

    The bucket is intentionally treated as private: the caller can upload the
    conventional object without exposing every event image publicly.
    """
    return _resolve_kiosk_background_url(supabase, cuenta_id, evento_id)
