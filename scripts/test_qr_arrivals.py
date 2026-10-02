from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from components.responsive import LayoutMode
from services.invitado_service import cargar_grupo_invitacion, resolver_invitacion_qr
from views.arrivals_view import arrivals_view


class Response:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class FakeSupabase:
    def __init__(self, qr_payload: dict[str, Any]) -> None:
        self.qr_payload = qr_payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        payload = self.qr_payload if name == "evp_oper_resolver_invitacion_qr" else {
            "ok": True,
            "codigo_resultado": "ARRIVAL_GROUP_LOADED",
            "destinatario": "Familia QR",
            "invitados": [{"invitado_id": 7, "nombre": "Invitado QR", "llegada_confirmada": False}],
        }
        return SimpleNamespace(execute=lambda: Response(payload))


class FailingSupabase:
    def rpc(self, _name: str, _params: dict[str, Any]) -> Any:
        raise RuntimeError("offline")


def contexto() -> dict[str, Any]:
    event = {"cuenta_id": 2, "evento_id": 1, "estado": "Activo", "fase_evento": "En_proceso", "rol": "Operador"}
    return {"usr_usuario_id": "operator-1", "evento_actual": event, "eventos_permitidos": [event], "puede_registrar_llegadas": True}


def walk(node: Any) -> list[Any]:
    result = [node]
    child = getattr(node, "content", None)
    if child is not None and child is not node:
        result.extend(walk(child))
    for item in getattr(node, "controls", None) or []:
        result.extend(walk(item))
    return result


