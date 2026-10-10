from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_map_service import (
    MAP_CONFIG_NOT_FOUND,
    MAP_INVALID_CONFIG,
    MAP_ROUTE_NOT_FOUND,
    MAP_TABLE_NOT_FOUND,
    calcular_ruta,
    load_map_config,
)


def calibrated_config() -> dict[str, Any]:
    return {
        "version": 1,
        "account_id": 2,
        "event_id": 10,
        "map": {"storage_bucket": "event-maps", "storage_path": "2/10/floorplan.jpg"},
        "origin": {"id": "KIOSK", "kind": "KIOSK", "x": 0.1, "y": 0.1},
        "tables": {
            "1": {"label": "Amor", "destination_node": "MESA_1"},
            "2": {"label": "Compromiso", "destination_node": "MESA_2"},
            "3": {"label": "Comprensión", "destination_node": "MESA_3"},
            "4": {"label": "Unidad", "destination_node": "MESA_4"},
        },
        "nodes": [
            {"id": "WAYPOINT_1", "kind": "WAYPOINT", "x": 0.2, "y": 0.1},
            {"id": "MESA_1", "kind": "MESA", "x": 0.3, "y": 0.1},
            {"id": "MESA_2", "kind": "MESA", "x": 0.4, "y": 0.2},
            {"id": "WAYPOINT_3", "kind": "WAYPOINT", "x": 0.2, "y": 0.3},
            {"id": "MESA_3", "kind": "MESA", "x": 0.3, "y": 0.3},
            {"id": "MESA_4", "kind": "MESA", "x": 0.2, "y": 0.4},
        ],
        "edges": [
            {"from": "KIOSK", "to": "WAYPOINT_1", "weight": 1.0, "bidirectional": True},
            {"from": "WAYPOINT_1", "to": "MESA_1", "weight": 1.0, "bidirectional": True},
            {"from": "KIOSK", "to": "MESA_2", "weight": 1.0, "bidirectional": True},
            {"from": "KIOSK", "to": "MESA_3", "weight": 9.0, "bidirectional": True},
            {"from": "KIOSK", "to": "WAYPOINT_3", "weight": 1.0, "bidirectional": True},
            {"from": "WAYPOINT_3", "to": "MESA_3", "weight": 1.0, "bidirectional": True},
            {"from": "KIOSK", "to": "MESA_4", "weight": 1.0, "bidirectional": True},
        ],
    }


def write_config(directory: Path, payload: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2_10.json").write_text(json.dumps(payload), encoding="utf-8")


def test_load_and_all_real_tables(directory: Path) -> None:
    write_config(directory, calibrated_config())
    config = load_map_config(2, 10, config_dir=directory)
    assert config.storage_bucket == "event-maps" and config.storage_path == "2/10/floorplan.jpg"
    assert {table.mesa_texto for table in config.tables.values()} == {"Amor", "Compromiso", "Comprensión", "Unidad"}
    for mesa_id, name in ((1, "Amor"), (2, "Compromiso"), (3, "Comprensión"), (4, "Unidad")):
        result = calcular_ruta(account_id=2, event_id=10, mesa_id=mesa_id, config_dir=directory)
        assert result.ok and result.mesa_texto == name
        assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in result.points)
    route_three = calcular_ruta(account_id=2, event_id=10, mesa_id=3, config_dir=directory)
    assert route_three.points == ((0.1, 0.1), (0.2, 0.3), (0.3, 0.3))


def test_controlled_errors(directory: Path) -> None:
    assert calcular_ruta(account_id=9, event_id=10, mesa_id=1, config_dir=directory).codigo == MAP_CONFIG_NOT_FOUND
    payload = calibrated_config(); write_config(directory, payload)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=99, config_dir=directory).codigo == MAP_TABLE_NOT_FOUND
    payload = calibrated_config(); payload["nodes"][0]["x"] = 1.1; write_config(directory, payload)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=1, config_dir=directory).codigo == MAP_INVALID_CONFIG
    payload = calibrated_config(); payload["nodes"] = [node for node in payload["nodes"] if node["id"] != "MESA_1"]; payload["edges"] = [edge for edge in payload["edges"] if edge["to"] != "MESA_1"]; write_config(directory, payload)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=1, config_dir=directory).codigo == MAP_INVALID_CONFIG
    payload = calibrated_config(); payload["edges"][0]["weight"] = 0; write_config(directory, payload)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=1, config_dir=directory).codigo == MAP_INVALID_CONFIG
    payload = calibrated_config(); payload["edges"] = [edge for edge in payload["edges"] if edge["to"] != "MESA_4"]; write_config(directory, payload)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=4, config_dir=directory).codigo == MAP_ROUTE_NOT_FOUND


def test_real_calibrated_config() -> None:
    config = load_map_config(2, 10)
    assert not config.calibration_pending
    assert len(config.nodes) == 15
    assert len(config.edges) == 14
    assert all(0.0 <= node.x <= 1.0 and 0.0 <= node.y <= 1.0 for node in config.nodes.values())
    assert all(edge.weight > 0.0 for edge in config.edges)

    expected_routes = {
        1: ("KIOSK", "ENTRADA_SALON", "CENTRAL_INFERIOR", "IZQUIERDA_INFERIOR", "IZQUIERDA_CENTRO_1", "MESA_1"),
        2: ("KIOSK", "ENTRADA_SALON", "CENTRAL_INFERIOR", "DERECHA_INFERIOR", "DERECHA_CENTRO_1", "MESA_2"),
        3: ("KIOSK", "ENTRADA_SALON", "CENTRAL_INFERIOR", "DERECHA_INFERIOR", "MESA_3"),
        4: ("KIOSK", "ENTRADA_SALON", "CENTRAL_INFERIOR", "IZQUIERDA_INFERIOR", "MESA_4"),
    }
    for mesa_id, expected_node_ids in expected_routes.items():
        result = calcular_ruta(account_id=2, event_id=10, mesa_id=mesa_id)
        assert result.ok
        assert result.node_ids == expected_node_ids
        assert result.points[0] == (config.nodes["KIOSK"].x, config.nodes["KIOSK"].y)
        assert result.node_ids[-1] == f"MESA_{mesa_id}"
        assert "ENTRADA_SALON" in result.node_ids
        assert result.total_distance > 0.0

    connected = {config.origin_id}
    while True:
        next_connected = set(connected)
        for edge in config.edges:
            if edge.source in connected:
                next_connected.add(edge.target)
            if edge.bidirectional and edge.target in connected:
                next_connected.add(edge.source)
        if next_connected == connected:
            break
        connected = next_connected
    assert connected == set(config.nodes)
    assert calcular_ruta(account_id=2, event_id=10, mesa_id=99).codigo == MAP_TABLE_NOT_FOUND


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        test_load_and_all_real_tables(directory)
        test_controlled_errors(directory)
    test_real_calibrated_config()
    print("Kiosk map service tests passed.")


if __name__ == "__main__":
    main()
