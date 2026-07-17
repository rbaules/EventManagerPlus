from __future__ import annotations

import os


os.environ["EVENTPLUS_MODE"] = "CHECKIN"

from app import main  # noqa: E402

import flet as ft  # noqa: E402


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
