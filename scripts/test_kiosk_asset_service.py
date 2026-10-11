from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_asset_service import (
    KIOSK_ASSET_SIGNED_URL_TTL_SECONDS,
    KIOSK_BACKGROUNDS_BUCKET,
    KIOSK_PANELS_BUCKET,
    KioskVisualAsset,
    KioskVisualAssetCache,
    kiosk_asset_location,
    resolve_kiosk_asset_url,
    resolve_kiosk_panel_url,
)
import services.kiosk_asset_service as kiosk_asset_service


class Bucket:
    def __init__(self, storage: "Storage", bucket: str) -> None:
        self.storage = storage
        self.bucket = bucket

    def create_signed_url(self, path: str, ttl: int) -> Any:
        self.storage.requests.append((self.bucket, path, ttl))
        if self.storage.error:
            raise self.storage.error
        return self.storage.responses.get(self.bucket, {})


class Storage:
    def __init__(self, responses: dict[str, Any], error: Exception | None = None) -> None:
        self.responses = responses
        self.error = error
        self.bucket = ""
        self.requests: list[tuple[str, str, int]] = []

    def from_(self, bucket: str) -> Bucket:
        self.bucket = bucket
        return Bucket(self, bucket)


class Client:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage


class _Headers:
    def get_content_type(self) -> str:
        return "image/jpeg"


class _JpegResponse:
    headers = _Headers()

    def __enter__(self) -> "_JpegResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self, _size: int) -> bytes:
        # SOF0: height=2, width=3. The remaining bytes only complete its segment.
        return b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x02\x00\x03" + (b"\x00" * 10)


def main() -> None:
    assert kiosk_asset_location(2, 10, "background").bucket == KIOSK_BACKGROUNDS_BUCKET
    assert kiosk_asset_location(2, 10, "background").path == "2/10.jpg"
    assert kiosk_asset_location(2, 10, "panel").bucket == KIOSK_PANELS_BUCKET
    assert kiosk_asset_location(2, 10, "panel").path == "2/10/panel.jpg"

    storage = Storage({KIOSK_PANELS_BUCKET: {"signedUrl": "https://example.invalid/panel.jpg"}})
    assert resolve_kiosk_panel_url(Client(storage), 2, 10) == "https://example.invalid/panel.jpg"
    assert storage.requests == [(KIOSK_PANELS_BUCKET, "2/10/panel.jpg", KIOSK_ASSET_SIGNED_URL_TTL_SECONDS)]

    assert resolve_kiosk_asset_url(Client(Storage({})), 2, 10, "panel") is None
    assert resolve_kiosk_panel_url(Client(Storage({}, RuntimeError("denied"))), 2, 10) is None

    original_urlopen = kiosk_asset_service.urlopen
    kiosk_asset_service.urlopen = lambda *_args, **_kwargs: _JpegResponse()
    try:
        jpeg_asset = kiosk_asset_service.load_kiosk_visual_asset(
            "https://example.invalid/panel.jpg", "panel"
        )
    finally:
        kiosk_asset_service.urlopen = original_urlopen
    assert jpeg_asset is not None
    assert jpeg_asset.data_url.startswith("data:image/jpeg;base64,")
    assert (jpeg_asset.width, jpeg_asset.height) == (3, 2)

    loads: list[tuple[str, str]] = []
    cache = KioskVisualAssetCache(
        loader=lambda url, asset_type: loads.append((url, asset_type)) or KioskVisualAsset(
            data_url=f"data:image/png;base64,{asset_type}",
            byte_count=128,
            width=100,
            height=50,
            cache_hit=False,
        )
    )
    cached_storage = Storage(
        {
            KIOSK_BACKGROUNDS_BUCKET: {"signedURL": "https://example.invalid/background.jpg"},
            KIOSK_PANELS_BUCKET: {"signedURL": "https://example.invalid/panel.jpg"},
        }
    )
    first = cache.get_or_load(Client(cached_storage), 2, 10, "background")
    second = cache.get_or_load(Client(cached_storage), 2, 10, "background")
    assert first is not None and not first.cache_hit
    assert second is not None and second.cache_hit
    assert len(cached_storage.requests) == 1 and len(loads) == 1
    cache.activate(2, 11)
    assert cache.get_or_load(Client(cached_storage), 2, 10, "background") is not None
    assert len(cached_storage.requests) == 2

    started = threading.Event()
    released = threading.Event()
    parallel_loads: list[str] = []
    concurrent_cache = KioskVisualAssetCache(
        loader=lambda url, asset_type: (
            started.set(), released.wait(1), parallel_loads.append(asset_type),
            KioskVisualAsset("data:image/png;base64,x", 1, 1, 1, False),
        )[-1]
    )
    results: list[Any] = []
    worker = lambda: results.append(
        concurrent_cache.get_or_load(Client(cached_storage), 2, 10, "panel")
    )
    first_worker = threading.Thread(target=worker)
    second_worker = threading.Thread(target=worker)
    first_worker.start()
    assert started.wait(1)
    second_worker.start()
    released.set()
    first_worker.join(1)
    second_worker.join(1)
    assert len(parallel_loads) == 1 and len(results) == 2 and all(results)
    print("Kiosk asset service tests passed.")


if __name__ == "__main__":
    main()
