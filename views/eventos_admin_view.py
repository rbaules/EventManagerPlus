from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import flet as ft

from services.evento_service import TIPOS_EVENTO_VALIDOS, normalizar_tipo_evento


@dataclass
class EventFormState:
    nombre_evento: str = ""
    nombre_evento_abrev: str = ""
    tipo_evento: str = "Otro"
    fecha_hora_inicio: str = ""
    fecha_hora_fin: str = ""
    cant_mesas: str = ""
    lugar_id: Any = None
    salon_id: Any = None
    fase_evento: str = "Pre_evento"
    estado: str = "Activo"
    modo: str = "crear"
    procesando: bool = False

    @classmethod
    def desde_evento(cls, modo: str, evento: dict[str, Any] | None = None) -> "EventFormState":
        item = evento or {}
        return cls(
            nombre_evento=str(item.get("nombre_evento") or item.get("eve_nombre_evento") or ""),
            nombre_evento_abrev=str(item.get("nombre_evento_abrev") or item.get("eve_nombre_evento_abrev") or ""),
            tipo_evento=(
                normalizar_tipo_evento(item.get("tipo_evento") or item.get("eve_tipo_evento"))
                or ("Otro" if modo == "crear" else "")
            ),
            fecha_hora_inicio=str(item.get("fecha_hora_inicio") or item.get("eve_fecha_hora_inicio") or ""),
            fecha_hora_fin=str(item.get("fecha_hora_fin") or item.get("eve_fecha_hora_fin") or ""),
            cant_mesas="" if (item.get("cant_mesas", item.get("eve_cant_mesas"))) is None else str(item.get("cant_mesas", item.get("eve_cant_mesas"))),
            lugar_id=item.get("lugar_id", item.get("eve_lugar_id")),
            salon_id=item.get("salon_id", item.get("eve_salon_id")),
            fase_evento=str(item.get("fase_evento") or item.get("eve_fase_evento") or "Pre_evento"),
            estado=str(item.get("estado") or item.get("eve_estado") or "Activo"),
            modo=modo,
        )

    def actualizar(self, valores: dict[str, Any]) -> None:
        for campo in asdict(self):
            if campo in valores and campo not in {"modo", "procesando"}:
                setattr(self, campo, valores[campo])

    def payload(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key not in {"modo", "procesando"}}


