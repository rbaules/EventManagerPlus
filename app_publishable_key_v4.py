"""
app.py - Prueba básica Google OAuth + Supabase Auth + EventPlus
Versión v4 usando SUPABASE_PUBLISHABLE_KEY.

Objetivo:
- Probar Google OAuth con Supabase.
- Validar que el trigger de auth.users actualiza evp_usr_usuario.
- Evitar el error "'str' object has no attribute 'get'".
- Si ocurre un error, mostrar traceback completo con número de línea.
- Corrige exchange_code_for_session para usar {"auth_code": code}, como espera supabase-py.

Requisitos:
    pip install flet supabase python-dotenv

.env:
    SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxxx.supabase.co
    SUPABASE_PUBLISHABLE_KEY=tu_publishable_key
    SUPABASE_OAUTH_REDIRECT_URL=http://localhost:8765/auth/callback
"""

from __future__ import annotations

import json
import os
import queue
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import flet as ft
from dotenv import load_dotenv
from supabase import Client, create_client


# -----------------------------------------------------------------------------
# Configuración
# -----------------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
REDIRECT_URL = os.getenv(
    "SUPABASE_OAUTH_REDIRECT_URL",
    "http://localhost:8765/auth/callback",
).strip()

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/auth/callback"

if not SUPABASE_URL:
    raise RuntimeError("Falta SUPABASE_URL en el archivo .env")

