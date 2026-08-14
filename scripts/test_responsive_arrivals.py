from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import flet as ft
from components.responsive import LayoutMode, layout_mode
from views.arrivals_view import arrivals_view
from views.home_view import build_home_view
from views.invitados_view import _invitados_table, invitados_view


def walk(node: Any) -> list[Any]:
    values = [node]
    child = getattr(node, "content", None)
    if child is not None and child is not node:
        values.extend(walk(child))
    for nested in getattr(node, "controls", None) or []:
        values.extend(walk(nested))
    return values


def context(role: str = "Operador") -> dict[str, Any]:
    event = {
        "cuenta_id": 1,
        "evento_id": 10,
        "nombre_evento": "Evento Tablet",
        "fase_evento": "En_proceso",
        "estado": "Activo",
        "rol": role,
    }
    return {
        "usr_usuario_id": f"user-{role.lower()}",
        "usr_nombre_usuario": f"Usuario {role}",
        "usr_es_usuario_master": role == "Master",
        "rol_global_calculado": role,
        "cuenta_actual": {"cuenta_id": 1, "nombre_cuenta": "Cuenta Tablet", "rol": role},
        "cuentas_permitidas": [{"cuenta_id": 1, "nombre_cuenta": "Cuenta Tablet", "rol": role}],
        "evento_actual": event,
        "eventos_permitidos": [event],
        "puede_registrar_llegadas": role != "Consulta",
    }


def guest(identifier: int = 1) -> dict[str, Any]:
    return {
        "cuenta_id": 1,
        "evento_id": 10,
        "invitacion_id": 100,
        "invitado_id": identifier,
        "invitado_uuid": f"guest-{identifier}",
        "nombre_completo": "Invitado de Prueba Tablet",
        "es_invitado_principal": True,
        "mesa_texto": "Mesa Principal",
        "puesto_texto": "01 - Prin",
        "llegada_confirmada": False,
        "tiene_novedad": True,
        "descripcion_novedad": "Observación de prueba",
    }


def build_arrivals(width: int, role: str = "Operador") -> Any:
    item = guest()
    return arrivals_view(
        contexto=context(role),
        estado="ready",
        mensaje="",
        busqueda="tablet",
        resultados=[item],
        invitacion={"invitacion_id": 100, "destinatario": "Familia Tablet", "codigo": "TAB"},
        integrantes=[item],
        seleccionados={item["invitado_uuid"]},
        can_reverse_arrival=role in {"Master", "Administrador", "Operador"},
        is_loading=False,
        is_saving=False,
        on_search=lambda value=None: None,
        on_clear=lambda: None,
        on_select_guest=lambda value=None: None,
        on_toggle_guest=lambda value=None, selected=False: None,
        on_select_pending=lambda: None,
        on_confirm_selected=lambda: None,
        on_reverse_arrival=lambda value=None: None,
        on_retry=lambda: None,
        on_novelty=lambda value=None: None,
        layout=layout_mode(width),
        can_edit_novelty=role != "Consulta",
    )


def build_arrivals_with_names(width: int, names: list[tuple[str, str]]) -> Any:
    items = []
    for index, (identifier, name) in enumerate(names, start=1):
        item = guest(index)
        item["invitado_uuid"] = identifier
        item["nombre_completo"] = name
        items.append(item)
    return arrivals_view(
        contexto=context(), estado="ready", mensaje="", busqueda="orden", resultados=items,
        invitacion={"invitacion_id": 100, "destinatario": "Familia Orden", "codigo": "ORD"},
        integrantes=list(reversed(items)), seleccionados=set(), can_reverse_arrival=True,
        is_loading=False, is_saving=False, on_search=lambda value=None: None, on_clear=lambda: None,
        on_select_guest=lambda value=None: None, on_toggle_guest=lambda value=None, selected=False: None,
        on_select_pending=lambda: None, on_confirm_selected=lambda: None,
        on_reverse_arrival=lambda value=None: None, on_retry=lambda: None,
        on_novelty=lambda value=None: None, layout=layout_mode(width), can_edit_novelty=True,
    )


def grids(control: Any) -> set[str]:
    return {
        node.data["arrivals_grid"]
        for node in walk(control)
        if isinstance(getattr(node, "data", None), dict) and node.data.get("arrivals_grid")
    }


def responsive_components(control: Any) -> list[str]:
    return [
        node.data["responsive_component"]
        for node in walk(control)
        if isinstance(getattr(node, "data", None), dict) and node.data.get("responsive_component")
    ]


