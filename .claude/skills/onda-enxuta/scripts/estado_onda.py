#!/usr/bin/env python3
"""estado_onda.py: o estado de uma Onda em arquivo, para o PedroOS ler.

A Onda grava aqui o que está fazendo; o PedroOS lê a pasta e mostra o painel da Onda,
fala os Avisos no Mac e não repete evento já falado (o `id` de cada evento é estável).
O formato está em `docs/estado-da-onda.md` do PedroOS. Um arquivo por onda:

    ${PEDROOS_ONDAS:-~/.pedroos/ondas}/<slug do Projeto>/<sessao>-onda<N>.json

Uso (sempre da raiz do repositório do Projeto, que tem o `.claude/fluxo.json`):
    estado_onda.py iniciar --sessao onda-a --onda 1 [--prd 12] [--issues 40 41] [--attach <id>]
    estado_onda.py issue   --sessao onda-a --onda 1 --numero 40 [--pr 77] [--status verde]
    estado_onda.py evento  --sessao onda-a --onda 1 --tipo erro --texto "..." [--pr 77]
    estado_onda.py fim     --sessao onda-a --onda 1 [--retro "dispensável"]
    estado_onda.py ler     --sessao onda-a --onda 1

`evento` de tipo `erro` ou `pronto-para-voce`, novo e com `aviso_celular` ligado no
fluxo.json, imprime uma linha `push: <mensagem>`. A sessão manda essa linha, literal,
pelo `PushNotification`. A mensagem termina com o comando para entrar na sessão
(`claude attach <nome>`). Evento repetido (mesmo tipo, texto e PR) não entra de novo
nem gera `push:`.

Saída 0, ou 2 com o motivo no stderr.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fluxo as config_do_fluxo  # noqa: E402

CONTRATO = 1
ESTADOS = ("rodando", "pronto-para-voce", "erro", "terminada")
TIPOS = ("checkpoint", "pr-pronto", "erro", "pronto-para-voce", "terminada")
NO_CELULAR = ("erro", "pronto-para-voce")
STATUS_DA_ISSUE = ("fila", "implementando", "revisao", "correcao", "verde", "baixa", "mergeado")
NOME_VALIDO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pasta_base() -> Path:
    return Path(os.environ.get("PEDROOS_ONDAS") or Path.home() / ".pedroos" / "ondas")


def caminho(slug: str, sessao: str, onda: int) -> Path:
    for valor in (slug, sessao):
        if not NOME_VALIDO.match(valor):
            raise config_do_fluxo.Erro(f"nome inválido para arquivo: {valor!r}")
    return pasta_base() / slug / f"{sessao}-onda{onda}.json"


def repo_do_git(base: Path) -> str | None:
    """`dono/repo` do remoto origin, ou None."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                             encoding="utf-8", check=True, cwd=base).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def ler(arq: Path) -> dict:
    if not arq.exists():
        raise config_do_fluxo.Erro(f"onda sem estado ainda: {arq} (rode `iniciar` antes)")
    return json.loads(arq.read_text(encoding="utf-8"))


def gravar(arq: Path, estado: dict) -> None:
    """Escrita atômica: o PedroOS nunca lê meio arquivo."""
    estado["atualizado"] = agora()
    arq.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=arq.parent, prefix=".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, arq)


def novo_estado(cfg: dict, base: Path, sessao: str, onda: int, prd: int | None, issues: list[int],
                attach: str | None) -> dict:
    nome = f"{sessao}-onda{onda}"
    return {
        "contrato": CONTRATO,
        "projeto": cfg["nome"],
        "slug": cfg["slug"],
        "repo": repo_do_git(base),
        "pasta": str(base),
        "sessao": sessao,
        "onda": onda,
        "id": nome,
        "attach": f"claude attach {attach or nome}",
        "prd": prd,
        "estado": "rodando",
        "inicio": agora(),
        "atualizado": agora(),
        "fim": None,
        "issues": [{"numero": n, "pr": None, "status": "fila"} for n in issues],
        "eventos": [],
        "retro": None,
    }