if not SUPABASE_PUBLISHABLE_KEY:
    raise RuntimeError("Falta SUPABASE_PUBLISHABLE_KEY en el archivo .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)


# -----------------------------------------------------------------------------
# Funciones seguras para leer datos
# -----------------------------------------------------------------------------

def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Lee una llave/atributo de forma segura.
    Evita errores como: AttributeError: 'str' object has no attribute 'get'.
    """
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                return parsed.get(key, default)
        except Exception:
            return default

    return getattr(obj, key, default)


def to_dict(value: Any) -> dict[str, Any] | None:
    """
    Convierte valores devueltos por Supabase a dict cuando sea posible.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            return {"_raw": value, "_parsed_type": type(parsed).__name__}
        except Exception:
            return {"_raw": value, "_type": "str"}

    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            pass

    return {"_raw": str(value), "_type": type(value).__name__}


def extract_data(response: Any) -> list[Any]:
    """
    Extrae response.data de forma robusta.
    """
    data = safe_get(response, "data", [])

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return [data]
        except Exception:
            return [data]

    return [data]


def pretty(obj: Any) -> str:
    """
    Representación legible para diagnóstico.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)


# -----------------------------------------------------------------------------
# Servidor local para capturar callback OAuth
# -----------------------------------------------------------------------------

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
                <p>Ya puedes cerrar esta pestaña y volver a EventPlus.</p>
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


# -----------------------------------------------------------------------------
# Supabase Auth
# -----------------------------------------------------------------------------

def get_oauth_url() -> str:
    response = supabase.auth.sign_in_with_oauth(
        {
            "provider": "google",
            "options": {"redirect_to": REDIRECT_URL},
        }
    )

    url = safe_get(response, "url")

    if not url and isinstance(response, str):
        # Algunas versiones podrían devolver directamente la URL.
        url = response

    if not url:
        raise RuntimeError(
            "Supabase no devolvió una URL OAuth.\n"
            f"Respuesta recibida:\n{pretty(to_dict(response) or str(response))}"
        )

    return str(url)


def exchange_code_for_session(code: str) -> Any:
    if not hasattr(supabase.auth, "exchange_code_for_session"):
        raise RuntimeError(
            "Tu versión de supabase-py no tiene exchange_code_for_session(). "
            "Actualiza con: pip install --upgrade supabase"
        )

    return supabase.auth.exchange_code_for_session({"auth_code": code})


def get_current_user() -> Any:
    response = supabase.auth.get_user()
    return safe_get(response, "user")


# -----------------------------------------------------------------------------
# Consultas EventPlus
# -----------------------------------------------------------------------------

SELECT_USUARIO = (
    "usr_usuario_id,"
    "usr_nombre_usuario,"
    "usr_nombre_usuario_abrev,"
    "usr_email,"
    "usr_usuario_auth_uuid,"
    "usr_es_usuario_master,"
    "usr_estado"
)


def buscar_usuario_eventplus_por_auth_uuid(auth_user_id: str) -> dict[str, Any] | None:
    response = (
        supabase
        .table("evp_usr_usuario")
        .select(SELECT_USUARIO)
        .eq("usr_usuario_auth_uuid", auth_user_id)
        .limit(1)
        .execute()
    )

    data = extract_data(response)
    if not data:
        return None

    return to_dict(data[0])


def buscar_usuario_eventplus_por_email(email: str) -> dict[str, Any] | None:
    response = (
        supabase
        .table("evp_usr_usuario")
        .select(SELECT_USUARIO)
        .ilike("usr_email", email)
        .limit(1)
        .execute()
    )

    data = extract_data(response)
    if not data:
        return None

    return to_dict(data[0])


def formato_usuario_eventplus(usuario: dict[str, Any] | None) -> str:
    if not usuario:
        return "No se encontró registro en evp_usr_usuario."

    if "_raw" in usuario:
        return (
            "La consulta devolvió una fila en formato inesperado:\n"
            f"Tipo detectado: {usuario.get('_type') or usuario.get('_parsed_type')}\n"
            f"Valor crudo:\n{usuario['_raw']}"
        )

    return "\n".join(
        [
            "Registro encontrado en evp_usr_usuario:",
            f"usr_usuario_id: {safe_get(usuario, 'usr_usuario_id')}",
            f"usr_nombre_usuario: {safe_get(usuario, 'usr_nombre_usuario')}",
            f"usr_nombre_usuario_abrev: {safe_get(usuario, 'usr_nombre_usuario_abrev')}",
            f"usr_email: {safe_get(usuario, 'usr_email')}",
            f"usr_usuario_auth_uuid: {safe_get(usuario, 'usr_usuario_auth_uuid')}",
            f"usr_es_usuario_master: {safe_get(usuario, 'usr_es_usuario_master')}",
            f"usr_estado: {safe_get(usuario, 'usr_estado')}",
        ]
    )


# -----------------------------------------------------------------------------
# App Flet
# -----------------------------------------------------------------------------

def main(page: ft.Page) -> None:
    page.title = "EventPlus - Prueba Google OAuth + Supabase"
    page.window.width = 950
    page.window.height = 760
    page.scroll = ft.ScrollMode.AUTO

    status = ft.Text("Listo para iniciar prueba.", size=16, selectable=True)

    result_box = ft.TextField(
        label="Resultado de la prueba",
        multiline=True,
        min_lines=22,
        max_lines=30,
        read_only=True,
        value="",
    )

    login_button = ft.ElevatedButton(
        "Iniciar sesión con Google",
        icon=ft.Icons.LOGIN,
    )

    logout_button = ft.OutlinedButton(
        "Cerrar sesión local",
        icon=ft.Icons.LOGOUT,
        visible=False,
    )

    def set_status(message: str) -> None:
        status.value = message
        page.update()

    def set_result(message: str) -> None:
        result_box.value = message
        page.update()

    def run_login_flow() -> None:
        try:
            login_button.disabled = True
            set_status("Solicitando URL OAuth a Supabase...")

            oauth_url = get_oauth_url()

            set_status(
                "Se abrirá el navegador para iniciar sesión con Google. "
                "Después del login, vuelve a esta ventana."
            )

            webbrowser.open(oauth_url)

            set_status(f"Esperando callback OAuth en {REDIRECT_URL} ...")

            callback_result = wait_for_oauth_callback(timeout_seconds=180)

            if safe_get(callback_result, "error"):
                raise RuntimeError(
                    f"OAuth error: {safe_get(callback_result, 'error')} - "
                    f"{safe_get(callback_result, 'error_description')}"
                )

            code = safe_get(callback_result, "code")
            if not code:
                raise RuntimeError(
                    "No se recibió el parámetro 'code' en el callback.\n"
                    f"Callback recibido:\n{pretty(callback_result)}"
                )

            set_status("Callback recibido. Intercambiando code por sesión Supabase...")

            exchange_code_for_session(str(code))

            user = get_current_user()
            if not user:
                raise RuntimeError("No se pudo obtener el usuario autenticado con supabase.auth.get_user().")

            auth_user_id = str(safe_get(user, "id", ""))
            email = str(safe_get(user, "email", ""))

            if not auth_user_id:
                raise RuntimeError(
                    "Supabase Auth no devolvió user.id.\n"
                    f"User recibido:\n{pretty(to_dict(user) or str(user))}"
                )

            set_status("Login exitoso. Consultando evp_usr_usuario para validar trigger...")

            usuario_eventplus = buscar_usuario_eventplus_por_auth_uuid(auth_user_id)

            diagnostico = [
                "LOGIN SUPABASE AUTH EXITOSO",
                "",
                f"auth.users.id: {auth_user_id}",
                f"auth.users.email: {email}",
                "",
                "VALIDACIÓN EVENTPLUS POR usr_usuario_auth_uuid",
                formato_usuario_eventplus(usuario_eventplus),
            ]

            if not usuario_eventplus and email:
                usuario_por_email = buscar_usuario_eventplus_por_email(email)
                diagnostico.extend(
                    [
                        "",
                        "BÚSQUEDA DE APOYO POR EMAIL",
                        formato_usuario_eventplus(usuario_por_email),
                    ]
                )

                if usuario_por_email and not safe_get(usuario_por_email, "usr_usuario_auth_uuid"):
                    diagnostico.extend(
                        [
                            "",
                            "DIAGNÓSTICO:",
                            "El usuario existe por email, pero usr_usuario_auth_uuid sigue vacío.",
                            "Eso sugiere que el trigger de auth.users no actualizó evp_usr_usuario.",
                            "Revisa la función/trigger de vinculación y que el email coincida.",
                        ]
                    )
                elif not usuario_por_email:
                    diagnostico.extend(
                        [
                            "",
                            "DIAGNÓSTICO:",
                            "No existe usuario preregistrado con este email en evp_usr_usuario.",
                            "Debes preregistrar el usuario antes de probar la vinculación.",
                        ]
                    )

            if usuario_eventplus and safe_get(usuario_eventplus, "usr_usuario_auth_uuid") == auth_user_id:
                diagnostico.extend(
                    [
                        "",
                        "RESULTADO:",
                        "Prueba exitosa. El usuario autenticado fue vinculado correctamente con evp_usr_usuario.",
                    ]
                )
            elif usuario_eventplus:
                diagnostico.extend(
                    [
                        "",
                        "RESULTADO:",
                        "Login exitoso, pero la vinculación no coincide exactamente. Revisa usr_usuario_auth_uuid.",
                    ]
                )

            set_result("\n".join(diagnostico))
            set_status("Prueba completada.")
            logout_button.visible = True

        except Exception as ex:
            set_status("La prueba falló.")
            set_result(
                "ERROR DURANTE LA PRUEBA\n\n"
                f"{type(ex).__name__}: {ex}\n\n"
                "TRACEBACK COMPLETO:\n"
                f"{traceback.format_exc()}\n\n"
                "Puntos a revisar:\n"
                "1. Que SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY estén correctos en .env.\n"
                "2. Que Google esté habilitado en Authentication > Providers.\n"
                "3. Que Supabase tenga esta Redirect URL permitida:\n"
                f"   {REDIRECT_URL}\n"
                "4. Que el usuario esté preregistrado en evp_usr_usuario con el mismo email.\n"
                "5. Que el trigger sobre auth.users exista y no tenga errores.\n"
                "6. Que ninguna otra aplicación esté usando el puerto 8765.\n"
            )
        finally:
            login_button.disabled = False
            page.update()

    def login_click(e: ft.ControlEvent) -> None:
        threading.Thread(target=run_login_flow, daemon=True).start()

    def logout_click(e: ft.ControlEvent) -> None:
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        logout_button.visible = False
        set_status("Sesión local cerrada.")
        set_result("")

    login_button.on_click = login_click
    logout_button.on_click = logout_click

    instructions = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Prueba básica Google OAuth + Supabase Auth",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Antes de probar, preregistra en evp_usr_usuario el mismo email "
                    "de Google que usarás para iniciar sesión, con usr_estado='Preregistrado' "
                    "y usr_usuario_auth_uuid=NULL.",
                    size=14,
                ),
                ft.Text(
                    f"Redirect URL usada por esta prueba: {REDIRECT_URL}",
                    size=14,
                    selectable=True,
                ),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY),
    )

    page.add(
        instructions,
        ft.Row([login_button, logout_button], spacing=12),
        status,
        result_box,
    )


if __name__ == "__main__":
    ft.run(main)
