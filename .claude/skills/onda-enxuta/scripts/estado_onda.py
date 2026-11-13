#!/usr/bin/env python3
"""estado_onda.py: o estado de uma Onda em arquivo, para o PedroOS ler.

A Onda grava aqui o que está fazendo; o PedroOS lê a pasta e mostra o painel da Onda,
fala os Avisos no Mac e não repete evento já falado (o `id` de cada evento é estável).
O formato está em `docs/estado-da-onda.md` do PedroOS. Um arquivo por onda:

    ${PEDROOS_ONDAS:-~/.pedroos/ondas}/<slug do Projeto>/<sessao>-onda<N>.json

Uso (sempre da raiz do repositório do Projeto, que tem o `.claude/fluxo.json`):
    estado_onda.py iniciar --sessao onda-a --onda 1 [--prd 12] [--issues 40 41] [--attach <id>]
                           [--descricao-valor "o que a Onda entrega, numa frase"]
    estado_onda.py issue   --sessao onda-a --onda 1 --numero 40 [--pr 77] [--status verde]
    estado_onda.py evento  --sessao onda-a --onda 1 --tipo erro --texto "..." [--pr 77]
    estado_onda.py fim     --sessao onda-a --onda 1 [--proxima 2 | --ultima] [--retro "dispensável"]
    estado_onda.py resolvido --sessao onda-a --onda 1 --texto "migration 124 aplicada"
    estado_onda.py mergeadas --issues 40 41 [--texto "subida onda-a-onda2b"]
    estado_onda.py retro   --sessao onda-a --onda 1 [--candidata 1 "check do semáforo" ...]
    estado_onda.py retro-dispensada --sessao onda-a --onda 1
    estado_onda.py ler     --sessao onda-a --onda 1

`evento` de tipo `erro`, `pronto-para-voce` ou `revert`, novo e com `aviso_celular` ligado no
fluxo.json, imprime uma linha `push: <mensagem>`. A sessão manda essa linha, literal,
pelo `PushNotification`. A mensagem termina com o comando para entrar na sessão
(`claude attach <nome>`). Evento repetido (mesmo tipo, texto e PR) não entra de novo
nem gera `push:`. O `revert` (a subida desfez o merge que quebrou o teste da main, issue
#327) não muda o estado da onda: a main voltou ao verde.

`resolvido` tira o "espera você" (e o "quebrou") quando a pendência acabou: a onda volta
para `terminada` (já teve `fim`) ou `rodando`, com o evento `resolvido`. Enquanto alguma
issue da onda segue em `baixa`, o estado continua `pronto-para-voce`. Sem nada pendente,
não muda nada. `mergeadas` é o que o `fechar_onda.py` chama depois do merge: em todas as
ondas do Projeto, a issue do lote que estava em `baixa` vira `mergeado` e a onda é resolvida.

`--descricao-valor` grava a Descrição de valor da Onda no campo `descricao_valor` (no `iniciar` novo
ou na retomada); sem ela, o arquivo não ganha o campo.

`retro` grava a Retro feita, com as Candidatas aceitas (número na Retro e título curto; nenhuma
também vale), e `retro-dispensada` grava a dispensa. Os dois escrevem o `registro_retro` e, rodados
de novo, substituem o que estava lá.

Saída 0, ou 2 com o motivo no stderr.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fluxo as config_do_fluxo  # noqa: E402

CONTRATO = 1
ESTADOS = ("rodando", "pronto-para-voce", "erro", "terminada")
TIPOS = ("checkpoint", "pr-pronto", "erro", "pronto-para-voce", "terminada", "revert")
NO_CELULAR = ("erro", "pronto-para-voce", "revert")
PENDENTES = ("pronto-para-voce", "erro")
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


def saida_de(*cmd: str) -> str | None:
    """A primeira linha do que o comando imprime, ou None se ele falhar ou não existir."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=15, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    linha = r.stdout.strip().splitlines()
    return (linha[0].strip() or None) if linha else None


def login_do_github() -> str | None:
    """Quem rodou a Onda: o login do `gh` desta máquina. Sem `gh` ou sem rede, None."""
    return saida_de("gh", "api", "user", "--jq", ".login")


