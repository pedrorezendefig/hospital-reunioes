#!/usr/bin/env python3
"""O que a sessão da onda está rodando, lido do transcript dela (só leitura).

Uso: sessao.py <transcript.jsonl> <nome-da-sessao>
Imprime um JSON numa linha:
  shell    o último Bash em primeiro plano ainda sem resultado: {descricao, comando, inicio}
           (ms desde a época), ou null
  subidas  cada `fechar_onda.py --prs` que a sessão rodou (sem --dry-run): {prs, inicio, fim}
           fim é null enquanto o processo ainda aparece no `ps`; depois, o mtime do arquivo
           de saída que o Bash em segundo plano devolveu
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

SUBIDA = re.compile(r"fechar_onda\.py\s+--prs\s+([\d\s]+)")
SAIDA = re.compile(r"written to: (\S+\.output)")


def ms(ts):
    # o python3 do sistema é 3.9: o fromisoformat dele não aceita o Z
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def rodando(nome):
    try:
        ps = subprocess.run(
            ["ps", "-eo", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    vivos = set()
    for linha in ps.splitlines():
        if (
            "fechar_onda.py" in linha
            and "--dry-run" not in linha
            and f"--sessao {nome}" in linha
        ):
            m = SUBIDA.search(linha)
            if m:
                vivos.add(tuple(int(x) for x in m.group(1).split()))
    return vivos


def main(caminho, nome):
    usos = {}  # id -> {descricao, comando, inicio, bg}
    sem_resultado = []  # ids de Bash em primeiro plano ainda abertos, em ordem
    subidas = {}  # id -> {prs, inicio, fim}
    with open(caminho, encoding="utf-8", errors="ignore") as f:
        for linha in f:
            try:
                e = json.loads(linha)
            except ValueError:
                continue
            msg = e.get("message") or {}
            conteudo = msg.get("content")
            if not isinstance(conteudo, list):
                continue
            for bloco in conteudo:
                tipo = bloco.get("type")
                if tipo == "tool_use" and bloco.get("name") == "Bash":
                    entrada = bloco.get("input") or {}
                    cmd = entrada.get("command") or ""
                    uso = {
                        "descricao": entrada.get("description") or "",
                        "comando": cmd,
                        "inicio": ms(e["timestamp"]),
                        "bg": bool(entrada.get("run_in_background")),
                    }
                    usos[bloco["id"]] = uso
                    if not uso["bg"]:
                        sem_resultado.append(bloco["id"])
                    m = SUBIDA.search(cmd)
                    if m and "--dry-run" not in cmd:
                        subidas[bloco["id"]] = {
                            "prs": [int(x) for x in m.group(1).split()],
                            "inicio": uso["inicio"],
                            "fim": None if uso["bg"] else ms(e["timestamp"]),
                        }
                elif tipo == "tool_result":
                    tid = bloco.get("tool_use_id")
                    if tid in sem_resultado:
                        sem_resultado.remove(tid)
                    if tid in subidas:
                        texto = bloco.get("content")
                        if isinstance(texto, list):
                            texto = " ".join(
                                str(b.get("text", ""))
                                for b in texto
                                if isinstance(b, dict)
                            )
                        m = SAIDA.search(str(texto or ""))
                        if m:
                            subidas[tid]["saida"] = m.group(1)
                        elif not usos[tid]["bg"]:
                            subidas[tid]["fim"] = ms(e["timestamp"])

    vivos = rodando(nome)
    for s in subidas.values():
        if tuple(s["prs"]) in vivos:
            s["fim"] = None
        elif s["fim"] is None:
            saida = s.get("saida")
            try:
                s["fim"] = int(os.stat(saida).st_mtime * 1000) if saida else s["inicio"]
            except OSError:
                s["fim"] = s["inicio"]
        s.pop("saida", None)

    shell = None
    if sem_resultado:
        u = usos[sem_resultado[-1]]
        shell = {
            "descricao": u["descricao"],
            "comando": u["comando"][:200],
            "inicio": u["inicio"],
        }
    print(
        json.dumps(
            {"shell": shell, "subidas": list(subidas.values())}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
