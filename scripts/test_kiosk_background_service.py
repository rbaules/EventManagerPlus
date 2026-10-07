from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_background_service import (
    KIOSK_BACKGROUNDS_BUCKET,
    KIOSK_BACKGROUND_SIGNED_URL_TTL_SECONDS,
    kiosk_background_object_path,
    resolve_kiosk_background_url,
)


class FakeBucket:
    def __init__(self, storage: "FakeStorage") -> None:
        self.storage = storage

    def create_signed_url(self, path: str, expires_in: int) -> Any:
        self.storage.calls.append((self.storage.bucket, path, expires_in))
        if self.storage.error is not None:
            raise self.storage.error
        return self.storage.response


class FakeStorage:
    def __init__(self, response: Any, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.bucket = ""
        self.calls: list[tuple[str, str, int]] = []

    def from_(self, bucket: str) -> FakeBucket:
        self.bucket = bucket
        return FakeBucket(self)


class FakeSupabase:
    def __init__(self, storage: FakeStorage) -> None:
        self.storage = storage


def main() -> None:
    assert kiosk_background_object_path(2, 9) == "2/9.jpg"
    storage = FakeStorage(
        {
            "signedURL": "https://example.invalid/signed",
            "signedUrl": "https://example.invalid/signed",
        }
    )
    assert resolve_kiosk_background_url(FakeSupabase(storage), 2, 9) == "https://example.invalid/signed"
    assert storage.calls == [
        (KIOSK_BACKGROUNDS_BUCKET, "2/9.jpg", KIOSK_BACKGROUND_SIGNED_URL_TTL_SECONDS)
    ]

    assert resolve_kiosk_background_url(FakeSupabase(FakeStorage({})), 2, 10) is None
    assert resolve_kiosk_background_url(FakeSupabase(FakeStorage({}, RuntimeError("missing"))), 2, 10) is None
    print("Kiosk background service tests passed.")


if __name__ == "__main__":
    main()
