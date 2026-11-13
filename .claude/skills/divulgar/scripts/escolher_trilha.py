#!/usr/bin/env python3
"""A trilha da Demonstração: a faixa da biblioteca menos usada nas demonstrações anteriores.

    python3 .claude/skills/divulgar/scripts/escolher_trilha.py [--climas tecnologia,animada]

Lê o campo "musica" de todo docs/comunicacao/**/video/meta.json (o caminho da faixa relativo a
~/Sons/musica, como "tecnologia/faixa.mp3"), conta quantas vezes cada faixa dos climas pedidos já
entrou e imprime o caminho inteiro da menos usada. No empate, a usada há mais tempo (a nunca usada
vem antes), depois a ordem dos climas pedidos e a do nome. O diretor vê várias demonstrações seguidas: trilha repetida
denuncia linha de montagem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
MUSICA = Path.home() / "Sons" / "musica"
EXTENSOES = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def faixas(musica: Path, climas: list[str]) -> list[str]:
    """As faixas dos climas pedidos, como caminho relativo à pasta de música."""
    achadas = []
    for clima in climas:
        pasta = musica / clima
        if pasta.is_dir():
            achadas += [f"{clima}/{a.name}" for a in sorted(pasta.iterdir()) if a.suffix.lower() in EXTENSOES]
    return achadas


def usos(raiz: Path) -> tuple[dict[str, int], dict[str, str]]:
    """Quantas vezes cada faixa entrou e quando entrou pela última vez (gerado_em do meta.json)."""
    contagem: dict[str, int] = {}
    ultimo: dict[str, str] = {}
    for meta in sorted(raiz.glob("docs/comunicacao/**/video/meta.json")):
        try:
            dados = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        faixa = dados.get("musica")
        if not faixa:
            continue
        contagem[faixa] = contagem.get(faixa, 0) + 1
        quando = str(dados.get("gerado_em", ""))
        if quando > ultimo.get(faixa, ""):
            ultimo[faixa] = quando
    return contagem, ultimo


def escolher(candidatas: list[str], contagem: dict[str, int], ultimo: dict[str, str]) -> str:
    # candidatas vem na ordem dos climas pedidos e, dentro de cada um, do nome: no empate, o primeiro clima vence.
    ordem = {f: i for i, f in enumerate(candidatas)}
    return min(candidatas, key=lambda f: (contagem.get(f, 0), ultimo.get(f, ""), ordem[f]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--climas", default="tecnologia,animada", help="pastas de ~/Sons/musica, em ordem (padrão: tecnologia,animada)")
    ap.add_argument("--musica", type=Path, default=MUSICA, help=argparse.SUPPRESS)
    ap.add_argument("--raiz", type=Path, default=RAIZ, help=argparse.SUPPRESS)
    a = ap.parse_args()
    climas = [c.strip() for c in a.climas.split(",") if c.strip()]
    candidatas = faixas(a.musica, climas)
    if not candidatas:
        print(f"nenhuma faixa em {a.musica} nos climas {', '.join(climas)}", file=sys.stderr)
        return 1
    contagem, ultimo = usos(a.raiz)
    escolhida = escolher(candidatas, contagem, ultimo)
    print(a.musica / escolhida)
    print(f"{escolhida}: usada {contagem.get(escolhida, 0)} vez(es) antes; grave \"musica\": \"{escolhida}\" no meta.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
