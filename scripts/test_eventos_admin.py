from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

import config
import components.event_header as header_module
from components.event_header import event_header
from services.authorization_service import capacidades_rol
from services.evento_service import (
    CAMPOS_ESTRUCTURALES,
    CAMPOS_NO_ESTRUCTURALES,
    actualizar_evento,
    cambiar_estado_evento,
    cerrar_evento,
    crear_evento,
    establecer_evento_predeterminado,
    iniciar_evento,
    listar_eventos_administrables,
    obtener_transiciones_permitidas,
    TIPOS_EVENTO_VALIDOS,
)
from views.eventos_admin_view import EventFormState, eventos_admin_view
from views.eventos_admin_view import _card
from views.eventos_admin_view import _form
from views.home_view import _registrar_resultado_form_evento
from services.evento_service import ResultadoEvento


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class Query:
    def __init__(self, db: "DB", table: str) -> None:
        self.db, self.table = db, table
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict[str, Any] = {}
        self.limit_count: int | None = None

    def select(self, _columns: str) -> "Query": return self
    def eq(self, column: str, value: Any) -> "Query":
        self.filters.append((column, value)); return self
    def order(self, _column: str, **_kwargs: Any) -> "Query": return self
    def limit(self, count: int) -> "Query":
        self.limit_count = count; return self
    def insert(self, payload: dict[str, Any]) -> "Query":
        self.mode, self.payload = "insert", dict(payload); return self
    def update(self, payload: dict[str, Any]) -> "Query":
        self.mode, self.payload = "update", dict(payload); return self
    def delete(self) -> "Query":
        raise AssertionError("Eventos admin nunca debe ejecutar DELETE")

    def matched(self) -> list[dict[str, Any]]:
        rows = self.db.tables[self.table]
        for col, value in self.filters:
            rows = [row for row in rows if row.get(col) == value]
        return rows[: self.limit_count] if self.limit_count is not None else rows

    def execute(self) -> Response:
        self.db.calls.append((self.table, self.mode, tuple(self.filters), dict(self.payload)))
        if self.db.raise_on == (self.table, self.mode):
            raise RuntimeError("simulated database failure")
        if self.mode == "insert":
            if self.db.empty_insert:
                return Response([])
            row = dict(self.payload)
            ids = [x["eve_evento_id"] for x in self.db.tables[self.table] if x["eve_cuenta_id"] == row["eve_cuenta_id"]]
            row["eve_evento_id"] = max(ids, default=0) + 1
            self.db.tables[self.table].append(row)
            return Response([dict(row)])
        rows = self.matched()
        if self.mode == "update":
            for row in rows:
                row.update(self.payload)
        return Response([dict(x) for x in rows])


class DB:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.raise_on: tuple[str, str] | None = None
        self.empty_insert = False
        self.tables = {
            "evp_eve_evento": [
                event_row(1, 10),
                event_row(2, 10, name="Evento ajeno"),
            ],
            "evp_lug_lugar": [
                {"lug_cuenta_id": 1, "lug_lugar_id": 1, "lug_nombre_lugar": "Hotel", "lug_estado": "Activo"},
                {"lug_cuenta_id": 1, "lug_lugar_id": 2, "lug_nombre_lugar": "Inactivo", "lug_estado": "Inactivo"},
                {"lug_cuenta_id": 2, "lug_lugar_id": 1, "lug_nombre_lugar": "Ajeno", "lug_estado": "Activo"},
            ],
            "evp_sal_salon": [
                {"sal_cuenta_id": 1, "sal_lugar_id": 1, "sal_salon_id": 1, "sal_nombre_salon": "A", "sal_estado": "Activo"},
                {"sal_cuenta_id": 1, "sal_lugar_id": 2, "sal_salon_id": 1, "sal_nombre_salon": "B", "sal_estado": "Activo"},
            ],
            "evp_mes_mesa": [],
            "evp_inv_invitacion": [],
            "evp_ivt_invitado": [],
            "evp_usr_usuario": [{"usr_usuario_id": "user-Administrador", "usr_cuenta_id_default": None, "usr_evento_id_default": None}],
        }

    def table(self, name: str) -> Query:
        return Query(self, name)


