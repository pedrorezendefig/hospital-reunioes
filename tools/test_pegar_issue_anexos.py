"""A ponte com o desenvolvimento: o script dos anexos (issue #1063, ADR 0069, decisão 2).

Quem pega a issue baixa os prints da Demanda por uma boca só,
`pegar-issue/scripts/anexos.py <issue>`: lê a issue pelo `gh`, acha o id da
Demanda no marcador do corpo, chama a rota de automação com a chave do
`tokens/.env` e grava os arquivos em `local/anexos/<issue>/`.

Estes testes rodam o script como o agente roda, num repositório git de mentira,
com um `gh` falso no PATH e um app falso num servidor HTTP local. Nem o GitHub
nem o app de verdade entram no teste.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "pegar-issue" / "scripts" / "anexos.py"

CHAVE = "chave-falsa-do-teste-1063"
DEMANDA = "3f2a9c1e-7b44-4d0a-9a51-0c6f7e8d1a22"
ISSUE = "1234"
PNG = b"\x89PNG\r\n\x1a\nprint-um"
JPG = b"\xff\xd8\xffprint-dois"

CORPO_COM_DEMANDA = (
    "## O que construir\n\nO botão some na tela de Reuniões.\n\n"
    f"Anexos: 2 imagens na Demanda\n\n<!-- demanda-vitta id=\"{DEMANDA}\" -->"
)


@pytest.fixture
def app_falso():
    """O app de mentira: a rota de automação e as URLs assinadas das imagens.

    `estado["anexos"]` é o que a rota devolve; `estado["status"]` muda a resposta
    dela; `pedidos` guarda cada chamada, com a chave que chegou."""
    pedidos: list[dict] = []
    estado: dict = {"status": 200, "anexos": None}

    class _Rota(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            pedidos.append({"caminho": self.path, "chave": self.headers.get("X-API-Key")})
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path == f"/api/automacao/tecnologia/demandas/{DEMANDA}/anexos":
                if estado["status"] != 200:
                    self.send_response(estado["status"])
                    self.end_headers()
                    self.wfile.write(b'{"detail": "recusado"}')
                    return
                anexos = estado["anexos"]
                if anexos is None:
                    anexos = [
                        {"nome": "tela do erro.png", "tipo": "image/png", "url": f"{base}/storage/um?token=x"},
                        {"nome": "depois.jpg", "tipo": "image/jpeg", "url": f"{base}/storage/dois?token=y"},
                    ]
                corpo = json.dumps({"anexos": anexos}).encode()
            elif self.path.startswith("/storage/um"):
                corpo = PNG
            elif self.path.startswith("/storage/dois"):
                corpo = JPG
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *_a):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), _Rota)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}/api", pedidos, estado
    servidor.shutdown()


@pytest.fixture
def repo(tmp_path):
    """Um clone de mentira: o `local/` e o `tokens/.env` moram na raiz dele."""
    raiz = tmp_path.resolve() / "clone"
    raiz.mkdir()
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    (raiz / "tokens").mkdir()
    (raiz / "tokens" / ".env").write_text(
        f"COOLIFY_BASE_URL=https://coolify.exemplo\nTECNOLOGIA_AUTOMACAO_API_KEY='{CHAVE}'\n", encoding="utf-8"
    )
    return raiz


def rodar(repo: Path, base: str, corpo: str = CORPO_COM_DEMANDA) -> subprocess.CompletedProcess:
    falso = repo.parent / "bin"
    falso.mkdir(exist_ok=True)
    (repo.parent / "issue.json").write_text(json.dumps({"body": corpo}), encoding="utf-8")
    gh = falso / "gh"
    gh.write_text('#!/bin/sh\ncat "$GH_ISSUE"\n', encoding="utf-8")
    gh.chmod(0o755)
    ambiente = {k: v for k, v in os.environ.items() if k != "TECNOLOGIA_AUTOMACAO_API_KEY"}
    ambiente.update(PATH=f"{falso}:{os.environ['PATH']}", GH_ISSUE=str(repo.parent / "issue.json"), HOSPITAL_API_URL=base)
    return subprocess.run(
        [sys.executable, str(SCRIPT), ISSUE], capture_output=True, text=True, env=ambiente, cwd=repo
    )


def test_grava_os_anexos_em_local_anexos_da_issue_e_imprime_os_caminhos(repo, app_falso):
    base, pedidos, _ = app_falso

    feito = rodar(repo, base)

    assert feito.returncode == 0, feito.stderr
    pasta = repo / "local" / "anexos" / ISSUE
    caminhos = feito.stdout.splitlines()
    assert caminhos == [str(pasta / "01-tela do erro.png"), str(pasta / "02-depois.jpg")]
    assert (pasta / "01-tela do erro.png").read_bytes() == PNG
    assert (pasta / "02-depois.jpg").read_bytes() == JPG
    # A chave veio do tokens/.env, no header, para a rota da Demanda do marcador.
    rota = [p for p in pedidos if "/automacao/" in p["caminho"]]
    assert rota == [{"caminho": f"/api/automacao/tecnologia/demandas/{DEMANDA}/anexos", "chave": CHAVE}]


def test_issue_sem_demanda_sai_zero_com_sem_anexos_e_nao_chama_o_app(repo, app_falso):
    base, pedidos, _ = app_falso

    feito = rodar(repo, base, corpo="## O que construir\n\nIssue aberta direto no GitHub.")

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout.strip() == "sem anexos"
    assert pedidos == []
    assert not (repo / "local").exists()


def test_demanda_sem_anexos_sai_zero_com_sem_anexos(repo, app_falso):
    base, _, estado = app_falso
    estado["anexos"] = []

    feito = rodar(repo, base)

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout.strip() == "sem anexos"
    assert not (repo / "local").exists()


def test_ponte_desligada_no_servidor_avisa_a_chave_que_falta_no_coolify(repo, app_falso):
    base, _, estado = app_falso
    estado["status"] = 503

    feito = rodar(repo, base)

    assert feito.returncode == 1
    assert "TECNOLOGIA_AUTOMACAO_API_KEY" in feito.stderr and "Coolify" in feito.stderr
    assert not (repo / "local").exists()


def test_sem_a_chave_no_tokens_env_avisa_e_nao_chama_o_app(repo, app_falso):
    base, pedidos, _ = app_falso
    (repo / "tokens" / ".env").write_text("TECNOLOGIA_AUTOMACAO_API_KEY=\n", encoding="utf-8")

    feito = rodar(repo, base)

    assert feito.returncode == 1
    assert "TECNOLOGIA_AUTOMACAO_API_KEY" in feito.stderr and "tokens/.env" in feito.stderr
    assert pedidos == []


def test_nome_do_anexo_nao_escapa_da_pasta_da_issue(repo, app_falso):
    """O nome vem de quem anexou: `../../x.png` não pode gravar fora de
    `local/anexos/<issue>/`."""
    base, _, estado = app_falso
    estado["anexos"] = [{"nome": "../../fora.png", "tipo": "image/png", "url": base.replace("/api", "/storage/um")}]

    feito = rodar(repo, base)

    assert feito.returncode == 0, feito.stderr
    assert feito.stdout.splitlines() == [str(repo / "local" / "anexos" / ISSUE / "01-fora.png")]
    assert not (repo / "local" / "fora.png").exists()


def test_o_endereco_padrao_e_o_backend_do_project_json():
    """Sem `HOSPITAL_API_URL`, o script fala com o backend que a subida confere,
    e não com um endereço escrito à mão no script."""
    project = json.loads((RAIZ / "docs" / "spec" / "deploy" / "project.json").read_text(encoding="utf-8"))
    fqdn = next(s for s in project["services"] if s["id"] == "backend")["deploy"]["fqdn"]
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import anexos
    finally:
        sys.path.remove(str(SCRIPT.parent))

    assert anexos.base_da_api({}) == fqdn.rstrip("/") + "/api"
