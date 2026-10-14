"""Testes do gate do anel do Vídeo de tarefa (tools/anel_video_manual.py).

Nota do Pedro no OK dos pilotos (PR #1246): o anel azul de destaque caía ao
lado do botão, começando no meio de "Painel" e cortando "Validação". A causa:
a composição media o alvo na montagem, antes de a fonte do app carregar, e a
medida saía com a fonte de reserva. O gate compara, em cada instante em que o
anel está aceso, a caixa do anel com a caixa do alvo que ele declara.

As caixas abaixo são as medidas do navegador (x, y, largura, altura, em pixels
do quadro de 1920x1080) no draft do print e no corrigido.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from anel_video_manual import desvio_do_anel, texto_sob_o_anel  # noqa: E402


def test_anel_deslocado_do_print_reprova():
    # Validação, 7,0 s: o anel começa em "Painel" e corta "Validação".
    anel = (847, 258, 226, 93)
    alvo = (924, 271, 192, 69)
    assert desvio_do_anel(anel, alvo)


def test_anel_mais_alto_que_o_alvo_reprova():
    # Validação, 32,5 s: medido com a fonte de reserva, o texto da Leitura da
    # IA quebrava em mais linhas e o anel descia 44 px abaixo do quadro.
    anel = (156, 625, 1614, 119)
    alvo = (169, 638, 1591, 62)
    assert desvio_do_anel(anel, alvo)


def test_anel_em_volta_do_alvo_passa():
    # O mesmo botão, com a medida feita depois da fonte: 8 px de folga
    # vezes o zoom de 1,45 da câmera em cada lado.
    anel = (912, 259, 216, 93)
    alvo = (924, 271, 192, 69)
    assert desvio_do_anel(anel, alvo) is None


def test_anel_menor_que_o_alvo_reprova():
    # O anel tem que contornar: se ele passa por dentro do alvo, corta o texto.
    anel = (930, 275, 180, 60)
    alvo = (924, 271, 192, 69)
    assert desvio_do_anel(anel, alvo)


def test_anel_que_passa_por_cima_do_rotulo_vizinho_reprova():
    # Redirecionar, 44 s: o anel contorna o valor "Faturamento", mas a folga
    # de cima corta o rótulo "SETOR" logo acima.
    anel = (830, 610, 720, 60)
    textos = [("SETOR", (842, 596, 64, 22)), ("Atendimento", (842, 700, 120, 22))]
    assert texto_sob_o_anel(anel, textos) == ["SETOR"]


def test_texto_longe_do_anel_passa():
    anel = (830, 610, 720, 60)
    textos = [("SETOR", (842, 560, 64, 22)), ("Atendimento", (842, 700, 120, 22))]
    assert texto_sob_o_anel(anel, textos) == []