class FakeAPIError(Exception):
    def __init__(self, message: str, code: str = "23514") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = "check constraint failed"
        self.hint = None


def event_row(account: int, event_id: int, *, name: str = "Gala", phase: str = "Pre_evento", state: str = "Activo") -> dict[str, Any]:
    return {
        "eve_cuenta_id": account, "eve_evento_id": event_id,
        "eve_nombre_evento": name, "eve_nombre_evento_abrev": "GAL",
        "eve_fase_evento": phase, "eve_tipo_evento": "Otro",
        "eve_lugar_id": 1, "eve_salon_id": 1, "eve_cant_mesas": 10,
        "eve_fecha_hora_inicio": "2026-08-15T18:00:00-05:00",
        "eve_fecha_hora_fin": "2026-08-15T23:00:00-05:00", "eve_estado": state,
    }


def context(role: str = "Administrador") -> dict[str, Any]:
    account = {"cuenta_id": 1, "nombre_cuenta": "Cuenta uno", "rol": role}
    event = {"cuenta_id": 1, "evento_id": 10, "fase_evento": "Pre_evento", "estado": "Activo", "rol": role}
    return {
        "usr_usuario_id": f"user-{role}", "rol_global_calculado": role,
        "cuentas_permitidas": [account], "cuenta_actual": account,
        "eventos_permitidos": [event], "evento_actual": event,
    }


def payload(**updates: Any) -> dict[str, Any]:
    data = {
        "nombre_evento": "Evento prueba admin", "nombre_evento_abrev": "TEST",
        "tipo_evento": "Otro", "fase_evento": "Pre_evento", "estado": "Activo",
        "lugar_id": 1, "salon_id": 1, "cant_mesas": "8",
        "fecha_hora_inicio": "2026-09-01T18:00:00-05:00",
        "fecha_hora_fin": "2026-09-01T22:00:00-05:00",
    }
    data.update(updates)
    return data


def test_capacidades_y_listado() -> None:
    assert capacidades_rol("Master").puede_ver_administracion_eventos
    assert capacidades_rol("Administrador").puede_crear_evento
    assert not capacidades_rol("Operador").puede_ver_administracion_eventos
    assert not capacidades_rol("Consulta").puede_editar_evento
    db = DB()
    result = listar_eventos_administrables(context("Administrador"), supabase=db)
    assert result.ok and len(result.eventos) == 1 and result.eventos[0]["cuenta_id"] == 1
    assert not listar_eventos_administrables(context("Operador"), supabase=db).ok
    assert all(("eve_cuenta_id", 1) in filters for table, mode, filters, _ in db.calls if table == "evp_eve_evento" and mode == "select")


def test_creacion_validaciones_y_tenant() -> None:
    db, ctx = DB(), context()
    assert crear_evento(ctx, payload(), supabase=db).ok
    assert not crear_evento(ctx, payload(nombre_evento=""), supabase=db).ok
    assert not crear_evento(ctx, payload(fecha_hora_fin="2026-09-01T17:00:00-05:00"), supabase=db).ok
    assert not crear_evento(ctx, payload(lugar_id=99), supabase=db).ok
    assert not crear_evento(ctx, payload(lugar_id=2, salon_id=1), supabase=db).ok
    assert not crear_evento(ctx, payload(lugar_id=1, salon_id=99), supabase=db).ok
    inserted = [call for call in db.calls if call[1] == "insert"]
    assert inserted and "eve_evento_id" not in inserted[0][3]
    assert inserted[0][3]["eve_cuenta_id"] == 1
    assert set(inserted[0][3]) == {
        "eve_cuenta_id", "eve_nombre_evento", "eve_nombre_evento_abrev",
        "eve_fase_evento", "eve_tipo_evento", "eve_lugar_id", "eve_salon_id",
        "eve_cant_mesas", "eve_fecha_hora_inicio", "eve_fecha_hora_fin", "eve_estado",
    }
    assert not crear_evento(context("Operador"), payload(), supabase=db).ok
    assert not crear_evento(context("Consulta"), payload(), supabase=db).ok

    empty_db = DB()
    empty_db.empty_insert = True
    empty = crear_evento(ctx, payload(), supabase=empty_db)
    assert not empty.ok and empty.estado == "empty_response" and empty.mensaje
    error_db = DB()
    error_db.raise_on = ("evp_eve_evento", "insert")
    error = crear_evento(ctx, payload(), supabase=error_db)
    assert not error.ok and error.estado == "data_error" and error.mensaje