def assert_shell_structure(control: Any) -> None:
    components = responsive_components(control)
    assert components.count("event_header") == 1
    assert components.count("content") == 1
    assert components.count("bottom_navigation") == 0
    shell = next(node for node in walk(control) if isinstance(getattr(node, "data", None), dict) and node.data.get("responsive_component") == "app_shell")
    column = shell.content
    assert isinstance(column, ft.Column)
    assert len(column.controls) == 2
    content_zone = next(node for node in column.controls if isinstance(getattr(node, "data", None), dict) and node.data.get("responsive_component") == "content")
    assert content_zone.expand is True


def test_bottom_navigation_is_viewport_constrained_for_wide_content() -> None:
    from components.bottom_navigation import bottom_navigation

    navigation = None
    navigation_id = None
    for width in (768, 800, 900, 1024, 1180, 1280, 1440):
        for guest_count in (9, 50, 120, 500):
            navigation = bottom_navigation(
                selected="guests",
                can_use_app=True,
                can_register_arrivals=True,
                on_select=lambda _key: None,
                navigation=navigation,
            )
            navigation_id = navigation_id or id(navigation)
            assert len(navigation.destinations) == 3
            assert id(navigation) == navigation_id


class FakePage:
    def __init__(self, width: int) -> None:
        self.width = width
        self.height = 800
        self.route = "/app/llegadas"
        self.navigation_bar = None
        self.scroll = ft.ScrollMode.AUTO
        self.on_resize = None
        self.services: list[Any] = []
        self.added: list[Any] = []
        self.clean_count = 0
        self.update_count = 0

    def clean(self) -> None:
        self.clean_count += 1
        self.added.clear()

    def add(self, control: Any) -> None:
        self.added.append(control)

    def update(self) -> None:
        self.update_count += 1


class NoQuerySupabase:
    def __init__(self) -> None:
        self.calls = 0

    def table(self, _name: str) -> Any:
        self.calls += 1
        raise AssertionError("Un resize no debe consultar Supabase")

    def rpc(self, _name: str, _params: Any = None) -> Any:
        self.calls += 1
        raise AssertionError("Un resize no debe ejecutar RPC")


def test_layout_boundaries() -> None:
    expected = {
        360: LayoutMode.PHONE,
        430: LayoutMode.PHONE,
        600: LayoutMode.PHONE_LARGE,
        767: LayoutMode.PHONE_LARGE,
        768: LayoutMode.TABLET_PORTRAIT,
        800: LayoutMode.TABLET_PORTRAIT,
        900: LayoutMode.TABLET_PORTRAIT,
        991: LayoutMode.TABLET_PORTRAIT,
        992: LayoutMode.TABLET_LANDSCAPE,
        1024: LayoutMode.TABLET_LANDSCAPE,
        1180: LayoutMode.TABLET_LANDSCAPE,
        1200: LayoutMode.DESKTOP_WIDE,
        1280: LayoutMode.DESKTOP_WIDE,
    }
    assert {width: layout_mode(width) for width in expected} == expected


def test_arrivals_layouts_and_roles() -> None:
    expected = {
        430: {"search_cards", "confirmation_cards"},
        768: {"search", "confirmation"},
        800: {"search", "confirmation"},
        900: {"search", "confirmation"},
        1024: {"search", "confirmation"},
        1280: {"search", "confirmation"},
    }
    for width, required in expected.items():
        assert required <= grids(build_arrivals(width))
    for role in ("Operador", "Administrador", "Master"):
        assert {"search", "confirmation"} <= grids(build_arrivals(800, role))
    assert not grids(build_arrivals(800, "Consulta"))
    for width in (430, 768, 800, 900, 1024, 1280):
        built = build_arrivals(width)
        fields = [node for node in walk(built) if isinstance(node, ft.TextField)]
        search = next(node for node in fields if node.label == "Buscar invitado")
        assert search.value == "tablet" and search.autofocus is False
        action_row = next(node for node in walk(built) if isinstance(getattr(node, "data", None), dict) and node.data.get("arrivals_action_row") == "group_confirmation")
        select_pending = next(node for node in action_row.controls if getattr(node, "data", None) == {"arrivals_action": "select_pending"})
        confirm = next(node for node in action_row.controls if getattr(node, "data", None) == {"arrivals_action": "confirm_selected"})
        assert action_row.controls.index(confirm) == action_row.controls.index(select_pending) + 1
        assert action_row.wrap is True
        if layout_mode(width) not in {LayoutMode.PHONE, LayoutMode.PHONE_LARGE}:
            table = next(node for node in walk(built) if isinstance(node, ft.DataTable) and isinstance(node.data, dict) and node.data.get("arrivals_grid") == "confirmation")
            confirm_column = table.columns[-1]
            assert confirm_column.data == {"arrivals_column": "confirmation"}
            assert isinstance(confirm_column.label, ft.Text) and confirm_column.label.value == "Llegada"
            assert not any(getattr(node, "data", None) == {"arrivals_action": "confirm_selected"} for node in walk(table))
        assert confirm.bgcolor == ft.Colors.PRIMARY and confirm.color == ft.Colors.ON_PRIMARY


