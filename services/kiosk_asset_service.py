from __future__ import annotations

import base64
import re
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal
from urllib.request import Request, urlopen


KIOSK_ASSET_SIGNED_URL_TTL_SECONDS = 3600
KIOSK_BACKGROUNDS_BUCKET = "kiosk-backgrounds"
KIOSK_PANELS_BUCKET = "kiosk-panels"
KIOSK_ASSET_MAX_BYTES = 15 * 1024 * 1024
KioskAssetType = Literal["background", "panel"]


@dataclass(frozen=True)
class KioskAssetLocation:
    asset_type: KioskAssetType
    bucket: str
    path: str


@dataclass(frozen=True)
class KioskVisualAsset:
    """A render-ready asset kept only in the current Kiosk session."""

    data_url: str
    byte_count: int
    width: int | None
    height: int | None
    cache_hit: bool


def _image_dimensions(payload: bytes, content_type: str) -> tuple[int | None, int | None]:
    """Read PNG/JPEG dimensions without adding an image-processing dependency."""
    if content_type == "image/png" and len(payload) >= 24 and payload[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")
    if content_type == "image/jpeg" and payload[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(payload):
            if payload[offset] != 0xFF:
                offset += 1
                continue
            marker = payload[offset + 1]
            offset += 2
            while marker == 0xFF and offset < len(payload):
                marker = payload[offset]
                offset += 1
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(payload):
                break
            size = int.from_bytes(payload[offset : offset + 2], "big")
            if size < 2 or offset + size > len(payload):
                break
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
                return (
                    int.from_bytes(payload[offset + 5 : offset + 7], "big"),
                    int.from_bytes(payload[offset + 3 : offset + 5], "big"),
                )
            offset += size
    return None, None


def load_kiosk_visual_asset(signed_url: str, asset_type: KioskAssetType) -> KioskVisualAsset | None:
    """Download one private image once, returning a safe local data URI."""
    try:
        started = perf_counter()
        request = Request(signed_url, headers={"Accept": "image/*"})
        with urlopen(request, timeout=15) as response:  # nosec B310 - URL came from Storage signing
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise ValueError("respuesta no es una imagen")
            payload = response.read(KIOSK_ASSET_MAX_BYTES + 1)
        if not payload or len(payload) > KIOSK_ASSET_MAX_BYTES:
            raise ValueError("tamano de imagen invalido")
        width, height = _image_dimensions(payload, content_type)
        print(
            "[KIOSK-ASSET][PERF] "
            f"stage=download asset={asset_type} duration_ms={(perf_counter() - started) * 1000:.1f} "
            f"bytes={len(payload)} width={width or '<unknown>'} height={height or '<unknown>'}"
        )
        conversion_started = perf_counter()
        data_url = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
        print(
            "[KIOSK-ASSET][PERF] "
            f"stage=data_uri asset={asset_type} duration_ms={(perf_counter() - conversion_started) * 1000:.1f}"
        )
        return KioskVisualAsset(data_url, len(payload), width, height, cache_hit=False)
    except Exception as ex:
        print(
            "[KIOSK-ASSET] "
            f"{asset_type} download unavailable type={type(ex).__name__} "
            f"message={_safe_error_detail(ex)}"
        )
        return None


class KioskVisualAssetCache:
    """Per-session cache for event artwork; signed URLs are never retained."""

    def __init__(self, *, loader: Any = None) -> None:
        self._lock = threading.Lock()
        self._assets: dict[tuple[int, int, KioskAssetType], KioskVisualAsset] = {}
        self._inflight: dict[tuple[int, int, KioskAssetType], threading.Event] = {}
        self._loader = loader or load_kiosk_visual_asset

    def clear(self) -> None:
        with self._lock:
            self._assets.clear()

    def activate(self, cuenta_id: int, evento_id: int) -> None:
        """Scope the cache to the active event and discard prior-event artwork."""
        active = (int(cuenta_id), int(evento_id))
        with self._lock:
            self._assets = {
                key: asset for key, asset in self._assets.items() if key[:2] == active
            }

    def get_or_load(
        self,
        supabase: Any,
        cuenta_id: int,
        evento_id: int,
        asset_type: KioskAssetType,
    ) -> KioskVisualAsset | None:
        key = (int(cuenta_id), int(evento_id), asset_type)
        with self._lock:
            cached = self._assets.get(key)
            if cached is not None:
                print(f"[KIOSK-ASSET] {asset_type} cache hit")
                return KioskVisualAsset(
                    cached.data_url, cached.byte_count, cached.width, cached.height, cache_hit=True
                )
            completed = self._inflight.get(key)
            if completed is None:
                completed = threading.Event()
                self._inflight[key] = completed
                owner = True
                print(f"[KIOSK-ASSET] {asset_type} cache miss")
            else:
                owner = False
                print(f"[KIOSK-ASSET] {asset_type} reuse in-flight")

        if not owner:
            completed.wait()
            with self._lock:
                cached = self._assets.get(key)
            if cached is None:
                return None
            return KioskVisualAsset(
                cached.data_url, cached.byte_count, cached.width, cached.height, cache_hit=True
            )

        try:
            signed_started = perf_counter()
            signed_url = resolve_kiosk_asset_url(supabase, key[0], key[1], asset_type)
            print(
                "[KIOSK-ASSET][PERF] "
                f"stage=create_signed_url asset={asset_type} "
                f"duration_ms={(perf_counter() - signed_started) * 1000:.1f}"
            )
            if signed_url is None:
                return None
            asset = self._loader(signed_url, asset_type)
            if asset is None:
                return None
            with self._lock:
                self._assets[key] = asset
            return asset
        finally:
            with self._lock:
                completed = self._inflight.pop(key, None)
            if completed is not None:
                completed.set()


def _safe_error_detail(error: Exception) -> str:
    """Keep diagnostics useful without exposing signed URLs or credentials."""
    message = str(error).replace("\n", " ").replace("\r", " ")
    message = re.sub(r"https?://\S+", "<url>", message, flags=re.IGNORECASE)
    message = re.sub(
        r"(?i)(access[_-]?token|refresh[_-]?token|token|apikey|authorization)"
        r"\s*[:=]\s*\S+",
        r"\1=<redacted>",
        message,
    )
    return message[:240] or "<sin detalle>"


def kiosk_asset_location(
    cuenta_id: int,
    evento_id: int,
    asset_type: KioskAssetType,
) -> KioskAssetLocation:
    account_id = int(cuenta_id)
    event_id = int(evento_id)
    if asset_type == "background":
        return KioskAssetLocation(
            asset_type=asset_type,
            bucket=KIOSK_BACKGROUNDS_BUCKET,
            path=f"{account_id}/{event_id}.jpg",
        )
    if asset_type == "panel":
        return KioskAssetLocation(
            asset_type=asset_type,
            bucket=KIOSK_PANELS_BUCKET,
            path=f"{account_id}/{event_id}/panel.jpg",
        )
    raise ValueError(f"Unsupported Kiosk asset type: {asset_type}")


def resolve_kiosk_asset_url(
    supabase: Any,
    cuenta_id: int,
    evento_id: int,
    asset_type: KioskAssetType,
) -> str | None:
    """Resolve a private event asset using the Page's authenticated client."""
    location = kiosk_asset_location(cuenta_id, evento_id, asset_type)
    if location.asset_type == "panel":
        print("[KIOSK-ASSET] panel format=jpg")
    print(
        "[KIOSK-ASSET] lookup "
        f"asset={location.asset_type} account_id={cuenta_id} event_id={evento_id} "
        f"bucket={location.bucket} path={location.path}"
    )
    try:
        response = (
            supabase.storage.from_(location.bucket).create_signed_url(
                location.path,
                KIOSK_ASSET_SIGNED_URL_TTL_SECONDS,
            )
        )
    except Exception as ex:
        print(
            "[KIOSK-ASSET] "
            f"{location.asset_type} unavailable type={type(ex).__name__} "
            f"message={_safe_error_detail(ex)}"
        )
        return None
    if isinstance(response, dict):
        url = response.get("signedURL") or response.get("signedUrl") or response.get("signed_url")
    else:
        url = (
            getattr(response, "signedURL", None)
            or getattr(response, "signedUrl", None)
            or getattr(response, "signed_url", None)
        )
    if not isinstance(url, str) or not url.strip():
        print(f"[KIOSK-ASSET] {location.asset_type} unavailable reason=missing_signed_url")
        return None
    print(f"[KIOSK-ASSET] {location.asset_type} ready")
    return url


def resolve_kiosk_background_url(supabase: Any, cuenta_id: int, evento_id: int) -> str | None:
    return resolve_kiosk_asset_url(supabase, cuenta_id, evento_id, "background")


def resolve_kiosk_panel_url(supabase: Any, cuenta_id: int, evento_id: int) -> str | None:
    return resolve_kiosk_asset_url(supabase, cuenta_id, evento_id, "panel")
