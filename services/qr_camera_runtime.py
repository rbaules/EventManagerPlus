"""Estado técnico mínimo compartido durante la extracción QR-KIOSK-0B."""

from __future__ import annotations

import asyncio


class QrCameraRuntime:
    def __init__(self) -> None:
        self.generation = 0
        self.snapshot_task: asyncio.Task[object] | None = None
        self.controller_initialized = False
        self.preview_paused = False
        self.lifecycle_lock = asyncio.Lock()

    def invalidate(self) -> int:
        self.generation += 1
        return self.generation