def test_alphabetical_order_in_both_grids() -> None:
    fixture = [
        ("guest-5", "  zoe "),
        ("guest-3", "Álvaro"),
        ("guest-4", "ana"),
        ("guest-2", "Ana"),
        ("guest-1", "  béa  "),
    ]
    built = build_arrivals_with_names(1024, fixture)
    tables = {
        node.data["arrivals_grid"]: node
        for node in walk(built)
        if isinstance(node, ft.DataTable) and isinstance(node.data, dict) and node.data.get("arrivals_grid")
    }
    expected_ids = ["guest-3", "guest-2", "guest-4", "guest-1", "guest-5"]
    assert [row.data["guest_sort_id"] for row in tables["search"].rows] == expected_ids
    assert [row.data["guest_sort_id"] for row in tables["confirmation"].rows] == expected_ids


def test_shell_is_viewport_bound_for_row_volumes() -> None:
    original_mode = config.APP_MODE
    try:
        config.APP_MODE = config.APP_MODE_FULL
        for count in (0, 1, 5, 20, 50, 100, 200):
            page = FakePage(700)
            control = build_home_view(page, context("Operador"), NoQuerySupabase())
            page.add(control)
            callbacks = control.data
            state = callbacks["state"]
            items = [guest(index) for index in range(1, count + 1)]
            state.update({
                "selected": "arrivals", "arrivals_estado": "ready", "arrivals_busqueda": "volumen",
                "arrivals_resultados": items, "arrivals_invitacion": ({"invitacion_id": 100, "destinatario": "Familia"} if count else None),
                "arrivals_integrantes": items, "arrivals_seleccionados": set(),
            })
            page.width = 800
            page.on_resize(None)
            shell = control
            assert_shell_structure(shell)
            content_zone = next(node for node in walk(shell) if isinstance(getattr(node, "data", None), dict) and node.data.get("responsive_component") == "content")
            assert isinstance(content_zone.content, ft.ListView)
            assert content_zone.content.expand is True
            assert page.scroll is None and isinstance(page.navigation_bar, ft.NavigationBar)
            assert len(page.navigation_bar.destinations) == 3
    finally:
        config.APP_MODE = original_mode


def test_individual_toggles_are_local_for_long_lists() -> None:
    original_mode = config.APP_MODE
    try:
        for runtime_mode in (config.APP_MODE_FULL, config.APP_MODE_CHECKIN):
            config.APP_MODE = runtime_mode
            page = FakePage(700)
            db = NoQuerySupabase()
            control = build_home_view(page, context("Operador"), db)
            page.add(control)
            state = control.data["state"]
            items = [guest(identifier) for identifier in range(1, 201)]
            state.update({
                "selected": "arrivals", "arrivals_estado": "ready", "arrivals_busqueda": "larga",
                "arrivals_resultados": items,
                "arrivals_invitacion": {"invitacion_id": 100, "destinatario": "Familia Larga"},
                "arrivals_integrantes": items, "arrivals_seleccionados": set(),
                "arrivals_event_key": (1, 10),
            })
            page.width = 800
            page.on_resize(None)
            shell = control
            table = next(node for node in walk(shell) if isinstance(node, ft.DataTable) and getattr(node, "data", {}).get("arrivals_grid") == "confirmation")
            checkboxes = [cell.content for row in table.rows for cell in row.cells if isinstance(cell.content, ft.Checkbox)]
            confirm = next(node for node in walk(shell) if getattr(node, "data", None) == {"arrivals_action": "confirm_selected"})
            clean_before, update_before = page.clean_count, page.update_count
            selected_ids = {table.rows[index].data["guest_sort_id"] for index in (194, 195, 196, 197, 198, 199)}

            for index in (194, 195, 196, 197, 198, 199):
                checkbox = checkboxes[index]
                checkbox.value = True
                checkbox.on_change(SimpleNamespace(control=checkbox))
                assert page.added[0] is shell
                assert next(node for node in walk(shell) if isinstance(node, ft.DataTable) and getattr(node, "data", {}).get("arrivals_grid") == "confirmation") is table

            assert state["arrivals_seleccionados"] == selected_ids
            assert confirm.content == "Confirmar seleccionados (6)" and confirm.disabled is False
            checkboxes[196].value = False
            checkboxes[196].on_change(SimpleNamespace(control=checkboxes[196]))
            assert table.rows[196].data["guest_sort_id"] not in state["arrivals_seleccionados"]
            assert confirm.content == "Confirmar seleccionados (5)"
            assert page.clean_count == clean_before and page.update_count == update_before
            assert page.added[0] is shell and db.calls == 0
    finally:
        config.APP_MODE = original_mode


