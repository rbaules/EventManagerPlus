from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import flet as ft

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import guardar_novedad, puede_editar_novedad
from services.time_service import fecha_hora_panama
from views.arrivals_view import construir_fila_llegada
from views.invitados_view import _invitado_card, _invitados_table


class Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class RpcCall:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def execute(self) -> Response:
        return Response(self.response)


class FakeSupabase:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> RpcCall:
        self.calls.append((name, params))
        return RpcCall(self.response)


def contexto(rol: str, fase: str = "En_proceso") -> dict[str, Any]:
    evento = {"cuenta_id": 1, "evento_id": 2, "rol": rol, "fase_evento": fase, "estado": "Activo"}
    return {"usr_usuario_id": "u1", "usr_es_usuario_master": rol == "Master", "rol_global_calculado": rol,
            "evento_actual": evento, "eventos_permitidos": [evento]}


def invitado(novedad: bool = False) -> dict[str, Any]:
    return {"invitado_uuid": "guest-1", "nombre_completo": "Ana", "cuenta_id": 1, "evento_id": 2,
            "invitacion_id": 23, "es_invitado_principal": True, "mesa_texto": "Mesa Principal",
            "llegada_confirmada": False, "tiene_novedad": novedad,
            "descripcion_novedad": "Requiere apoyo" if novedad else ""}


def test_servicio_ok_limpieza_y_errores() -> None:
    db = FakeSupabase({"ok": True, "codigo": "OK", "tiene_novedad": True, "descripcion": "Apoyo"})
    result = guardar_novedad("guest-1", "  Apoyo  ", supabase=db)
    assert result.ok and result.invitado and result.invitado["tiene_novedad"]
    assert db.calls == [("evp_admin_guardar_novedad_invitado", {"p_invitado_uuid": "guest-1", "p_descripcion": "Apoyo"})]

    clear_db = FakeSupabase({"ok": True, "codigo": "OK", "tiene_novedad": False, "descripcion": None})
    cleared = guardar_novedad("guest-1", "   ", supabase=clear_db)
    assert cleared.ok and not cleared.invitado["tiene_novedad"]
    assert clear_db.calls[0][1]["p_descripcion"] is None

    for code in ("FORBIDDEN", "CONSULTA_READ_ONLY", "EVENT_PHASE_READ_ONLY", "DESCRIPTION_TOO_LONG"):
        denied = guardar_novedad("guest-1", "Texto", supabase=FakeSupabase({"ok": False, "codigo": code}))
        assert not denied.ok and code not in denied.mensaje
    too_long = guardar_novedad("guest-1", "x" * 201, supabase=FakeSupabase({}))
    assert not too_long.ok and "200" in too_long.mensaje


def test_capacidades_fases() -> None:
    for rol in ("Master", "Administrador", "Operador"):
        assert puede_editar_novedad(contexto(rol, "Pre_evento"))
        assert puede_editar_novedad(contexto(rol, "En_proceso"))
        assert not puede_editar_novedad(contexto(rol, "Post_evento"))
    assert not puede_editar_novedad(contexto("Consulta"))


def test_grid_mobile_llegadas_y_hora() -> None:
    calls: list[str] = []
    noop = lambda value=None: None
    item = invitado(True)
    table = _invitados_table([item], noop, noop, noop, noop, False, False, False, lambda row: calls.append(row["invitado_uuid"]))
    novelty_button = table.controls[0].rows[0].cells[-1].content.controls[1]
    assert isinstance(novelty_button, ft.IconButton) and "Editar" in str(novelty_button.tooltip)
    novelty_button.on_click(None)
    assert calls == ["guest-1"]
    card = _invitado_card(item, noop, noop, noop, noop, False, False, False, noop)
    assert "Novedad: Si" in card.content.controls[2].value
    arrival = construir_fila_llegada(item, False, False, False, noop, noop, noop)
    texts = [control.value for container in arrival.content.controls for control in getattr(getattr(container, "content", None), "controls", []) if isinstance(control, ft.Text)]
    assert any("Novedad: Sí" in text for text in texts)
    assert fecha_hora_panama("2026-08-13T01:15:00+00:00") == "12/08/2026 08:15 PM"


def main() -> int:
    test_servicio_ok_limpieza_y_errores()
    test_capacidades_fases()
    test_grid_mobile_llegadas_y_hora()
    print("OK - guest incident service, authorization and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
