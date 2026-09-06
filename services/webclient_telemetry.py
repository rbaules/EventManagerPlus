from __future__ import annotations

import json
import logging
import math
import re
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request


LOGGER = logging.getLogger("eventplus.webclient")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _formatter.converter = time.gmtime
    _handler.setFormatter(_formatter)
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False

MAX_TELEMETRY_BODY_BYTES = 768
TELEMETRY_EVENTS = frozenset(
    {
        "OFFLINE",
        "ONLINE",
        "HEALTH_OK",
        "HEALTH_FAILED",
        "RECOVERY_START",
        "RESCUE_RELOAD",
        "FOREGROUND",
    }
)
_ALLOWED_FIELDS = frozenset(
    {"event", "client_recovery_id", "timestamp", "path", "elapsed_seconds"}
)
_RECOVERY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_SAFE_PATH_PATTERN = re.compile(r"^/app(?:/[A-Za-z0-9_-]+)*$|^/app/?$")


async def read_limited_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_TELEMETRY_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Payload demasiado grande.")
        except ValueError as ex:
            raise HTTPException(status_code=400, detail="Content-Length invalido.") from ex

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_TELEMETRY_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Payload demasiado grande.")
    return bytes(body)


def validate_webclient_telemetry(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - _ALLOWED_FIELDS:
        raise HTTPException(status_code=422, detail="Payload diagnostico invalido.")

    event = payload.get("event")
    recovery_id = payload.get("client_recovery_id")
    timestamp = payload.get("timestamp")
    path = payload.get("path")
    elapsed = payload.get("elapsed_seconds")

    if event not in TELEMETRY_EVENTS:
        raise HTTPException(status_code=422, detail="Evento diagnostico no permitido.")
    if not isinstance(recovery_id, str) or not _RECOVERY_ID_PATTERN.fullmatch(
        recovery_id
    ):
        raise HTTPException(status_code=422, detail="Identificador diagnostico invalido.")
    if not isinstance(timestamp, str) or len(timestamp) > 40:
        raise HTTPException(status_code=422, detail="Timestamp diagnostico invalido.")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as ex:
        raise HTTPException(status_code=422, detail="Timestamp diagnostico invalido.") from ex
    if parsed_timestamp.tzinfo is None:
        raise HTTPException(status_code=422, detail="Timestamp diagnostico sin zona horaria.")
    if not isinstance(path, str) or not _SAFE_PATH_PATTERN.fullmatch(path):
        raise HTTPException(status_code=422, detail="Ruta diagnostica invalida.")
    if elapsed is not None and (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(float(elapsed))
        or not 0 <= float(elapsed) <= 86_400
    ):
        raise HTTPException(status_code=422, detail="Duracion diagnostica invalida.")

    return {
        "event": event,
        "client_recovery_id": recovery_id,
        "timestamp": timestamp,
        "path": path,
        "elapsed_seconds": round(float(elapsed), 3) if elapsed is not None else None,
    }


async def parse_webclient_telemetry(request: Request) -> dict[str, Any]:
    body = await read_limited_body(request)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise HTTPException(status_code=400, detail="JSON diagnostico invalido.") from ex
    return validate_webclient_telemetry(payload)


def log_webclient_telemetry(payload: dict[str, Any]) -> None:
    fields = [
        f"client_recovery_id={payload['client_recovery_id']}",
        f"timestamp={payload['timestamp']}",
        f"path={payload['path']}",
    ]
    if payload["elapsed_seconds"] is not None:
        fields.append(f"elapsed_seconds={payload['elapsed_seconds']:.3f}")
    LOGGER.info("[WEBCLIENT][%s] %s", payload["event"], " ".join(fields))
