"""Independent MAP-0B navigation engine for calibrated Kiosk floor plans."""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAP_CONFIG_NOT_FOUND = "MAP_CONFIG_NOT_FOUND"
MAP_TABLE_NOT_FOUND = "MAP_TABLE_NOT_FOUND"
MAP_INVALID_CONFIG = "MAP_INVALID_CONFIG"
MAP_ROUTE_NOT_FOUND = "MAP_ROUTE_NOT_FOUND"

DEFAULT_MAP_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "kiosk_maps"


class MapConfigError(ValueError):
    """Expected, normalized configuration error; never exposed raw to callers."""


@dataclass(frozen=True)
class MapNode:
    node_id: str
    kind: str
    x: float
    y: float


@dataclass(frozen=True)
class MapTable:
    mesa_id: int
    mesa_texto: str
    destination_node: str


@dataclass(frozen=True)
class MapEdge:
    source: str
    target: str
    weight: float
    bidirectional: bool


@dataclass(frozen=True)
class MapConfig:
    account_id: int
    event_id: int
    storage_bucket: str
    storage_path: str
    origin_id: str
    nodes: dict[str, MapNode]
    tables: dict[int, MapTable]
    edges: tuple[MapEdge, ...]
    calibration_pending: bool


@dataclass(frozen=True)
class ResultadoRuta:
    ok: bool
    codigo: str
    mensaje: str
    account_id: int
    event_id: int
    mesa_id: int | None = None
    mesa_texto: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    node_ids: tuple[str, ...] = ()
    points: tuple[tuple[float, float], ...] = ()
    total_distance: float = 0.0


def _config_path(account_id: int, event_id: int, config_dir: Path) -> Path:
    return config_dir / f"{int(account_id)}_{int(event_id)}.json"


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise MapConfigError(f"{field} invalido")
    try:
        result = int(value)
    except (TypeError, ValueError) as ex:
        raise MapConfigError(f"{field} invalido") from ex
    if result < 1:
        raise MapConfigError(f"{field} invalido")
    return result


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise MapConfigError(f"{field} requerido")
    return result


def _normalized_point(raw: dict[str, Any], *, allow_pending: bool) -> tuple[float, float] | None:
    x, y = raw.get("x"), raw.get("y")
    if allow_pending and x is None and y is None:
        return None
    if isinstance(x, bool) or isinstance(y, bool):
        raise MapConfigError("coordenadas invalidas")
    try:
        point = (float(x), float(y))
    except (TypeError, ValueError) as ex:
        raise MapConfigError("coordenadas invalidas") from ex
    if not all(0.0 <= coordinate <= 1.0 for coordinate in point):
        raise MapConfigError("coordenadas fuera de rango")
    return point


def _parse_node(raw: Any, *, allow_pending: bool = False) -> MapNode | None:
    if not isinstance(raw, dict):
        raise MapConfigError("nodo invalido")
    point = _normalized_point(raw, allow_pending=allow_pending)
    if point is None:
        return None
    return MapNode(
        node_id=_text(raw.get("id"), "node.id"),
        kind=_text(raw.get("kind"), "node.kind"),
        x=point[0],
        y=point[1],
    )


def load_map_config(
    account_id: int,
    event_id: int,
    *,
    config_dir: Path = DEFAULT_MAP_CONFIG_DIR,
) -> MapConfig:
    """Load and validate the prototype config selected by tenant and event."""
    path = _config_path(account_id, event_id, config_dir)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as ex:
        raise MapConfigError("JSON de mapa invalido") from ex
    if not isinstance(raw, dict):
        raise MapConfigError("raiz de mapa invalida")
    if raw.get("version") != 1:
        raise MapConfigError("version de mapa incompatible")
    if raw.get("account_id") != int(account_id) or raw.get("event_id") != int(event_id):
        raise MapConfigError("identidad de cuenta/evento inconsistente")

    raw_map = raw.get("map")
    raw_origin = raw.get("origin")
    raw_tables = raw.get("tables")
    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges")
    if not isinstance(raw_map, dict) or not isinstance(raw_origin, dict):
        raise MapConfigError("mapa u origen invalido")
    if not isinstance(raw_tables, dict) or not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise MapConfigError("colecciones de mapa invalidas")

    storage_bucket = _text(raw_map.get("storage_bucket"), "map.storage_bucket")
    storage_path = _text(raw_map.get("storage_path"), "map.storage_path")
    origin_id = _text(raw_origin.get("id"), "origin.id")
    origin = _parse_node(raw_origin, allow_pending=True)
    nodes: dict[str, MapNode] = {}
    if origin is not None:
        nodes[origin.node_id] = origin
    for item in raw_nodes:
        node = _parse_node(item)
        assert node is not None
        if node.node_id in nodes:
            raise MapConfigError("id de nodo duplicado")
        nodes[node.node_id] = node

    tables: dict[int, MapTable] = {}
    for raw_mesa_id, item in raw_tables.items():
        if not isinstance(item, dict):
            raise MapConfigError("mesa invalida")
        mesa_id = _positive_int(raw_mesa_id, "mesa_id")
        if mesa_id in tables:
            raise MapConfigError("mesa_id duplicado")
        tables[mesa_id] = MapTable(
            mesa_id=mesa_id,
            mesa_texto=_text(item.get("label"), "mesa.label"),
            destination_node=_text(item.get("destination_node"), "mesa.destination_node"),
        )

    edges: list[MapEdge] = []
    for item in raw_edges:
        if not isinstance(item, dict):
            raise MapConfigError("edge invalido")
        source = _text(item.get("from"), "edge.from")
        target = _text(item.get("to"), "edge.to")
        if source not in nodes or target not in nodes or source == target:
            raise MapConfigError("edge referencia nodo inexistente")
        weight = item.get("weight")
        if weight is None:
            source_node = nodes[source]
            target_node = nodes[target]
            normalized_weight = math.hypot(
                source_node.x - target_node.x,
                source_node.y - target_node.y,
            )
        else:
            if isinstance(weight, bool):
                raise MapConfigError("edge.weight invalido")
            try:
                normalized_weight = float(weight)
            except (TypeError, ValueError) as ex:
                raise MapConfigError("edge.weight invalido") from ex
        if normalized_weight <= 0:
            raise MapConfigError("edge.weight invalido")
        if not isinstance(item.get("bidirectional"), bool):
            raise MapConfigError("edge.bidirectional invalido")
        edges.append(MapEdge(source, target, normalized_weight, item["bidirectional"]))

    calibration_pending = origin is None and not raw_nodes and not raw_edges
    return MapConfig(
        account_id=int(account_id),
        event_id=int(event_id),
        storage_bucket=storage_bucket,
        storage_path=storage_path,
        origin_id=origin_id,
        nodes=nodes,
        tables=tables,
        edges=tuple(edges),
        calibration_pending=calibration_pending,
    )