def test_edicion_campos_fase_dependencias_y_concurrencia() -> None:
    db, ctx = DB(), context()
    assert actualizar_evento(ctx, 10, {"nombre_evento": "Nuevo"}, supabase=db).ok
    for protected in ("cuenta_id", "evento_id", "eve_estado", "usr_usuario_id"):
        result = actualizar_evento(ctx, 10, {protected: "x"}, supabase=db)
        assert not result.ok and result.estado == "protected_field"
    db.tables["evp_mes_mesa"].append({"mes_cuenta_id": 1, "mes_evento_id": 10})
    same_location = actualizar_evento(ctx, 10, {"lugar_id": 1, "salon_id": 1}, supabase=db)
    assert not same_location.ok and same_location.estado == "no_changes"
    db.tables["evp_mes_mesa"].clear()
    db.tables["evp_eve_evento"][0]["eve_fase_evento"] = "En_proceso"
    running = actualizar_evento(ctx, 10, {"nombre_evento": "Permitido"}, supabase=db)
    assert running.ok and running.evento["nombre_evento"] == "Permitido"
    denied_location = actualizar_evento(ctx, 10, {"lugar_id": 2}, supabase=db)
    assert not denied_location.ok and denied_location.estado == "phase_denied"
    denied_type = actualizar_evento(ctx, 10, {"tipo_evento": "Corporativo"}, supabase=db)
    assert not denied_type.ok and denied_type.estado == "phase_denied"
    db.tables["evp_eve_evento"][0]["eve_fase_evento"] = "Post_evento"
    assert not actualizar_evento(ctx, 10, {"nombre_evento": "Bloqueado"}, supabase=db).ok


def test_edicion_horarios_y_cambios_reales() -> None:
    db, ctx = DB(), context()
    db.tables["evp_mes_mesa"].append({"mes_cuenta_id": 1, "mes_evento_id": 10})
    dependency_tables = {"evp_mes_mesa", "evp_inv_invitacion", "evp_ivt_invitado"}

    start = actualizar_evento(
        ctx, 10, {"fecha_hora_inicio": "2026-08-15T19:00:00-05:00"}, supabase=db,
    )
    assert start.ok
    update = [call for call in db.calls if call[0] == "evp_eve_evento" and call[1] == "update"][-1]
    assert update[3] == {"eve_fecha_hora_inicio": "2026-08-15T19:00:00-05:00"}
    assert not any(call[0] in dependency_tables for call in db.calls)

    db.calls.clear()
    end = actualizar_evento(
        ctx, 10, {"fecha_hora_fin": "2026-08-16T00:00:00-05:00"}, supabase=db,
    )
    assert end.ok
    assert [call for call in db.calls if call[1] == "update"][-1][3] == {
        "eve_fecha_hora_fin": "2026-08-16T00:00:00-05:00"
    }
    assert not any(call[0] in dependency_tables for call in db.calls)

    db.calls.clear()
    both = actualizar_evento(
        ctx,
        10,
        {
            "fecha_hora_inicio": "2026-08-15T20:00:00-05:00",
            "fecha_hora_fin": "2026-08-16T01:00:00-05:00",
        },
        supabase=db,
    )
    assert both.ok and not any(call[0] in dependency_tables for call in db.calls)

    db.calls.clear()
    renamed = actualizar_evento(ctx, 10, {"nombre_evento": "Nombre nuevo", "tipo_evento": "Corporativo"}, supabase=db)
    assert renamed.ok
    assert [call for call in db.calls if call[1] == "update"][-1][3] == {
        "eve_nombre_evento": "Nombre nuevo", "eve_tipo_evento": "Corporativo"
    }
    assert not any(call[0] in dependency_tables for call in db.calls)


