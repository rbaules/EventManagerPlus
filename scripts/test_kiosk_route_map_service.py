from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_route_map_service import (
    KIOSK_ROUTE_MAP_SIGNED_URL_TTL_SECONDS,
    MapAssetCache,
    load_kiosk_route_map_data_url,
    resolve_kiosk_route_map_url,
)
import services.kiosk_route_map_service as route_map_service


class Bucket:
    def __init__(self, storage: "Storage") -> None:
        self.storage = storage

    def create_signed_url(self, path: str, ttl: int) -> dict[str, str]:
        self.storage.request = (self.storage.bucket, path, ttl)
        if self.storage.error:
            raise self.storage.error
        return self.storage.response


class Storage:
    def __init__(self, response: dict[str, str], error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.bucket = ""
        self.request: tuple[str, str, int] | None = None

    def from_(self, bucket: str) -> Bucket:
        self.bucket = bucket
        return Bucket(self)


class Client:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage


def test_signed_url_uses_supplied_private_storage_identity() -> None:
    storage = Storage({"signedURL": "https://example.invalid/signed-map.jpg"})
    assert resolve_kiosk_route_map_url(Client(storage), "event-maps", "2/10/floorplan.jpg") == storage.response["signedURL"]
    assert storage.request == ("event-maps", "2/10/floorplan.jpg", KIOSK_ROUTE_MAP_SIGNED_URL_TTL_SECONDS)


def test_failures_are_a_safe_none_fallback() -> None:
    assert resolve_kiosk_route_map_url(Client(Storage({}, RuntimeError("denied"))), "event-maps", "2/10/floorplan.jpg") is None
    assert resolve_kiosk_route_map_url(Client(Storage({})), "event-maps", "2/10/floorplan.jpg") is None


def test_preload_creates_local_data_url_before_preview_publish() -> None:
    class Headers:
        def get_content_type(self) -> str:
            return "image/jpeg"

    class Response:
        headers = Headers()

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b"image-bytes"

    original = route_map_service.urlopen
    route_map_service.urlopen = lambda _request, timeout: Response()
    try:
        value = load_kiosk_route_map_data_url("https://example.invalid/signed-map.jpg")
    finally:
        route_map_service.urlopen = original
    assert value == "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM="


def test_asset_cache_reuses_local_data_url_and_coalesces_requests() -> None:
    cache = MapAssetCache()
    calls: list[str] = []

    def resolve(*_args: object) -> str:
        calls.append("signed")
        return "https://example.invalid/signed-map.jpg"

    def load(_url: str) -> str:
        calls.append("download")
        return "data:image/jpeg;base64,ZmFrZQ=="

    first = cache.get_or_load(Client(Storage({})), "event-maps", "2/10/floorplan.jpg", resolve_url=resolve, load_data_url=load)
    second = cache.get_or_load(Client(Storage({})), "event-maps", "2/10/floorplan.jpg", resolve_url=resolve, load_data_url=load)
    assert first is not None and not first.cache_hit and first.signed_url is not None
    assert second is not None and second.cache_hit and second.signed_url is None
    assert first.data_url == second.data_url
    assert calls == ["signed", "download"]


def test_asset_cache_coalesces_concurrent_downloads() -> None:
    cache = MapAssetCache()
    calls: list[str] = []
    download_started = threading.Event()
    release_download = threading.Event()

    def resolve(*_args: object) -> str:
        calls.append("signed")
        return "https://example.invalid/signed-map.jpg"

    def load(_url: str) -> str:
        calls.append("download")
        download_started.set()
        assert release_download.wait(1)
        return "data:image/jpeg;base64,ZmFrZQ=="

    results: list[object] = []
    def request_asset() -> None:
        results.append(cache.get_or_load(Client(Storage({})), "event-maps", "2/10/floorplan.jpg", resolve_url=resolve, load_data_url=load))

    first = threading.Thread(target=request_asset)
    second = threading.Thread(target=request_asset)
    first.start()
    assert download_started.wait(1)
    second.start()
    release_download.set()
    first.join(1)
    second.join(1)
    assert len(results) == 2 and all(result is not None for result in results)
    assert calls == ["signed", "download"]


def main() -> None:
    test_signed_url_uses_supplied_private_storage_identity()
    test_failures_are_a_safe_none_fallback()
    test_preload_creates_local_data_url_before_preview_publish()
    test_asset_cache_reuses_local_data_url_and_coalesces_requests()
    test_asset_cache_coalesces_concurrent_downloads()
    print("Kiosk route-map service tests passed.")


if __name__ == "__main__":
    main()
