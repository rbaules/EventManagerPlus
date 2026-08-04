from __future__ import annotations

from urllib.parse import quote, unquote


ROUTES = {
    "dashboard": "/app/dashboard",
    "guests": "/app/invitados",
    "arrivals": "/app/llegadas",
    "events_admin": "/app/eventos",
    "event_selection": "/app/eventos/seleccionar",
    "locations": "/app/lugares",
    "preferences": "/app/preferencias",
}


def route_for(section: str, identifier: object | None = None, action: str | None = None) -> str:
    base = ROUTES.get(section, ROUTES["dashboard"])
    if identifier is not None:
        base = f"{base}/{quote(str(identifier), safe='')}"
    return f"{base}/{action}" if action else base


def parse_app_route(route: str | None) -> tuple[str, str | None, str | None]:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    if clean in {"/", "/app", ROUTES["dashboard"]}:
        return "dashboard", None, None
    for section, base in sorted(ROUTES.items(), key=lambda item: len(item[1]), reverse=True):
        if clean == base:
            return section, None, None
        prefix = f"{base}/"
        if clean.startswith(prefix):
            parts = clean[len(prefix):].split("/")
            identifier = unquote(parts[0]) if parts[0] else None
            action = parts[1] if len(parts) > 1 else None
            return section, identifier, action
    return "dashboard", None, None