def test_edicion_estructural_y_sin_cambios() -> None:
    assert CAMPOS_ESTRUCTURALES == {"lugar_id", "salon_id", "cant_mesas"}
    assert {"nombre_evento", "tipo_evento", "fecha_hora_inicio", "fecha_hora_fin"} <= CAMPOS_NO_ESTRUCTURALES
    db, ctx = DB(), context()
    unchanged = actualizar_evento(
        ctx,
        10,
        {
            "nombre_evento": "Gala",
            "nombre_evento_abrev": "GAL",
            "tipo_evento": "Otro",
            "fecha_hora_inicio": "2026-08-15T23:00:00Z",
            "fecha_hora_fin": "2026-08-16T04:00:00Z",
            "cant_mesas": "10",
            "lugar_id": "1",
            "salon_id": "1",
        },
        supabase=db,
    )
    assert not unchanged.ok and unchanged.estado == "no_changes"
    assert not any(call[1] == "update" for call in db.calls)

    db.tables["evp_mes_mesa"].append({"mes_cuenta_id": 1, "mes_evento_id": 10})
    location = actualizar_evento(ctx, 10, {"lugar_id": 2, "salon_id": 1}, supabase=db)
    assert not location.ok and location.estado == "dependencies"
    assert any(call[0] == "evp_mes_mesa" for call in db.calls)
    db.calls.clear()
    tables = actualizar_evento(ctx, 10, {"cant_mesas": 12}, supabase=db)
    assert not tables.ok and tables.estado == "dependencies"
    assert any(call[0] == "evp_mes_mesa" for call in db.calls)


def test_formulario_guardar_invoca_una_vez_y_estado_proceso() -> None:
    received: list[dict[str, Any]] = []
    form = _form(
        {"modo": "crear", "evento": {"tipo_evento": "Otro", "estado": "Activo"}},
        [{"lug_lugar_id": 1, "lug_nombre_lugar": "Hotel"}],
        [{"sal_salon_id": 1, "sal_nombre_salon": "Salon"}],
        False,
        "",
        lambda value, captured: [],
        lambda value: received.append(value),
        lambda: None,
    )
    save_buttons = [
        control for control in _tree(form)
        if isinstance(control, ft.Button) and str(control.content) == "Guardar"
    ]
    assert len(save_buttons) == 1 and save_buttons[0].on_click is not None
    save_buttons[0].on_click(None)
    assert len(received) == 1
    assert set(received[0]) == {
        "nombre_evento", "nombre_evento_abrev", "tipo_evento",
        "fecha_hora_inicio", "fecha_hora_fin", "cant_mesas",
        "lugar_id", "salon_id", "fase_evento", "estado",
    }
    saving_form = _form(
        {"modo": "crear", "evento": {}}, [], [], True, "Guardando...",
        lambda value, captured: [], lambda value: None, lambda: None,
    )
    saving_button = next(
        control for control in _tree(saving_form)
        if isinstance(control, ft.Button) and str(control.content) == "Guardar"
    )
    assert saving_button.disabled is True


def test_tipos_evento_segun_esquema_y_fases() -> None:
    assert TIPOS_EVENTO_VALIDOS == (
        "Boda", "Cumpleaños", "Quinceaños", "Corporativo", "Otro"
    )
    for tipo_evento in TIPOS_EVENTO_VALIDOS:
        phase = "En_proceso" if tipo_evento == "Quinceaños" else "Pre_evento"
        form = _form(
            {"modo": "editar", "evento": event_row(1, 10, phase=phase) | {"tipo_evento": tipo_evento}},
            [], [], False, "", lambda lugar, values: [], lambda values: None, lambda: None,
        )
        type_dropdown = next(
            control for control in _tree(form)
            if isinstance(control, ft.Dropdown) and str(control.label) == "Tipo *"
        )
        assert type_dropdown.value == tipo_evento
        assert [option.key for option in type_dropdown.options] == list(TIPOS_EVENTO_VALIDOS)
        assert type_dropdown.disabled is (phase == "En_proceso")


