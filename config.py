from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

try:
    from app_public_config import (  # type: ignore
        SUPABASE_PUBLISHABLE_KEY as PUBLIC_SUPABASE_PUBLISHABLE_KEY,
        SUPABASE_URL as PUBLIC_SUPABASE_URL,
    )
except ImportError:
    PUBLIC_SUPABASE_URL = ""
    PUBLIC_SUPABASE_PUBLISHABLE_KEY = ""


SUPABASE_URL = (os.getenv("SUPABASE_URL") or PUBLIC_SUPABASE_URL or "").strip()
SUPABASE_PUBLISHABLE_KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY") or PUBLIC_SUPABASE_PUBLISHABLE_KEY or ""
).strip()
SUPABASE_OAUTH_REDIRECT_URL = os.getenv(
    "SUPABASE_OAUTH_REDIRECT_URL",
    "http://localhost:8765/auth/callback",
).strip()

APP_MODE_FULL = "FULL"
APP_MODE_CHECKIN = "CHECKIN"
APP_MODES = {APP_MODE_FULL, APP_MODE_CHECKIN}
APP_VERSION = os.getenv("EVENTPLUS_VERSION", "0.1.0-checkin").strip() or "0.1.0-checkin"
ANDROID_PACKAGE_ID = "com.eventplus.beta.checkin"
ANDROID_PRODUCT_NAME = "EventPlus Beta"
ANDROID_BUILD_VERSION = "0.1.0"
ANDROID_BUILD_NUMBER = "1"
ANDROID_DEEP_LINK_SCHEME = "eventplusbeta"
ANDROID_DEEP_LINK_HOST = "auth-callback"
ANDROID_OAUTH_REDIRECT_URL = f"{ANDROID_DEEP_LINK_SCHEME}://{ANDROID_DEEP_LINK_HOST}"


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


def is_android_platform(platform: object) -> bool:
    return str(platform).lower().endswith("android")


def get_oauth_redirect_url(platform: object | None = None) -> str:
    if platform is not None and is_android_platform(platform):
        return ANDROID_OAUTH_REDIRECT_URL
    return SUPABASE_OAUTH_REDIRECT_URL


def validate_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Falta SUPABASE_URL en el archivo .env")

    if not SUPABASE_PUBLISHABLE_KEY:
        raise RuntimeError("Falta SUPABASE_PUBLISHABLE_KEY en el archivo .env")
