from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_e2e_service import KioskE2EProfiler


def test_profiler_uses_one_page_origin_and_safe_fields() -> None:
    ticks = iter((10.0, 10.05, 10.2, 10.3, 10.4))
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        profiler = KioskE2EProfiler(clock=lambda: next(ticks))
        began = profiler.mark("E1_SESSION_RESTORE_BEGIN", cookie="secret-cookie")
        profiler.duration("E1_SESSION_RESTORE_END", began, query="context")
        profiler.ready()

    trace = output.getvalue()
    assert "stage=E0_PAGE_CREATED total_ms=50.0" in trace
    assert "stage=E1_SESSION_RESTORE_BEGIN total_ms=200.0" in trace
    assert "cookie=<redacted>" in trace
    assert "duration_ms=100.0" in trace
    assert "[KIOSK-E2E][READY] total_ms=400.0" in trace
    assert "secret-cookie" not in trace


def test_oauth_reuses_the_prevalidated_context() -> None:
    source = (ROOT / "views" / "login_view.py").read_text(encoding="utf-8")
    assert "web_context_prepared = True" in source
    assert "load_context=not context_already_loaded" in source


def main() -> None:
    test_profiler_uses_one_page_origin_and_safe_fields()
    test_oauth_reuses_the_prevalidated_context()
    print("Kiosk end-to-end profiler tests passed.")


if __name__ == "__main__":
    main()