def test_api_error_no_es_conexion_y_timeout_si() -> None:
    from services.evento_service import _error

    api = _error(FakeAPIError('violates check constraint "chk_eve_tipo_evento"'), "INSERT")
    assert api.estado == "constraint_error"
    assert api.mensaje == "El tipo de evento seleccionado no es valido."
    fechas = _error(FakeAPIError('violates check constraint "chk_eve_fechas"'), "UPDATE")
    assert fechas.estado == "constraint_error" and "posteriores" in fechas.mensaje
    duplicate = _error(FakeAPIError("duplicate key", code="23505"), "INSERT")
    assert duplicate.estado == "duplicate"
    timeout = _error(TimeoutError("request timed out"), "UPDATE")
    assert timeout.estado == "connection_error"


def test_esquema_autoritativo_tipos_y_migracion_registrada() -> None:
    schema = (ROOT / "esquema.sql").read_text(encoding="utf-8")
    assert '"eve_tipo_evento" character varying(15)' in schema
    assert "DEFAULT 'Otro'" in schema
    assert "DEFAULT 'O'" not in schema
    check_line = next(line for line in schema.splitlines() if 'CONSTRAINT "chk_eve_tipo_evento"' in line)
    check_values = tuple(re.findall(r"\('([^']+)'::character varying\)", check_line))
    assert check_values == TIPOS_EVENTO_VALIDOS
    migration = ROOT / "supabase" / "migrations" / "202608020001_fix_event_type_default.sql"
    rollback = ROOT / "supabase" / "migrations" / "202608020001_fix_event_type_default_rollback.sql"
    migration_sql = migration.read_text(encoding="utf-8")
    rollback_sql = rollback.read_text(encoding="utf-8")
    assert "aplicado manualmente" in migration_sql
    assert "SET DEFAULT 'Otro'" in migration_sql
    assert "SET DEFAULT 'Otro'" in rollback_sql
    assert "SET DEFAULT 'O'" not in rollback_sql


def test_creacion_todos_los_tipos_y_codigo_legado_rechazado() -> None:
    for value in TIPOS_EVENTO_VALIDOS:
        db = DB()
        result = crear_evento(context(), payload(tipo_evento=value), supabase=db)
        assert result.ok
        insert = next(call for call in db.calls if call[1] == "insert")
        assert insert[3]["eve_tipo_evento"] == value
        assert "eve_evento_id" not in insert[3]
    db = DB()
    invalid = crear_evento(context(), payload(tipo_evento="O"), supabase=db)
    assert not invalid.ok and invalid.estado == "invalid_type"
    assert not any(call[1] == "insert" for call in db.calls)


def test_estado_formulario_persistente_al_cambiar_lugar() -> None:
    state = EventFormState.desde_evento("crear")
    form_data = {"modo": "crear", "evento": {}, "estado_form": state}
    returned_rooms = [{"sal_salon_id": 2, "sal_nombre_salon": "Salon B"}]
    captures: list[dict[str, Any]] = []
    form = _form(
        form_data,
        [
            {"lug_lugar_id": 1, "lug_nombre_lugar": "Hotel A"},
            {"lug_lugar_id": 2, "lug_nombre_lugar": "Hotel B"},
        ],
        [{"sal_salon_id": 1, "sal_nombre_salon": "Salon A"}],
        False,
        "",
        lambda lugar, values: captures.append(dict(values)) or returned_rooms,
        lambda values: None,
        lambda: None,
    )
    fields = {str(control.label): control for control in _tree(form) if isinstance(control, ft.TextField)}
    dropdowns = {str(control.label): control for control in _tree(form) if isinstance(control, ft.Dropdown)}
    location_dropdowns = [control for control in _tree(form) if isinstance(control, ft.Dropdown) and "activo *" in str(control.label)]
    place_dropdown, room_dropdown = location_dropdowns
    fields["Nombre *"].value = "Evento conservado"
    fields["Nombre abreviado"].value = "CONS"
    fields["Inicio *"].value = "2026-09-01T18:00:00-05:00"
    fields["Final"].value = "2026-09-01T22:00:00-05:00"
    fields["Cantidad de mesas"].value = "12"
    dropdowns["Tipo *"].value = "Corporativo"
    place_dropdown.value = "2"
    room_dropdown.value = "1"
    room_dropdown.update = lambda: None
    place_dropdown.on_select(None)
    assert captures and captures[0]["nombre_evento"] == "Evento conservado"
    assert state.nombre_evento == "Evento conservado" and state.nombre_evento_abrev == "CONS"
    assert state.tipo_evento == "Corporativo" and state.fecha_hora_inicio.startswith("2026-09-01")
    assert state.lugar_id == "2" and state.salon_id is None
    assert room_dropdown.value is None
    assert [option.key for option in room_dropdown.options] == ["2"]