def test_empty_does_not_call_rpc() -> None:
    db = FakeSupabase({"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 1, "invitacion_id": 3})
    result = resolver_invitacion_qr(2, 1, "  ", supabase=db)
    assert not result.ok and result.estado == "empty_code" and not db.calls


def test_qr_resolution_loads_common_group() -> None:
    db = FakeSupabase({"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 1, "invitacion_id": 3})
    resolved = resolver_invitacion_qr(2, 1, " ab12 ", supabase=db)
    assert resolved.ok and resolved.invitacion == {"cuenta_id": 2, "evento_id": 1, "invitacion_id": 3}
    group = cargar_grupo_invitacion(contexto()["evento_actual"], resolved.invitacion, supabase=db)
    assert group.ok and group.invitacion and group.invitacion["invitacion_id"] == 3
    assert [name for name, _ in db.calls] == ["evp_oper_resolver_invitacion_qr", "evp_oper_obtener_grupo_invitacion"]
    assert db.calls[0][1]["p_codigo"] == "AB12"


def test_qr_errors_and_context_validation() -> None:
    expected = {
        "QR_INVALID_FORMAT": "Código QR inválido.",
        "QR_NOT_FOUND": "No se encontró una invitación asociada a este código.",
        "QR_NOT_AVAILABLE": "Este código QR no está disponible para este evento.",
        "QR_REVOKED": "Este código QR ya no es válido.",
        "QR_NOT_ALLOWED": "No tiene permisos para consultar este código en el evento seleccionado.",
        "QR_OPERATION_ERROR": "No fue posible consultar el código QR.",
    }
    for code, message in expected.items():
        db = FakeSupabase({"ok": False, "codigo_resultado": code})
        result = resolver_invitacion_qr(2, 1, "AB12", supabase=db)
        assert not result.ok and result.estado == code and result.mensaje == message

    unexpected = resolver_invitacion_qr(2, 1, "AB12", supabase=FakeSupabase({"ok": False, "codigo_resultado": "QR_UNEXPECTED"}))
    assert not unexpected.ok and unexpected.mensaje == "No fue posible consultar el código QR."
    failed = resolver_invitacion_qr(2, 1, "AB12", supabase=FailingSupabase())
    assert not failed.ok and failed.estado == "QR_OPERATION_ERROR" and failed.mensaje == "No fue posible consultar el código QR."

    db = FakeSupabase({"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 8, "invitacion_id": 3})
    result = resolver_invitacion_qr(2, 1, "AB12", supabase=db)
    assert not result.ok and result.estado == "unexpected_response"


def test_qr_ui_enter_and_button_share_handler_and_readonly_has_no_write_actions() -> None:
    calls: list[str] = []
    scanner_calls: list[str] = []
    control = arrivals_view(
        contexto(), "ready", "", "", [],
        {"cuenta_id": 2, "evento_id": 1, "invitacion_id": 3, "destinatario": "Familia QR"},
        [{"invitado_uuid": "arrival-2-1-3-7", "invitado_id": 7, "nombre_completo": "Invitado QR", "llegada_confirmada": False}],
        set(), False, False, False,
        lambda _value: None, lambda: None, lambda _item: None,
        lambda _item, _selected: None, lambda: None, lambda: None,
        lambda _item: None, lambda: None,
        layout=LayoutMode.PHONE, qr_codigo="ab12", on_qr_search=calls.append,
        on_open_scanner=lambda: scanner_calls.append("open"), can_confirm_arrival=False,
    )
    fields = [node for node in walk(control) if isinstance(node, ft.TextField)]
    qr = next(field for field in fields if field.label == "Código QR")
    assert qr.max_length == 4 and qr.capitalization == ft.TextCapitalization.CHARACTERS
    qr.on_submit(SimpleNamespace(control=SimpleNamespace(value="ab12")))
    button = next(node for node in walk(control) if getattr(node, "data", None) == {"arrivals_qr": "submit"})
    button.on_click(SimpleNamespace())
    assert calls == ["ab12", "ab12"]
    scan = next(node for node in walk(control) if getattr(node, "data", None) == {"arrivals_qr": "scan"})
    scan.on_click(SimpleNamespace())
    assert scanner_calls == ["open"]
    disabled_actions = [node for node in walk(control) if getattr(node, "data", None) in ({"arrivals_action": "select_pending"}, {"arrivals_action": "confirm_selected"})]
    assert disabled_actions and all(node.disabled for node in disabled_actions)

    close_calls: list[str] = []
    scanner_control = arrivals_view(
        contexto(), "ready", "", "", [], None, [], set(), False, False, False,
        lambda _value: None, lambda: None, lambda _item: None,
        lambda _item, _selected: None, lambda: None, lambda: None,
        lambda _item: None, lambda: None,
        scanner_active=True, scanner_message="Apunte la cámara al código QR.",
        scanner_preview=ft.Container(), on_close_scanner=lambda: close_calls.append("close"),
    )
    cancel = next(node for node in walk(scanner_control) if getattr(node, "data", None) == {"arrivals_qr": "cancel"})
    cancel.on_click(SimpleNamespace())
    assert close_calls == ["close"]
    assert any(isinstance(node, ft.TextField) and node.label == "Código QR" for node in walk(scanner_control))
    scanner_actions = [
        node for node in walk(scanner_control)
        if getattr(node, "data", None) in ({"arrivals_qr": "input"}, {"arrivals_qr": "submit"}, {"arrivals_qr": "scan"})
    ]
    assert len(scanner_actions) == 3 and all(node.disabled for node in scanner_actions)

    released_control = arrivals_view(
        contexto(), "ready", "", "", [], None, [], set(), False, False, False,
        lambda _value: None, lambda: None, lambda _item: None,
        lambda _item, _selected: None, lambda: None, lambda: None,
        lambda _item: None, lambda: None,
        scanner_active=False, qr_codigo="AB12",
    )
    released_actions = [
        node for node in walk(released_control)
        if getattr(node, "data", None) in ({"arrivals_qr": "input"}, {"arrivals_qr": "submit"}, {"arrivals_qr": "scan"})
    ]
    assert len(released_actions) == 3 and all(not node.disabled for node in released_actions)
    released_input = next(node for node in released_actions if getattr(node, "data", None) == {"arrivals_qr": "input"})
    assert released_input.value == "AB12"


def main() -> int:
    test_empty_does_not_call_rpc()
    test_qr_resolution_loads_common_group()
    test_qr_errors_and_context_validation()
    test_qr_ui_enter_and_button_share_handler_and_readonly_has_no_write_actions()
    print("OK - QR arrivals adapter, shared group flow, errors, UI and read-only checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
