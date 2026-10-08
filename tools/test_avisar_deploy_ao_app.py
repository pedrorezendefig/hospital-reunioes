"""O aviso da subida ao app (issue #1065, ADR 0069, decisão 4).

Depois do registro, a Action pós-merge chama `POST /api/webhooks/deploy` com a
versão, a data e os PRs do lote, assinado com `TECNOLOGIA_DEPLOY_WEBHOOK_SECRET`.
Estes testes rodam o script de verdade contra um servidor HTTP local (a
assinatura é conferida do lado de lá, como o app confere) e amarram o job do
`pos-merge.yml`: depois do registro, com o segredo só nele, e sem derrubar o run.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import avisar_deploy_ao_app as aviso  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "pos-merge.yml"

SEGREDO = "segredo-falso-do-teste-1065"

# A entrada como o `montar_registro` da subida a grava (onda com dois PRs).
ENTRADA = {
    "at": "2026-10-08T10:00:00-03:00",
    "app_version": "0.169.0",
    "notes": "onda-enxuta onda-a: PR #1100 (issue #673), PR #1101 (issues #700 #701), mergeados PR a PR. "
    "Merge pela API do GitHub, um build. Registro pela Action pos-merge depois do health.",
}


def _registro(entrada: dict = ENTRADA) -> str:
    return json.dumps({"entrada": entrada, "state": {}})


@pytest.fixture
def app_local():
    """Um app de mentira que confere a assinatura como o de verdade e guarda o
    que recebeu. `status` muda a resposta."""
    recebidos: list[dict] = []
    estado = {"status": 200}

    class _Rota(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            corpo = self.rfile.read(int(self.headers["Content-Length"]))
            esperada = "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
            recebidos.append(
                {
                    "caminho": self.path,
                    "assinatura_confere": hmac.compare_digest(esperada, self.headers.get("X-Hub-Signature-256", "")),
                    "corpo": json.loads(corpo),
                }
            )
            self.send_response(estado["status"])
            self.end_headers()
            self.wfile.write(b'{"recebido": true, "marcadas": 1}')

        def log_message(self, *_a):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), _Rota)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_port}", recebidos, estado
    servidor.shutdown()


def test_o_aviso_leva_versao_data_e_os_prs_do_lote_assinados(app_local):
    """Critério de aceite: o corpo é o do webhook (versão, data, PRs com as
    issues que fecham), assinado com o segredo, na rota de deploy."""
    base, recebidos, _ = app_local

    saida = aviso.main({"REGISTRO": _registro(), "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": SEGREDO}, base=base)

    assert saida == 0
    assert recebidos == [
        {
            "caminho": "/api/webhooks/deploy",
            "assinatura_confere": True,
            "corpo": {
                "versao": "0.169.0",
                "data": "2026-10-08T10:00:00-03:00",
                "prs": [{"numero": 1100, "fecha": [673]}, {"numero": 1101, "fecha": [700, 701]}],
            },
        }
    ]


@pytest.mark.parametrize("status", (401, 500, 503))
def test_o_app_que_recusa_nao_derruba_o_run(app_local, status, capsys):
    """Critério de aceite: o app fora do ar ou recusando é aviso no log do
    run, e a saída é zero. Quem cobre é a reconciliação de hora em hora."""
    base, _, estado = app_local
    estado["status"] = status

    saida = aviso.main({"REGISTRO": _registro(), "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": SEGREDO}, base=base)

    assert saida == 0
    assert "::warning::" in capsys.readouterr().out


def test_o_app_que_nao_responde_nao_derruba_o_run(capsys):
    """Porta fechada: a conexão recusada é aviso, e não erro do run."""
    saida = aviso.main(
        {"REGISTRO": _registro(), "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": SEGREDO}, base="http://127.0.0.1:9"
    )

    assert saida == 0
    assert "::warning::" in capsys.readouterr().out


def test_sem_o_segredo_nao_chama_ninguem(app_local, capsys):
    """Até o passo humano, o segredo não existe nos secrets do repositório: o
    passo diz isso e sai em zero, sem mandar aviso sem assinatura."""
    base, recebidos, _ = app_local

    saida = aviso.main({"REGISTRO": _registro(), "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": ""}, base=base)

    assert saida == 0
    assert recebidos == []
    assert "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET" in capsys.readouterr().out


def test_o_segredo_nao_aparece_no_log(app_local, capsys):
    base, _, estado = app_local
    estado["status"] = 401

    aviso.main({"REGISTRO": _registro(), "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": SEGREDO}, base=base)

    assert SEGREDO not in capsys.readouterr().out


def test_o_endereco_do_app_vem_do_project_json():
    """O mesmo backend que o health da subida confere, e não um endereço a
    mais para manter."""
    project = json.loads((RAIZ / "docs" / "spec" / "deploy" / "project.json").read_text(encoding="utf-8"))
    backend = next(s for s in project["services"] if s["id"] == "backend")

    assert aviso.base_do_app() == backend["deploy"]["fqdn"]


# ------------------------------------------------------------ o job da Action


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_o_job_chama_o_app_depois_do_registro_e_nao_falha_o_run():
    """Critério de aceite: o job só roda quando o passo que aplica o registro
    deu certo (no run que a subida dispara), não derruba o run, e o segredo
    entra por env no passo que chama o script, nunca no `run`."""
    w = _workflow()
    gerar = w["jobs"]["gerar"]
    aplicar = next(p for p in gerar["steps"] if p.get("name") == "Aplicar o registro do deploy")
    assert gerar["outputs"]["registro"] == f"${{{{ steps.{aplicar['id']}.outcome }}}}"

    job = w["jobs"]["em-producao"]
    assert job["needs"] == "gerar"
    assert job["if"] == "${{ !cancelled() && needs.gerar.outputs.registro == 'success' }}"
    assert job["continue-on-error"] is True
    assert "permissions" not in job and "environment" not in job
    chamar = next(p for p in job["steps"] if "run" in p)
    assert chamar["run"].strip() == "python3 tools/avisar_deploy_ao_app.py"
    assert chamar["env"] == {
        "REGISTRO": "${{ inputs.registro }}",
        "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET": "${{ secrets.TECNOLOGIA_DEPLOY_WEBHOOK_SECRET }}",
    }
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False


def test_o_script_roda_quando_o_leitor_do_registro_muda():
    """O script carrega o leitor do registro do backend pelo caminho, e os
    testes de `tools/` rodam no `manual.yml`: o PR que mexe só no leitor
    também precisa acordá-los."""
    manual = yaml.safe_load((RAIZ / ".github" / "workflows" / "manual.yml").read_text(encoding="utf-8"))
    on = manual["on"] if "on" in manual else manual[True]
    for evento in ("push", "pull_request"):
        assert "hospital-reunioes/backend/app/services/registro_do_deploy.py" in on[evento]["paths"], evento
