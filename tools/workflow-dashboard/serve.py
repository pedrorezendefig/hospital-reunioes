#!/usr/bin/env python3
"""Dashboard local do workflow — zero dependências (stdlib).

  python3 tools/workflow-dashboard/serve.py [--port 8765] [--no-open]

Somente leitura: consulta `gh`, lê deploys/releases da origin/main (git
fetch + show) e o resto de docs/spec/*, CONTEXT.md, docs/adr/ do clone.
Nunca escreve na working tree. Bind apenas em 127.0.0.1.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import collect as collector  # noqa: E402
import repositorio  # noqa: E402

STATIC = HERE / "static"
ROOT = HERE.parents[1]
TTL_SECONDS = 60

# último diagnóstico da máquina (aba Repositório): só roda no POST /api/diagnostico.
# Lock próprio: o script leva dezenas de segundos e não pode segurar o /api/data.
_diag: dict = {"resultado": None}
_diag_lock = threading.Lock()
# O POST exige este header: força preflight CORS, e o navegador barra um site
# qualquer de disparar o diagnóstico às cegas contra o painel em localhost.
HEADER_PAINEL = ("X-Requested-With", "workflow-dashboard")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
}

_cache: dict = {"ts": 0.0, "data": None}
_lock = threading.Lock()


def get_data(fresh: bool) -> dict:
    with _lock:
        if not fresh and _cache["data"] is not None and time.time() - _cache["ts"] < TTL_SECONDS:
            return _cache["data"]
        data = collector.collect(ROOT)
        _cache.update(ts=time.time(), data=data)
        return data


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkflowDashboard/1.0"

    def log_message(self, fmt, *args):  # silencia o log por request
        pass

    def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == "/api/data":
                fresh = "fresh" in parse_qs(url.query)
                self._send(200, get_data(fresh))
                return
            m = re.match(r"^/api/issue/(\d+)$", path)
            if m:
                self._send(200, collector.issue_detail(ROOT, int(m.group(1))))
                return
            if path == "/api/pasta":  # lista de arquivos de uma pasta, sob demanda (ao clicar)
                rel = (parse_qs(url.query).get("path") or [""])[0]
                r = repositorio.listar_pasta(ROOT, rel)
                self._send(200, r) if r else self._send(404, {"error": "não encontrado"})
                return
            if path == "/api/arquivo":
                rel = (parse_qs(url.query).get("path") or [""])[0]
                r = repositorio.ler_arquivo(ROOT, rel)
                self._send(200, r) if r else self._send(404, {"error": "não encontrado"})
                return
            if path == "/api/diagnostico":  # GET = último resultado, sem rodar
                self._send(200, _diag["resultado"] or {"itens": [], "faltas": 0, "quando": None})
                return
            if path == "/":
                path = "/index.html"
            static_root = STATIC.resolve()
            f = (static_root / path.lstrip("/")).resolve()
            try:  # exige que o alvo esteja DENTRO de static/ (anti path-traversal)
                f.relative_to(static_root)
            except ValueError:
                self._send(404, {"error": "não encontrado"})
                return
            if not f.is_file():
                self._send(404, {"error": "não encontrado"})
                return
            self._send(200, f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._send(500, {"error": str(e)})
            except Exception:
                pass

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/diagnostico":  # roda o diagnostico.sh (só lê a máquina) e guarda o resultado
                if self.headers.get(HEADER_PAINEL[0]) != HEADER_PAINEL[1]:
                    self._send(403, {"error": "só o próprio painel dispara o diagnóstico"})
                    return
                with _diag_lock:
                    _diag["resultado"] = repositorio.rodar_diagnostico(ROOT)
                self._send(200, _diag["resultado"])
                return
            self._send(404, {"error": "não encontrado"})
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._send(500, {"error": str(e)})
            except Exception:
                pass


def main():
    args = sys.argv[1:]
    port = 8765
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    server = None
    for candidate in range(port, port + 11):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        print(f"✗ nenhuma porta livre entre {port} e {port + 10}", file=sys.stderr)
        sys.exit(1)

    url = f"http://localhost:{port}"
    print(f"✓ Dashboard do workflow em {url}  (Ctrl+C para parar)")
    print("  primeira carga consulta o gh — pode levar alguns segundos")
    def _open():
        try:
            webbrowser.open(url)
        except Exception:
            pass  # headless/WSL sem browser: segue rodando

    if "--no-open" not in args:
        threading.Timer(0.6, _open).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✓ encerrado")


if __name__ == "__main__":
    main()
