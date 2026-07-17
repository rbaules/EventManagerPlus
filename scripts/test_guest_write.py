from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import (
    actualizar_invitado_planificado,
    crear_invitado_planificado,
    listar_invitaciones_evento,
    normalizar_invitado,
    puede_administrar_invitados_planificados,
)
from views.invitados_view import invitados_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


def normalizar(nombre: str) -> str:
    return " ".join(nombre.strip().lower().split())


def invitado_row(invitado_id: int, nombre: str, cuenta: int = 1, evento: int = 10) -> dict[str, Any]:
    return {
        "ivt_cuenta_id": cuenta,
        "ivt_evento_id": evento,
        "ivt_invitacion_id": 100,
        "ivt_invitado_id": invitado_id,
        "ivt_invitado_uuid": f"uuid-{cuenta}-{evento}-{invitado_id}",
        "ivt_nombre_invitado": nombre,
        "ivt_nombre_invitado_normalizado": normalizar(nombre),
        "ivt_es_invitado_principal": False,
        "ivt_es_invitado_imprevisto": False,
        "ivt_email": None,
        "ivt_telefono": None,
        "ivt_mesa_id": None,
        "ivt_puesto_id": None,
        "ivt_llegada_confirmada": False,
        "ivt_fecha_hora_conf_llegada": None,
        "ivt_tiene_novedad": False,
        "ivt_descripcion_novedad": None,
        "ivt_estado": "Activo",
    }


INVITACION = {
    "inv_cuenta_id": 1,
    "inv_evento_id": 10,
    "inv_invitacion_id": 100,
    "inv_cod_abrev_invitacion": "ABC",
    "inv_destinatario_invitacion": "Familia Demo",
    "inv_estado": "Activo",
}


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table_name = table
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict[str, Any] = {}

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def order(self, _column: str) -> "FakeQuery":
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def execute(self) -> Response:
        if self.db.fail:
            raise self.db.fail
        if self.table_name == "evp_inv_invitacion":
            rows = self.db.invitaciones
        else:
            rows = self.db.invitados

        if self.mode == "insert":
            new_id = max([row["ivt_invitado_id"] for row in self.db.invitados] or [0]) + 1
            row = dict(self.payload)
            row["ivt_invitado_id"] = new_id
            row["ivt_invitado_uuid"] = f"uuid-{row['ivt_cuenta_id']}-{row['ivt_evento_id']}-{new_id}"
            row["ivt_nombre_invitado_normalizado"] = normalizar(row["ivt_nombre_invitado"])
            row.setdefault("ivt_tiene_novedad", False)
            row.setdefault("ivt_descripcion_novedad", None)
            row.setdefault("ivt_fecha_hora_conf_llegada", None)
            self.db.invitados.append(row)
            return Response([row])

        matched = [
            row
            for row in rows
            if all(row.get(column) == value for column, value in self.filters)
        ]
        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
                if "ivt_nombre_invitado" in self.payload:
                    row["ivt_nombre_invitado_normalizado"] = normalizar(self.payload["ivt_nombre_invitado"])
            return Response(matched)
        return Response(matched)


class FakeSupabase:
    def __init__(self, invitados: list[dict[str, Any]] | None = None, fail: Exception | None = None) -> None:
        self.invitados = invitados or []
        self.invitaciones = [dict(INVITACION)]
        self.fail = fail

    def table(self, name: str) -> FakeQuery:
        assert name in {"evp_ivt_invitado", "evp_inv_invitacion"}
        return FakeQuery(self, name)


def contexto(rol: str = "Administrador", fase: str = "Pre_evento", autorizado: bool = True) -> dict[str, Any]:
    evento = {
        "cuenta_id": 1,
        "evento_id": 10,
        "nombre_evento": "Evento Test",
        "fase_evento": fase,
        "estado": "Activo",
        "rol": rol,
    }
    return {
        "usr_usuario_id": "user-1",
        "rol_global_calculado": rol,
        "evento_actual": evento,
        "eventos_permitidos": [evento] if autorizado else [],
    }


def payload(nombre: str = "Ana Perez") -> dict[str, Any]:
    return {
        "invitacion_id": 100,
        "nombre_completo": nombre,
        "email": "",
        "telefono": "",
        "mesa_id": "",
        "puesto_id": "",
        "es_invitado_principal": False,
    }


