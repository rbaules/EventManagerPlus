"""Local, non-destructive point calibrator for a downloaded event floor plan.

The source image stays outside Git. This tool only reads a local JPG and lets
the browser export a points JSON file; it never writes the production map
configuration automatically.
"""

from __future__ import annotations

import argparse
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PAGE = """<!doctype html>
<html lang=\"es\"><meta charset=\"utf-8\"><title>EVKOR · Calibrar plano</title>
<style>body{font-family:system-ui;margin:20px;color:#4b241c}canvas{max-width:95vw;border:1px solid #d9c7bc;cursor:crosshair}input,button{font:inherit;margin:4px}#points{white-space:pre-wrap}</style>
<h1>Calibración de plano Kiosk</h1>
<p>Etiqueta el punto y haz clic sobre el plano. Coordenadas: (0,0) arriba-izquierda; (1,1) abajo-derecha.</p>
<label>Punto <input id=\"label\" value=\"KIOSK\"></label><button id=\"remove\">Eliminar último</button><button id=\"export\">Exportar JSON</button>
<p><input id=\"picker\" type=\"file\" accept=\"image/jpeg,image/png\"> Úsalo sólo si no se pasó <code>--image</code>.</p>
<canvas id=\"canvas\"></canvas><pre id=\"points\"></pre>
<script>
const canvas=document.querySelector('#canvas'), ctx=canvas.getContext('2d'), image=new Image(), points=[];
function redraw(){if(!canvas.width)return;ctx.drawImage(image,0,0);ctx.fillStyle='#971b1f';ctx.font='18px sans-serif';for(const p of points){ctx.beginPath();ctx.arc(p.pixel_x,p.pixel_y,5,0,Math.PI*2);ctx.fill();ctx.fillText(p.id,p.pixel_x+8,p.pixel_y-8)}document.querySelector('#points').textContent=JSON.stringify({points},null,2)}
function load(src){image.onload=()=>{canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;redraw()};image.src=src}
canvas.addEventListener('click',event=>{const id=document.querySelector('#label').value.trim();if(!id)return alert('Indica una etiqueta');if(points.some(p=>p.id===id))return alert('La etiqueta ya existe');const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)*canvas.width/rect.width,y=(event.clientY-rect.top)*canvas.height/rect.height;points.push({id,pixel_x:Math.round(x),pixel_y:Math.round(y),normalized_x:x/canvas.width,normalized_y:y/canvas.height});redraw()});
document.querySelector('#remove').onclick=()=>{points.pop();redraw()};document.querySelector('#export').onclick=()=>{const blob=new Blob([JSON.stringify({points},null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='kiosk_map_points.json';a.click();URL.revokeObjectURL(a.href)};
document.querySelector('#picker').onchange=e=>{const file=e.target.files[0];if(file)load(URL.createObjectURL(file))};
if(location.pathname==='/floorplan.jpg'){} else fetch('/image-ready').then(r=>r.json()).then(x=>{if(x.ready)load('/floorplan.jpg')});
</script></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibra puntos normalizados de un plano local.")
    parser.add_argument("--image", type=Path, required=True, help="Copia local de floorplan.jpg; no se agrega al repositorio.")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    image = args.image.resolve()
    if not image.is_file():
        parser.error(f"No existe la imagen: {image}")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route == "/":
                body = PAGE.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            elif route == "/image-ready":
                body = b'{"ready":true}'
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            elif route == "/floorplan.jpg":
                body = image.read_bytes()
                self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(image.name)[0] or "image/jpeg"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            else:
                self.send_error(404)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Abre http://127.0.0.1:{args.port}/ en un navegador local. Ctrl+C para detener.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
