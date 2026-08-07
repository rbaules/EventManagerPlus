from __future__ import annotations

from typing import Any

import flet as ft

from models.usuario_admin_models import ResultadoPaginadoUsuarios, UsuarioDetalle, UsuarioResumen


def _option(value: Any, text: Any | None = None) -> ft.DropdownOption:
    return ft.DropdownOption(key=str(value), text=str(text if text is not None else value))


def _status(title: str, message: str, icon: Any, on_retry: Any = None) -> ft.Control:
    controls: list[ft.Control] = [
        ft.Icon(icon, size=42, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(title, size=21, weight=ft.FontWeight.BOLD),
        ft.Text(message, text_align=ft.TextAlign.CENTER, color=ft.Colors.ON_SURFACE_VARIANT),
    ]
    if on_retry:
        controls.append(ft.OutlinedButton(content="Reintentar", icon=ft.Icons.REFRESH, on_click=lambda e: on_retry()))
    return ft.Container(ft.Column(controls, horizontal_alignment=ft.CrossAxisAlignment.CENTER), alignment=ft.Alignment.CENTER, padding=32)


def _summary_card(item: UsuarioResumen, on_detail: Any) -> ft.Control:
    scope = "Global" if item.acceso_global else f"{len(item.cuentas_visibles)} cuenta(s)"
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PERSON, color=ft.Colors.PRIMARY),
                ft.Column([
                    ft.Text(item.nombre or "Sin nombre", weight=ft.FontWeight.BOLD, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(item.email, size=13, color=ft.Colors.ON_SURFACE_VARIANT, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=2, expand=True),
            ]),
            ft.Text(f"Estado: {item.estado} · {'Master' if item.es_master else 'No Master'}"),
            ft.Text(f"Alcance: {scope}"),
            ft.Text(f"Roles visibles: {', '.join(item.roles_visibles) or 'Sin rol visible'}"),
            ft.Text(f"Eventos asignados: {item.cantidad_eventos_asignados} · Auth: {'Sí' if item.auth_uuid_presente else 'No'}"),
            ft.OutlinedButton(content="Ver detalle", icon=ft.Icons.VISIBILITY, on_click=lambda e, uid=item.usuario_id: on_detail(uid)),
        ], spacing=8),
        padding=14,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        col={"xs": 12, "sm": 6, "lg": 4},
    )


def _table(items: tuple[UsuarioResumen, ...], on_detail: Any) -> ft.Control:
    rows = []
    for item in items:
        rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Text(item.nombre, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
            ft.DataCell(ft.Text(item.email, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)),
            ft.DataCell(ft.Text(item.estado)),
            ft.DataCell(ft.Text("Global" if item.acceso_global else "Por cuenta")),
            ft.DataCell(ft.Text(str(len(item.cuentas_visibles)), tooltip=", ".join(item.cuentas_visibles))),
            ft.DataCell(ft.Text(", ".join(item.roles_visibles) or "—", tooltip=", ".join(item.roles_visibles))),
            ft.DataCell(ft.Text(str(item.cantidad_eventos_asignados))),
            ft.DataCell(ft.Text("Sí" if item.auth_uuid_presente else "No")),
            ft.DataCell(ft.IconButton(icon=ft.Icons.VISIBILITY, tooltip="Ver detalle", on_click=lambda e, uid=item.usuario_id: on_detail(uid))),
        ]))
    return ft.Row([ft.DataTable(
        columns=[ft.DataColumn(label) for label in ("Nombre", "Correo", "Estado", "Alcance", "Cuentas", "Roles", "Eventos", "Auth", "")],
        rows=rows, column_spacing=18, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=10,
    )], scroll=ft.ScrollMode.AUTO)


def user_admin_view(
    resultado: ResultadoPaginadoUsuarios,
    filtros: dict[str, Any],
    *,
    is_mobile: bool,
    loading: bool,
    on_apply_filters: Any,
    on_refresh: Any,
    on_page: Any,
    on_detail: Any,
) -> ft.Control:
    search = ft.TextField(label="Buscar por nombre o correo", value=str(filtros.get("busqueda") or ""), prefix_icon=ft.Icons.SEARCH, on_submit=lambda e: apply())
    state = ft.Dropdown(label="Estado", value=str(filtros.get("estado") or "Todos"), options=[_option(v) for v in ("Todos", "Activo", "Inactivo", "Preregistrado")])
    kind = ft.Dropdown(label="Tipo", value=str(filtros.get("tipo") or "Todos"), options=[_option(v) for v in ("Todos", "Master", "No Master")])
    role = ft.Dropdown(label="Rol visible", value=str(filtros.get("rol") or "Todos"), options=[_option(v) for v in ("Todos", "Administrador", "Operador", "Consulta")])
    account_options = [_option("", "Todas las cuentas")] + [_option(cid, name) for cid, name in resultado.cuentas_filtro]
    account = ft.Dropdown(label="Cuenta", value=str(filtros.get("cuenta_id") or ""), options=account_options)

    def apply() -> None:
        on_apply_filters({"busqueda": search.value or "", "estado": state.value or "Todos", "tipo": kind.value or "Todos", "rol": role.value or "Todos", "cuenta_id": account.value or None})

    header = ft.Column([
        ft.Text("Usuarios", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Consulta de perfiles, relaciones y acceso efectivo. Este módulo es estrictamente de solo lectura.", color=ft.Colors.ON_SURFACE_VARIANT),
        ft.ResponsiveRow([
            ft.Container(search, col={"xs": 12, "md": 4}),
            ft.Container(state, col={"xs": 6, "md": 2}),
            ft.Container(kind, col={"xs": 6, "md": 2}),
            ft.Container(role, col={"xs": 6, "md": 2}),
            ft.Container(account, col={"xs": 6, "md": 2}),
        ]),
        ft.Row([
            ft.FilledButton(content="Aplicar filtros", icon=ft.Icons.FILTER_ALT, on_click=lambda e: apply(), disabled=loading),
            ft.OutlinedButton(content="Actualizar", icon=ft.Icons.REFRESH, on_click=lambda e: on_refresh(), disabled=loading),
        ], wrap=True),
    ], spacing=12)
    if loading:
        body = _status("Cargando usuarios", "Espere mientras se consulta la información autorizada.", ft.Icons.HOURGLASS_TOP)
    elif resultado.estado == "denied":
        body = _status("Acceso denegado", resultado.mensaje, ft.Icons.LOCK)
    elif resultado.estado == "error":
        body = _status("No fue posible cargar", resultado.mensaje, ft.Icons.ERROR_OUTLINE, on_refresh)
    elif not resultado.items:
        body = _status("Sin resultados", resultado.mensaje, ft.Icons.PERSON_SEARCH)
    else:
        body = ft.ResponsiveRow([_summary_card(item, on_detail) for item in resultado.items]) if is_mobile else _table(resultado.items, on_detail)
    pagination = ft.Row([
        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, tooltip="Página anterior", disabled=loading or not resultado.has_previous, on_click=lambda e: on_page(resultado.pagina - 1)),
        ft.Text(f"Página {resultado.pagina} de {max(1, resultado.total_paginas)} · {resultado.total} usuario(s)"),
        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, tooltip="Página siguiente", disabled=loading or not resultado.has_next, on_click=lambda e: on_page(resultado.pagina + 1)),
    ], alignment=ft.MainAxisAlignment.CENTER)
    return ft.Column([header, ft.Divider(), body, pagination], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)