def nome_do_mac() -> str | None:
    """O nome do computador (o do Compartilhamento do macOS); fora do Mac, o hostname."""
    return saida_de("scutil", "--get", "ComputerName") or socket.gethostname().removesuffix(".local") or None


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
        "login": login_do_github(),
        "mac": nome_do_mac(),
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
        "registro_retro": None,
        "proxima": None,
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


def resolver(estado: dict, texto: str) -> bool:
    """Dá baixa no que esperava o humano. False se nada esperava."""
    if estado["estado"] not in PENDENTES:
        return False
    registrar_evento(estado, "resolvido", texto, None)
    if any(i["status"] == "baixa" for i in estado["issues"]):
        estado["estado"] = "pronto-para-voce"
    else:
        estado["estado"] = "terminada" if estado.get("fim") else "rodando"
    return True


def marcar_mergeadas(slug: str, numeros: list[int], origem: str | None) -> list[Path]:
    """Em cada onda do Projeto, a issue em `baixa` que acabou de ser mergeada vira `mergeado`."""
    pasta = pasta_base() / slug
    mudados = []
    for arq in sorted(pasta.glob("*.json")) if pasta.is_dir() else []:
        try:
            estado = ler(arq)
        except (json.JSONDecodeError, OSError):
            continue
        saiu = [i for i in estado.get("issues", []) if i.get("numero") in numeros and i.get("status") == "baixa"]
        if not saiu:
            continue
        for i in saiu:
            i["status"] = "mergeado"
        nomes = " e ".join(f"#{i['numero']}" for i in saiu)
        texto = f"{nomes} {'mergeada' if len(saiu) == 1 else 'mergeadas'}" + (f" ({origem})" if origem else "")
        resolver(estado, texto)
        gravar(arq, estado)
        mudados.append(arq)
    return mudados


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
    p.add_argument("--descricao-valor", help="a Descrição de valor da Onda: o que ela entrega, numa frase")
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
    seguinte = p.add_mutually_exclusive_group()
    seguinte.add_argument("--proxima", type=int, help="número da onda seguinte, já lançada")
    seguinte.add_argument("--ultima", action="store_true", help="fila vazia: não há onda seguinte")
    sub.add_parser("ler", parents=[comuns])
    p = sub.add_parser("retro", parents=[comuns])
    p.add_argument("--candidata", nargs=2, action="append", default=[], metavar=("NUMERO", "TITULO"),
                   help="Candidata aceita: o número dela na Retro e o título curto (repita para cada uma)")
    sub.add_parser("retro-dispensada", parents=[comuns])
    p = sub.add_parser("resolvido", parents=[comuns])
    p.add_argument("--texto", required=True, help="o que resolveu, numa frase")
    p = sub.add_parser("mergeadas")
    p.add_argument("--issues", type=int, nargs="+", required=True)
    p.add_argument("--texto", help="de onde veio o merge (a chave da subida)")
    args = ap.parse_args(argv)

    try:
        base = config_do_fluxo.raiz()
        cfg = config_do_fluxo.carregar(base)
        if args.cmd == "mergeadas":
            for arq in marcar_mergeadas(cfg["slug"], args.issues, args.texto):
                print(arq)
            return 0
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
            if args.descricao_valor:
                estado["descricao_valor"] = args.descricao_valor
            gravar(arq, estado)
            print(arq)
            return 0
        estado = ler(arq)
        if args.cmd == "resolvido":
            if resolver(estado, args.texto):
                gravar(arq, estado)
            return 0
        if args.cmd in ("retro", "retro-dispensada"):
            feita = args.cmd == "retro"
            try:
                candidatas = [{"numero": int(n), "titulo": t} for n, t in (args.candidata if feita else [])]
            except ValueError:
                raise config_do_fluxo.Erro("o número da Candidata precisa ser inteiro")
            estado["registro_retro"] = {"tipo": "feita" if feita else "dispensada", "em": agora(),
                                        "candidatas": candidatas}
            gravar(arq, estado)
            return 0
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
            # O PedroOS fala o fim da onda dizendo se a seguinte começou ou se esta foi a última.
            estado["proxima"] = args.proxima if args.proxima is not None else (False if args.ultima else None)
            texto = f"onda {args.onda} terminada"
            if args.proxima is not None:
                texto += f", onda {args.proxima} começou"
            elif args.ultima:
                texto += ", foi a última"
            registrar_evento(estado, "terminada", texto, None)
            gravar(arq, estado)
            return 0
    except (config_do_fluxo.Erro, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
