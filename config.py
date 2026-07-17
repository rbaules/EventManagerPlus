from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
SUPABASE_OAUTH_REDIRECT_URL = os.getenv(
    "SUPABASE_OAUTH_REDIRECT_URL",
    "http://localhost:8765/auth/callback",
).strip()

APP_MODE_FULL = "FULL"
APP_MODE_CHECKIN = "CHECKIN"
APP_MODES = {APP_MODE_FULL, APP_MODE_CHECKIN}
APP_VERSION = os.getenv("EVENTPLUS_VERSION", "0.1.0-checkin").strip() or "0.1.0-checkin"


def get_app_mode() -> str:
    raw_mode = os.getenv("EVENTPLUS_MODE", APP_MODE_FULL).strip().upper() or APP_MODE_FULL
    if raw_mode not in APP_MODES:
        print("[APP][WARNING] Modo de aplicacion invalido; usando FULL:", raw_mode)
        return APP_MODE_FULL
    return raw_mode


APP_MODE = get_app_mode()


def is_checkin_mode() -> bool:
    return APP_MODE == APP_MODE_CHECKIN

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/auth/callback"


def validate_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Falta SUPABASE_URL en el archivo .env")

    if not SUPABASE_PUBLISHABLE_KEY:
        raise RuntimeError("Falta SUPABASE_PUBLISHABLE_KEY en el archivo .env")
