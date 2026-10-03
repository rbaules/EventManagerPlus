"""Estado técnico mínimo compartido durante la extracción QR-KIOSK-0B."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from services.qr_scanner_service import QrFrameGate


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

    def accept_snapshot_code(
        self,
        codigo: str,
        generation: int,
        scanner_active: bool,
        expected_key: tuple[int, int],
        session_key: tuple[int, int] | None,
        current_key: tuple[int, int] | None,
        gate: QrFrameGate,
        on_code_accepted: Callable[[str, int, tuple[int, int]], bool],
    ) -> bool:
        if not self.is_scanner_session_current(
            generation,
            scanner_active,
            expected_key,
            session_key,
            current_key,
        ) or not gate.try_begin_decode():
            return False
        accepted = gate.finish_decode(codigo)
        return bool(accepted and on_code_accepted(accepted, generation, expected_key))
