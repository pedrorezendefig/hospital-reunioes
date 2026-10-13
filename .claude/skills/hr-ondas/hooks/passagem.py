#!/usr/bin/env python3
"""As ondas de cada linhagem de sessão, lidas das passagens da /onda-enxuta (só leitura).

Uso: passagem.py <dir das passagens>
Imprime um JSON numa linha, por linhagem ("onda-gestao" de "onda-gestao-onda4.md"):
  ondas     {"4": [1143], "5": [1145], ...}: a fila-alvo fixa, pelas linhas "- Onda N: #a, #b".
            A passagem mais nova manda: a onda de uma issue é a da última passagem que a cita.
  escritas  números das passagens que existem na pasta (a onda N nasce da passagem N).
"""

import json
import os
import re
import sys

ARQUIVO = re.compile(r"^(?P<linhagem>.+)-onda(?P<n>\d+)\.md$")
LINHA = re.compile(r"^-\s*Onda\s+(\d+):\s*(?:exatamente\s+)?(#.*)$")
PARENTESES = re.compile(r"\([^)]*\)")


def fatias(texto):
    """"#1140, depois da #1139 (onda-ia); #1144, depois da #1139" -> [1140, 1144]."""
    numeros = []
    for item in PARENTESES.sub("", texto).split(";"):
        item = re.split(r"\bdepois\b|\.\s|\.$", item, maxsplit=1)[0]
        numeros += [int(n) for n in re.findall(r"#(\d+)", item)]
    return numeros


def ler(pasta):
    linhagens = {}
    for nome in sorted(os.listdir(pasta)):
        m = ARQUIVO.match(nome)
        if not m:
            continue
        n = int(m.group("n"))
        linhagem = linhagens.setdefault(m.group("linhagem"), {"ondas": {}, "escritas": [], "_de": {}})
        linhagem["escritas"].append(n)
        with open(os.path.join(pasta, nome), encoding="utf-8", errors="ignore") as f:
            for linha in f:
                lm = LINHA.match(linha.strip())
                if not lm:
                    continue
                onda = int(lm.group(1))
                for issue in fatias(lm.group(2)):
                    if linhagem["_de"].get(issue, -1) <= n:
                        linhagem["_de"][issue] = n
                        linhagem["ondas"][issue] = onda
    saida = {}
    for nome, l in linhagens.items():
        ondas = {}
        for issue, onda in l["ondas"].items():
            ondas.setdefault(str(onda), []).append(issue)
        saida[nome] = {"ondas": {k: sorted(v) for k, v in sorted(ondas.items(), key=lambda kv: int(kv[0]))},
                       "escritas": sorted(l["escritas"])}
    return saida


if __name__ == "__main__":
    try:
        print(json.dumps(ler(sys.argv[1]), ensure_ascii=False))
    except OSError:
        print("{}")