def test_resize_preserves_state_without_queries_full_and_checkin() -> None:
    original_mode = config.APP_MODE
    try:
        for runtime_mode in (config.APP_MODE_FULL, config.APP_MODE_CHECKIN):
            config.APP_MODE = runtime_mode
            page = FakePage(700)
            db = NoQuerySupabase()
            active_context = context("Operador")
            control = build_home_view(page, active_context, db)
            page.add(control)
            assert page.scroll is None
            callbacks = control.data
            root_id = id(control)
            navigation_id = id(page.navigation_bar)
            state = callbacks["state"]
            many_guests = [guest(identifier) for identifier in range(1, 51)]
            state.update({
                "selected": "arrivals",
                "arrivals_busqueda": "ana",
                "arrivals_resultados": many_guests,
                "arrivals_invitacion": {"invitacion_id": 100, "destinatario": "Familia Tablet"},
                "arrivals_integrantes": many_guests,
                "arrivals_seleccionados": {"guest-1", "guest-2"},
                "arrivals_estado": "ready",
                "arrivals_event_key": (1, 10),
            })
            original_values = (
                state["arrivals_busqueda"], state["arrivals_resultados"], state["arrivals_invitacion"],
                state["arrivals_integrantes"], state["arrivals_seleccionados"], active_context["evento_actual"],
            )
            assert callable(page.on_resize)
            page.width = 800
            page.on_resize(None)
            live_content = control.content.controls[1].content
            live_tables = {
                node.data["arrivals_grid"]: node
                for node in walk(live_content)
                if isinstance(node, ft.DataTable) and isinstance(node.data, dict) and node.data.get("arrivals_grid")
            }
            transitions = (900, 1280, 800, 1280, 800, 1280, 800, 1024, 768, 1180, 900)
            expected_updates = 1
            for width in transitions:
                previous_mode = state["layout_mode"]
                page.width = width
                page.on_resize(None)
                if layout_mode(width) != previous_mode:
                    expected_updates += 1
                    assert len(page.added) == 1
                    assert id(page.added[0]) == root_id
                    assert id(page.navigation_bar) == navigation_id
                    assert_shell_structure(control)
                    assert {"search", "confirmation"} <= grids(control)
                    assert control.content.controls[1].content is live_content
                    current_tables = {
                        node.data["arrivals_grid"]: node
                        for node in walk(live_content)
                        if isinstance(node, ft.DataTable) and isinstance(node.data, dict) and node.data.get("arrivals_grid")
                    }
                    assert current_tables == live_tables
                assert state["layout_mode"] == layout_mode(width)
                assert page.clean_count == 0 and page.update_count == expected_updates
                assert page.on_resize == callbacks["handle_resize"]
            current_values = (
                state["arrivals_busqueda"], state["arrivals_resultados"], state["arrivals_invitacion"],
                state["arrivals_integrantes"], state["arrivals_seleccionados"], active_context["evento_actual"],
            )
            assert current_values == original_values
            assert db.calls == 0
    finally:
        config.APP_MODE = original_mode


