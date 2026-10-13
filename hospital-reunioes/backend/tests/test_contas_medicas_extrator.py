"""Extrator de texto de PDF do módulo Contas médicas (issue #1116, ADR 0070).

O PDF é gerado aqui mesmo, pelo WeasyPrint do projeto: PDF real de conta ou de
prontuário nunca entra no repositório. Para provar o teto de memória e o prazo,
um `pdftotext` falso entra na frente do PATH e faz o papel do arquivo hostil.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from app.services import contas_medicas_extrator as extrator
from app.services import transcricao_extractor
from app.services.contas_medicas_extrator import (
    ErroLeitura,
    Pagina,
    Palavra,
    extrair_paginas,
    extrair_palavras,
    paginas_do_texto_guardado,
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
# testa não tem `tesseract`: um falso entra na frente do PATH e faz o papel dele,
# com o form feed no fim, como o de verdade imprime.
CAPA_DO_PRONTUARIO = "DECLARAÇÃO DE RECEBIMENTO DE PRONTUÁRIO " + " ".join(
    f"Grupo: {grupo} Quantidade: 1"
    for grupo in ("EVOLUÇÃO MEDICA", "PRESCRICAO MEDICA", "ANOTAÇÕES DE ENFERMAGEM", "TERMOS DIGITALIZADOS")
)
PAGINA_COM_TEXTO = "EVOLUÇÃO MEDICA " + "Paciente estável, sem queixas, segue em observação na unidade. " * 4
LIDO_PELO_OCR = "TERMO DE CONSENTIMENTO LIVRE E ESCLARECIDO"


def _tesseract_falso(pasta: Path, monkeypatch: pytest.MonkeyPatch, corpo: str) -> None:
    falso = pasta / "tesseract"
    falso.write_text(f"#!{sys.executable}\nimport sys, time\n{corpo}\n", encoding="utf-8")
    falso.chmod(falso.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ['PATH']}")


def test_pagina_digitalizada_do_prontuario_ganha_o_texto_do_ocr_marcada_como_ocr(tmp_path, monkeypatch):
    _tesseract_falso(tmp_path, monkeypatch, f"sys.stdout.write({LIDO_PELO_OCR!r} + '\\n\\f')")

    paginas = extrair_paginas(_pdf(CAPA_DO_PRONTUARIO, "", PAGINA_COM_TEXTO))

    assert [(p.numero, p.ocr, p.sem_texto) for p in paginas] == [(1, False, False), (2, True, False), (3, False, False)]
    assert LIDO_PELO_OCR in paginas[1].texto
    assert LIDO_PELO_OCR not in paginas[2].texto
    # Guardado no bucket e lido de volta, a página continua sendo de OCR e o
    # form feed do `tesseract` não abre página nova.
    guardadas = paginas_do_texto_guardado(texto_para_guardar(paginas))
    assert [(p.numero, p.ocr) for p in guardadas] == [(1, False), (2, True), (3, False)]
