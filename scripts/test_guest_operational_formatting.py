from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import normalizar_invitado
from services.time_service import fecha_hora_panama, hora_panama, parse_instant
from views.invitados_view import _hora_llegada, _invitacion_texto, _invitacion_tooltip


def _row(*, principal: bool = True, mesa: int | None = 5) -> dict[str, object]:
    return {
        "ivt_cuenta_id": 1,
        "ivt_evento_id": 2,
        "ivt_invitacion_id": 23,
        "ivt_invitado_id": 1,
        "ivt_invitado_uuid": "guest-1",
        "ivt_nombre_invitado": "Invitado",
        "ivt_es_invitado_principal": principal,
        "ivt_es_invitado_imprevisto": False,
        "ivt_mesa_id": mesa,
        "ivt_llegada_confirmada": True,
        "ivt_fecha_hora_conf_llegada": "2026-08-13T01:15:00+00:00",
        "ivt_tiene_novedad": False,
        "ivt_estado": "Activo",
    }


def test_conversion_temporal() -> None:
    value = "2026-08-13T01:15:00+00:00"
    assert parse_instant(value) is not None
    assert hora_panama(value) == "08:15 PM"
    assert fecha_hora_panama(value) == "12/08/2026 08:15 PM"
    assert parse_instant("2026-08-12T20:15:00") is None


def test_presentacion_consulta_mesa_e_invitacion() -> None:
    principal = normalizar_invitado(_row(), {5: "Mesa Familia Rodríguez"})
    acompanante = normalizar_invitado(_row(principal=False, mesa=None), {})
    assert principal is not None and acompanante is not None
    assert principal["mesa_texto"] == "Mesa Familia Rodríguez"
    assert acompanante["mesa_texto"] == "Sin mesa"
    assert _hora_llegada(principal) == "08:15 PM"
    assert _invitacion_texto(principal) == "23 - Prin"
    assert _invitacion_texto(acompanante) == "23 - Acom"
    assert _invitacion_tooltip(principal) == "Invitación 23 - Principal"


def main() -> int:
    test_conversion_temporal()
    test_presentacion_consulta_mesa_e_invitacion()
    print("OK - guest operational formatting tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
