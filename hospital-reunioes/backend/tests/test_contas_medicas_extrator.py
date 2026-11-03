"""Extrator de texto de PDF do módulo Contas médicas (issue #1116, ADR 0070).

O PDF é gerado aqui mesmo, pelo WeasyPrint do projeto: PDF real de conta ou de
prontuário nunca entra no repositório. Para provar o teto de memória e o prazo,
um `pdftotext` falso entra na frente do PATH e faz o papel do arquivo hostil.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import sys
import time
from pathlib import Path

import pytest

from app.services import contas_medicas_extrator as extrator
from app.services import contas_medicas_extrator_filho as filho
from app.services import transcricao_extractor
from app.services.contas_medicas_extrator import (
    ErroLeitura,
    Pagina,
    Palavra,
    extrair_paginas,
    extrair_palavras,
    ler_digitalizadas,
    texto_para_guardar,
)


def _pdf(*paginas: str) -> bytes:
    from weasyprint import HTML

    corpo = "".join(
        f'<div style="page-break-before: always">{"<p>" + texto + "</p>" if texto else ""}</div>' for texto in paginas
    )
    return HTML(string=f"<html><body>{corpo}</body></html>").write_pdf()


def _pdftotext_falso(pasta: Path, monkeypatch: pytest.MonkeyPatch, corpo: str) -> None:
    falso = pasta / "pdftotext"
    falso.write_text(f"#!{sys.executable}\n{corpo}\n", encoding="utf-8")
    falso.chmod(falso.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ['PATH']}")


def test_texto_volta_por_pagina_com_a_numeracao_do_pdf_e_pagina_vazia_marcada(caplog):
    caplog.set_level(logging.DEBUG)

    paginas = extrair_paginas(_pdf("Fatura Individual Atendimento 900001", "", "Total da Conta 1.374,87"))

    assert [(p.numero, p.sem_texto) for p in paginas] == [(1, False), (2, True), (3, False)]
    assert "Fatura Individual Atendimento 900001" in paginas[0].texto
    assert paginas[1].texto.strip() == ""
    assert "Total da Conta 1.374,87" in paginas[2].texto
    assert all(isinstance(p, Pagina) for p in paginas)
    assert "900001" not in caplog.text


def test_prazo_da_leitura_e_120_segundos():
    assert extrator.PRAZO_DA_LEITURA == 120


def test_leitura_que_passa_do_prazo_e_interrompida(tmp_path, monkeypatch, caplog):
    _pdftotext_falso(tmp_path, monkeypatch, "import time\ntime.sleep(60)")
    monkeypatch.setattr(extrator, "PRAZO_DA_LEITURA", 1.0)

    inicio = time.monotonic()
    resultado = extrair_paginas(_pdf("qualquer"))

    assert resultado == ErroLeitura(extrator.MENSAGEM_PDF_GRANDE_DEMAIS)
    assert time.monotonic() - inicio < 10
    assert "morta por tempo" in caplog.text


def test_leitura_que_passa_do_teto_de_memoria_e_interrompida(tmp_path, monkeypatch, caplog):
    # 300 MB escritos de verdade, para o RSS subir; o teto do teste fica em 100 MB.
    _pdftotext_falso(tmp_path, monkeypatch, "import time\nx = b'1' * (300 * 1024 * 1024)\ntime.sleep(60)")
    monkeypatch.setattr(transcricao_extractor, "TETO_DE_MEMORIA_DO_FILHO", 100 * 1024 * 1024)

    resultado = extrair_paginas(_pdf("qualquer"))

    assert resultado == ErroLeitura(extrator.MENSAGEM_PDF_GRANDE_DEMAIS)
    assert "morta por memoria" in caplog.text


def test_pdf_que_o_pdftotext_nao_le_devolve_erro_de_leitura():
    resultado = extrair_paginas(b"%PDF-1.4 isto nao e um pdf de verdade")

    assert resultado == ErroLeitura(extrator.MENSAGEM_PDF_ILEGIVEL)


def test_palavras_voltam_com_a_posicao_so_das_paginas_pedidas():
    palavras = extrair_palavras(_pdf("Fatura Individual", "Dose Padrão Duração", "Total"), [2, 9])

    assert list(palavras) == [2]
    assert [p.texto for p in palavras[2]] == ["Dose", "Padrão", "Duração"]
    dose, padrao, _ = palavras[2]
    assert isinstance(dose, Palavra)
    assert dose.x0 < dose.x1 < padrao.x0
    assert dose.topo == padrao.topo


def test_palavras_de_arquivo_que_nao_e_pdf_voltam_erro_de_leitura():
    resultado = extrair_palavras(b"%PDF-1.4 isto nao e um pdf de verdade", [1])

    assert resultado == ErroLeitura(extrator.MENSAGEM_PDF_ILEGIVEL)


# OCR das páginas digitalizadas do Prontuário (issue #1191). A máquina de quem
# testa não tem `tesseract`: um falso entra na frente do PATH e faz o papel dele.
# O `escrever` do falso grava o texto e o TSV em `<base>.txt` e `<base>.tsv`, como
# o de verdade faz com `txt tsv` (#1398), cada palavra com a confiança pedida.
CAPA_DO_PRONTUARIO = "DECLARAÇÃO DE RECEBIMENTO DE PRONTUÁRIO " + " ".join(
    f"Grupo: {grupo} Quantidade: 1"
    for grupo in ("EVOLUÇÃO MEDICA", "PRESCRICAO MEDICA", "ANOTAÇÕES DE ENFERMAGEM", "TERMOS DIGITALIZADOS")
)
PAGINA_COM_TEXTO = "EVOLUÇÃO MEDICA " + "Paciente estável, sem queixas, segue em observação na unidade. " * 4
LIDO_PELO_OCR = "TERMO DE CONSENTIMENTO LIVRE E ESCLARECIDO"
SO_UNIX_OCR = pytest.mark.so_unix("PATH só com o poppler por symlink, e o filho morto por SIGKILL")


ESCREVER_COMO_O_TESSERACT = """\
def escrever(texto, confianca=90):
    if sys.argv[2] == "stdout":
        sys.stdout.write(texto)
        return
    with open(sys.argv[2] + ".txt", "w", encoding="utf-8") as f:
        f.write(texto)
    linhas = ["\\t".join("level page_num block_num par_num line_num word_num left top width height conf text".split())]
    linhas += [f"5\\t1\\t1\\t1\\t1\\t{i}\\t0\\t0\\t9\\t9\\t{confianca}\\t{p}" for i, p in enumerate(texto.split())]
    with open(sys.argv[2] + ".tsv", "w", encoding="utf-8") as f:
        f.write("\\n".join(linhas) + "\\n")
