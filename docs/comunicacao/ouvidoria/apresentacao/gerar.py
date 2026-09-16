# /// script
# requires-python = ">=3.11"
# dependencies = ["python-pptx>=1.0", "pillow", "qrcode"]
# ///
"""Gera a apresentação da Ouvidoria (PowerPoint) a partir do manual publicado.

Uso:
    uv run docs/comunicacao/ouvidoria/apresentacao/gerar.py [--sem-videos] [--saida ARQUIVO]

O texto dos slides espelha a seção Ouvidoria do Manual do usuário. Os prints vêm
de docs/manual/src/assets/ouvidoria/. Os vídeos de capítulo vêm do manual
publicado na Vercel (não ficam no git) e são baixados para apresentacao/videos/
na primeira execução. O .pptx gerado fica fora do git, como os MP4 (ADR 0044).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[3]
MANUAL_IMG = REPO / "docs/manual/src/assets/ouvidoria"
# Telas que ainda não estão no manual publicado: prints tirados do app rodando
# na versão desta apresentação.
IMG_NOVA = AQUI / "img"
LOGO = REPO / "docs/comunicacao/_assets/logo-hsm.png"
MODELO = AQUI / "modelo.pptx"
VIDEOS = AQUI / "videos"
MANUAL_URL = "https://manual-hsm.vercel.app"
VERSAO_APP = "0.116.1"
DATA = "setembro de 2026"

# Design system do app (docs/manual/src/styles/tema.css, variáveis CSS)
FONTE = "HP Simplified"
AZUL = RGBColor(0x2B, 0x2E, 0x7E)
AZUL_ESCURO = RGBColor(0x1A, 0x1C, 0x4E)
AZUL_CLARO = RGBColor(0x3B, 0x6F, 0xB6)
VERDE = RGBColor(0x88, 0xD7, 0xA4)
LARANJA = RGBColor(0xFF, 0xC0, 0x67)
VERMELHO = RGBColor(0xFC, 0x9D, 0x9D)
TEXTO = RGBColor(0x1E, 0x29, 0x3B)
TEXTO_2 = RGBColor(0x64, 0x74, 0x8B)
BORDA = RGBColor(0xE2, 0xE8, 0xF0)
FUNDO_SUAVE = RGBColor(0xF6, 0xF7, 0xFB)
BRANCO = RGBColor(0xFF, 0xFF, 0xFF)

LARGURA = Inches(13.333)
ALTURA = Inches(7.5)
MARGEM = Inches(0.6)


# ---------------------------------------------------------------- utilitários


def _fonte(run, tamanho, cor=TEXTO, negrito=False):
    run.font.name = FONTE
    run.font.size = Pt(tamanho)
    run.font.color.rgb = cor
    run.font.bold = negrito


def texto(slide, x, y, w, h, linhas, tamanho=14, cor=TEXTO, negrito=False,
          alinhamento=PP_ALIGN.LEFT, ancora=MSO_ANCHOR.TOP, espaco=4):
    """Caixa de texto. `linhas` é str ou lista de str/(str, dict)."""
    caixa = slide.shapes.add_textbox(x, y, w, h)
    tf = caixa.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = ancora
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    if isinstance(linhas, str):
        linhas = [linhas]
    for i, linha in enumerate(linhas):
        opts = {}
        if isinstance(linha, tuple):
            linha, opts = linha
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinhamento
        p.space_before = Pt(0)
        p.space_after = Pt(espaco)
        p.line_spacing = 1.05
        run = p.add_run()
        run.text = linha
        _fonte(run, opts.get("tamanho", tamanho), opts.get("cor", cor),
               opts.get("negrito", negrito))
    return caixa


def retangulo(slide, x, y, w, h, cor, borda=None, arredondado=True):
    forma = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if arredondado else MSO_SHAPE.RECTANGLE,
        x, y, w, h)
    if arredondado:
        forma.adjustments[0] = 0.04
    forma.fill.solid()
    forma.fill.fore_color.rgb = cor
    if borda is None:
        forma.line.fill.background()
    else:
        forma.line.color.rgb = borda
        forma.line.width = Pt(0.75)
    forma.shadow.inherit = False
    forma.text_frame.text = ""
    return forma


def cartao(slide, x, y, w, h, titulo, corpo, cor_faixa=AZUL, tamanho_corpo=12,
           tamanho_titulo=14):
    retangulo(slide, x, y, w, h, BRANCO, borda=BORDA)
    retangulo(slide, x, y, Inches(0.08), h, cor_faixa, arredondado=False)
    texto(slide, x + Inches(0.2), y + Inches(0.1), w - Inches(0.3), Inches(0.4),
          titulo, tamanho=tamanho_titulo, cor=AZUL_ESCURO, negrito=True)
    texto(slide, x + Inches(0.2), y + Inches(0.5), w - Inches(0.3), h - Inches(0.6),
          corpo, tamanho=tamanho_corpo, cor=TEXTO)


def imagem_ajustada(slide, caminho, x, y, w, h, legenda=None, borda=True):
    """Encaixa a imagem dentro da caixa (x, y, w, h) sem distorcer."""
    with Image.open(caminho) as im:
        iw, ih = im.size
    escala = min(w / iw, h / ih)
    lw, lh = int(iw * escala), int(ih * escala)
    px = x + (w - lw) // 2
    py = y
    pic = slide.shapes.add_picture(str(caminho), px, py, lw, lh)
    if borda:
        pic.line.color.rgb = BORDA
        pic.line.width = Pt(0.75)
    if legenda:
        texto(slide, x, py + lh + Inches(0.05), w, Inches(0.5), legenda,
              tamanho=10, cor=TEXTO_2, alinhamento=PP_ALIGN.CENTER)
    return pic


def tabela(slide, x, y, w, cabecalho, linhas, larguras, tamanho=11,
           altura_linha=Inches(0.42)):
    n_lin = len(linhas) + 1
    n_col = len(cabecalho)
    forma = slide.shapes.add_table(n_lin, n_col, x, y, w, altura_linha * n_lin)
    tab = forma.table
    total = sum(larguras)
    for i, frac in enumerate(larguras):
        tab.columns[i].width = int(w * frac / total)
    for r in range(n_lin):
        tab.rows[r].height = altura_linha
    for c, titulo in enumerate(cabecalho):
        cel = tab.cell(0, c)
        cel.fill.solid()
        cel.fill.fore_color.rgb = AZUL
        _celula(cel, titulo, tamanho, BRANCO, True)
    for r, linha in enumerate(linhas, start=1):
        for c, valor in enumerate(linha):
            cel = tab.cell(r, c)
            cel.fill.solid()
            cel.fill.fore_color.rgb = BRANCO if r % 2 else FUNDO_SUAVE
            _celula(cel, valor, tamanho, TEXTO, c == 0)
    return forma


def _celula(cel, valor, tamanho, cor, negrito):
    cel.margin_left = cel.margin_right = Inches(0.08)
    cel.margin_top = cel.margin_bottom = Inches(0.04)
    cel.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cel.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    p.line_spacing = 1.0
    run = p.add_run()
    run.text = valor
    _fonte(run, tamanho, cor, negrito)


def notas(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt


# ---------------------------------------------------------------- moldura


class Deck:
    def __init__(self, com_videos: bool):
        # modelo.pptx foi exportado pelo Keynote só para trazer um modelo de notas
        # do apresentador que Keynote e PowerPoint aceitam (o padrão da python-pptx
        # o Keynote recusa como "formato inválido").
        self.prs = Presentation(MODELO)
        lista = self.prs.slides._sldIdLst
        for sid in list(lista):
            self.prs.part.drop_rel(sid.rId)
            lista.remove(sid)
        self.prs.slide_width = LARGURA
        self.prs.slide_height = ALTURA
        self.branco = next(l for l in self.prs.slide_layouts if l.name == "Em Branco")
        self.com_videos = com_videos
        self.n = 0

    def novo(self):
        self.n += 1
        s = self.prs.slides.add_slide(self.branco)
        for forma in list(s.shapes):
            forma._element.getparent().remove(forma._element)
        return s

    def rodape(self, slide, escuro=False):
        cor = BRANCO if escuro else TEXTO_2
        texto(slide, MARGEM, ALTURA - Inches(0.45), Inches(6), Inches(0.3),
              "Ouvidoria · Plataforma de Gestão · Hospital São Matheus",
              tamanho=9, cor=cor)
        texto(slide, LARGURA - MARGEM - Inches(1), ALTURA - Inches(0.45), Inches(1),
              Inches(0.3), str(self.n), tamanho=9, cor=cor, alinhamento=PP_ALIGN.RIGHT)

    def logo(self, slide, x, y, altura):
        with Image.open(LOGO) as im:
            iw, ih = im.size
        largura = int(altura * iw / ih)
        return slide.shapes.add_picture(str(LOGO), x, y, largura, altura)

    def conteudo(self, rotulo, titulo, subtitulo=None):
        """Slide de conteúdo com faixa de rótulo, título e rodapé."""
        s = self.novo()
        retangulo(s, 0, 0, LARGURA, Inches(0.12), AZUL, arredondado=False)
        texto(s, MARGEM, Inches(0.3), Inches(9), Inches(0.3), rotulo.upper(),
              tamanho=10, cor=AZUL_CLARO, negrito=True)
        texto(s, MARGEM, Inches(0.55), Inches(10.5), Inches(0.7), titulo,
              tamanho=26, cor=AZUL_ESCURO, negrito=True)
        y_sub = Inches(1.2)
        if subtitulo:
            texto(s, MARGEM, Inches(1.2), Inches(11.5), Inches(0.5), subtitulo,
                  tamanho=13, cor=TEXTO_2)
            y_sub = Inches(1.75)
        self.logo(s, LARGURA - MARGEM - Inches(1.4), Inches(0.28), Inches(0.75))
        self.rodape(s)
        return s, y_sub

    def abertura(self, numero, titulo, intro, pontos, video, duracao):
        """Abertura de capítulo: fundo escuro, texto à esquerda, vídeo à direita."""
        s = self.novo()
        retangulo(s, 0, 0, LARGURA, ALTURA, AZUL_ESCURO, arredondado=False)
        retangulo(s, 0, 0, Inches(0.18), ALTURA, LARANJA, arredondado=False)
        texto(s, MARGEM, Inches(0.7), Inches(3), Inches(0.4),
              f"CAPÍTULO {numero}", tamanho=12, cor=VERDE, negrito=True)
        texto(s, MARGEM, Inches(1.05), Inches(6), Inches(1.4), titulo,
              tamanho=34, cor=BRANCO, negrito=True)
        texto(s, MARGEM, Inches(2.5), Inches(5.9), Inches(1.6), intro,
              tamanho=14, cor=BRANCO)
        y = Inches(4.15)
        for ponto in pontos:
            retangulo(s, MARGEM, y + Inches(0.1), Inches(0.1), Inches(0.1), VERDE,
                      arredondado=False)
            texto(s, MARGEM + Inches(0.25), y - Inches(0.02), Inches(5.6), Inches(0.5),
                  ponto, tamanho=12, cor=BRANCO)
            y += Inches(0.42)
        # vídeo
        vx, vy = Inches(7.0), Inches(1.3)
        vw = LARGURA - vx - MARGEM
        vh = int(vw * 9 / 16)
        poster = VIDEOS / f"poster-cap{numero}.png"
        mp4 = VIDEOS / f"video-cap{numero}.mp4"
        if self.com_videos and mp4.exists():
            s.shapes.add_movie(str(mp4), vx, vy, vw, vh,
                               poster_frame_image=str(poster) if poster.exists() else None,
                               mime_type="video/mp4")
            legenda = f"Vídeo do capítulo · {duracao} · sem narração · clique para assistir"
        else:
            if poster.exists():
                s.shapes.add_picture(str(poster), vx, vy, vw, vh)
            else:
                retangulo(s, vx, vy, vw, vh, AZUL)
            legenda = f"Vídeo do capítulo · {duracao} · em {MANUAL_URL}"
        texto(s, vx, vy + vh + Inches(0.1), vw, Inches(0.4), legenda,
              tamanho=10, cor=VERDE, alinhamento=PP_ALIGN.CENTER)
        self.rodape(s, escuro=True)
        return s


# ---------------------------------------------------------------- slides


def slide_capa(d: Deck):
    s = d.novo()
    retangulo(s, 0, 0, Inches(0.35), ALTURA, AZUL, arredondado=False)
    retangulo(s, Inches(0.35), 0, Inches(0.12), ALTURA, LARANJA, arredondado=False)
    d.logo(s, Inches(1.1), Inches(0.7), Inches(1.1))
    texto(s, Inches(1.1), Inches(2.3), Inches(10.5), Inches(0.4),
          "PLATAFORMA DE GESTÃO · MÓDULO DE OUVIDORIA", tamanho=12, cor=AZUL_CLARO,
          negrito=True)
    texto(s, Inches(1.1), Inches(2.75), Inches(11), Inches(2),
          "O que acontece com o que as pessoas contam para a gente",
          tamanho=40, cor=AZUL_ESCURO, negrito=True)
    texto(s, Inches(1.1), Inches(4.7), Inches(10.5), Inches(1.0),
          "A Ouvidoria do começo ao fim, com as telas de verdade do sistema. "
          "Mostra um processo do hospital, passo a passo, para quem trabalha nele.",
          tamanho=16, cor=TEXTO_2)
    texto(s, Inches(1.1), Inches(6.3), Inches(10), Inches(0.4),
          f"Para as áreas do hospital · {DATA} · sistema na versão {VERSAO_APP}",
          tamanho=11, cor=TEXTO_2)
    notas(s, "Abertura. Diga a quem é: quem recebe casos da Ouvidoria, quem cobra "
             "respostas, ou quem só quer entender o que acontece quando alguém reclama. "
             "Os slides seguem a mesma ordem do manual publicado.")


def slide_uma_pagina(d: Deck):
    s, y = d.conteudo("Antes de começar", "Como funciona, em uma página")
    texto(s, MARGEM, y, Inches(12), Inches(0.9),
          "Toda manifestação de paciente vira um caso com número, dono e prazo. "
          "Quem escreve, quem lê o QR na parede e a assistente do WhatsApp só registram. "
          "Quem decide é sempre uma pessoa: o ouvidor.", tamanho=15)
    numeros = [
        ("4", "portas por onde um caso entra", AZUL),
        ("1", "pessoa decide a gravidade: o ouvidor", AZUL_CLARO),
        ("4 h", "é o prazo mais curto, para caso grave", LARANJA),
        ("0", "casos parados sem alguém cobrando", VERDE),
    ]
    largura = Inches(2.85)
    gap = Inches(0.25)
    x = MARGEM
    yt = Inches(2.5)
    for grande, legenda, cor in numeros:
        retangulo(s, x, yt, largura, Inches(2.2), BRANCO, borda=BORDA)
        retangulo(s, x, yt, largura, Inches(0.1), cor, arredondado=False)
        texto(s, x, yt + Inches(0.3), largura, Inches(1), grande, tamanho=54,
              cor=AZUL_ESCURO, negrito=True, alinhamento=PP_ALIGN.CENTER)
        texto(s, x + Inches(0.2), yt + Inches(1.4), largura - Inches(0.4), Inches(0.7),
              legenda, tamanho=13, cor=TEXTO_2, alinhamento=PP_ALIGN.CENTER)
        x += largura + gap
    etiquetas = ["Feito para quem trabalha no hospital", "Telas reais do sistema",
                 "Um vídeo por capítulo", "Tudo o que está em produção hoje"]
    x = MARGEM
    for e in etiquetas:
        w = Inches(2.85)
        retangulo(s, x, Inches(5.2), w, Inches(0.5), FUNDO_SUAVE)
        texto(s, x, Inches(5.2), w, Inches(0.5), e, tamanho=11, cor=AZUL,
              alinhamento=PP_ALIGN.CENTER, ancora=MSO_ANCHOR.MIDDLE)
        x += w + gap
    texto(s, MARGEM, Inches(6.0), Inches(12), Inches(0.6),
          "Uma regra vale para tudo: nenhuma porta de entrada decide nada. "
          "O tipo, o setor, a gravidade e o sigilo são sempre escolha do ouvidor, depois de ler.",
          tamanho=12, cor=TEXTO_2)
    notas(s, "Os quatro números resumem o módulo. Destaque o zero: o sistema cobra "
             "sozinho e sobe a escada até a Diretoria.")


def slide_seis_palavras(d: Deck):
    s, y = d.conteudo("Antes de começar", "As seis palavras que você vai ver o tempo todo",
                      "O sistema usa sempre as mesmas palavras. Se estas seis ficarem claras, "
                      "o resto fica fácil.")
    cards = [
        ("Manifestação", "Tudo que uma pessoa conta para a Ouvidoria: reclamação, elogio, "
         "sugestão, denúncia. Também chamamos de caso. Ganha um número na hora."),
        ("Protocolo", "O número da manifestação, no formato 2026-0001. Nasce sozinho, na "
         "ordem de chegada. É o que a pessoa guarda."),
        ("Ouvidor", "Quem lê o relato, decide do que se trata, escolhe o setor e cobra a "
         "resposta. Nenhuma decisão é automática."),
        ("Responsável do setor", "Quem responde pela área quando um caso chega nela. Não "
         "precisa de login: recebe um e-mail com um botão e responde por ali."),
        ("Gravidade", "O tamanho do problema, em quatro degraus: crítico, alto, médio e "
         "baixo. Define quanto tempo o setor tem. Quem escolhe é o ouvidor."),
        ("Situação", "Onde o caso está agora: esperando a Ouvidoria, esperando o setor, "
         "esperando o manifestante, respondido ou encerrado. Muda sozinha."),
    ]
    w, h = Inches(3.9), Inches(2.1)
    gap = Inches(0.2)
    for i, (t, c) in enumerate(cards):
        col, lin = i % 3, i // 3
        cartao(s, MARGEM + col * (w + gap), y + Inches(0.1) + lin * (h + gap), w, h, t, c,
               cor_faixa=[AZUL, AZUL_CLARO, VERDE][col])
    notas(s, "Vocabulário. Peça para as áreas usarem as mesmas palavras. 'Caso' e "
             "'manifestação' são a mesma coisa. 'Responsável do setor' é quem vai receber o "
             "e-mail: pode ser gente da própria plateia.")


def slide_caminho(d: Deck):
    s, y = d.conteudo("Antes de começar", "O caminho de um caso, do começo ao fim",
                      "Todo caso segue os mesmos cinco passos. Os capítulos são esses passos, na ordem.")
    passos = [
        ("A pessoa conta", "Por uma das quatro portas. Recebe o protocolo na hora e um e-mail "
         "avisando que chegou."),
        ("O ouvidor lê e encaminha", "Decide do que se trata, qual setor responde e o tamanho "
         "do problema. O setor recebe o e-mail com o prazo."),
        ("O setor conta o que fez", "O responsável abre o link do e-mail, lê e escreve o que "
         "foi feito para corrigir. Sem login."),
        ("O sistema cobra sozinho", "Se o prazo se aproxima, avisa. Se vence, cobra. Se "
         "continua parado, sobe para o gestor e depois para a Diretoria."),
        ("A Ouvidoria encerra e avisa", "O ouvidor lê a resposta, encerra com uma conclusão e "
         "a pessoa recebe um e-mail contando no que deu."),
    ]
    w = Inches(2.3)
    gap = Inches(0.16)
    x = MARGEM
    yt = y + Inches(0.15)
    for i, (t, c) in enumerate(passos):
        cor = [AZUL, AZUL, AZUL_CLARO, LARANJA, VERDE][i]
        retangulo(s, x, yt, w, Inches(0.7), cor)
        texto(s, x, yt, w, Inches(0.7), str(i + 1), tamanho=24, cor=BRANCO, negrito=True,
              alinhamento=PP_ALIGN.CENTER, ancora=MSO_ANCHOR.MIDDLE)
        retangulo(s, x, yt + Inches(0.7), w, Inches(2.1), BRANCO, borda=BORDA)
        texto(s, x + Inches(0.12), yt + Inches(0.85), w - Inches(0.24), Inches(0.7), t,
              tamanho=13, cor=AZUL_ESCURO, negrito=True)
        texto(s, x + Inches(0.12), yt + Inches(1.5), w - Inches(0.24), Inches(1.3), c,
              tamanho=11, cor=TEXTO)
        x += w + gap
    retangulo(s, MARGEM, Inches(5.1), Inches(12.1), Inches(0.95), FUNDO_SUAVE)
    texto(s, MARGEM + Inches(0.2), Inches(5.15), Inches(11.7), Inches(0.9), [
        ("O sistema nunca aciona um setor por conta própria.", {"negrito": True, "cor": AZUL_ESCURO}),
        "Só o ouvidor aciona uma área, e sempre depois de ler. Sozinho, o sistema cobra quem "
        "já foi acionado e avisa quem precisa saber.",
    ], tamanho=12)
    notas(s, "Mostre que os cinco passos são os capítulos. O passo 4 é o único que a máquina "
             "faz sozinha, e mesmo assim só cobra quem já foi acionado por uma pessoa.")


# capítulo 1 ----------------------------------------------------------------


def cap1(d: Deck):
    s = d.abertura(1, "Por onde o caso chega",
                   "São quatro portas. Todas terminam no mesmo lugar: um caso com número "
                   "próprio, esperando o ouvidor ler. Nenhuma delas decide setor, tipo ou gravidade.",
                   ["Pelo site, sem senha: a pessoa escreve e recebe o número na tela.",
                    "Pelo cartaz na parede: a mesma página, aberta pelo QR. Já diz de onde veio.",
                    "Pelo WhatsApp, com a Ana: a assistente registra. Ela não classifica.",
                    "Pelo telefone ou pelo balcão: o ouvidor digita, com a hora real do contato."],
                   video=1, duracao="0:55")
    notas(s, "Vídeo: um elogio entra pelo cartaz do Pronto Atendimento e a página do caso "
             "mostra de onde veio. Reforce: porta de entrada nunca decide nada.")

    s, y = d.conteudo("Capítulo 1 · Por onde o caso chega", "Pelo site, sem senha")
    texto(s, MARGEM, y, Inches(6.2), Inches(4.8), [
        ("Uma página aberta na internet, feita pensando no celular.", {"negrito": True, "cor": AZUL_ESCURO}),
        "O único campo obrigatório é o relato. Dizer o nome é opcional, e existe uma caixa "
        "para quem quer ficar anônimo.",
        "Quatro botões para a pessoa dizer do que se trata, com Elogio na frente de propósito. "
        "Ninguém é obrigado a escolher. O que ela marcar aparece depois como \"O manifestante "
        "informou\", opinião dela, não classificação do hospital.",
        "O relato aceita até dez mil letras. A pessoa conta a história inteira, do jeito dela, "
        "e o texto entra no caso sem ninguém editar.",
        "Proteções que ninguém vê: limite de envios por minuto e uma armadilha invisível "
        "contra robôs.",
        "O caso nasce sem tipo definido e, por segurança, é tratado como sigiloso até o ouvidor "
        "ler e classificar.",
    ], tamanho=12, espaco=8)
    imagem_ajustada(s, MANUAL_IMG / "formulario-publico-mobile.png", Inches(7.1), y,
                    Inches(1.6), Inches(4.7), legenda="No celular, pelo QR do Pronto Atendimento")
    imagem_ajustada(s, MANUAL_IMG / "formulario-publico-desktop.png", Inches(8.9), y,
                    Inches(3.85), Inches(4.7), legenda="No computador, a mesma página")
    notas(s, "O formulário público. Destaque a origem no topo (quando vem do QR) e o protocolo "
             "que aparece na própria tela ao enviar, sem esperar e-mail.")

    s, y = d.conteudo("Capítulo 1 · Por onde o caso chega", "Pelo cartaz na parede")
    texto(s, MARGEM, y, Inches(5.6), Inches(4.9), [
        ("Cada cartaz é um Ponto de escuta:", {"negrito": True, "cor": AZUL_ESCURO}),
        "um setor, um nome de lugar (\"Sala de espera\") e um código curto de seis letras. "
        "O QR não leva direto ao formulário: leva a um endereço do hospital que decide para "
        "onde mandar a pessoa.",
        "Se um dia o QR tiver que abrir a conversa da Ana em vez do formulário, nenhum cartaz "
        "precisa ser reimpresso. Muda o destino no sistema.",
        ("Como fazer um cartaz novo", {"negrito": True, "cor": AZUL_ESCURO}),
        "1. Abra a tela Pontos de escuta, no menu da Ouvidoria.",
        "2. Escolha o setor e dê um nome ao lugar. O código sai sozinho.",
        "3. Baixe o \"Cartaz A5\": um PDF pronto, com a logo, o QR e o endereço.",
        "4. Imprima em A5 e cole.",
        "Para tirar de circulação, aposente. Não apaga nada: o cartaz continua funcionando, "
        "só para de dizer de onde a pessoa está falando.",
        ("O setor do cartaz não é o setor responsável.", {"negrito": True, "cor": AZUL_ESCURO}),
        "Ele diz de onde a pessoa falou, não quem tem que responder. Isso é sempre o ouvidor.",
    ], tamanho=11, espaco=5)
    imagem_ajustada(s, MANUAL_IMG / "pontos.png", Inches(6.5), y, Inches(3.6), Inches(4.7),
                    legenda="A tela Pontos de escuta")
    imagem_ajustada(s, MANUAL_IMG / "cartaz-pa.png", Inches(10.3), y, Inches(2.45), Inches(4.7),
                    legenda="O cartaz A5 sai pronto")
    notas(s, "Pontos de escuta. Quem cadastra e imprime é o ouvidor ou a Diretoria, na "
             "própria tela. Se a área quiser um cartaz novo, pede à Ouvidoria.")

    s, y = d.conteudo("Capítulo 1 · Por onde o caso chega",
                      "Pelo WhatsApp, com a Ana, e pelo telefone ou pelo balcão")
    cartao(s, MARGEM, y, Inches(5.9), Inches(2.3), "Pelo WhatsApp, com a Ana",
           "A Ana é a assistente que conversa com pacientes e acompanhantes pelo WhatsApp. "
           "Ela não é usuária do sistema: registra o caso por uma porta própria, com nome, "
           "contato e o relato inteiro. Ela também guarda um palpite sobre a gravidade, mas "
           "o palpite fica separado e nunca vira a classificação. Se tentar mandar uma decisão "
           "que é do ouvidor, o sistema recusa e diz por quê.", cor_faixa=VERDE)
    cartao(s, MARGEM, y + Inches(2.5), Inches(5.9), Inches(2.3), "Pelo telefone ou pelo balcão",
           "Nem todo mundo escreve. O botão \"Nova manifestação\" abre um formulário onde o "
           "ouvidor digita o caso que chegou por telefone, presencialmente ou por e-mail. "
           "A data e a hora são as do contato de verdade, não as do clique: um telefonema "
           "de ontem entra com a hora de ontem, e o prazo conta a partir dali. O que a pessoa "
           "disse entra inteiro, sem resumo e sem correção.", cor_faixa=AZUL_CLARO)
    imagem_ajustada(s, MANUAL_IMG / "nova-manifestacao-modal.png", Inches(6.9), y,
                    Inches(5.85), Inches(4.5),
                    legenda="Registro feito pelo ouvidor. Anexa foto, PDF, áudio ou documento de até 20 MB.")
    notas(s, "As duas portas que passam por gente. A Ana registra e não classifica. O balcão "
             "continua existindo, e a hora que vale é a do contato real.")


# capítulo 2 ----------------------------------------------------------------


def cap2(d: Deck):
    s = d.abertura(2, "A Ouvidoria lê e encaminha",
                   "É aqui que o caso deixa de ser um relato solto e vira uma demanda com dono "
                   "e com prazo. Tudo acontece em um clique só, e esse clique é sempre de uma pessoa.",
                   ["A lista de casos, na ordem do trabalho do dia.",
                    "Classificar e acionar: quatro coisas acontecem no mesmo clique.",
                    "O que é sigiloso, e quem vê o quê.",
                    "A página do caso: onde este caso emperrou."],
                   video=2, duracao="0:58")
    notas(s, "Vídeo: o ponto azul, a tela de classificar e o caso mudando de faixa com o "
             "e-mail saindo.")

    s, y = d.conteudo("Capítulo 2 · A Ouvidoria lê e encaminha", "A lista de casos")
    imagem_ajustada(s, MANUAL_IMG / "fila.png", MARGEM, y, Inches(6.6), Inches(4.75),
                    legenda="A lista. O ponto azul: a Ouvidoria ainda não viu. Laranja: vence em menos de um dia.")
    xc = Inches(7.5)
    wc = Inches(5.25)
    texto(s, xc, y, wc, Inches(0.9),
          "Agrupa os casos por situação, na ordem do trabalho do dia: primeiro o que espera o "
          "ouvidor encerrar, depois o que não foi lido, depois o que está com os setores.",
          tamanho=12)
    cartao(s, xc, y + Inches(1.0), wc, Inches(1.1), "Três informações, três lugares fixos",
           "Situação na faixa colorida. Gravidade na etiqueta redonda. Prazo na cor da data. "
           "Nunca trocam de lugar.", tamanho_corpo=11, tamanho_titulo=12)
    cartao(s, xc, y + Inches(2.2), wc, Inches(1.1), "O ponto azul é do caso, não da pessoa",
           "Abrir, classificar ou encerrar apaga o ponto para todos. Pausa, devolução e resposta "
           "do setor não apagam: são novidades a ver.", tamanho_corpo=11, tamanho_titulo=12,
           cor_faixa=AZUL_CLARO)
    cartao(s, xc, y + Inches(3.4), wc, Inches(1.1), "A cor da data é só sobre tempo",
           "Vermelho: venceu ou vence hoje. Laranja: menos de um dia de folga. Cinza: o resto. "
           "Nada a ver com a cor da gravidade.", tamanho_corpo=11, tamanho_titulo=12,
           cor_faixa=LARANJA)
    notas(s, "Cada linha tem dois andares: em cima o que identifica o caso, embaixo quem cuida "
             "e até quando. À direita, a única ação que faz sentido agora. O botão Cobrar vai "
             "para quem responde hoje, não para quem recebeu o e-mail original.")

    s, y = d.conteudo("Capítulo 2 · A Ouvidoria lê e encaminha", "Classificar e acionar",
                      "Quando o ouvidor confirma, quatro coisas acontecem ao mesmo tempo: o caso "
                      "muda de situação, o prazo é calculado e congelado, a decisão fica registrada "
                      "e o responsável recebe o e-mail.")
    tabela(s, MARGEM, y, Inches(6.6), ["Campo", "O que é"], [
        ("Tipo", "Denúncia, reclamação, sugestão, elogio, relato de conduta ou informação. "
         "É o tipo, e só ele, que faz um caso nascer sigiloso."),
        ("Área responsável", "Da lista de setores. Sem titular no momento, sobe direto para o "
         "gestor e a Diretoria é avisada. Sem titular e sem gestor, o sistema recusa."),
        ("Gravidade", "Crítico, alto, médio ou baixo. Define o prazo. Caso crítico avisa a "
         "Diretoria na hora, inclusive de madrugada."),
        ("Recado para o setor", "O texto do ouvidor, com as palavras dele. É o que vai no "
         "e-mail e na tela de quem responde."),
    ], larguras=[1.1, 3.2], tamanho=11, altura_linha=Inches(0.78))
    retangulo(s, MARGEM, y + Inches(4.05), Inches(6.6), Inches(0.75), FUNDO_SUAVE)
    texto(s, MARGEM + Inches(0.15), y + Inches(4.08), Inches(6.3), Inches(0.7),
          "Sem o recado para o setor, o botão nem liga. O responsável é de fora da Ouvidoria e "
          "o relato não sai dali: o recado é a única coisa que explica o que resolver.",
          tamanho=11, cor=AZUL_ESCURO)
    imagem_ajustada(s, MANUAL_IMG / "validar-modal.png", Inches(7.5), y, Inches(5.25), Inches(4.7),
                    legenda="Nada vem preenchido pela Ana nem pelo formulário: a decisão começa em branco.")
    notas(s, "O clique mais importante do módulo. Mostre que o palpite da Ana e o que a pessoa "
             "marcou ficam guardados à parte. A decisão começa em branco.")

    s, y = d.conteudo("Capítulo 2 · A Ouvidoria lê e encaminha", "O que é sigiloso",
                      "Denúncia e relato de conduta nascem sigilosos em qualquer porta. Caso ainda "
                      "não classificado também é tratado como sigiloso, por segurança.")
    tabela(s, MARGEM, y, Inches(8.3), ["Situação", "Quem vê o caso completo", "O que o setor recebe"], [
        ("Caso comum", "Ouvidor e Diretoria veem tudo. O resto do sistema vê só o índice: "
         "número, setor, situação e prazo.", "Resumo, relato inteiro, recado da Ouvidoria e quem falou."),
        ("Caso sigiloso", "Só ouvidor e Diretoria. Nem aparece na lista de quem está fora.",
         "Só o recado da Ouvidoria. Sem resumo, sem relato, sem nome."),
        ("Caso anônimo", "Como o comum, mas sem os dados de quem falou.",
         "Só o recado. O anonimato se desfaria no texto do relato."),
        ("Quem administra o sistema", "Fica de fora por regra: quem cuida do sistema não lê denúncia.",
         "Não recebe."),
    ], larguras=[1.3, 3.2, 3.0], tamanho=11, altura_linha=Inches(0.7))
    texto(s, MARGEM, y + Inches(3.7), Inches(8.3), Inches(1.1), [
        ("O sigilo automático é o mínimo.", {"negrito": True, "cor": AZUL_ESCURO}),
        "O ouvidor pode aumentar o sigilo de um caso que a lista não previu. Ele não pode tirar "
        "o sigilo de um tipo que já nasce sigiloso. Tirar o sigilo fica registrado no histórico "
        "e no registro de quem acessou.",
    ], tamanho=11)
    imagem_ajustada(s, MANUAL_IMG / "caso-denuncia-sigilosa.png", Inches(9.3), y,
                    Inches(3.45), Inches(4.7), legenda="Denúncia anônima: a caixa de sigilo não desmarca.")
    notas(s, "Sigilo é regra do sistema, não do combinado. Nem quem administra o sistema lê "
             "denúncia. Para a área, o caso sigiloso chega só com o recado do ouvidor.")

    s, y = d.conteudo("Capítulo 2 · A Ouvidoria lê e encaminha", "A página do caso",
                      "Cada caso tem uma página própria, pelo número do protocolo. Ela mostra "
                      "onde este caso emperrou.")
    imagem_ajustada(s, MANUAL_IMG / "caso-respondido.png", MARGEM, y, Inches(2.75), Inches(4.75),
                    legenda="Um caso respondido pelo setor")
    xc = Inches(3.7)
    wc = Inches(4.4)
    cartao(s, xc, y, wc, Inches(2.2), "Os quatro momentos",
           "Entrada (hora real do contato), validação (quando o ouvidor encaminhou), resposta "
           "(quando o setor respondeu) e conclusão (quando a Ouvidoria encerrou). A página mostra "
           "quanto tempo de expediente passou entre cada um.", tamanho_corpo=11)
    cartao(s, xc, y + Inches(2.4), wc, Inches(2.2), "O histórico não se apaga",
           "Todo movimento grava o que era antes, o que virou, quem fez e quando. Ninguém edita e "
           "ninguém apaga, nem quem administra o sistema. Erro se conserta com um movimento novo.",
           tamanho_corpo=11, cor_faixa=AZUL_CLARO)
    xc2 = xc + wc + Inches(0.25)
    cartao(s, xc2, y, wc, Inches(2.2), "Os e-mails ficam registrados",
           "Todo e-mail existe primeiro como registro no caso, antes de sair. É isso que prova que "
           "a cobrança foi feita, e é daí que sai o botão \"Reenviar\". O reenvio vira registro "
           "novo, sem apagar o original.", tamanho_corpo=11, cor_faixa=VERDE)
    cartao(s, xc2, y + Inches(2.4), wc, Inches(2.2), "Encerrar exige duas coisas",
           "Uma conclusão escolhida numa lista e um texto explicando. Sem os dois, o caso não "
           "fecha. O encerramento dispara o aviso para quem falou.", tamanho_corpo=11,
           cor_faixa=LARANJA)
    notas(s, "A página do caso, de cima para baixo: de onde veio, o que a pessoa marcou, os "
             "dados, os quatro momentos, a classificação, o resumo, o relato, os e-mails, a "
             "resposta do setor e o histórico.")


# capítulo 3 ----------------------------------------------------------------


def cap3(d: Deck):
    s = d.abertura(3, "O setor responde",
                   "Quem responde pela área é a pessoa menos treinada no sistema, e o sistema foi "
                   "feito sabendo disso. Ela recebe um e-mail com um botão, abre no celular, lê e "
                   "responde ali mesmo, sem login e sem treinamento.",
                   ["O link vale para aquele caso e aquela pessoa. Tem validade e é usado uma vez.",
                    "A tela tem ordem fixa: gravidade e prazo primeiro.",
                    "Três blocos de texto separados de propósito.",
                    "Resposta curta não liga o botão.",
                    "Se o caso não é da área, ela devolve à Ouvidoria pelo mesmo link."],
                   video=3, duracao="1:00")
    notas(s, "Este é o capítulo da plateia. Vídeo: o e-mail de acionamento, a tela do "
             "responsável e a resposta curta que não liga o botão.")

    s, y = d.conteudo("Capítulo 3 · O setor responde", "A tela de quem responde")
    imagem_ajustada(s, MANUAL_IMG / "portal-setor-mobile.png", MARGEM, y, Inches(1.3), Inches(4.7),
                    legenda="No celular")
    imagem_ajustada(s, MANUAL_IMG / "portal-setor-desktop.png", Inches(2.1), y, Inches(4.6),
                    Inches(4.7), legenda="No computador, em duas colunas")
    xc = Inches(7.2)
    wc = Inches(5.55)
    texto(s, xc, y, wc, Inches(1.3),
          "Ordem fixa: gravidade, prazo em contagem regressiva, número, setor e assunto, quem "
          "falou, os três blocos de texto, o campo único, os dois botões e, por último, o link "
          "de devolver. Nada entra entre a gravidade e o prazo: a ordem da tela substitui o "
          "treinamento que a pessoa não teve.",
          tamanho=12)
    cartao(s, xc, y + Inches(1.5), wc, Inches(2.0), "Os três blocos de texto", [
        "Resumo: uma frase sobre o que aconteceu.",
        "Relato integral: as palavras da pessoa, sem edição.",
        "Recado da Ouvidoria: o que o ouvidor pede que seja apurado.",
        "Separados, a área responde ao paciente, e não à interpretação da Ouvidoria. Em caso "
        "sigiloso ou anônimo, sai só o recado.",
    ], tamanho_corpo=11)
    cartao(s, xc, y + Inches(3.7), wc, Inches(1.05), "O link é de uso único",
           "Vale para aquele caso e aquela pessoa, tem validade e some depois da resposta. Se o "
           "caso voltar para o setor, sai um link novo.", tamanho_corpo=11, cor_faixa=AZUL_CLARO)
    notas(s, "Peça para a plateia olhar a tela como quem vai recebê-la. Anexo é opcional: foto, "
             "PDF, áudio ou documento até 20 MB.")

    s, y = d.conteudo("Capítulo 3 · O setor responde", "Quando o caso não é do seu setor",
                      "A área que recebe um caso que não é dela devolve à Ouvidoria pelo mesmo "
                      "link, com o motivo escrito. Quem escolhe a área certa continua sendo o ouvidor.")
    imagem_ajustada(s, IMG_NOVA / "portal-devolucao-fim.png", MARGEM, y, Inches(5.9), Inches(2.9),
                    legenda="O que a área vê: o link fica no fim da tela e abre o campo do motivo")
    imagem_ajustada(s, IMG_NOVA / "caso-devolvido.png", Inches(6.9), y, Inches(5.85), Inches(2.9),
                    legenda="O que o ouvidor vê: o motivo no topo do caso e o botão de encaminhar")
    cards = [
        ("Um link discreto, no fim da tela",
         "\"Este caso não é do meu setor?\" abre o campo. Fica abaixo dos dois botões e em letra "
         "menor: devolver não pode ser mais fácil do que responder.", AZUL),
        ("A área não escolhe o destino",
         "Ela escreve por que o caso não é dela. Se souber de quem é, escreve também, e isso "
         "ajuda. Quem despacha continua sendo o ouvidor.", AZUL_CLARO),
        ("O que acontece no mesmo clique",
         "O caso volta para a fila da Ouvidoria, o relógio da área para e o link deixa de valer. "
         "A Ouvidoria e a Diretoria recebem um e-mail com o setor e o motivo.", LARANJA),
        ("A área certa recebe o prazo inteiro",
         "O ouvidor encaminha pela mesma tela de validar, já preenchida, e o relógio da área nova "
         "começa do zero. O tempo perdido com a área errada fica na conta da Ouvidoria.", VERDE),
    ]
    wc = Inches(2.87)
    gap = Inches(0.2)
    for i, (titulo, corpo, cor) in enumerate(cards):
        cartao(s, MARGEM + i * (wc + gap), y + Inches(3.4), wc, Inches(1.75), titulo, corpo,
               cor_faixa=cor, tamanho_corpo=10, tamanho_titulo=12)
    notas(s, "Novidade desta versão. Para as áreas: se o caso não é seu, não responda por "
             "responder. Devolva pelo link, com o motivo. O caso não morre: ele volta para o "
             "ouvidor no mesmo protocolo, e o manifestante não ganha um número novo.")

    s, y = d.conteudo("Capítulo 3 · O setor responde",
                      "O que o sistema recusa, e o que vem depois da resposta")
    tabela(s, MARGEM, y, Inches(6.6), ["Tentativa", "O que acontece"], [
        ("Resposta muito curta", "O botão fica apagado até ter pelo menos vinte letras. A tela "
         "pede: conte o que foi feito para corrigir."),
        ("Resposta gigante", "Um aviso aparece perto do limite, e o botão trava se passar."),
        ("Mais prazo depois de vencer", "Recusado. O pedido tem que ser feito antes do vencimento."),
        ("Mais prazo duas vezes", "Recusado. Vale uma vez por caso."),
        ("Mais prazo sem explicar", "Recusado. A justificativa é obrigatória e vai para o ouvidor."),
    ], larguras=[1.6, 3.2], tamanho=11, altura_linha=Inches(0.7))
    xc = Inches(7.5)
    wc = Inches(5.25)
    passos = [
        ("O caso vira \"respondido\" e sobe para o topo da lista do ouvidor",
         "No bloco \"Aguardando seu encerramento\". A resposta entra no histórico.", AZUL),
        ("Se a resposta for fraca, o ouvidor devolve",
         "Com motivo obrigatório, que vai no e-mail para o setor. Chega um link novo.", LARANJA),
        ("Quem responde mal não ganha relógio novo",
         "A área volta a ter metade do prazo da gravidade, somado ao tempo que já correu. Se "
         "já estourou, continua estourado.", VERMELHO),
        ("Se a resposta for boa, o ouvidor encerra",
         "Com uma conclusão, e a pessoa que falou recebe o aviso.", VERDE),
    ]
    yy = y
    for t, c, cor in passos:
        retangulo(s, xc, yy, Inches(0.08), Inches(1.05), cor, arredondado=False)
        texto(s, xc + Inches(0.2), yy - Inches(0.03), wc - Inches(0.2), Inches(1.1), [
            (t, {"negrito": True, "cor": AZUL_ESCURO, "tamanho": 12}), c], tamanho=11, espaco=2)
        yy += Inches(1.18)
    notas(s, "O que o sistema barra e o que vem depois. A frase que fica: quem responde mal não "
             "ganha relógio novo.")


# capítulo 4 ----------------------------------------------------------------


def cap4(d: Deck):
    s = d.abertura(4, "O relógio e a cobrança",
                   "O prazo vem da gravidade, e quem define a tabela é a Diretoria. Depois que o "
                   "caso é encaminhado, o prazo fica congelado nele. A cobrança não depende de "
                   "ninguém abrir tela: o sistema varre a lista sozinho, a cada dez minutos.",
                   ["Quanto tempo cada um tem.",
                    "Como o prazo é contado: expediente, feriados e o dia do fato.",
                    "Quando ninguém responde: a escada de quatro degraus.",
                    "Quando a vida complica: seis desvios que o sistema já entende."],
                   video=4, duracao="1:02")
    notas(s, "Vídeo: a tabela de prazos, a sexta que vence na terça, o pedido de mais prazo e a "
             "escada de cobrança.")

    s, y = d.conteudo("Capítulo 4 · O relógio e a cobrança", "Quanto tempo cada um tem",
                      "Campo em branco quer dizer \"não existe prazo para essa combinação\". "
                      "Zero quer dizer \"imediato\".")
    tabela(s, MARGEM, y, Inches(7.4), ["Momento", "Crítico", "Alto", "Médio", "Baixo"], [
        ("Avisar que chegou", "no mesmo dia", "24 horas", "24 horas", "24 horas"),
        ("A Ouvidoria ler e encaminhar", "imediato", "4 horas úteis", "1 dia útil", "1 dia útil"),
        ("A área responder", "4 horas úteis", "2 dias úteis", "4 dias úteis", "não passa pela área"),
        ("Concluir com a pessoa", "sem prazo fixo", "5 dias úteis", "7 dias úteis", "2 dias úteis"),
    ], larguras=[2.2, 1.3, 1.3, 1.3, 1.5], tamanho=11, altura_linha=Inches(0.55))
    texto(s, MARGEM, y + Inches(2.95), Inches(7.4), Inches(1.9), [
        "Só um prazo corre no relógio de parede: o aviso de que a manifestação chegou. Ele conta "
        "em horas corridas, com noite e fim de semana, porque é uma promessa a quem esperou. "
        "Todo o resto conta só em horário de expediente.",
        "Estes números são o ponto de partida. O que vale é o que estiver na tela de prazos, "
        "porque a Diretoria pode mudar. Mudar a tabela não mexe em caso já encaminhado.",
    ], tamanho=11, cor=TEXTO_2, espaco=6)
    xc = Inches(8.3)
    wc = Inches(4.45)
    graus = [
        ("Crítico", "Risco à vida, à segurança ou à imagem. A área responde em 4 horas úteis, e a "
         "Diretoria é avisada na hora.", VERMELHO),
        ("Alto", "Dano relevante ao paciente ou ao serviço. 2 dias úteis.", LARANJA),
        ("Médio", "Falha que precisa de correção, sem dano imediato. 4 dias úteis.", AZUL_CLARO),
        ("Baixo", "Sugestão, elogio ou queixa que a própria Ouvidoria resolve. Não passa pela área.",
         VERDE),
    ]
    yy = y
    for t, c, cor in graus:
        retangulo(s, xc, yy, wc, Inches(1.05), BRANCO, borda=BORDA)
        retangulo(s, xc, yy, Inches(0.08), Inches(1.05), cor, arredondado=False)
        texto(s, xc + Inches(0.2), yy + Inches(0.05), wc - Inches(0.3), Inches(1.0), [
            (t, {"negrito": True, "cor": AZUL_ESCURO, "tamanho": 12}), c], tamanho=11, espaco=2)
        yy += Inches(1.18)
    notas(s, "A tabela é da Diretoria, editável na tela de prazos. Cada mudança guarda quem "
             "mudou, quando, e de quanto para quanto. Caso já encaminhado mantém o prazo antigo.")

    s, y = d.conteudo("Capítulo 4 · O relógio e a cobrança",
                      "Como o prazo é contado, e o que acontece sem resposta")
    wc = Inches(5.9)
    cartao(s, MARGEM, y, wc, Inches(1.35), "O expediente",
           "Segunda a sexta, das 8h às 17h. A hora útil anda dentro desse período e para às 17h. "
           "Encaminhado às 16h50, sobram dez minutos daquele dia.", tamanho_corpo=11)
    cartao(s, MARGEM, y + Inches(1.5), wc, Inches(1.35), "Os feriados",
           "Nacionais, do estado do Rio e do município do Rio, numa lista que a Diretoria edita. "
           "Feriado sai da conta.", tamanho_corpo=11, cor_faixa=AZUL_CLARO)
    cartao(s, MARGEM, y + Inches(3.0), wc, Inches(1.7), "O dia do fato não conta",
           "Encaminhado na sexta às 16h50 com prazo de 2 dias úteis: a contagem abre na segunda "
           "às 8h e vence na terça às 17h. Uma conta só, para todo mundo: lista, página do caso, "
           "e-mail e relatório mostram o mesmo prazo e a mesma frase.", tamanho_corpo=11,
           cor_faixa=VERDE)
    xc = Inches(6.85)
    wc2 = Inches(5.9)
    texto(s, xc, y - Inches(0.05), wc2, Inches(0.4), "A escada de quatro degraus",
          tamanho=14, cor=AZUL_ESCURO, negrito=True)
    degraus = [
        ("Um dia útil antes de vencer", "Lembrete para o titular. Ainda dá tempo de responder.", AZUL_CLARO),
        ("No vencimento, sem resposta", "Cobrança para o titular e o substituto. A ausência de uma "
         "pessoa não trava o caso.", LARANJA),
        ("Um dia útil depois", "O gestor da área. Deixa de ser assunto do setor e vira assunto da gestão.",
         LARANJA),
        ("Dois dias úteis depois", "A Diretoria, o último degrau da escada.", VERMELHO),
    ]
    yy = y + Inches(0.4)
    for i, (t, c, cor) in enumerate(degraus):
        recuo = Inches(0.35) * i
        retangulo(s, xc + recuo, yy, wc2 - recuo, Inches(0.72), BRANCO, borda=BORDA)
        retangulo(s, xc + recuo, yy, Inches(0.5), Inches(0.72), cor, arredondado=False)
        texto(s, xc + recuo, yy, Inches(0.5), Inches(0.72), str(i + 1), tamanho=16, cor=BRANCO,
              negrito=True, alinhamento=PP_ALIGN.CENTER, ancora=MSO_ANCHOR.MIDDLE)
        texto(s, xc + recuo + Inches(0.6), yy + Inches(0.02), wc2 - recuo - Inches(0.7), Inches(0.7), [
            (t, {"negrito": True, "cor": AZUL_ESCURO, "tamanho": 11}), c], tamanho=10, espaco=1)
        yy += Inches(0.82)
    texto(s, xc, yy + Inches(0.05), wc2, Inches(1.0), [
        "Cobrança respeita horário comercial: a que nasce de madrugada espera o expediente abrir. "
        "A exceção é o caso crítico, que sai na hora.",
        "Antes de subir um degrau, o sistema olha se existe alguém lá. Se não existe, carimba "
        "\"não há a quem escalar\" e avisa a Diretoria, em vez de subir um degrau vazio.",
    ], tamanho=10, cor=TEXTO_2, espaco=3)
    notas(s, "O sistema varre os casos abertos a cada dez minutos. Cada degrau é um e-mail para "
             "uma pessoa diferente. Se o e-mail falha, tenta de novo; na terceira falha, avisa "
             "quem cuida do sistema.")

    s, y = d.conteudo("Capítulo 4 · O relógio e a cobrança", "Quando a vida complica",
                      "O sistema já entende sete situações que fogem do caminho reto.")
    desvios = [
        ("A área precisa de mais tempo", "Pede pelo próprio link, com justificativa e quantos dias. "
         "Uma vez só, antes de vencer, e o prazo novo nunca passa de 30 dias úteis da entrada. "
         "Quem decide é o ouvidor."),
        ("A resposta veio fraca", "O ouvidor devolve com motivo obrigatório. A área volta a ter "
         "metade do prazo, somado ao tempo já corrido. Se já estourou, continua estourado."),
        ("Falta informação de quem reclamou", "O caso vai para \"aguardando manifestante\" e o "
         "relógio da área para. Quando volta, o vencimento anda o mesmo tanto. O relatório mostra "
         "esse tempo separado."),
        ("A pessoa some", "Depois de duas tentativas de contato registradas e cinco dias úteis, o "
         "ouvidor encerra por \"sem retorno do manifestante\". Conclusão neutra nas estatísticas."),
        ("A pessoa volta a reclamar do mesmo", "Em até 30 dias, o caso original é marcado como "
         "reincidência e reabre. Não nasce protocolo novo. A reabertura só pode aumentar o sigilo."),
        ("O caso teve várias idas e voltas", "Cada devolução e cada resposta viram um ciclo com "
         "histórico próprio. O indicador guarda o prazo que foi rompido, não a hora da resposta final."),
        ("O caso não é daquela área", "A área devolve pelo próprio link, com motivo obrigatório. "
         "O caso volta para a fila da Ouvidoria, o relógio da área para e o ouvidor encaminha "
         "para a área certa, que recebe o prazo inteiro."),
    ]
    w, h = Inches(2.87), Inches(2.15)
    gap = Inches(0.2)
    for i, (t, c) in enumerate(desvios):
        col, lin = i % 4, i // 4
        cartao(s, MARGEM + col * (w + gap), y + lin * (h + gap), w, h, t, c,
               cor_faixa=[LARANJA, VERMELHO, AZUL_CLARO, VERDE][col], tamanho_corpo=10,
               tamanho_titulo=12)
    notas(s, "Sete desvios. Os mais comuns para as áreas: pedir mais prazo (uma vez, antes de "
             "vencer, com justificativa), a devolução por resposta fraca (metade do prazo, sem "
             "relógio novo) e a devolução à Ouvidoria, que é a novidade desta versão.")


# capítulo 5 ----------------------------------------------------------------


def cap5(d: Deck):
    s = d.abertura(5, "O que volta para quem falou",
                   "Só dois e-mails saem do hospital para fora, e os dois só existem quando há um "
                   "e-mail de contato no caso. Um avisa que chegou. O outro conta no que deu.",
                   ["O relato da pessoa nunca volta por e-mail.",
                    "A resposta que o setor escreveu nunca sai.",
                    "Nenhum nome de colaborador aparece.",
                    "Sem e-mail de contato, o caso registra: \"não enviado, sem canal\"."],
                   video=5, duracao="0:56")
    notas(s, "Vídeo: o aviso de que chegou e o aviso de que terminou, os dois únicos e-mails que saem.")

    s, y = d.conteudo("Capítulo 5 · O que volta para quem falou", "Dois e-mails, e só")
    imagem_ajustada(s, MANUAL_IMG / "email-acuse.png", MARGEM, y, Inches(3.3), Inches(4.2),
                    legenda="Chegou. Sai sozinho na abertura. Traz o protocolo e nada do conteúdo.")
    imagem_ajustada(s, MANUAL_IMG / "email-encerramento.png", Inches(4.1), y, Inches(3.3), Inches(4.2),
                    legenda="Terminou. Sai quando o ouvidor encerra. Protocolo, conclusão e o caminho para voltar a falar.")
    xc = Inches(7.8)
    wc = Inches(4.95)
    texto(s, xc, y, wc, Inches(4.8), [
        ("Por que os dois e-mails contam tão pouco", {"negrito": True, "cor": AZUL_ESCURO, "tamanho": 14}),
        "Os e-mails saem por um serviço de envio de fora do Brasil. Por isso foi decidido campo a "
        "campo o que pode viajar: o protocolo e a conclusão. Nada mais.",
        ("O texto do encerramento sai do hospital.", {"negrito": True, "cor": AZUL_ESCURO}),
        "A tela avisa isso antes do campo. Quem escreve precisa saber que a frase será lida por "
        "um paciente ou familiar. Nada de nome de colaborador, nada de medida disciplinar, nada "
        "de detalhe da apuração interna.",
        ("Quando não há canal, o caso diz.", {"negrito": True, "cor": AZUL_ESCURO}),
        "Sem e-mail de contato, pedido de anonimato ou contato só por telefone: o aviso não sai e "
        "o caso registra \"não enviado, sem canal\". O texto da conclusão continua no registro.",
    ], tamanho=11, espaco=6)
    notas(s, "Para as áreas: a resposta que vocês escrevem nunca sai do hospital. Quem escreve a "
             "conclusão para o paciente é a Ouvidoria, e a tela avisa que aquilo vai para fora.")


# capítulo 6 ----------------------------------------------------------------


def cap6(d: Deck):
    s = d.abertura(6, "Quem faz o quê",
                   "O acesso à Ouvidoria é separado do resto do sistema. Ter acesso a reuniões ou a "
                   "documentos não dá acesso a nenhum caso, e nem quem administra o sistema lê um "
                   "caso sigiloso.",
                   ["Ouvidor e Diretoria Executiva entram com login.",
                    "O responsável do setor não entra: recebe um e-mail com link próprio.",
                    "Cada setor tem titular, substituto e gestor da área, com período.",
                    "Para tirar alguém do papel, encerre a vigência. Nunca apague."],
                   video=6, duracao="0:58")
    notas(s, "Vídeo: a concessão do acesso, a vigência do responsável e o setor sem titular.")

    s, y = d.conteudo("Capítulo 6 · Quem faz o quê", "Quem faz o quê")
    tabela(s, MARGEM, y, Inches(12.15), ["Quem", "Como entra", "O que pode fazer", "O que não pode"], [
        ("Ouvidor", "Login, com acesso concedido por quem administra.",
         "Abrir qualquer caso, inclusive sigiloso. Registrar, classificar, encaminhar, devolver, "
         "reabrir, cobrar, decidir prazo e encerrar. Arquivar e desarquivar caso encerrado. "
         "Cadastrar pontos de escuta. Lançar a nota externa. Ver painel e relatórios.",
         "Mexer na tabela de prazos e feriados. Cadastrar responsáveis de setor. Apagar um caso."),
        ("Diretoria Executiva", "Login, mesmo caminho.",
         "Tudo o que o ouvidor faz, mais a tabela de prazos, os feriados e os responsáveis por "
         "setor. Apagar o caso encerrado, com motivo escrito. Recebe os casos que subiram a "
         "escada, o aviso de caso grave e os relatórios.",
         "Apagar ou editar o histórico de um caso. Ninguém pode."),
        ("Responsável do setor", "Não entra. Recebe e-mail com link próprio. Titular, substituto ou gestor.",
         "Ler o caso que veio para ele, responder o que foi feito, anexar arquivo, pedir mais "
         "prazo uma vez e devolver à Ouvidoria o caso que não é da área.",
         "Ver a lista, ver outros casos, ou saber o nome de quem falou em caso protegido."),
        ("Quem usa o resto do sistema", "Login normal, sem acesso à Ouvidoria.",
         "Ver só o índice dos casos não sigilosos: número, setor, situação e prazo.",
         "Abrir o caso. Ver caso sigiloso."),
        ("Quem administra o sistema", "Login com poderes de administração.",
         "Dar e tirar o acesso à Ouvidoria (fica registrado). Receber avisos técnicos.",
         "Ler caso sigiloso. Editar histórico."),
        ("Ana, no WhatsApp", "Por uma porta de serviço, com chave própria.",
         "Registrar uma manifestação e consultar o andamento de um protocolo.",
         "Classificar, mudar situação, definir conclusão, tipo ou sigilo."),
    ], larguras=[1.5, 2.2, 4.4, 3.0], tamanho=10, altura_linha=Inches(0.66))
    notas(s, "Quem administra o sistema abre a tela de usuários e escolhe 'Acesso à Ouvidoria': "
             "sem acesso, ouvidor ou Diretoria Executiva. Quem sai do hospital perde o acesso sozinho.")

    s, y = d.conteudo("Capítulo 6 · Quem faz o quê", "Responsáveis por setor",
                      "Cada setor tem quem responde por ele, com um papel e um período.")
    xc = MARGEM
    wc = Inches(5.6)
    papeis = [
        ("Titular", "Recebe o encaminhamento e o lembrete.", AZUL),
        ("Substituto", "Entra junto na cobrança do vencimento. A ausência de uma pessoa não trava o caso.",
         AZUL_CLARO),
        ("Gestor da área", "Recebe quando a coisa sobe. Sem titular, o caso vai direto para ele e a "
         "Diretoria é avisada.", LARANJA),
    ]
    yy = y
    for t, c, cor in papeis:
        cartao(s, xc, yy, wc, Inches(1.05), t, c, cor_faixa=cor, tamanho_corpo=11, tamanho_titulo=13)
        yy += Inches(1.2)
    retangulo(s, xc, yy + Inches(0.05), wc, Inches(1.0), FUNDO_SUAVE)
    texto(s, xc + Inches(0.15), yy + Inches(0.08), wc - Inches(0.3), Inches(0.95), [
        ("Para tirar alguém do papel, encerre a vigência. Nunca apague.", {"negrito": True, "cor": AZUL_ESCURO}),
        "O período tem fim inclusivo: quem sai no dia 31 ainda responde no dia 31. Apagar quebraria "
        "o histórico dos casos antigos.",
    ], tamanho=11, espaco=2)
    imagem_ajustada(s, MANUAL_IMG / "responsaveis.png", Inches(6.6), y, Inches(6.15), Inches(4.7),
                    legenda="O Centro Cirúrgico está \"sem titular vigente\": só gestor. Um caso para lá sobe direto.")
    notas(s, "Pergunta para a plateia: quem é o titular do seu setor hoje? Quem é o substituto? Só "
             "a Diretoria cadastra. Se a área não sabe, é hora de acertar.")


# capítulo 7 ----------------------------------------------------------------


def cap7(d: Deck):
    s = d.abertura(7, "O que a Diretoria enxerga",
                   "Um único lugar faz todas as contas. Por isso o número do painel nunca "
                   "discorda do número do relatório.",
                   ["O painel, em tempo real.",
                    "Os relatórios quinzenal e mensal, por e-mail.",
                    "A nota externa: Google e Reclame Aqui, lançadas à mão.",
                    "Arquivar o caso encerrado, e apagar antes dos cinco anos.",
                    "O que o sistema apaga sozinho depois de cinco anos."],
                   video=7, duracao="1:03")
    notas(s, "Vídeo: o painel se atualizando, a nota do Google lançada e o relatório quinzenal chegando.")

    s, y = d.conteudo("Capítulo 7 · O que a Diretoria enxerga", "O painel, em tempo real")
    imagem_ajustada(s, MANUAL_IMG / "painel.png", MARGEM, y, Inches(6.2), Inches(4.75),
                    legenda="Casos por situação, graves em aberto, vencidos, vence hoje, próximos vencimentos e áreas devendo.")
    xc = Inches(7.3)
    wc = Inches(5.45)
    cartao(s, xc, y, wc, Inches(1.45), "Duas perguntas diferentes",
           "Quase tudo responde \"o que entrou no período\". Mas \"vencidos por área\" responde o "
           "que está pendente agora. A área com o caso mais atrasado não some só porque o caso "
           "entrou no mês passado.", tamanho_corpo=11)
    cartao(s, xc, y + Inches(1.6), wc, Inches(1.45), "Quando falta dado, o painel avisa",
           "Se alguma parte não conseguiu ser lida, aparece marcada como incompleta. O painel "
           "prefere dizer que falta dado a mostrar um número errado.", tamanho_corpo=11,
           cor_faixa=LARANJA)
    cartao(s, xc, y + Inches(3.2), wc, Inches(1.45), "Caso grave sai daqui quando encerra",
           "Não quando a área responde. Enquanto a Ouvidoria não concluir, ele continua contando "
           "como grave em aberto.", tamanho_corpo=11, cor_faixa=VERMELHO)
    notas(s, "O painel mostra o nome de quem responde nas áreas devendo. Para as áreas: o seu "
             "nome aparece aqui quando o prazo estoura.")

    s, y = d.conteudo("Capítulo 7 · O que a Diretoria enxerga", "Os relatórios e a nota externa")
    tabela(s, MARGEM, y, Inches(7.6), ["Relatório", "Quando", "O que traz"], [
        ("Quinzenal", "Dias 1 e 16", "Quantos casos entraram por tipo, área, gravidade e porta; "
         "quanto a área cumpriu de prazo; quanto tempo o caso passou em cada trecho; o que está "
         "pendente; e o retrato externo, com a nota do Google e do Reclame Aqui daquele momento."),
        ("Mensal", "Dia 1", "Tudo do quinzenal, mais como a nota externa evoluiu e uma seção de "
         "sugestões de ação escrita por inteligência artificial. Ela recebe só os números somados, "
         "nunca o relato de ninguém."),
    ], larguras=[1.2, 1.1, 5.3], tamanho=11, altura_linha=Inches(1.05))
    texto(s, MARGEM, y + Inches(3.3), Inches(7.6), Inches(1.5), [
        ("A nota externa é um diário: cada anotação vira uma linha nova.", {"negrito": True, "cor": AZUL_ESCURO}),
        "As estrelas do Google e o índice do Reclame Aqui não são medidos pelo sistema: o ouvidor "
        "lê e digita, e cada vez nasce uma linha nova com data e autor. O relatório de julho, "
        "reenviado em setembro, mostra a nota de julho. Ausência de nota nunca vira zero.",
    ], tamanho=11, espaco=4)
    imagem_ajustada(s, MANUAL_IMG / "nota-externa.png", Inches(8.5), y, Inches(4.25), Inches(4.7),
                    legenda="Escalas diferentes de propósito: 4,3 de 5 e 7,8 de 10, sempre juntas do número.")
    notas(s, "Os dois relatórios vão para a Diretoria Executiva. O registro guarda quem recebeu e o "
             "que saiu. Se o envio falhar, dá para reenviar exatamente o mesmo documento.")

    s, y = d.conteudo("Capítulo 7 · O que a Diretoria enxerga",
                      "Arquivar: o caso encerrado sai da lista",
                      "Arquivar é organização da lista. O caso continua existindo, continua "
                      "contando nos relatórios e volta com um clique.")
    imagem_ajustada(s, IMG_NOVA / "fila-arquivo.png", MARGEM, y, Inches(7.3), Inches(4.4),
                    legenda="O botão em cada encerrado, o lote no cabeçalho do grupo e o filtro Arquivados no topo.")
    xc = Inches(8.2)
    wc = Inches(4.55)
    cartao(s, xc, y, wc, Inches(1.4), "Um por um, ou todos de uma vez",
           "Cada caso encerrado tem o botão Arquivar. O grupo dos encerrados tem \"Arquivar todos "
           "os encerrados\", que faz a leva inteira de uma vez.", tamanho_corpo=11, tamanho_titulo=13)
    cartao(s, xc, y + Inches(1.55), wc, Inches(1.4), "Tem volta",
           "A lista nasce sem os arquivados. O filtro Arquivados mostra o que foi guardado, e "
           "Desarquivar traz o caso de volta para a lista.", tamanho_corpo=11, tamanho_titulo=13,
           cor_faixa=AZUL_CLARO)
    cartao(s, xc, y + Inches(3.1), wc, Inches(1.4), "Não muda o caso",
           "Arquivar não muda a situação, não entra no histórico e não tira o caso das contas do "
           "painel nem dos relatórios. Só caso encerrado arquiva.", tamanho_corpo=11,
           tamanho_titulo=13, cor_faixa=VERDE)
    notas(s, "Novidade desta versão. Arquivar é do ouvidor e da Diretoria. Serve para a lista "
             "parar de crescer sem fim, sem esconder nada de ninguém: o filtro mostra tudo.")

    s, y = d.conteudo("Capítulo 7 · O que a Diretoria enxerga",
                      "Apagar: quando a Diretoria decide antecipar",
                      "Apagar tira do caso o relato, quem falou, os anexos e a resposta da área. "
                      "Ficam o protocolo, a linha do tempo e os números.")
    imagem_ajustada(s, IMG_NOVA / "apagar-modal-zoom.png", MARGEM, y, Inches(4.4), Inches(3.5),
                    legenda="O motivo é obrigatório e fica gravado no caso e no histórico.")
    imagem_ajustada(s, IMG_NOVA / "caso-apagado-zoom.png", Inches(5.5), y, Inches(7.25), Inches(3.5),
                    legenda="Depois: o caso diz quando foi apagado, por quem e por quê.")
    retangulo(s, MARGEM, y + Inches(4.1), Inches(12.15), Inches(1.0), FUNDO_SUAVE)
    texto(s, MARGEM + Inches(0.2), y + Inches(4.15), Inches(11.75), Inches(0.95), [
        ("Só a Diretoria apaga, um caso por vez, e só caso encerrado.", {"negrito": True, "cor": AZUL_ESCURO}),
        "Não tem volta, e o caso apagado não reabre: quem voltar a reclamar registra manifestação "
        "nova. Como o protocolo, as datas, o tipo, a área, a gravidade e o desfecho ficam, o "
        "relatório que já saiu continua batendo com o sistema.",
    ], tamanho=11)
    notas(s, "Novidade desta versão. É a mesma limpeza da retenção dos cinco anos, feita hoje "
             "por decisão humana. Nada some da contabilidade: some o texto.")

    s, y = d.conteudo("Capítulo 7 · O que a Diretoria enxerga", "O que o sistema apaga sozinho")
    w = Inches(5.95)
    cartao(s, MARGEM, y + Inches(0.3), w, Inches(2.6), "Depois de cinco anos, o relato some", [
        "De madrugada, o sistema apaga o conteúdo dos casos encerrados há mais de cinco anos, "
        "contados da conclusão.",
        "Ele varre os cinco lugares onde o relato pode estar: a manifestação, os anexos, as "
        "observações do histórico, as tentativas de contato e o detalhe dos avisos enviados.",
        "O que os relatórios contam é preservado: some o texto, ficam os números.",
        "A Diretoria pode antecipar isso num caso encerrado, com motivo escrito. O efeito é o mesmo.",
    ], tamanho_corpo=13, tamanho_titulo=16)
    cartao(s, MARGEM + w + Inches(0.25), y + Inches(0.3), w, Inches(2.6), "Números nunca levam nome junto", [
        "Antes de qualquer texto entrar numa conta ou num resumo, o sistema tira dele os dados "
        "que identificam pessoas.",
        "Isso vale inclusive para o que a inteligência artificial lê no relatório mensal: ela "
        "recebe o agregado, nunca o relato.",
    ], tamanho_corpo=13, tamanho_titulo=16, cor_faixa=VERDE)
    notas(s, "Retenção e privacidade. Ninguém precisa lembrar de apagar: o sistema faz de "
             "madrugada, cinco anos depois do encerramento.")


# fechamento ----------------------------------------------------------------


def slide_o_que_vem(d: Deck):
    s, y = d.conteudo("Depois do manual", "O que entrou agora, e o que ainda vem",
                      "A apresentação anterior mostrava o sistema na versão 0.109. "
                      f"Esta mostra a {VERSAO_APP}.")
    w = Inches(5.95)
    blocos = [
        ("JÁ NO AR", VERDE, "O que entrou desde a versão anterior", [
            "Devolução à Ouvidoria: a área devolve pelo próprio link o caso que não é dela, com "
            "motivo obrigatório, e o ouvidor encaminha para a área certa no mesmo protocolo.",
            "Arquivar: o caso encerrado sai da lista, um por um ou em lote, e volta pelo filtro.",
            "Apagar: a Diretoria tira o relato de um caso encerrado antes dos cinco anos, com "
            "motivo escrito. Os números dos relatórios continuam iguais.",
        ]),
        ("EM CONSTRUÇÃO", LARANJA, "Avaliações do Google viram casos", [
            "A avaliação que o paciente deixa no Google entra na fila da Ouvidoria como qualquer "
            "manifestação, com canal de origem próprio.",
            "A resposta pública do hospital sai revisada por humano e travada por um checklist de "
            "sigilo: não confirmar vínculo de paciente, não citar data, procedimento, diagnóstico ou "
            "setor, não admitir erro, não citar colaborador.",
            "Depende da aprovação do Google para o acesso à API. Sem data prometida.",
        ]),
    ]
    for i, (etiqueta, cor, titulo, corpo) in enumerate(blocos):
        x = MARGEM + i * (w + Inches(0.25))
        cartao(s, x, y, w, Inches(3.4), titulo, corpo, tamanho_corpo=12, tamanho_titulo=15,
               cor_faixa=cor)
        retangulo(s, x + w - Inches(1.9), y + Inches(0.12), Inches(1.7), Inches(0.32), cor)
        texto(s, x + w - Inches(1.9), y + Inches(0.12), Inches(1.7), Inches(0.32), etiqueta,
              tamanho=9, cor=AZUL_ESCURO, negrito=True, alinhamento=PP_ALIGN.CENTER,
              ancora=MSO_ANCHOR.MIDDLE)
    notas(s, "A coluna da esquerda é o que a plateia ainda não viu funcionando: mostre os três "
             "slides novos (capítulos 3 e 7). A da direita não está no ar. Não prometa data.")


def slide_anexo_prds(d: Deck):
    s, y = d.conteudo("Anexo", "De onde veio cada parte",
                      "Cada bloco do sistema nasceu de um documento de produto (PRD), numerado no GitHub. "
                      "Este mapa é para quem acompanha o desenvolvimento.")
    tabela(s, MARGEM, y, Inches(12.15), ["PRD", "O que entregou", "Onde aparece nesta apresentação"], [
        ("317", "Núcleo e entrada: o centralizador de manifestações, formulário público, QR dos "
         "cartazes, lista, classificar e acionar, e-mails, acessos.", "Capítulos 1, 2, 5 e 6"),
        ("318", "Governança de prazo: a tela do responsável, prorrogação, devolução e a escada de escalonamento.",
         "Capítulos 3 e 4"),
        ("319", "Inteligência: painel em tempo real, relatórios quinzenal e mensal, nota externa e retenção.",
         "Capítulo 7"),
        ("287", "Dados do Atendimento da Ana no app: a porta de serviço da assistente do WhatsApp.",
         "Capítulo 1"),
        ("467", "Canal aberto honra o cartaz: os quatro botões do formulário como sugestão do manifestante.",
         "Capítulo 1"),
        ("468", "Fundação: caso com endereço próprio, retorno pós-login, celular e os quatro momentos.",
         "Capítulo 2"),
        ("470", "Linha do tempo do caso e o ponto azul de novidade para o ouvidor.", "Capítulo 2"),
        ("471", "Lista em dois níveis e os retornos ao manifestante.", "Capítulos 2 e 5"),
        ("598", "Devolução à Ouvidoria: a área devolve o caso que não é dela, a Ouvidoria é "
         "avisada e o ouvidor reaciona no mesmo protocolo.", "Capítulos 3, 4 e 6"),
        ("591", "Arquivar e apagar: o arquivo da lista, em lote, e a retenção antecipada pela "
         "Diretoria.", "Capítulos 6 e 7"),
        ("472", "Em construção: avaliações do Google viram manifestações.", "O que ainda vem"),
    ], larguras=[0.9, 6.2, 2.4], tamanho=10, altura_linha=Inches(0.42))
    notas(s, "Slide de apoio. Os números são das issues do GitHub do projeto. A plateia das áreas "
             "não precisa deste slide.")


def slide_fechamento(d: Deck, qr_path: Path):
    s = d.novo()
    retangulo(s, 0, 0, LARGURA, ALTURA, AZUL_ESCURO, arredondado=False)
    retangulo(s, 0, 0, Inches(0.18), ALTURA, VERDE, arredondado=False)
    texto(s, MARGEM, Inches(1.2), Inches(7.5), Inches(1.6),
          "O manual completo está online, com os vídeos e as telas.",
          tamanho=30, cor=BRANCO, negrito=True)
    texto(s, MARGEM, Inches(3.0), Inches(7.2), Inches(1.6), [
        "As telas desta apresentação são capturas reais do sistema. Se alguma delas não bater com "
        "o que você vê, avise a Ouvidoria: o manual é atualizado junto com o sistema.",
    ], tamanho=14, cor=BRANCO)
    retangulo(s, MARGEM, Inches(4.6), Inches(5.6), Inches(0.6), BRANCO)
    texto(s, MARGEM, Inches(4.6), Inches(5.6), Inches(0.6), MANUAL_URL.replace("https://", ""),
          tamanho=16, cor=AZUL_ESCURO, negrito=True, alinhamento=PP_ALIGN.CENTER,
          ancora=MSO_ANCHOR.MIDDLE)
    texto(s, MARGEM, Inches(5.5), Inches(7), Inches(0.4),
          f"Atualizado em {DATA} · mostra o sistema na versão {VERSAO_APP}",
          tamanho=11, cor=VERDE)
    lado = Inches(3.2)
    qx = LARGURA - MARGEM - lado - Inches(0.6)
    retangulo(s, qx - Inches(0.25), Inches(1.6), lado + Inches(0.5), lado + Inches(0.9), BRANCO)
    s.shapes.add_picture(str(qr_path), qx, Inches(1.85), lado, lado)
    texto(s, qx - Inches(0.25), Inches(1.85) + lado + Inches(0.05), lado + Inches(0.5), Inches(0.4),
          "Aponte a câmera do celular", tamanho=11, cor=TEXTO_2, alinhamento=PP_ALIGN.CENTER)
    d.rodape(s, escuro=True)
    notas(s, "Encerramento. Deixe o QR na tela enquanto responde perguntas.")


# ---------------------------------------------------------------- execução


def baixar_videos():
    VIDEOS.mkdir(exist_ok=True)
    for i in range(1, 8):
        mp4 = VIDEOS / f"video-cap{i}.mp4"
        poster = VIDEOS / f"poster-cap{i}.png"
        if not mp4.exists():
            print(f"baixando video-cap{i}.mp4 ...")
            original = VIDEOS / f"original-cap{i}.mp4"
            urllib.request.urlretrieve(
                f"{MANUAL_URL}/video/ouvidoria/cap-{i}.mp4", original
            )
            # 1080p vira 720p: o vídeo ocupa menos da metade do slide e o deck cai de 35 para uns 15 MB
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(original),
                            "-vf", "scale=1280:-2", "-c:v", "libx264", "-crf", "28",
                            "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            "-an", str(mp4)], check=True)
            original.unlink()
        if not poster.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2", "-i", str(mp4),
                            "-frames:v", "1", str(poster)], check=True)


def gerar_qr(destino: Path):
    import qrcode

    img = qrcode.make(MANUAL_URL, border=1)
    img.save(destino)


def conferir_tipografia(prs):
    """Trava do CLAUDE.md: nada de travessão nem meia-risca no que o usuário vê."""
    proibidos = {"—", "–"}
    for n, slide in enumerate(prs.slides, start=1):
        textos = []
        for forma in slide.shapes:
            if forma.has_text_frame:
                textos.append(forma.text_frame.text)
            if forma.has_table:
                for linha in forma.table.rows:
                    for cel in linha.cells:
                        textos.append(cel.text_frame.text)
        textos.append(slide.notes_slide.notes_text_frame.text)
        for t in textos:
            if any(c in t for c in proibidos):
                sys.exit(f"travessão ou meia-risca no slide {n}: {t[:80]!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-videos", action="store_true", help="não baixa nem embute os MP4")
    ap.add_argument("--saida", type=Path, default=AQUI / "ouvidoria-apresentacao.pptx")
    args = ap.parse_args()

    if not args.sem_videos:
        baixar_videos()
    qr = AQUI / "videos" / "qr-manual.png" if not args.sem_videos else AQUI / "qr-manual.png"
    qr.parent.mkdir(exist_ok=True)
    gerar_qr(qr)

    d = Deck(com_videos=not args.sem_videos)
    slide_capa(d)
    slide_uma_pagina(d)
    slide_seis_palavras(d)
    slide_caminho(d)
    cap1(d)
    cap2(d)
    cap3(d)
    cap4(d)
    cap5(d)
    cap6(d)
    cap7(d)
    slide_o_que_vem(d)
    slide_anexo_prds(d)
    slide_fechamento(d, qr)

    conferir_tipografia(d.prs)
    d.prs.save(args.saida)
    tamanho = args.saida.stat().st_size / 1_000_000
    print(f"{args.saida} · {len(d.prs.slides)} slides · {tamanho:.1f} MB")


if __name__ == "__main__":
    main()
