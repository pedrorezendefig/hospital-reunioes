#!/usr/bin/env python3
"""/todas-issues: as issues abertas de todos os Projetos, por Categoria e por Projeto (PedroOS #70).

Pede a lista ao servidor do PedroOS (rota /api/todas-issues, que junta o Registro e o Coletor) com a
porta e o token que o servidor grava em ~/.pedroos/sessao.json ao subir. Sem o PedroOS rodando, avisa
e sai com 2: nunca cai no `gh` repo por repo.

Uso:
  todas_issues.py [--atualizar]           a lista, só leitura (--atualizar: o servidor lê o GitHub de novo)
  todas_issues.py --plano [--atualizar]   as Ondas de todos os Projetos (#75): grava um prompt por Projeto
                                          e termina em "Posso lançar?", sem lançar nada
  todas_issues.py --lancar ID [ID ...]    com o "pode": abre um Terminal por Projeto com o prompt do plano
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

SESSAO = Path(os.environ.get("PEDROOS_SESSAO") or Path.home() / ".pedroos" / "sessao.json")
PROMPTS = Path(os.environ.get("PEDROOS_ONDAS_PROMPTS") or Path(tempfile.gettempdir()) / "onda-enxuta" / "todas-issues")
PARALELO_MAX = 3  # o mesmo teto da montar-ondas-enxutas
ORDEM_FATIA = {"fatia:P": 0, "fatia:M": 1, "fatia:G": 2}
# Fases do Coletor em que a issue já está com alguém (claim, PR) ou já passou: nunca entra numa Onda nova.
FORA_DA_FILA = {"pr_aberto", "mergeada", "em_producao", "humana", "encerrada_sem_pr", "triagem"}
COMO_SUBIR = "Suba o PedroOS (`cd ~/PedroDev/OS/app && npm run dev`, ou o serviço do `scripts/instalar-servico.sh`) e rode de novo."


def parar(motivo: str) -> None:
    print(f"O PedroOS não está rodando ({motivo}). {COMO_SUBIR}")
    sys.exit(2)


def pedir(atualizar: bool) -> dict:
    return chamar("/api/todas-issues" + ("?atualizar=1" if atualizar else ""))


def chamar(caminho: str, corpo: dict | None = None) -> dict:
    try:
        sessao = json.loads(SESSAO.read_text(encoding="utf-8"))
        porta, token = int(sessao["porta"]), str(sessao["token"])
    except (OSError, ValueError, KeyError, TypeError):
        parar(f"sem sessão em {SESSAO}")
    cabecalhos = {"x-pedroos-token": token}
    dados = None
    if corpo is not None:
        cabecalhos["content-type"] = "application/json"
        dados = json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=dados, headers=cabecalhos)
    try:
        with urllib.request.urlopen(pedido, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            parar(f"a sessão em {SESSAO} é de uma subida que já caiu")
        raise SystemExit(f"O PedroOS respondeu {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except (urllib.error.URLError, OSError) as e:
        parar(f"ninguém responde em 127.0.0.1:{porta}: {getattr(e, 'reason', e)}")


def linha(i: dict) -> str:
    partes = [f"#{i['numero']}", i["titulo"], f"[{i.get('fase') or 'sem fase'}]",
              ", ".join(i.get("responsaveis") or []) or "sem Responsável"]
    if i.get("prd"):
        partes.append(f"PRD #{i['prd']}")
    return "- " + "  ·  ".join(partes)


def imprimir(dado: dict) -> str:
    total = sum(len(p["issues"]) for c in dado["categorias"] for p in c["projetos"])
    saida = [f"# Todas as issues: {total} issues abertas (lidas em {dado.get('gerado_em') or '?'})"]
    for c in dado["categorias"]:
        saida += ["", f"## {c['nome']}"]
        for p in c["projetos"]:
            cabeca = f"### {p['nome']} ({p['repo']})"
            if p.get("erro"):
                saida += ["", f"{cabeca}: não li o GitHub ({p['erro']})"]
                continue
            saida += ["", f"{cabeca}: {len(p['issues'])} abertas"] + [linha(i) for i in p["issues"]]
    return "\n".join(saida)


def apta(i: dict, designado_tira_da_fila: bool, login: str) -> bool:
    """A regra da montar-ondas-enxutas com o que o Coletor já leu: `ready-for-agent`, sem claim
    (`in-progress`) e sem PR. No Projeto com `designado_tira_da_fila` (o Hospital), o assignee é o dono
    do card e a Onda de quem roda pega só os cards dele; nos outros, o assignee não conta."""
    labels = i.get("labels") or []
    if designado_tira_da_fila and not (i.get("designada") and login in (i.get("responsaveis") or [])):
        return False
    return "ready-for-agent" in labels and "in-progress" not in labels and i.get("fase") not in FORA_DA_FILA


def ordem(i: dict) -> tuple:
    fatia = min((ORDEM_FATIA[l] for l in i.get("labels") or [] if l in ORDEM_FATIA), default=len(ORDEM_FATIA))
    return (fatia, i["numero"])


def arquivo_do_prompt(id_projeto: str) -> Path:
    return PROMPTS / (re.sub(r"[^\w.-]+", "-", id_projeto) + "-onda1.md")


def sessao_de(projeto: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", projeto["nome"].lower()).strip("-") or "projeto"


def montar_onda(projeto: dict, login: str) -> dict | None:
    """As Ondas de um Projeto: as aptas em ondas de até 3 (fatia:P antes), e as bloqueadas no fim, para a
    /onda-enxuta puxar quando a bloqueadora fechar. Projeto sem apta não ganha Onda."""
    # PRD não é trabalho: fecha sozinho quando a última filha fecha (montar-ondas-enxutas). É PRD o pai de
    # outra issue aberta, ou o título "PRD:" (o que ainda não tem fatia)
    prds = {i["prd"] for i in projeto["issues"] if i.get("prd")}
    na_fila = [i for i in projeto["issues"] if apta(i, bool(projeto.get("designado_tira_da_fila")), login)
               and i["numero"] not in prds and not re.match(r"PRD\b", i.get("titulo") or "")]
    aptas = sorted((i for i in na_fila if i.get("fase") != "bloqueada"), key=ordem)
    if not aptas:
        return None
    bloqueadas = sorted((i for i in na_fila if i.get("fase") == "bloqueada"), key=ordem)
    paralelo = min(PARALELO_MAX, len(aptas))
    ondas = [aptas[k:k + paralelo] for k in range(0, len(aptas), paralelo)]
    lista = lambda issues: ", ".join(f"#{i['numero']}" for i in issues)
    fila = [f"- Onda {n}: {lista(o)}" for n, o in enumerate(ondas, 1)]
    if bloqueadas:
        fila.append(f"- Depois da bloqueadora: {lista(bloqueadas)}")
    fora = len(projeto["issues"]) - len(aptas) - len(bloqueadas)
    prompt = "\n".join([
        f"/onda-enxuta --sessao {sessao_de(projeto)} --onda 1 --paralelo {paralelo}",
        "",
        "Fila-alvo FIXA desta sessão, montada pela /todas-issues. Não use a fila geral.",
        *fila,
        "A onda é toda issue desta fila já desbloqueada, até o --paralelo: a que destravar antes da onda "
        "prevista entra na primeira onda que encontrar livre.",
        "",
    ])
    return {"fila": fila, "fora": fora, "paralelo": paralelo, "prompt": prompt}


def quem_roda() -> str:
    """O login do GitHub de quem roda: no Projeto em que o assignee é o dono, a Onda é dos cards dele."""
    return subprocess.run(["gh", "api", "user", "-q", ".login"], capture_output=True, text=True, check=True).stdout.strip()


def planejar(dado: dict) -> str:
    """O plano de Ondas de todos os Projetos. Grava o prompt de cada um e termina na pergunta: lançar é o
    `--lancar`, que só roda com o "pode". Apaga antes os prompts do plano anterior: o `--lancar` só acha
    o Projeto que tem Onda neste plano."""
    PROMPTS.mkdir(parents=True, exist_ok=True)
    for velho in PROMPTS.glob("*-onda1.md"):
        velho.unlink()
    saida, ids, nomes, sem_onda = [], [], [], []
    # só pergunta ao gh quem roda quando algum Projeto separa a fila pelo dono do card
    regra = any(p.get("designado_tira_da_fila") for c in dado["categorias"] for p in c["projetos"])
    login = quem_roda() if regra else ""
    for c in dado["categorias"]:
        bloco = []
        for p in c["projetos"]:
            onda = None if p.get("erro") else montar_onda(p, login)
            if not onda:
                sem_onda.append(p["nome"])
                continue
            arq = arquivo_do_prompt(p["id"])
            arq.write_text(onda["prompt"], encoding="utf-8")
            ids.append(p["id"])
            nomes.append(p["nome"])
            bloco += ["", f"### {p['nome']} ({p['repo']}): sessão {sessao_de(p)}, --paralelo {onda['paralelo']}",
                      *onda["fila"], f"- Fora do plano: {onda['fora']} (triagem, humana, em andamento ou PR aberto)",
                      f"- Prompt: {arq}"]
        if bloco:
            saida += ["", f"## {c['nome']}", *bloco]
    cabeca = f"# Plano de Ondas de todos os Projetos: {len(ids)} Projetos com Onda (lidas em {dado.get('gerado_em') or '?'})"
    if not ids:
        return "\n".join([cabeca, "", "Nenhum Projeto tem issue apta (ready-for-agent, sem claim e sem PR). Nada a lançar."])
    rodape = ["", f"Sem Onda: {', '.join(sem_onda)}." if sem_onda else "Todos os Projetos com issue aberta têm Onda.",
              "", "Lançar (só com o \"pode\"):",
              f"python3 ~/.claude/skills/todas-issues/scripts/todas_issues.py --lancar {' '.join(ids)}",
              "", f"Posso lançar? Abre um Terminal por Projeto, com a Onda de cada um: {', '.join(nomes)}."]
    return "\n".join([cabeca, *saida, *rodape])


def lancar(ids: list[str]) -> int:
    """Abre um Terminal por Projeto (rota /api/ondas/terminal) com o prompt que o último --plano gravou.
    Projeto sem Onda no último plano não abre."""
    faltam = [i for i in ids if not arquivo_do_prompt(i).exists()]
    if not ids or faltam:
        print(f"Sem plano para {', '.join(faltam) or 'nenhum Projeto'}: rode o --plano antes. Nada foi lançado.")
        return 1
    for id_projeto in ids:
        prompt = arquivo_do_prompt(id_projeto).read_text(encoding="utf-8")
        r = chamar("/api/ondas/terminal", {"id": id_projeto, "prompt": prompt})
        print(f"Terminal aberto: {id_projeto} em {r.get('pasta')}{' (clonou antes)' if r.get('clonou') else ''}")
    return 0


def main(argv: list[str]) -> None:
    if "--lancar" in argv:
        sys.exit(lancar(argv[argv.index("--lancar") + 1:]))
    dado = pedir("--atualizar" in argv)
    print(planejar(dado) if "--plano" in argv else imprimir(dado))


if __name__ == "__main__":
    main(sys.argv[1:])
