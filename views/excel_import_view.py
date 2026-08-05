from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from models.excel_import_models import ImportPreview
from services.excel_import_service import PREVIEW_ROW_LIMIT


def excel_import_view(
    contexto: dict[str, Any],
    estado: str,
    mensaje: str,
    filename: str,
    file_size: int,
    preview: ImportPreview | None,
    on_download_template: Callable[[], Any],
    on_select_file: Callable[[], Any],
    on_download_errors: Callable[[], Any],
) -> ft.Control:
    cuenta, evento = contexto.get("cuenta_actual") or {}, contexto.get("evento_actual") or {}
    summary = preview.summary if preview else None
    cards: list[ft.Control] = []
    if summary:
        for label, value in (
            ("Filas", summary.processed_rows), ("Invitaciones", summary.invitations),
            ("Invitados", summary.guests), ("Mesas", summary.tables),
            ("Errores", summary.errors), ("Advertencias", summary.warnings),
        ):
            cards.append(ft.Container(ft.Column([ft.Text(str(value), size=24, weight=ft.FontWeight.BOLD), ft.Text(label)]), padding=12, border_radius=10, bgcolor=ft.Colors.SURFACE_CONTAINER, col={"xs": 6, "md": 2}))
    table: ft.Control = ft.Container()
    if preview and preview.rows:
        invalid_rows = {issue.excel_row for issue in preview.errors}
        table = ft.Column([
            ft.Text(f"Vista previa (primeras {min(len(preview.rows), PREVIEW_ROW_LIMIT)} filas)", weight=ft.FontWeight.BOLD),
            ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(label)) for label in ("Código", "Destinatario", "Orden", "Nombre", "Principal", "Mesa", "Estado")],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(value)) for value in (
                    row.invitation_code, row.recipient, str(row.guest_order or ""), row.guest_name,
                    "Sí" if row.is_primary else "No", row.table_name or "Sin mesa",
                    "Error" if row.excel_row in invalid_rows else "Válida",
                )]) for row in preview.rows[:PREVIEW_ROW_LIMIT]],
            )], scroll=ft.ScrollMode.AUTO),
        ])
    issues: ft.Control = ft.Container()
    if preview and (preview.errors or preview.warnings):
        issues = ft.Column([
            ft.Text("Incidencias", weight=ft.FontWeight.BOLD),
            *[ft.Text(f"Fila {i.excel_row} · {i.column}: {i.message}", color=ft.Colors.ERROR if i.severity == "ERROR" else ft.Colors.ON_SURFACE_VARIANT) for i in (*preview.errors, *preview.warnings)[:20]],
        ])
    ready = bool(preview and preview.is_valid)
    return ft.Column([
        ft.Text("Importar invitados", size=28, weight=ft.FontWeight.BOLD),
        ft.Text(f"Cuenta: {cuenta.get('nombre_cuenta', '-')} · Evento: {evento.get('nombre_evento', '-')} · Fase: {evento.get('fase_evento', '-')} · Estado: {evento.get('estado', '-')}", color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text("Descargue la plantilla, complete una fila por invitado y valide el archivo completo. No se escribirán datos en esta etapa."),
        ft.Row([
            ft.Button("Descargar plantilla", icon=ft.Icons.DOWNLOAD, on_click=lambda e: on_download_template()),
            ft.Button("Seleccionar archivo", icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: on_select_file()),
        ], wrap=True),
        ft.Text(f"Archivo: {filename} ({file_size:,} bytes)" if filename else "Ningún archivo seleccionado"),
        ft.ProgressBar(visible=estado == "loading"),
        ft.Text(mensaje, color=ft.Colors.ERROR if estado == "error" else ft.Colors.ON_SURFACE_VARIANT),
        ft.ResponsiveRow(cards, spacing=10, run_spacing=10) if cards else ft.Container(),
        table,
        issues,
        ft.Row([
            ft.Button("Descargar errores", icon=ft.Icons.DOWNLOAD, disabled=not bool(preview and (preview.errors or preview.warnings)), on_click=lambda e: on_download_errors()),
            ft.Button("Seleccionar otro archivo", disabled=not bool(filename), on_click=lambda e: on_select_file()),
            ft.Button("Continuar a importación", disabled=True, tooltip="La importación transaccional se habilitará en la siguiente etapa."),
        ], wrap=True),
        ft.Text("Archivo válido y listo para importación." if ready else "", color=ft.Colors.GREEN),
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
