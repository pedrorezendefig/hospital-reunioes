#!/usr/bin/env python3
"""Gate do anel do Vídeo de tarefa: o anel de destaque tem que contornar o alvo.

Nota do Pedro no OK dos pilotos (PR #1246): em partes dos dois vídeos o anel
azul caía ao lado do botão. A causa era a medida feita na montagem: o script
da composição roda antes de a fonte do app carregar, o layout ainda está na
fonte de reserva (mais larga), e as caixas medidas ali (anel, dedo, câmera,
rolagem) saem deslocadas. O `hyperframes check` não vê, porque o anel é um
elemento válido em qualquer lugar do quadro.

O gate abre a composição no navegador, espera a fonte como o render espera,
anda pelo timeline de 0,1 em 0,1 s e, em todo instante em que o anel
(`#mk`) está aceso, compara a caixa dele com a caixa do alvo que ele declara
em `data-alvo` (um ou mais ids, separados por espaço). Reprova o anel que não
contorna o alvo ou que sobra demais de um lado.

Uso:
  python3 tools/anel_video_manual.py \\
      --composicao docs/manual/video/<modulo>/<slug>/index.html
Sai com código 1 se algum instante reprovar. Precisa do Playwright para
Python com o Chromium instalado (`python3 -m playwright install chromium`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

Caixa = tuple[float, float, float, float]  # x, y, largura, altura no quadro

PASSO = 0.1  # segundos entre amostras
FOLGA_MINIMA = -2  # px: o anel pode encostar no alvo, não entrar nele
FOLGA_MAXIMA = 20  # px por lado: 8 px de folga vezes o zoom mais forte, com sobra
SOBRA_DO_TEXTO = 1  # px: encostar na letra não conta


def desvio_do_anel(anel: Caixa, alvo: Caixa) -> str | None:
    """Por que o anel não contorna o alvo, ou None se contorna."""
    ax, ay, aw, ah = anel
    bx, by, bw, bh = alvo
    folgas = {
        "esquerda": bx - ax,
        "cima": by - ay,
        "direita": (ax + aw) - (bx + bw),
        "baixo": (ay + ah) - (by + bh),
    }
    ruins = [
        f"{lado} {folga:+.0f} px"
        for lado, folga in folgas.items()
        if not FOLGA_MINIMA <= folga <= FOLGA_MAXIMA
    ]
    if not ruins:
        return None
    return (
        f"anel fora do alvo ({', '.join(ruins)}; a folga de cada lado fica "
        f"entre {FOLGA_MINIMA} e {FOLGA_MAXIMA} px)"
    )


def texto_sob_o_anel(anel: Caixa, textos: list[tuple[str, Caixa]]) -> list[str]:
    """Os textos de fora do alvo que o anel atravessa.

    O anel contorna o alvo com folga; se a folga cai em cima do rótulo ou da
    linha vizinha, a borda azul corta o texto. A caixa que o navegador dá ao
    texto tem respiro acima e abaixo da letra, então conta só a faixa da
    letra (sem o quarto de cima e o quinto de baixo), e encostar não conta.
    """
    ax, ay, aw, ah = anel
    cortados = []
    for texto, (tx, ty, tw, th) in textos:
        topo, base = ty + 0.25 * th, ty + 0.8 * th
        sobra_x = min(ax + aw, tx + tw) - max(ax, tx)
        sobra_y = min(ay + ah, base) - max(ay, topo)
        if sobra_x > SOBRA_DO_TEXTO and sobra_y > SOBRA_DO_TEXTO:
            cortados.append(texto)
    return cortados


_MEDE = """(t) => {
  const tl = window.__timelines[document.querySelector('[data-composition-id]').dataset.compositionId];
  tl.seek(t, false);
  const mk = document.getElementById('mk');
  if (!mk || Number(getComputedStyle(mk).opacity) < 0.99) return null;
  const caixa = (el) => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const ids = (mk.dataset.alvo || '').split(' ').filter(Boolean);
  const faltam = ids.filter((id) => !document.getElementById(id));
  if (!ids.length || faltam.length) return { anel: caixa(mk), ids, faltam };
  const alvos = ids.map((id) => document.getElementById(id));
  const rs = alvos.map(caixa);
  const alvo = [Math.min(...rs.map((r) => r[0])), Math.min(...rs.map((r) => r[1])),
                Math.max(...rs.map((r) => r[2])), Math.max(...rs.map((r) => r[3]))];
  // Texto visível de fora do alvo: opacidade somada dos ancestrais, recorte
  // de quem esconde o que transborda, e nada coberto por outra camada (a
  // janela que abre por cima, o aviso do navegador). Para o teste de quem está
  // por cima, camada transparente e o próprio anel não contam.
  (window.__semToque || []).forEach((el) => { el.style.pointerEvents = ''; });
  window.__semToque = [mk, document.getElementById('dedo')].filter(Boolean);
  document.querySelectorAll('body *').forEach((el) => { if (Number(getComputedStyle(el).opacity) < 0.5) window.__semToque.push(el); });
  window.__semToque.forEach((el) => { el.style.pointerEvents = 'none'; });
  const coberto = (pai, v) => {
    const topo = document.elementFromPoint((v[0] + v[2]) / 2, (v[1] + v[3]) / 2);
    return !topo || !(pai.contains(topo) || topo.contains(pai));
  };
  const textos = [];
  const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = andar.nextNode(); n; n = andar.nextNode()) {
    const texto = n.textContent.trim();
    const pai = n.parentElement;
    if (!texto || !pai || alvos.some((a) => a.contains(pai)) || mk.contains(pai)) continue;
    let opacidade = 1, recorte = [-1e9, -1e9, 1e9, 1e9];
    for (let el = pai; el; el = el.parentElement) {
      const s = getComputedStyle(el);
      opacidade *= Number(s.opacity);
      if (s.visibility === 'hidden') opacidade = 0;
      if (s.overflow !== 'visible') {
        const c = caixa(el);
        recorte = [Math.max(recorte[0], c[0]), Math.max(recorte[1], c[1]), Math.min(recorte[2], c[2]), Math.min(recorte[3], c[3])];
      }
    }
    if (opacidade < 0.5) continue;
    const faixa = document.createRange();
    faixa.selectNodeContents(n);
    for (const r of faixa.getClientRects()) {
      const v = [Math.max(r.left, recorte[0]), Math.max(r.top, recorte[1]), Math.min(r.right, recorte[2]), Math.min(r.bottom, recorte[3])];
      if (v[2] > v[0] && v[3] > v[1] && !coberto(pai, v)) textos.push([texto.slice(0, 40), v]);
    }
  }
  return { anel: caixa(mk), alvo, ids, faltam, textos };
}"""


def _xywh(c: list[float]) -> Caixa:
    return (c[0], c[1], c[2] - c[0], c[3] - c[1])


def checar(composicao: Path) -> list[str]:
    """Um achado por trecho aceso em que o anel não contorna o alvo."""
    from playwright.sync_api import sync_playwright

    achados: list[str] = []
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1920, "height": 1080})
        pagina.goto(composicao.resolve().as_uri())
        pagina.wait_for_function(
            "() => window.__timelines && Object.keys(window.__timelines).length"
        )
        # O render espera a fonte antes do primeiro quadro; o gate também.
        pagina.evaluate("() => document.fonts.ready.then(() => true)")
        duracao = float(
            pagina.evaluate(
                "() => document.querySelector('[data-composition-id]').dataset.duration"
            )
        )
        trecho_com_achado = None  # alvo do trecho aceso que já rendeu achado
        acesos = 0
        for i in range(int(duracao / PASSO) + 1):
            t = round(i * PASSO, 2)
            m = pagina.evaluate(_MEDE, t)
            if m is None:
                trecho_com_achado = None
                continue
            acesos += 1
            if not m["ids"]:
                motivo = "anel aceso sem data-alvo: declare o alvo no marca()"
            elif m["faltam"]:
                motivo = f"data-alvo cita id que não existe: {' '.join(m['faltam'])}"
            else:
                anel = _xywh(m["anel"])
                cortados = texto_sob_o_anel(
                    anel, [(tx, _xywh(c)) for tx, c in m["textos"]]
                )
                motivo = desvio_do_anel(anel, _xywh(m["alvo"])) or (
                    f"anel atravessa texto fora do alvo: {' | '.join(cortados)}"
                    if cortados
                    else None
                )
            # Um achado por trecho aceso: o primeiro instante que reprova.
            if motivo and trecho_com_achado != m["ids"]:
                achados.append(f"{t:.1f} s, alvo {' '.join(m['ids']) or '?'}: {motivo}")
                trecho_com_achado = m["ids"]
        navegador.close()
    if not acesos:
        achados.append(
            "o anel (#mk) não acende em instante nenhum: o gate não viu nada"
        )
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--composicao", type=Path, required=True)
    args = ap.parse_args()
    achados = checar(args.composicao)
    for achado in achados:
        print(f"ANEL: {achado}")
    if achados:
        return 1
    print("Anel OK: contorna o alvo em todo instante aceso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