def test_resultado_formulario_siempre_visible() -> None:
    success_state = {
        "eventos_admin_form": {"modo": "crear"},
        "eventos_admin_form_message": "Guardando...",
        "eventos_admin_mensaje": "",
    }
    _registrar_resultado_form_evento(
        success_state,
        ResultadoEvento(True, "created", "Evento creado correctamente.", {}),
    )
    assert success_state["eventos_admin_form"] is None
    assert success_state["eventos_admin_mensaje"] == "Evento creado correctamente."

    error_state = {
        "eventos_admin_form": {"modo": "crear"},
        "eventos_admin_form_message": "Guardando...",
        "eventos_admin_mensaje": "",
    }
    _registrar_resultado_form_evento(
        error_state,
        ResultadoEvento(False, "validation", "El nombre del evento es requerido."),
    )
    assert error_state["eventos_admin_form"] is not None
    assert error_state["eventos_admin_form_message"] == "El nombre del evento es requerido."
    assert error_state["eventos_admin_mensaje"] == "El nombre del evento es requerido."


def test_ciclo_de_vida_estado_y_default() -> None:
    db, ctx = DB(), context()
    assert obtener_transiciones_permitidas({"fase_evento": "Pre_evento", "estado": "Activo"}) == ("En_proceso",)
    assert not cerrar_evento(ctx, 10, supabase=db).ok
    started = iniciar_evento(ctx, 10, supabase=db)
    assert started.ok and started.evento["fase_evento"] == "En_proceso"
    assert not iniciar_evento(ctx, 10, supabase=db).ok
    closed = cerrar_evento(ctx, 10, supabase=db)
    assert closed.ok and closed.evento["fase_evento"] == "Post_evento"
    assert not iniciar_evento(ctx, 10, supabase=db).ok
    assert not cambiar_estado_evento(ctx, 10, "Inactivo", supabase=db).ok
    db.tables["evp_eve_evento"][0]["eve_fase_evento"] = "Pre_evento"
    assert cambiar_estado_evento(ctx, 10, "Inactivo", supabase=db).ok
    assert not iniciar_evento(ctx, 10, supabase=db).ok
    assert cambiar_estado_evento(ctx, 10, "Activo", supabase=db).ok
    default = establecer_evento_predeterminado(ctx, 10, supabase=db)
    assert default.ok and ctx["usr_evento_id_default"] == 10
    assert db.tables["evp_usr_usuario"][0]["usr_evento_id_default"] == 10


def test_ui_roles_filtros_y_checkin() -> None:
    denied = eventos_admin_view(context("Operador"), "denied", "", [], [], [], None, "", False, {}, *(lambda *a: None for _ in range(11)))
    assert isinstance(denied, ft.Control)
    ready = eventos_admin_view(context(), "ready", "", [], [], [], None, "", False, {}, *(lambda *a: None for _ in range(11)))
    assert isinstance(ready, ft.ListView)
    old = header_module.is_checkin_mode
    header_module.is_checkin_mode = lambda: True
    try:
        header = event_header(context(), lambda: None, lambda: None, on_manage_events=lambda: None)
        popup = header.content.controls[2].content.controls[1]
        assert all(item.content != "Administración de eventos" for item in popup.items)
    finally:
        header_module.is_checkin_mode = old
    assert config.APP_MODE in {"FULL", "CHECKIN"}