def _state(title: str, message: str, icon: Any, on_retry: Any = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Icon(icon, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(title, size=21, weight=ft.FontWeight.BOLD),
        ft.Text(message, text_align=ft.TextAlign.CENTER, color=ft.Colors.ON_SURFACE_VARIANT),
    ]
    if on_retry:
        controls.append(ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()))
    return ft.Container(ft.Column(controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=28, alignment=ft.Alignment.CENTER)


def _option(key: Any, text: Any) -> ft.DropdownOption:
    return ft.DropdownOption(key=str(key), text=str(text))


def _form(
    form: dict[str, Any],
    lugares: list[dict[str, Any]],
    salones: list[dict[str, Any]],
    saving: bool,
    message: str,
    on_place_change: Any,
    on_save: Any,
    on_cancel: Any,
) -> ft.Control:
    form_state = form.get("estado_form")
    if not isinstance(form_state, EventFormState):
        form_state = EventFormState.desde_evento(str(form.get("modo") or "crear"), form.get("evento"))
        form["estado_form"] = form_state
    event = form_state.payload()
    fase = form_state.fase_evento
    solo_lectura = fase in {"Post_evento", "Cerrado"}
    en_proceso = fase == "En_proceso"
    nombre = ft.TextField(label="Nombre *", value=str(event.get("nombre_evento") or ""), max_length=50)
    abrev = ft.TextField(label="Nombre abreviado", value=str(event.get("nombre_evento_abrev") or ""), max_length=20)
    tipo_actual = str(event.get("tipo_evento") or "")
    opciones_tipo = list(TIPOS_EVENTO_VALIDOS)
    if tipo_actual and tipo_actual not in TIPOS_EVENTO_VALIDOS:
        print("[EVENTOS_ADMIN][WARNING] Tipo de evento legado no permitido:", repr(tipo_actual))
        opciones_tipo.append(tipo_actual)
    tipo = ft.Dropdown(
        label="Tipo *",
        value=tipo_actual or None,
        options=[_option(value, value) for value in opciones_tipo],
    )
    inicio = ft.TextField(
        label="Inicio *",
        value=str(event.get("fecha_hora_inicio") or ""),
        hint_text="2026-08-15T18:00:00-05:00",
        keyboard_type=ft.KeyboardType.DATETIME,
    )
    fin = ft.TextField(
        label="Final",
        value=str(event.get("fecha_hora_fin") or ""),
        hint_text="2026-08-15T23:00:00-05:00",
        keyboard_type=ft.KeyboardType.DATETIME,
    )
    mesas = ft.TextField(
        label="Cantidad de mesas",
        value="" if event.get("cant_mesas") is None else str(event.get("cant_mesas")),
        keyboard_type=ft.KeyboardType.NUMBER,
        disabled=en_proceso or solo_lectura,
    )
    lugar = ft.Dropdown(
        label="Lugar activo *",
        value=str(event.get("lugar_id") or "") or None,
        options=[_option(item.get("lug_lugar_id"), item.get("lug_nombre_lugar")) for item in lugares],
        disabled=en_proceso or solo_lectura,
    )
    salon = ft.Dropdown(
        label="Salón activo *",
        value=str(event.get("salon_id") or "") or None,
        options=[_option(item.get("sal_salon_id"), item.get("sal_nombre_salon")) for item in salones],
        disabled=not lugar.value or en_proceso or solo_lectura,
    )

    for control in (nombre, abrev, inicio, fin):
        control.disabled = solo_lectura
    tipo.disabled = en_proceso or solo_lectura

    def valores_actuales() -> dict[str, Any]:
        return {
            "nombre_evento": nombre.value,
            "nombre_evento_abrev": abrev.value,
            "tipo_evento": tipo.value,
            "fecha_hora_inicio": inicio.value,
            "fecha_hora_fin": fin.value,
            "cant_mesas": mesas.value,
            "lugar_id": lugar.value,
            "salon_id": salon.value,
            "fase_evento": fase,
            "estado": form_state.estado,
        }

    def place_selected(e: ft.ControlEvent) -> None:
        captured = valores_actuales()
        captured["lugar_id"] = lugar.value
        form_state.actualizar(captured)
        options = on_place_change(lugar.value, captured) or []
        valid_ids = {str(item.get("sal_salon_id")) for item in options}
        if salon.value is not None and str(salon.value) not in valid_ids:
            salon.value = None
            form_state.salon_id = None
        salon.options = [_option(item.get("sal_salon_id"), item.get("sal_nombre_salon")) for item in options]
        salon.disabled = not lugar.value or en_proceso or solo_lectura
        salon.update()

    lugar.on_select = place_selected

    def save(_e: ft.ControlEvent) -> None:
        captured = valores_actuales()
        form_state.actualizar(captured)
        on_save(captured)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Crear evento" if form.get("modo") == "crear" else "Editar evento", size=21, weight=ft.FontWeight.BOLD),
                ft.ResponsiveRow(
                    [
                        ft.Container(nombre, col={"xs": 12, "md": 8}),
                        ft.Container(abrev, col={"xs": 12, "md": 4}),
                        ft.Container(tipo, col={"xs": 12, "sm": 4}),
                        ft.Container(mesas, col={"xs": 12, "sm": 4}),
                        ft.Container(inicio, col={"xs": 12, "md": 6}),
                        ft.Container(fin, col={"xs": 12, "md": 6}),
                        ft.Container(lugar, col={"xs": 12, "md": 6}),
                        ft.Container(salon, col={"xs": 12, "md": 6}),
                    ],
                    spacing=10,
                    run_spacing=10,
                ),
                ft.Text(message, color=ft.Colors.ERROR) if message else ft.Container(),
                ft.Row(
                    [
                        ft.Button(content="Guardar", icon=ft.Icons.SAVE, disabled=saving or solo_lectura, on_click=save),
                        ft.OutlinedButton(content="Cancelar", disabled=saving, on_click=lambda e: on_cancel()),
                        ft.ProgressRing(width=22, height=22, visible=saving),
                    ],
                    wrap=True,
                ),
            ],
            spacing=12,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
    )


