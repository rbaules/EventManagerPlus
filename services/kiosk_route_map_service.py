"""Authenticated signed-URL lookup for an already-calculated Kiosk route map."""

from __future__ import annotations

import base64
import re
import threading
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen


KIOSK_ROUTE_MAP_SIGNED_URL_TTL_SECONDS = 3600
KIOSK_ROUTE_MAP_MAX_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class MapAsset:
    """A local, render-ready event asset; never a persistent signed URL."""

    data_url: str
    cache_hit: bool
    signed_url: str | None = None


class MapAssetCache:
    """Small per-Kiosk memory cache that coalesces concurrent asset loads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._assets: dict[tuple[str, str], str] = {}
        self._inflight: dict[tuple[str, str], threading.Event] = {}

    def clear(self) -> None:
        with self._lock:
            self._assets.clear()

    def get_or_load(
        self,
        supabase: Any,
        bucket: str,
        path: str,
        *,
        resolve_url: Any = None,
        load_data_url: Any = None,
    ) -> MapAsset | None:
        """Return one local data URI, downloading at most once per key."""
        key = (bucket, path)
        resolver = resolve_url or resolve_kiosk_route_map_url
        loader = load_data_url or load_kiosk_route_map_data_url
        with self._lock:
            cached = self._assets.get(key)
            if cached is not None:
                print("[KIOSK-MAP] asset cache hit")
                return MapAsset(data_url=cached, cache_hit=True)
            event = self._inflight.get(key)
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
                owner = True
                print("[KIOSK-MAP] asset cache miss")
            else:
                owner = False

        if not owner:
            event.wait()
            with self._lock:
                cached = self._assets.get(key)
            if cached is not None:
                print("[KIOSK-MAP] asset cache hit")
                return MapAsset(data_url=cached, cache_hit=True)
            return None

        signed_url: str | None = None
        try:
            signed_started = perf_counter()
            signed_url = resolver(supabase, bucket, path)
            print(f"[KIOSK-MAP][PERF] stage=create_signed_url duration_ms={(perf_counter() - signed_started) * 1000:.1f}")
            if signed_url is None:
                return None
            image_started = perf_counter()
            data_url = loader(signed_url)
            print(
                "[KIOSK-MAP][PERF] stage=download_and_data_uri "
                f"duration_ms={(perf_counter() - image_started) * 1000:.1f}"
            )
            if data_url is None:
                return None
            with self._lock:
                self._assets[key] = data_url
            return MapAsset(data_url=data_url, cache_hit=False, signed_url=signed_url)
        finally:
            with self._lock:
                completed = self._inflight.pop(key, None)
            if completed is not None:
                completed.set()


def _safe_error_detail(error: Exception) -> str:
    message = str(error).replace("\n", " ").replace("\r", " ")
    message = re.sub(r"https?://\S+", "<url>", message, flags=re.IGNORECASE)
    return message[:240] or "<sin detalle>"


def resolve_kiosk_route_map_url(supabase: Any, bucket: str, path: str) -> str | None:
    """Use the caller's existing authenticated client; never log its signed URL."""
    try:
        response = (
            supabase.storage.from_(bucket).create_signed_url(path, KIOSK_ROUTE_MAP_SIGNED_URL_TTL_SECONDS)
        )
    except Exception as ex:
        print(
            "[KIOSK-MAP] signed_url failed "
            f"type={type(ex).__name__} message={_safe_error_detail(ex)}"
        )
        return None
    if isinstance(response, dict):
        url = response.get("signedURL") or response.get("signed_url")
    else:
        url = getattr(response, "signedURL", None) or getattr(response, "signed_url", None)
    if not isinstance(url, str) or not url.strip():
        print("[KIOSK-MAP] signed_url failed type=InvalidResponse message=<missing_url>")
        return None
    print("[KIOSK-MAP] signed_url ready")
    return url


def load_kiosk_route_map_data_url(signed_url: str) -> str | None:
    """Fetch an already-authorized map into a local image data URL.

    Flet 0.85.3 does not provide a reliable Image load callback. Loading the
    raster before exposing its separate transparent route layer makes the map
    and route one visual commit, without logging the signed URL or its query
    string.
    """
    try:
        download_started = perf_counter()
        request = Request(signed_url, headers={"Accept": "image/*"})
        with urlopen(request, timeout=15) as response:  # nosec B310 - signed URL is app-generated
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise ValueError("respuesta no es una imagen")
            payload = response.read(KIOSK_ROUTE_MAP_MAX_BYTES + 1)
        if not payload or len(payload) > KIOSK_ROUTE_MAP_MAX_BYTES:
            raise ValueError("tamaño de imagen inválido")
        print(
            "[KIOSK-MAP][PERF] stage=download_floorplan "
            f"duration_ms={(perf_counter() - download_started) * 1000:.1f}"
        )
    except Exception as ex:
        print(
            "[KIOSK-MAP] map_image failed "
            f"type={type(ex).__name__} message={_safe_error_detail(ex)}"
        )
        return None
    conversion_started = perf_counter()
    data_url = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
    print(
        "[KIOSK-MAP][PERF] stage=jpg_to_data_uri "
        f"duration_ms={(perf_counter() - conversion_started) * 1000:.1f}"
    )
    print("[KIOSK-MAP] map_image ready")
    return data_url
