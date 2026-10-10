"""Local browser preview for a calibrated Kiosk route; it never calls Storage."""

from __future__ import annotations

import argparse
import html
import json
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_map_service import ResultadoRuta, calcular_ruta


class PreviewError(ValueError):
    """Controlled preview input error."""


@dataclass(frozen=True)
class PreviewData:
    route: ResultadoRuta
    image_width: int
    image_height: int
    pixel_points: tuple[tuple[float, float], ...]


def normalized_to_pixel(x: float, y: float, image_width: int, image_height: int) -> tuple[float, float]:
    """Convert an immutable normalized map coordinate to the local image space."""
    if image_width <= 0 or image_height <= 0:
        raise PreviewError("Las dimensiones de la imagen deben ser positivas.")
    if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        raise PreviewError("La ruta contiene coordenadas normalizadas fuera de rango.")
    return x * image_width, y * image_height


def points_to_pixels(
    points: Iterable[tuple[float, float]], image_width: int, image_height: int
) -> tuple[tuple[float, float], ...]:
    return tuple(normalized_to_pixel(x, y, image_width, image_height) for x, y in points)


def read_jpeg_dimensions(image_path: Path) -> tuple[int, int]:
    """Read JPEG dimensions without decoding or modifying the supplied image."""
    try:
        payload = image_path.read_bytes()
    except OSError as exc:
        raise PreviewError(f"No se pudo leer el plano local: {image_path}") from exc
    if len(payload) < 4 or payload[:2] != b"\xff\xd8":
        raise PreviewError("El preview requiere un JPG local valido.")

    index = 2
    sof_markers = {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}
    while index + 9 <= len(payload):
        if payload[index] != 0xFF:
            index += 1
            continue
        while index < len(payload) and payload[index] == 0xFF:
            index += 1
        if index >= len(payload):
            break
        marker = payload[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(payload):
            break
        segment_length = int.from_bytes(payload[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(payload):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(payload[index + 3 : index + 5], "big")
            width = int.from_bytes(payload[index + 5 : index + 7], "big")
            if width > 0 and height > 0:
                return width, height
        index += segment_length
    raise PreviewError("No se pudieron determinar las dimensiones del JPG local.")


def prepare_preview(account_id: int, event_id: int, mesa_id: int, image_size: tuple[int, int]) -> PreviewData:
    """Resolve using the production-independent map service, never duplicate Dijkstra."""
    route = calcular_ruta(account_id=account_id, event_id=event_id, mesa_id=mesa_id)
    if not route.ok:
        raise PreviewError(f"{route.codigo}: {route.mensaje}")
    if len(route.node_ids) != len(route.points) or len(route.points) < 2:
        raise PreviewError("La ruta calculada no contiene suficientes puntos para visualizarse.")
    width, height = image_size
    return PreviewData(
        route=route,
        image_width=width,
        image_height=height,
        pixel_points=points_to_pixels(route.points, width, height),
    )


def build_preview_document(preview: PreviewData) -> str:
    """Create a canvas document served only by the local preview server."""
    route = preview.route
    payload = json.dumps(
        {
            "points": preview.pixel_points,
            "node_ids": route.node_ids,
            "distance": route.total_distance,
        },
        ensure_ascii=False,
    )
    title = html.escape("Preview de ruta")
    return f"""<!doctype html>
<html lang=\"es\"><head><meta charset=\"utf-8\"><title>{title}</title>
<style>body{{margin:0;background:#271820;color:#fff7ec;font-family:Arial,sans-serif}}header{{padding:12px 18px;background:#5d1831}}canvas{{display:block;max-width:100%;height:auto;margin:auto}}</style>
</head><body><header><strong>{title}</strong> · Distancia normalizada: {route.total_distance:.6f}</header>
<canvas id=\"map\" aria-label=\"Preview de ruta\"></canvas><script>
const route={payload}; const image=new Image(); const canvas=document.getElementById('map'); const ctx=canvas.getContext('2d');
const ROUTE_COLOR='#E53935'; const CURVE_FACTOR=0.20;
function distance(a,b){{return Math.hypot(b[0]-a[0],b[1]-a[1])}}
function toward(from,to,distanceToTravel){{const length=distance(from,to);if(!length)return from;return [from[0]+(to[0]-from[0])*distanceToTravel/length,from[1]+(to[1]-from[1])*distanceToTravel/length]}}
function drawSmoothedRoute(points){{ctx.beginPath();ctx.moveTo(...points[0]);if(points.length===2){{ctx.lineTo(...points[1]);return}}for(let index=1;index<points.length-1;index++){{const previous=points[index-1],current=points[index],next=points[index+1];const curveDistance=Math.min(distance(previous,current),distance(current,next))*CURVE_FACTOR;const entry=toward(current,previous,curveDistance);const exit=toward(current,next,curveDistance);ctx.lineTo(...entry);ctx.quadraticCurveTo(...current,...exit)}}ctx.lineTo(...points.at(-1))}}
image.onload=()=>{{canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;ctx.drawImage(image,0,0);ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle=ROUTE_COLOR;ctx.lineWidth=Math.max(11,Math.min(13,image.naturalWidth/250));const dashUnit=ctx.lineWidth;ctx.setLineDash([dashUnit*1.5,dashUnit*1.35]);drawSmoothedRoute(route.points);ctx.stroke();ctx.setLineDash([]);const markerRadius=Math.max(14,Math.min(16,image.naturalWidth/200));function drawEndpoint(point){{ctx.fillStyle=ROUTE_COLOR;ctx.beginPath();ctx.arc(...point,markerRadius,0,2*Math.PI);ctx.fill()}}drawEndpoint(route.points[0]);drawEndpoint(route.points.at(-1))}}; image.src='/floorplan.jpg';
</script></body></html>"""


def make_handler(document: str, image_path: Path) -> type[BaseHTTPRequestHandler]:
    class PreviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if self.path == "/":
                body = document.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            elif self.path == "/floorplan.jpg":
                body = image_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
            else:
                self.send_error(404)
                return
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return PreviewHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre un preview local de una ruta Kiosk MAP-0B.")
    parser.add_argument("--account", required=True, type=int)
    parser.add_argument("--event", required=True, type=int)
    parser.add_argument("--mesa", required=True, type=int)
    parser.add_argument("--image", required=True, type=Path, help="Copia local JPG del plano autorizado.")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()

    image_path = args.image.resolve()
    image_size = read_jpeg_dimensions(image_path)
    preview = prepare_preview(args.account, args.event, args.mesa, image_size)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(build_preview_document(preview), image_path))
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"[MAP-PREVIEW] mesa={args.mesa} node_ids={','.join(preview.route.node_ids)}")
    print(f"[MAP-PREVIEW] distance={preview.route.total_distance:.6f} segments={len(preview.pixel_points) - 1}")
    print(f"[MAP-PREVIEW] local_url={address} (Ctrl+C para cerrar)")
    threading.Timer(0.1, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