def _card(
    event: dict[str, Any],
    lugares: dict[int, str],
    salones: dict[tuple[int, int], str],
    default_id: Any,
    on_edit: Any,
    on_state: Any,
    on_start: Any,
    on_close: Any,
    on_default: Any,
) -> ft.Control:
    phase = str(event.get("fase_evento") or "")
    state = str(event.get("estado") or "")
    pre = phase == "Pre_evento"
    running = phase == "En_proceso"
    active = state == "Activo"
    event_id = event.get("evento_id")
    abbreviated_name = str(event.get("nombre_evento_abrev") or "").strip()
    actions: list[ft.Control] = [
        ft.OutlinedButton(content="Editar", icon=ft.Icons.EDIT, disabled=phase in {"Post_evento", "Cerrado"}, on_click=lambda e: on_edit(event)),
        ft.OutlinedButton(
            content="Desactivar" if active else "Activar",
            icon=ft.Icons.TOGGLE_ON if active else ft.Icons.TOGGLE_OFF,
            disabled=phase in {"Post_evento", "Cerrado"},
            on_click=lambda e: on_state(event, "Inactivo" if active else "Activo"),
        ),
        ft.Button(content="Iniciar", icon=ft.Icons.PLAY_ARROW, disabled=not (pre and active), on_click=lambda e: on_start(event)),
        ft.Button(content="Cerrar", icon=ft.Icons.STOP_CIRCLE, disabled=not (running and active), on_click=lambda e: on_close(event)),
        ft.OutlinedButton(
            content="Predeterminado" if str(default_id) == str(event_id) else "Hacer predeterminado",
            icon=ft.Icons.STAR if str(default_id) == str(event_id) else ft.Icons.STAR_OUTLINE,
            disabled=not active or str(default_id) == str(event_id),
            on_click=lambda e: on_default(event),
        ),
    ]
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    str(event.get("nombre_evento") or ""),
                    size=19,
                    weight=ft.FontWeight.BOLD,
                ),
                *(
                    [ft.Text(abbreviated_name, size=13, color=ft.Colors.ON_SURFACE_VARIANT)]
                    if abbreviated_name
                    else []
                ),
                ft.Row(
                    [
                        ft.Container(ft.Text(phase, size=12), padding=ft.Padding.symmetric(horizontal=9, vertical=4), border_radius=14, bgcolor=ft.Colors.SECONDARY_CONTAINER),
                        ft.Container(ft.Text(state, size=12), padding=ft.Padding.symmetric(horizontal=9, vertical=4), border_radius=14, bgcolor=ft.Colors.PRIMARY_CONTAINER),
                    ],
                    wrap=True,
                ),
                ft.Text(
                    f"{event.get('fecha_hora_inicio_legible') or 'Sin fecha'} · "
                    f"{lugares.get(int(event.get('lugar_id') or 0), 'Lugar no disponible')} / "
                    f"{salones.get((int(event.get('lugar_id') or 0), int(event.get('salon_id') or 0)), 'Salón no disponible')}",
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Row(actions, wrap=True),
            ],
            spacing=10,
        ),
        padding=15,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=12,
    )


