#!/usr/bin/env python3
"""Baixa os anexos da Demanda de uma issue (issue #1063, ADR 0069, decisão 2).

O print que o diretor anexa à Demanda vive só no app e nunca vai para o GitHub
(o repositório é público). Quem desenvolve busca por aqui, a boca única: o
`/pegar-issue`, o `hr-implementador` e o `hr-corretor` chamam este script quando
o corpo da issue diz "Anexos".

Uso:
  python3 .claude/skills/pegar-issue/scripts/anexos.py <issue>

Lê a issue pelo `gh`, acha o id da Demanda no marcador oculto do corpo
(`<!-- demanda-vitta id="..." -->`), chama a rota de automação do app com a
chave `TECNOLOGIA_AUTOMACAO_API_KEY` (do ambiente ou do `tokens/.env` do clone
principal) e grava as imagens em `local/anexos/<issue>/` na raiz do clone em que
roda (fora do git). Imprime um caminho por linha; o agente lê cada um como
arquivo. O `/ship` apaga a pasta ao abrir o PR.

Saída 0 com os caminhos, ou com "sem anexos" quando a issue não tem Demanda ou a
Demanda não tem imagem guardada. Saída 1 com o motivo no stderr quando não deu
para baixar (chave ausente, ponte desligada no servidor, app fora do ar): quem
chama segue sem as imagens e cita o motivo no relatório. A chave nunca é
impressa.

`HOSPITAL_API_URL` troca o endereço da API (testes e stack local); sem ela, é o
backend do `docs/spec/deploy/project.json`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ_DO_SCRIPT = Path(__file__).resolve().parents[4]
PROJECT = RAIZ_DO_SCRIPT / "docs" / "spec" / "deploy" / "project.json"
CHAVE = "TECNOLOGIA_AUTOMACAO_API_KEY"
MARCADOR = re.compile(r"<!--\s*demanda-vitta id=\"([^\"]+)\"\s*-->")
TIMEOUT_S = 30


class Falha(Exception):
    """O motivo, numa frase, de não ter baixado."""


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def base_da_api(env) -> str:
    if env.get("HOSPITAL_API_URL"):
        return env["HOSPITAL_API_URL"].rstrip("/")
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    backend = next(s for s in project["services"] if s.get("id") == "backend")
    return backend["deploy"]["fqdn"].rstrip("/") + "/api"


def chave(env) -> str:
    """A chave do ambiente ou, sem ela, do `tokens/.env` do clone principal.

    O worktree não tem `tokens/` (fica fora do git): o arquivo mora na árvore
    principal, a dona do `.git` que o worktree compartilha."""
    if env.get(CHAVE):
        return env[CHAVE]
    principal = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    arquivo = principal / "tokens" / ".env"
    if arquivo.is_file():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            nome, _, valor = linha.partition("=")
            if nome.strip() == CHAVE:
                return valor.strip().strip("'\"")
    return ""


def demanda_da_issue(numero: str) -> str | None:
    corpo = json.loads(subprocess.run(
        ["gh", "issue", "view", numero, "--json", "body"], capture_output=True, text=True, check=True
    ).stdout).get("body") or ""
    achado = MARCADOR.search(corpo)
    return achado.group(1) if achado else None


def listar(base: str, demanda: str, chave_api: str) -> list[dict]:
    pedido = urllib.request.Request(
        f"{base}/automacao/tecnologia/demandas/{demanda}/anexos", headers={"X-API-Key": chave_api}
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as resposta:
            return json.load(resposta)["anexos"]
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            raise Falha(f"a ponte está desligada no servidor: falta criar {CHAVE} na tela do Coolify") from exc
        if exc.code == 401:
            raise Falha(f"o app recusou a chave: confira {CHAVE} no tokens/.env (o mesmo valor do Coolify)") from exc
        raise Falha(f"o app respondeu {exc.code} à lista de anexos") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise Falha(f"o app não respondeu ({type(exc).__name__})") from exc


def nome_seguro(posicao: int, nome: str) -> str:
    """O nome vem de quem anexou: só a parte final, sem caminho, numerado na
    ordem da Demanda para dois prints de mesmo nome não se sobreporem."""
    final = Path(nome.replace("\\", "/")).name.strip() or "imagem"
    return f"{posicao:02d}-{final}"


def main(argv: list[str], env=os.environ) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print("uso: anexos.py <issue>", file=sys.stderr)
        return 2
    numero = argv[0]
    demanda = demanda_da_issue(numero)
    if not demanda:
        print("sem anexos")
        return 0
    chave_api = chave(env)
    if not chave_api:
        print(
            f"Anexos não baixados: falta {CHAVE} no tokens/.env (peça ao Pedro; o mesmo valor do Coolify).",
            file=sys.stderr,
        )
        return 1
    try:
        anexos = listar(base_da_api(env), demanda, chave_api)
        if not anexos:
            print("sem anexos")
            return 0
        pasta = Path(git("rev-parse", "--show-toplevel")) / "local" / "anexos" / numero
        pasta.mkdir(parents=True, exist_ok=True)
        faltaram = 0
        for posicao, anexo in enumerate(anexos, start=1):
            destino = pasta / nome_seguro(posicao, anexo.get("nome") or "")
            try:
                if not anexo.get("url"):
                    raise OSError("sem URL assinada")
                with urllib.request.urlopen(anexo["url"], timeout=TIMEOUT_S) as resposta:
                    destino.write_bytes(resposta.read())
            except (urllib.error.URLError, OSError) as exc:
                print(f"Anexo {posicao} não baixou ({type(exc).__name__}).", file=sys.stderr)
                faltaram += 1
                continue
            print(destino)
        return 1 if faltaram else 0
    except Falha as falha:
        print(f"Anexos não baixados: {falha}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