def _error(
    codigo: str,
    mensaje: str,
    account_id: int,
    event_id: int,
    *,
    mesa_id: int | None = None,
    config: MapConfig | None = None,
) -> ResultadoRuta:
    return ResultadoRuta(
        ok=False,
        codigo=codigo,
        mensaje=mensaje,
        account_id=account_id,
        event_id=event_id,
        mesa_id=mesa_id,
        storage_bucket=config.storage_bucket if config else None,
        storage_path=config.storage_path if config else None,
    )


def _shortest_path(config: MapConfig, start: str, target: str) -> list[str] | None:
    adjacency: dict[str, list[tuple[str, float]]] = {node_id: [] for node_id in config.nodes}
    for edge in config.edges:
        adjacency[edge.source].append((edge.target, edge.weight))
        if edge.bidirectional:
            adjacency[edge.target].append((edge.source, edge.weight))
    frontier: list[tuple[float, str]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[str, str] = {}
    while frontier:
        distance, node_id = heapq.heappop(frontier)
        if distance != distances.get(node_id):
            continue
        if node_id == target:
            path = [target]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return list(reversed(path))
        for next_node, weight in sorted(adjacency[node_id], key=lambda item: item[0]):
            candidate = distance + weight
            if candidate < distances.get(next_node, float("inf")):
                distances[next_node] = candidate
                previous[next_node] = node_id
                heapq.heappush(frontier, (candidate, next_node))
    return None


def calcular_ruta(
    *,
    account_id: int,
    event_id: int,
    mesa_id: int,
    config_dir: Path = DEFAULT_MAP_CONFIG_DIR,
) -> ResultadoRuta:
    """Resolve a Dijkstra path by account, event and mesa_id only."""
    try:
        config = load_map_config(account_id, event_id, config_dir=config_dir)
    except FileNotFoundError:
        return _error(MAP_CONFIG_NOT_FOUND, "No existe configuracion de mapa para este evento.", account_id, event_id, mesa_id=mesa_id)
    except MapConfigError:
        return _error(MAP_INVALID_CONFIG, "La configuracion del mapa no es valida.", account_id, event_id, mesa_id=mesa_id)

    try:
        normalized_mesa_id = int(mesa_id)
    except (TypeError, ValueError):
        normalized_mesa_id = -1
    table = config.tables.get(normalized_mesa_id)
    if table is None:
        return _error(MAP_TABLE_NOT_FOUND, "La mesa no esta configurada en el mapa.", account_id, event_id, mesa_id=mesa_id, config=config)
    if config.calibration_pending:
        return _error(MAP_ROUTE_NOT_FOUND, "El plano aun no tiene puntos calibrados.", account_id, event_id, mesa_id=mesa_id, config=config)
    if config.origin_id not in config.nodes or table.destination_node not in config.nodes:
        return _error(MAP_INVALID_CONFIG, "La configuracion referencia un nodo inexistente.", account_id, event_id, mesa_id=mesa_id, config=config)

    path = _shortest_path(config, config.origin_id, table.destination_node)
    if path is None:
        return _error(MAP_ROUTE_NOT_FOUND, "No existe una ruta transitable hacia esta mesa.", account_id, event_id, mesa_id=mesa_id, config=config)
    total_distance = sum(
        math.hypot(
            config.nodes[current].x - config.nodes[previous].x,
            config.nodes[current].y - config.nodes[previous].y,
        )
        for previous, current in zip(path, path[1:])
    )
    return ResultadoRuta(
        ok=True,
        codigo="OK",
        mensaje="Ruta calculada.",
        account_id=account_id,
        event_id=event_id,
        mesa_id=table.mesa_id,
        mesa_texto=table.mesa_texto,
        storage_bucket=config.storage_bucket,
        storage_path=config.storage_path,
        node_ids=tuple(path),
        points=tuple((config.nodes[node_id].x, config.nodes[node_id].y) for node_id in path),
        total_distance=total_distance,
    )