def _info_row(label: str, value: Any) -> ft.Control:
    return ft.Row([ft.Text(label, weight=ft.FontWeight.BOLD, width=180), ft.Text("—" if value in (None, "") else str(value), selectable=True, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START)


def user_admin_detail_view(
    detalle: UsuarioDetalle | None,
    *,
    estado: str,
    mensaje: str,
    loading: bool,
    on_back: Any,
    on_retry: Any,
) -> ft.Control:
    if loading:
        body = _status("Cargando detalle", "Validando el alcance del usuario solicitado.", ft.Icons.HOURGLASS_TOP)
    elif detalle is None:
        body = _status("Detalle no disponible", mensaje or "No tiene acceso al usuario solicitado.", ft.Icons.LOCK if estado == "denied" else ft.Icons.ERROR_OUTLINE, on_retry if estado == "error" else None)
    else:
        general = ft.Container(ft.Column([
            _info_row("Nombre", detalle.nombre), _info_row("Correo administrativo", detalle.email),
            _info_row("Estado", detalle.estado), _info_row("Master", "Sí" if detalle.es_master else "No"),
            _info_row("UUID Auth presente", "Sí" if detalle.auth_uuid_presente else "No"),
            _info_row("Cuenta predeterminada", detalle.cuenta_id_default), _info_row("Evento predeterminado", detalle.evento_id_default),
        ], spacing=8), padding=14)
        accounts = [ft.Container(ft.Column([
            ft.Text(item.cuenta_nombre, weight=ft.FontWeight.BOLD),
            ft.Text(f"Rol: {item.rol} · Relación: {item.estado_relacion} · Cuenta: {item.estado_cuenta}"),
            ft.Text(f"Predeterminada: {'Sí' if item.es_predeterminada else 'No'} · Acceso efectivo: {'Sí' if item.acceso_efectivo else 'No'}"),
        ], spacing=5), padding=12, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8) for item in detalle.cuentas]
        events = [ft.Container(ft.Column([
            ft.Text(f"{item.cuenta_nombre} · {item.evento_nombre}", weight=ft.FontWeight.BOLD),
            ft.Text(f"Fase: {item.fase_evento} · Estado: {item.estado_evento} · Acceso: {item.tipo_acceso}"),
            ft.Text(f"Asignación: {item.estado_relacion or 'No requerida'} · Predeterminado: {'Sí' if item.es_predeterminado else 'No'} · Efectivo: {'Sí' if item.acceso_efectivo else 'No'}"),
        ], spacing=5), padding=12, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=8) for item in detalle.eventos]
        warnings = [ft.Row([ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ERROR), ft.Text(text, expand=True)]) for text in detalle.advertencias]
        audit = ft.Container(ft.Column([_info_row("Creado", detalle.creado), _info_row("Modificado", detalle.modificado)], spacing=8), padding=14)
        body = ft.Column([
            ft.ExpansionTile(title="Datos generales", leading=ft.Icons.PERSON, controls=[general], expanded=True),
            ft.ExpansionTile(title=f"Cuentas ({len(accounts)})", leading=ft.Icons.BUSINESS, controls=accounts or [ft.Text("Sin cuentas visibles.")]),
            ft.ExpansionTile(title=f"Eventos ({len(events)})", leading=ft.Icons.EVENT, controls=events or [ft.Text("Sin eventos visibles.")]),
            ft.ExpansionTile(title=f"Advertencias ({len(warnings)})", leading=ft.Icons.WARNING_AMBER, controls=warnings or [ft.Text("Sin advertencias.")]),
            ft.ExpansionTile(title="Auditoría disponible", leading=ft.Icons.HISTORY, controls=[audit]),
        ], scroll=ft.ScrollMode.AUTO, expand=True)
    return ft.Column([
        ft.Row([ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Volver", on_click=lambda e: on_back()), ft.Text("Detalle de usuario", size=26, weight=ft.FontWeight.BOLD)]),
        ft.Text("Información autorizada en modo solo lectura.", color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Divider(), body,
    ], expand=True)