def id_do_evento(tipo: str, texto: str, pr: int | None) -> str:
    return hashlib.sha1(f"{tipo}|{pr or ''}|{texto}".encode("utf-8")).hexdigest()[:12]


def mensagem_push(estado: dict, texto: str) -> str:
    return f"{estado['projeto']}, {estado['id']}: {texto}. Entrar: {estado['attach']}"


def registrar_evento(estado: dict, tipo: str, texto: str, pr: int | None) -> bool:
    """Acrescenta o evento e ajusta o estado da onda. False se ele já estava lá."""
    eid = id_do_evento(tipo, texto, pr)
    if any(e["id"] == eid for e in estado["eventos"]):
        return False
    estado["eventos"].append({"id": eid, "tipo": tipo, "texto": texto, "pr": pr, "em": agora()})
    if tipo == "erro":
        estado["estado"] = "erro"
    elif tipo == "pronto-para-voce" and estado["estado"] != "erro":
        estado["estado"] = "pronto-para-voce"
    elif tipo == "terminada" and estado["estado"] == "rodando":
        estado["estado"] = "terminada"
    return True


def main(argv: list[str]) -> int:
    for f in (sys.stdout, sys.stderr):
        f.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Estado da Onda em arquivo, para o PedroOS.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    comuns = argparse.ArgumentParser(add_help=False)
    comuns.add_argument("--sessao", required=True)
    comuns.add_argument("--onda", type=int, required=True)
    p = sub.add_parser("iniciar", parents=[comuns])
    p.add_argument("--prd", type=int)
    p.add_argument("--issues", type=int, nargs="*", default=[])
    p.add_argument("--attach", help="id ou nome que o `claude attach` usa (padrão: <sessao>-onda<N>)")
    p = sub.add_parser("issue", parents=[comuns])
    p.add_argument("--numero", type=int, required=True)
    p.add_argument("--pr", type=int)
    p.add_argument("--status", choices=STATUS_DA_ISSUE)
    p = sub.add_parser("evento", parents=[comuns])
    p.add_argument("--tipo", choices=TIPOS, required=True)
    p.add_argument("--texto", required=True)
    p.add_argument("--pr", type=int)
    p = sub.add_parser("fim", parents=[comuns])
    p.add_argument("--retro")
    sub.add_parser("ler", parents=[comuns])
    args = ap.parse_args(argv)

    try:
        base = config_do_fluxo.raiz()
        cfg = config_do_fluxo.carregar(base)
        arq = caminho(cfg["slug"], args.sessao, args.onda)
        if args.cmd == "iniciar":
            if arq.exists():  # retomada: a mesma onda de novo não apaga o que já foi gravado
                estado = ler(arq)
                conhecidas = {i["numero"] for i in estado["issues"]}
                estado["issues"] += [{"numero": n, "pr": None, "status": "fila"}
                                     for n in args.issues if n not in conhecidas]
                if args.attach:
                    estado["attach"] = f"claude attach {args.attach}"
            else:
                estado = novo_estado(cfg, base, args.sessao, args.onda, args.prd, args.issues, args.attach)
            gravar(arq, estado)
            print(arq)
            return 0
        estado = ler(arq)
        if args.cmd == "ler":
            print(json.dumps(estado, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "issue":
            item = next((i for i in estado["issues"] if i["numero"] == args.numero), None)
            if item is None:
                item = {"numero": args.numero, "pr": None, "status": "fila"}
                estado["issues"].append(item)
            if args.pr is not None:
                item["pr"] = args.pr
            if args.status:
                item["status"] = args.status
            gravar(arq, estado)
            return 0
        if args.cmd == "evento":
            novo = registrar_evento(estado, args.tipo, args.texto, args.pr)
            gravar(arq, estado)
            if novo and args.tipo in NO_CELULAR and cfg.get("aviso_celular", True):
                print(f"push: {mensagem_push(estado, args.texto)}")
            return 0
        if args.cmd == "fim":
            estado["fim"] = agora()
            estado["retro"] = args.retro
            registrar_evento(estado, "terminada", f"onda {args.onda} terminada", None)
            gravar(arq, estado)
            return 0
    except (config_do_fluxo.Erro, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
