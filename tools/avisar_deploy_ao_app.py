#!/usr/bin/env python3
"""Avisa o app de que uma versão subiu (issue #1065, ADR 0069, decisão 4).

O job `em-producao` do `pos-merge.yml` roda este script no run que a subida
dispara, depois do passo que aplica o registro. Ele lê a entrada nova do
registro (`REGISTRO`, o input do `workflow_dispatch`), monta o corpo do webhook
de deploy (versão, data e os PRs do lote com as issues que fecham), assina com
`TECNOLOGIA_DEPLOY_WEBHOOK_SECRET` no formato do GitHub (`X-Hub-Signature-256`)
e faz `POST /api/webhooks/deploy` no backend do `project.json`. O app marca Em
produção as Demandas dessas issues.

O corpo sai do MESMO leitor que a reconciliação do app usa sobre o
`history.json` (`registro_do_deploy.py`, carregado pelo caminho): duas leituras
das `notes` divergiriam, e a issue que o aviso chama de "subiu" seria outra na
passagem de hora em hora.

Saída sempre 0. O app fora do ar, recusando ou sem o segredo cadastrado não
derruba o run: a reconciliação de hora em hora lê o `history.json` da `main` e
marca o que este aviso não entregou. O segredo nunca é impresso.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LEITOR_DO_REGISTRO = RAIZ / "hospital-reunioes" / "backend" / "app" / "services" / "registro_do_deploy.py"
PROJECT = RAIZ / "docs" / "spec" / "deploy" / "project.json"
ROTA = "/api/webhooks/deploy"
SEGREDO = "TECNOLOGIA_DEPLOY_WEBHOOK_SECRET"

# O app responde em segundos; o teto existe para um backend pendurado não
# segurar o runner.
TIMEOUT_S = 30

AVISO_DA_RECONCILIACAO = "a reconciliação de hora em hora marca Em produção pelo history.json da main."


def _leitor_do_registro():
    spec = importlib.util.spec_from_file_location("registro_do_deploy", LEITOR_DO_REGISTRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def base_do_app() -> str:
    """O endereço do backend, o mesmo que o health da subida confere."""
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    backend = next(s for s in project["services"] if s.get("id") == "backend")
    return backend["deploy"]["fqdn"].rstrip("/")


def main(env=os.environ, base: str | None = None) -> int:
    segredo = env.get(SEGREDO, "")
    if not segredo:
        print(f"::notice::{SEGREDO} não está nos secrets do repositório: o app não foi avisado, e {AVISO_DA_RECONCILIACAO}")
        return 0
    try:
        entrada = json.loads(env["REGISTRO"])["entrada"]
        corpo_do_aviso = _leitor_do_registro().aviso_da_entrada(entrada)
        if corpo_do_aviso is None:
            print(f"::warning::O registro não traz versão: o app não foi avisado, e {AVISO_DA_RECONCILIACAO}")
            return 0
        corpo = json.dumps(corpo_do_aviso).encode("utf-8")
        assinatura = "sha256=" + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
        pedido = urllib.request.Request(
            (base or base_do_app()) + ROTA,
            data=corpo,
            method="POST",
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": assinatura},
        )
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as resposta:
            print(f"O app recebeu o aviso da v{corpo_do_aviso['versao']}: {resposta.read(500).decode('utf-8', 'replace')}")
    except urllib.error.HTTPError as exc:
        print(f"::warning::O app respondeu {exc.code} ao aviso da subida; {AVISO_DA_RECONCILIACAO}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::O app não recebeu o aviso da subida ({type(exc).__name__}); {AVISO_DA_RECONCILIACAO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