"""


def _tesseract_falso(pasta: Path, monkeypatch: pytest.MonkeyPatch, corpo: str) -> None:
    falso = pasta / "tesseract"
    falso.write_text(f"#!{sys.executable}\nimport sys, time\n{ESCREVER_COMO_O_TESSERACT}\n{corpo}\n", encoding="utf-8")
    falso.chmod(falso.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ['PATH']}")


def _ler(*paginas: str) -> list[Pagina]:
    """O que a fila faz com o Prontuário: o texto do `pdftotext`, depois o OCR."""
    pdf = _pdf(*paginas)
    return ler_digitalizadas(pdf, extrair_paginas(pdf))


def test_pagina_digitalizada_do_prontuario_ganha_o_texto_do_ocr_marcada_como_ocr(tmp_path, monkeypatch):
    _tesseract_falso(tmp_path, monkeypatch, f"escrever({LIDO_PELO_OCR!r} + '\\n\\f')")

    paginas = _ler(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO)

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, True, False), (3, False, False)]
    assert LIDO_PELO_OCR in paginas[1].texto
    assert LIDO_PELO_OCR not in paginas[2].texto
    # O form feed do `tesseract` não abre página nova no texto da página.
    assert "\f" not in paginas[1].texto


def test_o_envio_nao_passa_pelo_ocr_e_o_texto_guardado_fica_sem_ele(tmp_path, monkeypatch):
    # O envio chama `extrair_paginas` dentro da requisição, atrás do proxy de 30 s,
    # e guarda o texto no bucket: o OCR fica de fora dos dois (revisão do PR #1203).
    chamado = tmp_path / "tesseract-chamado"
    _tesseract_falso(tmp_path, monkeypatch, f"open({str(chamado)!r}, 'w').close()\ntime.sleep(60)")

    inicio = time.monotonic()
    paginas = extrair_paginas(_pdf(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO))

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, False, True), (3, False, False)]
    assert not chamado.exists()
    assert time.monotonic() - inicio < 10
    assert extrator.MARCA_DO_OCR.encode() not in texto_para_guardar(paginas)


def test_pagina_sem_texto_da_conta_nao_passa_pelo_ocr(tmp_path, monkeypatch):
    _tesseract_falso(tmp_path, monkeypatch, f"escrever({LIDO_PELO_OCR!r})")

    paginas = _ler("Atendimento:900001 Paciente: FULANO Conta:12345 Fatura Individual", "")

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, False, True)]


@SO_UNIX_OCR
@pytest.mark.parametrize(
    "tesseract",
    [
        pytest.param("sys.stderr.write('Error during processing.')\nsys.exit(1)", id="ilegivel"),
        pytest.param("escrever('  \\n\\f')", id="imagem-sem-letra"),
        pytest.param(None, id="ausente"),
    ],
)
def test_pagina_que_o_ocr_nao_le_fica_sem_texto_e_a_leitura_continua(tmp_path, monkeypatch, tesseract):
    if tesseract is None:
        # PATH só com o poppler: o runner do CI pode ter o `tesseract` instalado.
        for binario in ("pdftotext", "pdftoppm"):
            (tmp_path / binario).symlink_to(shutil.which(binario))
        monkeypatch.setenv("PATH", str(tmp_path))
    else:
        _tesseract_falso(tmp_path, monkeypatch, tesseract)

    paginas = _ler(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO)

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, False, True), (3, False, False)]


def test_ocr_de_todas_as_paginas_cabe_num_prazo_da_leitura(tmp_path, monkeypatch):
    # Três páginas digitalizadas, cada uma mais lenta que o prazo inteiro: o OCR
    # do PDF todo para no prazo, não um prazo por página (revisão do PR #1203).
    _tesseract_falso(tmp_path, monkeypatch, "time.sleep(60)")
    monkeypatch.setattr(extrator, "PRAZO_DA_LEITURA", 3.0)
    pdf = _pdf(CAPA_DO_PRONTUARIO, "", "", "", PAGINA_COM_TEXTO)
    lidas_pelo_pdftotext = extrair_paginas(pdf)

    inicio = time.monotonic()
    paginas = ler_digitalizadas(pdf, lidas_pelo_pdftotext)

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [
        (1, False, False),
        (2, False, True),
        (3, False, True),
        (4, False, True),
        (5, False, False),
    ]
    # Um prazo por página levaria três; o vigia do PDF inteiro corta em um.
    assert time.monotonic() - inicio < 2 * 3.0
    # As que o prazo cortou saem não lidas (#1398); as de texto, sem qualidade.
    assert [p.qualidade for p in paginas] == [None, "nao_lida", "nao_lida", "nao_lida", None]


@pytest.mark.parametrize(
    ("confianca", "qualidade"),
    [(95, "legivel"), (70, "legivel"), (69, "duvidosa"), (50, "duvidosa"), (49, "ilegivel"), (12, "ilegivel")],
)
def test_cada_digitalizada_sai_com_a_faixa_da_confianca_do_ocr(tmp_path, monkeypatch, confianca, qualidade):
    _tesseract_falso(tmp_path, monkeypatch, f"escrever({LIDO_PELO_OCR!r}, {confianca})")

    paginas = _ler(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO)

    assert [(p.numero, p.qualidade) for p in paginas] == [(1, None), (2, qualidade), (3, None)]
    assert LIDO_PELO_OCR in paginas[1].texto


# Folha impressa e digitalizada de cabeça para baixo (achada num Prontuário
# real): o OCR da página virada sai lixo. O falso responde à
# pergunta da orientação (`--psm 0`) com o giro pedido e, no OCR, diz onde está a
# faixa escura que a página tem no topo, lendo a imagem que recebeu, com a
# confiança pedida para cada lado em que ela está (90 se não pedida).
TESSERACT_QUE_VE_A_FAIXA = """\
from PIL import Image
if "--psm" in sys.argv:
    sys.stdout.write("Page number: 0\\nRotate: {giro}\\nOrientation confidence: 0.30\\n")
    sys.exit(0)
