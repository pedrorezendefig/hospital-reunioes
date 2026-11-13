#!/usr/bin/env python3
"""Sub-agentes da onda (implementador, revisor, corretor) de todas as sessões recentes do Projeto, vivas ou
encerradas: o tempo de cada etapa da Fatia sobrevive ao fim da sessão que a levou.

Uso: historico.py <cache.json> <dias> <numeros> <pasta de projeto>...
  numeros: "1617,1655,...", as issues e os PRs do painel; só fica o sub-agente cuja descrição cita um deles.
Saída: lista JSON no formato SubAgente do mod (sessao é o id da sessão).
O cache guarda cada .jsonl pelo mtime e pelo tamanho: sessão encerrada não se relê.
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime

TIPO = re.compile(r"^(?:hr|onda)-(?:implementador|revisor|corretor)$")


def ms(iso):
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def ultima_linha(caminho):
    with open(caminho, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        bloco = b""
        while pos > 0:
            ler = min(65536, pos)
            pos -= ler
            f.seek(pos)
            bloco = f.read(ler) + bloco
            linhas = bloco.rstrip(b"\n").split(b"\n")
            if len(linhas) > 1 or pos == 0:
                return linhas[-1]
    return b""


def ler(jsonl, meta):
    with open(jsonl, "rb") as f:
        primeira = json.loads(f.readline() or b"{}")
    ultima = json.loads(ultima_linha(jsonl) or b"{}")
    inicio = ms(primeira.get("timestamp"))
    if inicio is None:
        return None
    fim = ms(ultima.get("timestamp")) or inicio
    msg = ultima.get("message") or {}
    return {
        "sessao": os.path.basename(os.path.dirname(os.path.dirname(jsonl))),
        "id": os.path.basename(jsonl)[: -len(".jsonl")],
        "tipo": meta.get("agentType") or "?",
        "descricao": meta.get("description") or "",
        "esforco": meta.get("effort"),
        "modelo": None,
        "inicio": inicio,
        "fim": fim,
        "ctx": 0,
        "terminou": ultima.get("type") == "assistant" and msg.get("stop_reason") == "end_turn",
    }


def main():
    cache_arq, dias, numeros, pastas = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4:]
    alvo = {int(n) for n in numeros.split(",") if n.isdigit()}
    try:
        with open(cache_arq) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    limite = time.time() - dias * 86400
    novo, saida = {}, []
    for pasta in pastas:
        for meta_arq in glob.glob(os.path.join(pasta, "*", "subagents", "*.meta.json")):
            jsonl = meta_arq[: -len(".meta.json")] + ".jsonl"
            try:
                st = os.stat(jsonl)
            except OSError:
                continue
            if st.st_mtime < limite:
                continue
            chave = f"{st.st_mtime_ns}:{st.st_size}"
            item = cache.get(jsonl)
            if not item or item.get("chave") != chave:
                try:
                    with open(meta_arq) as f:
                        meta = json.load(f)
                    agente = ler(jsonl, meta) if TIPO.match(meta.get("agentType") or "") else None
                except (OSError, ValueError):
                    continue
                item = {"chave": chave, "agente": agente}
            novo[jsonl] = item
            a = item["agente"]
            if a and alvo & {int(n) for n in re.findall(r"\d+", a["descricao"])}:
                saida.append(a)
    tmp = f"{cache_arq}.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(novo, f)
    os.replace(tmp, cache_arq)
    json.dump(sorted(saida, key=lambda a: a["inicio"]), sys.stdout)


if __name__ == "__main__":
    main()