def test_autorizacion_roles_y_fases() -> None:
    assert puede_administrar_invitados_planificados(contexto("Administrador", "Pre_evento"))
    assert puede_administrar_invitados_planificados(contexto("Master", "Pre_evento"))
    assert not puede_administrar_invitados_planificados(contexto("Operador", "Pre_evento"))
    assert not puede_administrar_invitados_planificados(contexto("Consulta", "Pre_evento"))
    assert not puede_administrar_invitados_planificados(contexto("Administrador", "En_proceso"))
    assert not puede_administrar_invitados_planificados(contexto("Master", "Post_evento"))
    assert not puede_administrar_invitados_planificados(contexto("Administrador", "Pre_evento", autorizado=False))
    assert not puede_administrar_invitados_planificados({"usr_usuario_id": "u", "evento_actual": None})


def test_creacion_validaciones_duplicados_y_permisos() -> None:
    db = FakeSupabase()
    creado = crear_invitado_planificado(contexto(), payload("  Ana   Perez  "), supabase=db)
    assert creado.ok
    assert creado.invitado and creado.invitado["nombre_completo"] == "Ana Perez"
    assert db.invitados[0]["ivt_es_invitado_imprevisto"] is False
    assert "ivt_invitado_id" in db.invitados[0]

    vacio = crear_invitado_planificado(contexto(), payload("   "), supabase=FakeSupabase())
    assert not vacio.ok and vacio.estado == "invalid_data"

    largo = crear_invitado_planificado(contexto(), payload("X" * 81), supabase=FakeSupabase())
    assert not largo.ok and largo.estado == "invalid_data"

    duplicado = crear_invitado_planificado(contexto(), payload("ana perez"), supabase=db)
    assert not duplicado.ok and duplicado.estado == "duplicate"

    otro_evento = FakeSupabase([invitado_row(1, "Ana Perez", cuenta=2, evento=10)])
    permitido = crear_invitado_planificado(contexto(), payload("Ana Perez"), supabase=otro_evento)
    assert permitido.ok

    rol = crear_invitado_planificado(contexto("Operador", "Pre_evento"), payload("Luis"), supabase=FakeSupabase())
    assert not rol.ok and rol.estado == "role_denied"

    fase = crear_invitado_planificado(contexto("Administrador", "En_proceso"), payload("Luis"), supabase=FakeSupabase())
    assert not fase.ok and fase.estado == "phase_denied"

    rls = crear_invitado_planificado(contexto(), payload("Luis"), supabase=FakeSupabase(fail=PermissionError("permission denied")))
    assert not rls.ok and rls.estado == "permission_denied"


def test_edicion_valida_y_duplicados() -> None:
    original_db = invitado_row(1, "Ana Perez")
    original = normalizar_invitado(original_db)
    assert original is not None
    db = FakeSupabase([original_db, invitado_row(2, "Luis Gomez")])

    ok = actualizar_invitado_planificado(contexto(), original, payload("Ana Perez"), supabase=db)
    assert ok.ok

    cambio = actualizar_invitado_planificado(contexto(), original, payload("Ana Maria Perez"), supabase=db)
    assert cambio.ok and cambio.invitado and cambio.invitado["nombre_completo"] == "Ana Maria Perez"

    dup = actualizar_invitado_planificado(contexto(), original, payload("Luis Gomez"), supabase=db)
    assert not dup.ok and dup.estado == "duplicate"

    otro_evento = dict(original, evento_id=99)
    rechazado = actualizar_invitado_planificado(contexto(), otro_evento, payload("Carlos"), supabase=db)
    assert not rechazado.ok and rechazado.estado == "event_changed"

    inexistente_original = normalizar_invitado(invitado_row(99, "No Existe"))
    assert inexistente_original is not None
    inexistente = actualizar_invitado_planificado(contexto(), inexistente_original, payload("Nuevo"), supabase=db)
    assert not inexistente.ok and inexistente.estado == "not_found"


def test_invitaciones_y_ui_builds() -> None:
    invs = listar_invitaciones_evento(contexto()["evento_actual"], supabase=FakeSupabase())
    assert invs.ok and len(invs.invitaciones) == 1

    control = invitados_view(
        contexto(),
        "ready",
        [],
        "",
        "invitado",
        "",
        "todos",
        False,
        False,
        None,
        True,
        True,
        True,
        True,
        True,
        invs.invitaciones,
        {"modo": "crear", "datos": payload(), "original": None},
        "",
        False,
        lambda value=None: None,
        lambda value=None: None,
        lambda: None,
        lambda value=None: None,
        lambda: None,
        lambda: None,
        lambda value=None: None,
        lambda: None,
        lambda: None,
        lambda: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
    )
    assert control is not None


def main() -> int:
    test_autorizacion_roles_y_fases()
    test_creacion_validaciones_duplicados_y_permisos()
    test_edicion_valida_y_duplicados()
    test_invitaciones_y_ui_builds()
    print("OK - guest planned creation/editing authorization, validation, duplicate checks, and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
