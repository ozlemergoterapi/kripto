import json
import secrets
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "static"


def make_server(engine, host="127.0.0.1", port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/state":
                self.reply(200, engine.view())
            elif self.path == "/api/session":
                # Browsers cannot read this cross-origin; no permissive CORS headers.
                self.reply(200, {"token": token})
            elif self.path == "/health":
                self.reply(200, {"service": "ok", "mode": "paper", "strategy_validated": False})
            elif self.path.startswith("/api/entry-chart/"):
                id = self.path[len("/api/entry-chart/"):]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", id):
                    self.reply(400, {"error":"Geçersiz grafik kimliği"})
                    return
                chart = engine.store.entry_chart(id)
                self.reply(200 if chart else 404, chart or {"error":"Bu pozisyonun giriş anı grafiği kaydedilmemiş. Geçmişe dönük grafik üretilmez."})
            elif self.path in ("/", "/app.js", "/charts.js", "/style.css"):
                name = "index.html" if self.path == "/" else self.path[1:]
                mime = {"index.html": "text/html", "app.js": "text/javascript", "charts.js":"text/javascript", "style.css": "text/css"}[name]
                self.reply(200, (STATIC / name).read_bytes(), mime + "; charset=utf-8")
            else:
                self.reply(404, {"error": "Bulunamadı"})

        def do_POST(self):
            if self.headers.get("X-LSA-Token") != token:
                self.reply(403, {"error": "Geçersiz oturum"})
                return
            if self.path != "/api/control":
                self.reply(404, {"error": "Bulunamadı"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError("size")
                body = json.loads(self.rfile.read(length))
                ok, message = engine.control(body["action"])
                self.reply(200 if ok else 409, {"ok": ok, "message": message})
            except (ValueError, KeyError, TypeError):
                self.reply(400, {"error": "Geçersiz komut"})

    return ThreadingHTTPServer((host, port), Handler)