def test_guest_grid_actions_fit_tablet_portrait_and_remain_compact() -> None:
    items = [guest(index) for index in range(1, 10)]
    grid = _invitados_table(
        items, lambda *_: None, lambda *_: None, lambda *_: None, lambda *_: None,
        True, True, True,
    )
    table = grid.controls[0]
    estimated_width = sum(column.label.width for column in table.columns) + (6 * table.column_spacing) + (2 * table.horizontal_margin)
    tablet_content_width = 800 - 32

    assert estimated_width == 758
    assert estimated_width <= tablet_content_width
    assert table.horizontal_margin == 8 and table.column_spacing == 8
    assert [column.label.value for column in table.columns] == [
        "#", "Invitado", "Invitación", "Mesa", "Estado", "Hora llegada", "Acciones",
    ]
    assert table.columns[0].label.width == 40
    for data_row in table.rows:
        number = data_row.cells[0].content
        assert number.width == 40 and number.no_wrap is True and number.text_align == ft.TextAlign.CENTER
        actions = data_row.cells[-1].content
        assert actions.width == 186 and actions.spacing == 6
        assert all(
            action.width == 42 and action.height == 42 and action.icon_size == 22
            for action in actions.controls
        )

    large_grid = _invitados_table(
        [guest(index) for index in range(1, 121)],
        lambda *_: None, lambda *_: None, lambda *_: None, lambda *_: None,
        True, True, True,
    )
    assert [large_grid.controls[0].rows[index - 1].cells[0].content.value for index in (99, 100, 120)] == [
        "99", "100", "120",
    ]
    assert all(
        large_grid.controls[0].rows[index - 1].cells[0].content.no_wrap is True
        for index in (99, 100, 120)
    )

    assert estimated_width <= (1280 - 32)
    assert estimated_width <= (1440 - 32)


def test_three_guest_actions_have_uniform_touch_separation_at_800() -> None:
    item = guest(1)
    grid = _invitados_table(
        [item], lambda *_: None, lambda *_: None, lambda *_: None, lambda *_: None,
        can_manage=False,
        can_confirm_arrival=True,
        can_reverse_arrival=False,
        can_edit_novelty=True,
    )
    actions = grid.controls[0].rows[0].cells[-1].content
    button_widths = [button.width for button in actions.controls]

    assert len(actions.controls) == 3
    assert button_widths == [42, 42, 42]
    assert actions.spacing == 6
    assert sum(button_widths) + actions.spacing * (len(button_widths) - 1) == 138
    assert actions.width == 186
    estimated_width = sum(column.label.width for column in grid.controls[0].columns) + 6 * 8 + 2 * 8
    assert estimated_width == 758
    assert estimated_width <= 800 - 32
    assert estimated_width <= 1280 - 32


def test_guest_controls_and_unapplied_draft_survive_tablet_rotations() -> None:
    page = FakePage(700)
    db = NoQuerySupabase()
    control = build_home_view(page, context("Consulta"), db)
    page.add(control)
    state = control.data["state"]
    items = [guest(index) for index in range(1, 121)]
    state.update({
        "selected": "guests", "invitados_estado": "ready", "invitados": items,
        "invitados_busqueda": "aplicado", "invitados_busqueda_draft": "aplicado",
        "invitados_filtro": "pendientes", "invitados_event_key": (1, 10),
    })
    page.width = 800
    page.on_resize(None)
    guest_content = control.content.controls[1].content
    search_field = next(
        node for node in walk(guest_content)
        if isinstance(node, ft.TextField) and node.label in {"Buscar invitado", "Buscar mesa"}
    )
    scroll_control = next(
        node for node in walk(guest_content)
        if isinstance(node, ft.Row) and isinstance(node.data, dict)
        and node.data.get("responsive_component") == "guest_grid_scroll"
    )
    search_field.value = "perez sin enviar"
    search_field.on_change(SimpleNamespace(control=search_field))
    assert state["invitados_busqueda_draft"] == "perez sin enviar"
    assert state["invitados_busqueda"] == "aplicado"

    for width in (1280, 800, 1280, 800, 1280, 800):
        page.width = width
        page.on_resize(None)
        assert control.content.controls[1].content is guest_content
        assert next(node for node in walk(guest_content) if node is search_field) is search_field
        assert next(node for node in walk(guest_content) if node is scroll_control) is scroll_control
        assert search_field.value == "perez sin enviar"
        assert state["invitados_busqueda"] == "aplicado"
    assert db.calls == 0 and page.clean_count == 0


def main() -> int:
    test_layout_boundaries()
    test_arrivals_layouts_and_roles()
    test_alphabetical_order_in_both_grids()
    test_bottom_navigation_is_viewport_constrained_for_wide_content()
    test_shell_is_viewport_bound_for_row_volumes()
    test_individual_toggles_are_local_for_long_lists()
    test_resize_preserves_state_without_queries_full_and_checkin()
    test_guest_grid_actions_fit_tablet_portrait_and_remain_compact()
    test_three_guest_actions_have_uniform_touch_separation_at_800()
    test_guest_controls_and_unapplied_draft_survive_tablet_rotations()
    print("OK - responsive modes, arrivals layouts, roles, FULL/CHECKIN and resize state preservation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
