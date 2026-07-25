from __future__ import annotations

import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from config import (
    CALLBACK_HOST,
    CALLBACK_PATH,
    CALLBACK_PORT,
    SUPABASE_OAUTH_REDIRECT_URL,
    get_oauth_redirect_url,
)
from db import get_supabase_client
from services.response_utils import pretty, safe_get, to_dict


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Ruta no encontrada.")
            return

        params = parse_qs(parsed.query)

        result = {
            "code": params["code"][0] if "code" in params and params["code"] else None,
            "error": params["error"][0] if "error" in params and params["error"] else None,
            "error_description": (
                params["error_description"][0]
                if "error_description" in params and params["error_description"]
                else None
            ),
            "raw_path": self.path,
        }

        OAuthCallbackHandler.result_queue.put(result)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        html = """
        <!doctype html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <title>EventPlus - Login completado</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; color: #222; }
                .box {
                    max-width: 640px;
                    border: 1px solid #ddd;
                    border-radius: 12px;
                    padding: 24px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                }
                h1 { margin-top: 0; }
            </style>
        </head>
        <body>
            <div class="box">
                <h1>Login completado</h1>
                <p>Ya puedes cerrar esta pestana y volver a EventPlus.</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))


def wait_for_oauth_callback(timeout_seconds: int = 180) -> dict[str, Any]:
    OAuthCallbackHandler.result_queue = queue.Queue()

    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        return OAuthCallbackHandler.result_queue.get(timeout=timeout_seconds)
    finally:
        server.shutdown()
        server.server_close()


def parse_oauth_callback_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return {
        "code": params["code"][0] if "code" in params and params["code"] else None,
        "error": params["error"][0] if "error" in params and params["error"] else None,
        "error_description": (
            params["error_description"][0]
            if "error_description" in params and params["error_description"]
            else None
        ),
    }


def get_oauth_url(redirect_url: str | None = None) -> str:
    supabase = get_supabase_client()
    redirect_to = redirect_url or get_oauth_redirect_url()
    response = supabase.auth.sign_in_with_oauth(
        {
            "provider": "google",
            "options": {"redirect_to": redirect_to},
        }
    )

    url = safe_get(response, "url")

    if not url and isinstance(response, str):
        # Algunas versiones podrian devolver directamente la URL.
        url = response

    if not url:
        raise RuntimeError(
            "Supabase no devolvio una URL OAuth.\n"
            f"Respuesta recibida:\n{pretty(to_dict(response) or str(response))}"
        )

    return str(url)


def exchange_code_for_session(code: str) -> Any:
    supabase = get_supabase_client()
    if not hasattr(supabase.auth, "exchange_code_for_session"):
        raise RuntimeError(
            "Tu version de supabase-py no tiene exchange_code_for_session(). "
            "Actualiza con: pip install --upgrade supabase"
        )

    return supabase.auth.exchange_code_for_session({"auth_code": code})


def get_current_user() -> Any:
    supabase = get_supabase_client()
    response = supabase.auth.get_user()
    return safe_get(response, "user")


def sign_out_local_session() -> None:
    get_supabase_client().auth.sign_out()
