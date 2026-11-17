#!/usr/bin/env python3
"""Локальный сервер сайта — повторяет то, что на VPS делает nginx:
  - чистые URL: /katalog -> site/katalog.html, /katalog.html -> 301 /katalog
  - /api/*, /upload*, /healthz, /katalog и /katalog/{slug} -> бэкенд
Запуск: python3 serve_local.py  ->  http://localhost:8080
Редиректы бэкенда (вход -> экран кода -> ЛК) и его cookie пробрасываются как есть."""
import http.client
import http.server
import socketserver
from pathlib import Path

SITE = Path(__file__).parent / "site"
BACKEND = ("127.0.0.1", 8100)
PORT = 8080
HOP = {"transfer-encoding", "connection", "keep-alive", "proxy-connection", "upgrade", "content-length"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        self._proxied = False
        super().__init__(*a, directory=str(SITE), **kw)

    # ── прокси на бэкенд ──
    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers["Host"] = self.headers.get("Host", f"localhost:{PORT}")
        headers["X-Forwarded-Proto"] = "http"
        if body is not None:
            headers["Content-Length"] = str(len(body))
        try:
            conn = http.client.HTTPConnection(*BACKEND, timeout=60)
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
        except OSError:
            self.send_error(502, "Backend is not running (start-backend.bat)")
            return
        self._proxied = True
        self.send_response(resp.status, resp.reason)
        for k, v in resp.getheaders():          # Set-Cookie может быть несколько — все уйдут
            if k.lower() not in HOP | {"date", "server"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        conn.close()

    # ── статика с чистыми URL ──
    def do_GET(self):
        if self.path.startswith(("/api/", "/upload", "/healthz", "/katalog/")) or self.path.split("?")[0] in ("/katalog", "/prices.json"):
            return self._proxy()
        path = self.path.split("?")[0].split("#")[0]
        if path.endswith(".html"):
            clean = "/" if path == "/index.html" else path[:-5]
            self.send_response(301)
            self.send_header("Location", clean)
            self.end_headers()
            return
        if path != "/" and "." not in path.rsplit("/", 1)[-1] and (SITE / (path.strip("/") + ".html")).exists():
            query = ("?" + self.path.split("?", 1)[1]) if "?" in self.path else ""
            self.path = "/" + path.strip("/") + ".html" + query
        return super().do_GET()

    def do_POST(self):
        return self._proxy()

    def end_headers(self):
        if not self._proxied:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/assets/" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print(f"Сайт: http://localhost:{PORT}   Ctrl+C — остановить")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
