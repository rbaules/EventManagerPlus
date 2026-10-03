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
        self.camera_description = None

    def invalidate(self) -> int:
        self.generation += 1
        return self.generation

    def is_scanner_session_current(
        self,
        generation: int,
        scanner_active: bool,
        expected_key: tuple[int, int],
        session_key: tuple[int, int] | None,
        current_key: tuple[int, int] | None,
    ) -> bool:
        return (
            generation == self.generation
            and scanner_active
            and expected_key == session_key
            and expected_key == current_key
        )
