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

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/auth/callback"


def validate_config() -> None:
    if not SUPABASE_URL:
        raise RuntimeError("Falta SUPABASE_URL en el archivo .env")

    if not SUPABASE_PUBLISHABLE_KEY:
        raise RuntimeError("Falta SUPABASE_PUBLISHABLE_KEY en el archivo .env")