def _children(control: ft.Control) -> list[ft.Control]:
    values: list[ft.Control] = []
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        values.append(content)
    controls = getattr(control, "controls", None)
    if isinstance(controls, list):
        values.extend(item for item in controls if isinstance(item, ft.Control))
    return values


def _tree(control: ft.Control) -> list[ft.Control]:
    result = [control]
    for child in _children(control):
        result.extend(_tree(child))
    return result


def test_tarjeta_layout_intrinseco_y_listado_scroll() -> None:
    event = {
        "cuenta_id": 1,
        "evento_id": 10,
        "nombre_evento": "Gala anual",
        "nombre_evento_abrev": "GALA",
        "fase_evento": "Pre_evento",
        "estado": "Activo",
        "fecha_hora_inicio_legible": "15/08/2026 06:00 PM",
        "lugar_id": 1,
        "salon_id": 1,
    }
    callback = lambda *args: None
    default_filters = {"busqueda": "", "fase": "Todas", "estado": "Todos", "desde": "", "hasta": ""}
    card = _card(
        event,
        {1: "Hotel Central"},
        {(1, 1): "Gran Salón"},
        None,
        callback,
        callback,
        callback,
        callback,
        callback,
    )
    controls = _tree(card)
    assert not any(isinstance(control, ft.Image) for control in controls)
    assert card.expand is not True and card.height is None
    assert not any(getattr(control, "expand", None) is True for control in controls)
    assert not any(
        isinstance(control, ft.Container)
        and control.content is None
        and control.bgcolor is not None
        for control in controls
    )
    texts = [str(control.value) for control in controls if isinstance(control, ft.Text)]
    assert texts.index("Gala anual") < texts.index("Pre_evento")
    card_column = card.content
    assert isinstance(card_column, ft.Column)
    assert isinstance(card_column.controls[0], ft.Text)
    assert card_column.controls[0].value == "Gala anual"
    assert isinstance(card_column.controls[1], ft.Text)
    assert card_column.controls[1].value == "GALA"
    assert isinstance(card_column.controls[-1], ft.Row)
    buttons = [control for control in controls if isinstance(control, (ft.Button, ft.OutlinedButton))]
    states = {str(control.content): control.disabled for control in buttons}
    assert states == {
        "Editar": False,
        "Desactivar": False,
        "Iniciar": False,
        "Cerrar": True,
        "Hacer predeterminado": False,
    }

    empty = eventos_admin_view(
        context(), "ready", "", [], [], [], None, "", False, default_filters,
        *(callback for _ in range(11)),
    )
    one = eventos_admin_view(
        context(), "ready", "", [event], [], [], None, "", False, default_filters,
        *(callback for _ in range(11)),
    )
    many = eventos_admin_view(
        context(), "ready", "", [{**event, "evento_id": value} for value in range(1, 8)],
        [], [], None, "", False, default_filters, *(callback for _ in range(11)),
    )
    assert isinstance(empty, ft.ListView) and isinstance(one, ft.ListView) and isinstance(many, ft.ListView)
    assert empty.expand is True and one.expand is True and many.expand is True
    assert empty.height is None and one.height is None and many.height is None
    header = one.controls[0]
    assert isinstance(header, ft.Row) and header.wrap is True
    header_details = header.controls[0]
    assert isinstance(header_details, ft.Text)
    assert header_details.value == "Administración de eventos"
    assert not any("Cuenta activa:" in str(control.value) for control in _tree(one) if isinstance(control, ft.Text))
    assert isinstance(one.controls[1], ft.ResponsiveRow)
    assert one.controls[1].height is None and one.controls[1].expand is not True
    assert any(
        isinstance(control, ft.Text) and control.value == "Sin resultados"
        for control in _tree(empty)
    )
    assert len([control for control in many.controls if isinstance(control, ft.Container) and control.border is not None]) == 7
    minimal_card = ft.Container(content=ft.Text("Evento de prueba"))
    assert minimal_card.expand is not True and minimal_card.height is None


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")
    print(f"[OK] Eventos admin: {len(tests)} grupos.")
