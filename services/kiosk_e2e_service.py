from __future__ import annotations

import re
import threading
from time import perf_counter
from typing import Any, Callable


def _safe_value(value: Any) -> str:
    """Keep startup logs diagnostic-only: no cookies, tokens, or user data."""
    if value is None:
        return "none"
    text = str(value)
    if re.search(r"token|cookie|bearer|authorization|https?://", text, re.IGNORECASE):
        return "<redacted>"
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", text)[:80] or "empty"


class KioskE2EProfiler:
    """Per-Page, PII-free timeline for the standalone Kiosk startup path."""

    def __init__(self, *, clock: Callable[[], float] = perf_counter) -> None:
        self._clock = clock
        self.started_at = clock()
        self._lock = threading.Lock()
        self.events: list[tuple[str, float]] = []
        self._markers: dict[str, float] = {}
        self.mark("E0_PAGE_CREATED")

    def mark(self, stage: str, **fields: Any) -> float:
        now = self._clock()
        with self._lock:
            total_ms = max(0.0, (now - self.started_at) * 1000)
            self.events.append((stage, total_ms))
        details = " ".join(
            f"{key}={_safe_value(value)}" for key, value in sorted(fields.items())
        )
        suffix = f" {details}" if details else ""
        print(f"[KIOSK-E2E][PERF] stage={stage} total_ms={total_ms:.1f}{suffix}")
        return now

    def duration(self, stage: str, began_at: float, **fields: Any) -> float:
        now = self._clock()
        duration_ms = max(0.0, (now - began_at) * 1000)
        total_ms = max(0.0, (now - self.started_at) * 1000)
        details = " ".join(
            f"{key}={_safe_value(value)}" for key, value in sorted(fields.items())
        )
        suffix = f" {details}" if details else ""
        print(
            f"[KIOSK-E2E][PERF] stage={stage} total_ms={total_ms:.1f} "
            f"duration_ms={duration_ms:.1f}{suffix}"
        )
        return now

    def ready(self) -> None:
        now = self._clock()
        total_ms = max(0.0, (now - self.started_at) * 1000)
        with self._lock:
            self.events.append(("E10_SCANNER_READY", total_ms))
        print(f"[KIOSK-E2E][READY] total_ms={total_ms:.1f}")
        oauth_callback_at = self._markers.get("E1_OAUTH_CALLBACK_RECEIVED")
        if oauth_callback_at is not None:
            print(
                "[KIOSK-E2E][OAUTH_READY] "
                f"callback_to_ready_ms={max(0.0, (now - oauth_callback_at) * 1000):.1f}"
            )

    def checkpoint(self, stage: str, **fields: Any) -> float:
        now = self.mark(stage, **fields)
        with self._lock:
            self._markers[stage] = now
        return now