def eventos_admin_view(
    contexto: dict[str, Any],
    estado: str,
    mensaje: str,
    eventos: list[dict[str, Any]],
    lugares: list[dict[str, Any]],
    salones: list[dict[str, Any]],
    form: dict[str, Any] | None,
    form_message: str,
    saving: bool,
    filtros: dict[str, str],
    on_retry: Any,
    on_new: Any,
    on_edit: Any,
    on_place_change: Any,
    on_save: Any,
    on_cancel: Any,
    on_filter: Any,
    on_state: Any,
    on_start: Any,
    on_close: Any,
    on_default: Any,
) -> ft.Control:
    cuenta = contexto.get("cuenta_actual") or {}
    if not cuenta:
        return _state("Sin cuenta activa", "Selecciona una cuenta antes de administrar eventos.", ft.Icons.ACCOUNT_BALANCE)
    if estado == "denied":
        return _state("Acceso denegado", "Tu rol no permite acceder a la administración de eventos.", ft.Icons.LOCK_OUTLINE)
    if estado == "loading":
        return _state("Cargando", "Consultando eventos de la cuenta activa.", ft.Icons.HOURGLASS_TOP)
    if estado == "error":
        return _state("No fue posible cargar el módulo", mensaje, ft.Icons.ERROR_OUTLINE, on_retry)
    search = ft.TextField(label="Buscar por nombre", value=filtros.get("busqueda", ""), prefix_icon=ft.Icons.SEARCH)
    phase = ft.Dropdown(label="Fase", value=filtros.get("fase") or "Todas", options=[_option(x, x) for x in ("Todas", "Pre_evento", "En_proceso", "Post_evento", "Cerrado")])
    status = ft.Dropdown(label="Estado", value=filtros.get("estado") or "Todos", options=[_option(x, x) for x in ("Todos", "Activo", "Suspendido", "Inactivo")])
    start = ft.TextField(label="Desde", value=filtros.get("desde", ""), hint_text="AAAA-MM-DD")
    end = ft.TextField(label="Hasta", value=filtros.get("hasta", ""), hint_text="AAAA-MM-DD")
    visible = []
    for event in eventos:
        text = str(event.get("nombre_evento") or "").lower()
        date = str(event.get("fecha_hora_inicio") or "")[:10]
        if filtros.get("busqueda", "").lower() not in text:
            continue
        if filtros.get("fase") not in ("", "Todas") and event.get("fase_evento") != filtros.get("fase"):
            continue
        if filtros.get("estado") not in ("", "Todos") and event.get("estado") != filtros.get("estado"):
            continue
        if filtros.get("desde") and date < filtros["desde"]:
            continue
        if filtros.get("hasta") and date > filtros["hasta"]:
            continue
        visible.append(event)
    places = {int(x.get("lug_lugar_id")): str(x.get("lug_nombre_lugar")) for x in lugares}
    rooms = {(int(x.get("sal_lugar_id")), int(x.get("sal_salon_id"))): str(x.get("sal_nombre_salon")) for x in salones}
    controls: list[ft.Control] = [
        ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("Administración de eventos", size=26, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Cuenta activa: {cuenta.get('nombre_cuenta') or cuenta.get('cuenta_id')}", color=ft.Colors.ON_SURFACE_VARIANT),
                    ]
                ),
                ft.Button(content="Crear evento", icon=ft.Icons.ADD, on_click=lambda e: on_new()),
            ],
            wrap=True,
        )
    ]
    if mensaje:
        controls.append(ft.Text(mensaje, color=ft.Colors.ON_SURFACE_VARIANT))
    if form:
        controls.append(_form(form, lugares, salones, saving, form_message, on_place_change, on_save, on_cancel))
    controls.append(
        ft.ResponsiveRow(
            [
                ft.Container(search, col={"xs": 12, "md": 4}),
                ft.Container(phase, col={"xs": 6, "md": 2}),
                ft.Container(status, col={"xs": 6, "md": 2}),
                ft.Container(start, col={"xs": 6, "md": 2}),
                ft.Container(end, col={"xs": 6, "md": 2}),
                ft.Container(ft.Button(content="Aplicar filtros", icon=ft.Icons.FILTER_ALT, on_click=lambda e: on_filter({"busqueda": search.value, "fase": phase.value, "estado": status.value, "desde": start.value, "hasta": end.value})), col=12),
            ],
            spacing=9,
            run_spacing=9,
        )
    )
    controls.extend(
        [_card(item, places, rooms, contexto.get("usr_evento_id_default"), on_edit, on_state, on_start, on_close, on_default) for item in visible]
        or [_state("Sin resultados", "No hay eventos que coincidan con los filtros.", ft.Icons.EVENT_BUSY)]
    )
    return ft.ListView(controls=controls, spacing=14, expand=True)
