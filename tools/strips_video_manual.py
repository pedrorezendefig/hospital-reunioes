#!/usr/bin/env python3
"""Gate de strips do Vídeo de tarefa: dez quadros de cada lado de cada corte.

O `hyperframes check` amostra o vídeo em poucos instantes e não vê o corte. É
no corte que o vídeo quebra: um quadro preto entre duas telas, a legenda que
fica um instante sem a placa. Este gate lê os cortes da composição (início e
fim de cada clipe), tira do MP4 os dez quadros antes e os dez depois de cada
um, grava uma strip por corte (linha de cima: antes; linha de baixo: depois) e
reprova

- quadro preto: quase todo o quadro escuro;
- legenda sem fundo: quadro dentro do tempo de um card `legenda-de-passo` em
  que a placa da legenda não está no retângulo que o `tokens.css` declara.

Emenda de 13/10/2026 à ADR 0057, issue #1230. A strip é também a evidência que
o `VERIFY.md` do vídeo cita.

Uso:
  python3 tools/strips_video_manual.py --mp4 <render.mp4> \\
      --composicao docs/manual/video/<modulo>/<slug>/index.html
Sai com código 1 se algum corte reprovar.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import zlib
from html.parser import HTMLParser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TOKENS_PADRAO = RAIZ / "docs" / "manual" / "video" / "_estilo" / "tokens.css"

QUADROS_POR_LADO = 10
LARGURA, ALTURA = 320, 180  # quadro reduzido: sobra para ver e analisar
PALCO = (1920, 1080)
ESCURO = 24  # luma abaixo disso conta como preto
FRACAO_PRETA = 0.98
TOLERANCIA_DA_PLACA = 48  # o H.264 mexe na cor; diferença por canal aceita
FRACAO_DA_PLACA = 0.5  # o resto é o texto e o número em cima da placa
CARD_DA_LEGENDA = "legenda-de-passo"


class _Clipes(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elementos: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atributos = {nome: valor or "" for nome, valor in attrs}
        if "data-start" in atributos or "data-composition-id" in atributos:
            self.elementos.append(atributos)


def _segundos(valor: str) -> float | None:
    try:
        return float(valor)
    except ValueError:
        return None  # tempo relativo a outro clipe: fica fora da conta


def ler_composicao(html: str) -> tuple[list[float], list[tuple[float, float]]]:
    """Os cortes (segundos) e os intervalos em que há legenda de passo."""
    leitor = _Clipes()
    leitor.feed(html)
    raiz = next(e for e in leitor.elementos if "data-composition-id" in e)
    total = _segundos(raiz.get("data-duration", "")) or 0.0
    cortes: set[float] = set()
    legendas: list[tuple[float, float]] = []
    for elemento in leitor.elementos:
        if elemento is raiz:
            continue
        inicio = _segundos(elemento.get("data-start", ""))
        duracao = _segundos(elemento.get("data-duration", ""))
        if inicio is None or duracao is None:
            continue
        cortes.update(t for t in (inicio, inicio + duracao) if 0 < t < total)
        if CARD_DA_LEGENDA in elemento.get("data-composition-src", ""):
            legendas.append((inicio, inicio + duracao))
    return sorted(round(t, 3) for t in cortes), legendas


def _tokens(css: str) -> dict[str, str]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return {n: " ".join(v.split()) for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+);", css)}


def _resolver(tokens: dict[str, str], nome: str) -> str:
    valor = tokens[nome]
    referencia = re.fullmatch(r"var\((--[\w-]+)\)", valor)
    return _resolver(tokens, referencia.group(1)) if referencia else valor


def placa_da_legenda(css: str) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
    """A cor da placa e o retângulo dela no quadro reduzido, lidos dos tokens."""
    tokens = _tokens(css)
    cor = _resolver(tokens, "--video-legenda-fundo").lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    rgb = (int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16))
    px = {
        lado: float(_resolver(tokens, f"--video-legenda-{lado}").removesuffix("px"))
        for lado in ("esquerda", "topo", "largura", "altura")
    }
    ex, ey = LARGURA / PALCO[0], ALTURA / PALCO[1]
    x0, y0 = int(px["esquerda"] * ex) + 1, int(px["topo"] * ey) + 1
    x1 = int((px["esquerda"] + px["largura"]) * ex) - 1
    y1 = int((px["topo"] + px["altura"]) * ey) - 1
    return rgb, (x0, y0, x1, y1)


def _sonda(mp4: Path) -> tuple[float, int]:
    saida = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate:format=duration", "-of", "json", str(mp4),
        ],
        capture_output=True, text=True, check=True,
    )
    dados = json.loads(saida.stdout)
    num, den = dados["streams"][0]["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    return fps, round(float(dados["format"]["duration"]) * fps)


def _quadros(mp4: Path, indices: list[int]) -> dict[int, bytes]:
    """Os quadros pedidos, numa passada só, em RGB reduzido."""
    escolha = "+".join(f"eq(n,{i})" for i in indices)
    saida = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(mp4),
            "-vf", f"select='{escolha}',scale={LARGURA}:{ALTURA}",
            "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ],
        capture_output=True, check=True,
    )
    tamanho = LARGURA * ALTURA * 3
    return {i: saida.stdout[k * tamanho : (k + 1) * tamanho] for k, i in enumerate(indices)}


def e_preto(quadro: bytes) -> bool:
    pixels = range(0, len(quadro), 3 * 4)  # um pixel a cada quatro basta
    escuros = sum(
        1
        for p in pixels
        if 0.299 * quadro[p] + 0.587 * quadro[p + 1] + 0.114 * quadro[p + 2] < ESCURO
    )
    return escuros >= FRACAO_PRETA * len(pixels)


def tem_placa(quadro: bytes, cor: tuple[int, int, int], caixa: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = caixa
    total = iguais = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = (y * LARGURA + x) * 3
            total += 1
            if all(abs(quadro[p + c] - cor[c]) <= TOLERANCIA_DA_PLACA for c in range(3)):
                iguais += 1
    return total > 0 and iguais >= FRACAO_DA_PLACA * total


def _png(caminho: Path, largura: int, altura: int, rgb: bytes) -> None:
    def bloco(tipo: bytes, dados: bytes) -> bytes:
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo))

    linhas = b"".join(
        b"\x00" + rgb[y * largura * 3 : (y + 1) * largura * 3] for y in range(altura)
    )
    caminho.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(linhas, 6))
        + bloco(b"IEND", b"")
    )


def _strip(caminho: Path, antes: list[bytes], depois: list[bytes]) -> None:
    """Grade 10x2: a linha de cima é antes do corte, a de baixo é depois."""
    vazio = b"\x00" * (LARGURA * ALTURA * 3)
    linhas = []
    for fileira in (antes, depois):
        fileira = fileira + [vazio] * (QUADROS_POR_LADO - len(fileira))
        for y in range(ALTURA):
            linhas.append(
                b"".join(q[y * LARGURA * 3 : (y + 1) * LARGURA * 3] for q in fileira)
            )
    _png(caminho, LARGURA * QUADROS_POR_LADO, ALTURA * 2, b"".join(linhas))


def checar(mp4: Path, composicao: Path, tokens: Path, saida: Path) -> list[str]:
    cortes, legendas = ler_composicao(composicao.read_text(encoding="utf-8"))
    fps, total = _sonda(mp4)
    placa = placa_da_legenda(tokens.read_text(encoding="utf-8")) if legendas else None

    janelas = []
    for t in cortes:
        meio = round(t * fps)
        antes = list(range(max(0, meio - QUADROS_POR_LADO), min(meio, total)))
        depois = list(range(meio, min(meio + QUADROS_POR_LADO, total)))
        janelas.append((t, antes, depois))
    pedidos = sorted({i for _, a, d in janelas for i in a + d})
    quadros = _quadros(mp4, pedidos) if pedidos else {}

    saida.mkdir(parents=True, exist_ok=True)
    for velha in saida.glob("corte-*.png"):
        velha.unlink()

    problemas: list[str] = []
    for numero, (t, antes, depois) in enumerate(janelas, start=1):
        _strip(
            saida / f"corte-{numero:02d}-{t:.2f}s.png",
            [quadros[i] for i in antes],
            [quadros[i] for i in depois],
        )
        for i in antes + depois:
            instante = i / fps
            if e_preto(quadros[i]):
                problemas.append(f"corte em {t:.2f}s: quadro preto em {instante:.2f}s")
                continue
            meio_quadro = 0.5 / fps
            com_legenda = any(
                a + meio_quadro <= instante < b - meio_quadro for a, b in legendas
            )
            if placa and com_legenda and not tem_placa(quadros[i], *placa):
                problemas.append(
                    f"corte em {t:.2f}s: legenda sem fundo em {instante:.2f}s "
                    "(a placa da legenda não está no lugar)"
                )
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp4", type=Path, required=True)
    ap.add_argument("--composicao", type=Path, required=True)
    ap.add_argument("--tokens", type=Path, default=TOKENS_PADRAO)
    ap.add_argument("--saida", type=Path, help="padrão: renders/strips/ da composição")
    args = ap.parse_args()

    saida = args.saida or args.composicao.parent / "renders" / "strips"
    problemas = checar(args.mp4, args.composicao, args.tokens, saida)
    if problemas:
        print(
            "Gate de strips falhou:\n" + "\n".join(f"  - {p}" for p in problemas)
            + f"\nStrips em {saida}",
            file=sys.stderr,
        )
        return 1
    print(f"Strips OK. Olhe as imagens em {saida} e cite no VERIFY.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
