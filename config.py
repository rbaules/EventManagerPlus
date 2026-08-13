from __future__ import annotations

import os
import ipaddress
from urllib.parse import urlparse

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
_DEFAULT_WEB_OAUTH_PORT = (
    "8560"
    if os.getenv("EVENTPLUS_ASGI", "false").strip().lower()
    in {"1", "true", "yes", "on"}
    else "8550"
)
EVENTPLUS_WEB_OAUTH_REDIRECT_URL = os.getenv(
    "EVENTPLUS_WEB_OAUTH_REDIRECT_URL",
    f"http://127.0.0.1:{_DEFAULT_WEB_OAUTH_PORT}/auth/callback",
).strip()
EVENTPLUS_PUBLIC_BASE_URL = os.getenv("EVENTPLUS_PUBLIC_BASE_URL", "").strip()
EVENTPLUS_WEB_OAUTH_CALLBACK_PATH = "/auth/callback"


def normalize_web_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme.lower(), parsed.scheme.lower())
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("La URL base web debe ser una URL HTTP(S) absoluta.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("La URL base web no admite credenciales, query ni fragmento.")
    if parsed.path not in {"", "/"}:
        raise ValueError("La URL base web no debe incluir una ruta.")
    try:
        parsed.port
    except ValueError as ex:
        raise ValueError("La URL base web contiene un puerto inválido.") from ex
    return f"{scheme}://{parsed.netloc}"


def _request_origin_allowed(base_url: str) -> bool:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_private
    except ValueError:
        return False


def resolve_web_base_url(page_url: str | None = None) -> tuple[str, str]:
    if EVENTPLUS_PUBLIC_BASE_URL:
        return normalize_web_base_url(EVENTPLUS_PUBLIC_BASE_URL), "config"
    if page_url:
        candidate = normalize_web_base_url(page_url)
        if _request_origin_allowed(candidate):
            return candidate, "request"
        raise ValueError("El origen web público requiere EVENTPLUS_PUBLIC_BASE_URL.")
    parsed_fallback = urlparse(EVENTPLUS_WEB_OAUTH_REDIRECT_URL)
    fallback = normalize_web_base_url(
        f"{parsed_fallback.scheme}://{parsed_fallback.netloc}"
    )
    if not _request_origin_allowed(fallback):
        raise ValueError("El fallback OAuth web no es un origen local permitido.")
    return fallback, "fallback"


def resolve_web_oauth_redirect_url(page_url: str | None = None) -> tuple[str, str, str]:
    base_url, source = resolve_web_base_url(page_url)
    redirect_to = f"{base_url}{EVENTPLUS_WEB_OAUTH_CALLBACK_PATH}"
    if urlparse(redirect_to).port == 3000 and (urlparse(redirect_to).hostname or "").lower() == "localhost":
        raise ValueError("localhost:3000 no es un callback OAuth válido de EventPlus.")
    return base_url, redirect_to, source
EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS = max(
    30,
    int(os.getenv("EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS", "600")),
)
EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS = max(
    1,
    int(os.getenv("EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS", "120")),
)
EVENTPLUS_AUTH_DEBUG = (
    os.getenv("EVENTPLUS_AUTH_DEBUG", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
EVENTPLUS_SESSION_COOKIE_NAME = (
    os.getenv("EVENTPLUS_SESSION_COOKIE_NAME", "eventplus_session").strip()
    or "eventplus_session"
)
EVENTPLUS_SESSION_COOKIE_SECURE = (
    os.getenv("EVENTPLUS_SESSION_COOKIE_SECURE", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
EVENTPLUS_SESSION_COOKIE_SAMESITE = (
    os.getenv("EVENTPLUS_SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    or "lax"
)
if EVENTPLUS_SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError(
        "EVENTPLUS_SESSION_COOKIE_SAMESITE debe ser lax, strict o none."
    )
EVENTPLUS_SESSION_TTL_SECONDS = max(
    60,
    int(os.getenv("EVENTPLUS_SESSION_TTL_SECONDS", "28800")),
)
EVENTPLUS_SESSION_ROTATE_ON_RESTORE = (
    os.getenv("EVENTPLUS_SESSION_ROTATE_ON_RESTORE", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
EVENTPLUS_SESSION_REPOSITORY = (
    os.getenv("EVENTPLUS_SESSION_REPOSITORY", "memory").strip().lower()
    or "memory"
)
if EVENTPLUS_SESSION_REPOSITORY != "memory":
    raise RuntimeError(
        "Esta version solo admite EVENTPLUS_SESSION_REPOSITORY=memory."
    )


def _configure_flet_web_oauth_endpoint() -> None:
    callback_path = EVENTPLUS_WEB_OAUTH_CALLBACK_PATH.strip("/")
    if not callback_path:
        raise RuntimeError(
            "EVENTPLUS_WEB_OAUTH_REDIRECT_URL debe incluir una ruta de callback."
        )
    os.environ.setdefault("FLET_OAUTH_CALLBACK_HANDLER_ENDPOINT", callback_path)
    os.environ.setdefault(
        "FLET_OAUTH_STATE_TIMEOUT",
        str(EVENTPLUS_WEB_OAUTH_STATE_TTL_SECONDS),
    )


_configure_flet_web_oauth_endpoint()

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

    if EVENTPLUS_PUBLIC_BASE_URL:
        try:
            normalize_web_base_url(EVENTPLUS_PUBLIC_BASE_URL)
        except ValueError as ex:
            raise RuntimeError("EVENTPLUS_PUBLIC_BASE_URL no es válida.") from ex

    parsed_web_redirect = urlparse(EVENTPLUS_WEB_OAUTH_REDIRECT_URL)
    if parsed_web_redirect.scheme not in {"http", "https"} or not parsed_web_redirect.netloc:
        raise RuntimeError(
            "EVENTPLUS_WEB_OAUTH_REDIRECT_URL debe ser una URL HTTP(S) absoluta."
        )