imagem = Image.open(sys.argv[1]).convert("L")
w, h = imagem.size
lados = {{
    "FAIXA NO TOPO": (0, 0, w, h // 4),
    "FAIXA EMBAIXO": (0, h - h // 4, w, h),
    "FAIXA NA ESQUERDA": (0, 0, w // 4, h),
    "FAIXA NA DIREITA": (w - w // 4, 0, w, h),
}}
escura = min(lados, key=lambda lado: imagem.crop(lados[lado]).resize((1, 1)).getpixel((0, 0)))
dpi = Image.open(sys.argv[1]).info.get("dpi", (0, 0))[0]
escrever(f"{{escura}} DPI {{round(dpi)}}", {confiancas!r}.get(escura, 90))
"""


def _pdf_com_faixa_no_topo() -> bytes:
    from weasyprint import HTML

    capa = f"<p>{CAPA_DO_PRONTUARIO}</p>"
    faixa = '<div style="height: 8cm; background: black"></div>'
    paginas = "".join(f'<div style="page-break-before: always">{corpo}</div>' for corpo in (capa, faixa))
    return HTML(string=f"<html><body>{paginas}</body></html>").write_pdf()


@pytest.mark.parametrize(
    ("giro", "lido"),
    [
        ("0", "FAIXA NO TOPO"),
        # O `Rotate` do tesseract é o giro anti-horário que a página levou; desvirar
        # é girar de volta no horário, e a faixa do topo vai para o lado oposto.
        ("90", "FAIXA NA DIREITA"),
        ("180", "FAIXA EMBAIXO"),
        ("270", "FAIXA NA ESQUERDA"),
    ],
)
def test_pagina_digitalizada_virada_e_desvirada_antes_do_ocr(tmp_path, monkeypatch, giro, lido):
    _tesseract_falso(tmp_path, monkeypatch, TESSERACT_QUE_VE_A_FAIXA.format(giro=giro, confiancas={}))
    pdf = _pdf_com_faixa_no_topo()

    paginas = ler_digitalizadas(pdf, extrair_paginas(pdf))

    assert paginas[1].ocr
    # A imagem desvirada mantém o DPI da rasterização: sem ele o OCR lê pior.
    assert paginas[1].texto.split(extrator.MARCA_DO_OCR)[1].strip() == f"{lido} DPI 300"


@pytest.mark.parametrize(
    ("confiancas", "lido", "qualidade"),
    [
        # O OSD diz 0°, a folha está de cabeça para baixo e sai ilegível: girada
        # 180°, ela sai legível, e fica essa leitura.
        pytest.param({"FAIXA NO TOPO": 20, "FAIXA EMBAIXO": 80}, "FAIXA EMBAIXO", "legivel", id="virada"),
        # A legível não é girada, mesmo que a girada lesse ainda melhor.
        pytest.param({"FAIXA NO TOPO": 75, "FAIXA EMBAIXO": 95}, "FAIXA NO TOPO", "legivel", id="legivel"),
        # Girada também não lê: fica a leitura de maior confiança, a de antes.
        pytest.param({"FAIXA NO TOPO": 30, "FAIXA EMBAIXO": 10}, "FAIXA NO TOPO", "ilegivel", id="manuscrita"),
    ],
)
def test_folha_ilegivel_que_o_osd_nao_gira_e_lida_de_novo_girada(tmp_path, monkeypatch, confiancas, lido, qualidade):
    _tesseract_falso(tmp_path, monkeypatch, TESSERACT_QUE_VE_A_FAIXA.format(giro="0", confiancas=confiancas))
    pdf = _pdf_com_faixa_no_topo()

    paginas = ler_digitalizadas(pdf, extrair_paginas(pdf))

    assert paginas[1].texto.split(extrator.MARCA_DO_OCR)[1].strip() == f"{lido} DPI 300"
    assert paginas[1].qualidade == qualidade


@SO_UNIX_OCR
def test_filho_do_ocr_morto_deixa_a_pagina_sem_texto_e_a_leitura_continua(tmp_path, monkeypatch, caplog):
    # O `pdftoppm` falso mata o filho que o chamou, como o OOM do cgroup faria.
    falso = tmp_path / "pdftoppm"
    corpo = "import os, signal\nos.kill(os.getppid(), signal.SIGKILL)"
    falso.write_text(f"#!{sys.executable}\n{corpo}\n", encoding="utf-8")
    falso.chmod(falso.stat().st_mode | stat.S_IXUSR)
    _tesseract_falso(tmp_path, monkeypatch, f"escrever({LIDO_PELO_OCR!r})")

    paginas = _ler(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO)

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, False, True), (3, False, False)]
    assert "OCR das paginas digitalizadas falhou" in caplog.text


# Qualidade da leitura de cada folha digitalizada (issue #1398). O `tesseract` de
# verdade lê imagens desenhadas aqui mesmo, pelo Pillow: uma folha impressa, uma
# de ruído e a mesma impressa de cabeça para baixo. Nada de PDF real.
FOLHA_IMPRESSA = (
    "PRESCRICAO MEDICA DO PACIENTE INTERNADO",
    "Dipirona sodica quinhentos miligramas",
    "Administrar conforme orientacao medica",
    "Controle de sinais vitais a cada seis horas",
)


def _tesseract_com_portugues() -> bool:
    import subprocess

    if shutil.which("tesseract") is None:
        return False
    idiomas = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()
    return "por" in idiomas


COM_TESSERACT = pytest.mark.skipif(
    not _tesseract_com_portugues(), reason="sem tesseract com o idioma por (o CI instala os dois)"
)


def _folhas_desenhadas(caminho: Path) -> None:
    import random

    from PIL import Image, ImageDraw, ImageFont

    impressa = Image.new("L", (1240, 600), 255)
    desenho = ImageDraw.Draw(impressa)
    fonte = ImageFont.load_default(size=36)
    for i, linha in enumerate(FOLHA_IMPRESSA):
        desenho.text((60, 60 + i * 110), linha, fill=0, font=fonte)
    sorteio = random.Random(1398)
    ruido = Image.frombytes("L", impressa.size, bytes(sorteio.choice((0, 255)) for _ in range(1240 * 600)))
    impressa.save(caminho, save_all=True, append_images=[ruido, impressa.rotate(180)], resolution=150)


@COM_TESSERACT
def test_filho_do_ocr_devolve_texto_e_confianca_de_cada_folha(tmp_path):
    pdf = tmp_path / "folhas.pdf"
    _folhas_desenhadas(pdf)

    lidas = filho.ocr(str(pdf), [1, 2, 3], prazo=60.0)

    assert set(lidas) == {"1", "2", "3"}
    impressa, ruido, virada = lidas["1"], lidas["2"], lidas["3"]
    assert "PRESCRICAO MEDICA" in impressa["texto"]
    assert impressa["confianca"] >= 70
    assert ruido["confianca"] < 50
    assert "PRESCRICAO MEDICA" in virada["texto"]
    assert virada["confianca"] >= 70
