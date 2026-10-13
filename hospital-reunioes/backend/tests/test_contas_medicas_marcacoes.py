"""Marcações de caixa e botão e formulário em branco aprendido (issue #1132, PRD #1128).

No PDF do MV a marcação não está no texto: cada caixa (14 x 14) e cada botão
(140 x 160) é uma imagem, e o `pdftotext` devolve "VMI VNI Cateter nasal" sem
dizer qual foi marcado. O PDF dos testes é montado aqui, à mão, com texto em
Helvetica e imagens em tons de cinza cuja fração de pixels escuros é a medida
pelo diretor nos desenhos do MV (caixa vazia 0,27 e marcada 0,39; botão vazio
0,48 e marcado 0,61). PDF real nunca entra em teste.
"""

from __future__ import annotations

import re
import tomllib
import zlib
from datetime import date
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_contas_medicas_prontuario import ATENDIMENTO, CAPA_QUE_BATE, montar

from app.services import contas_medicas_extrator as extrator
from app.services.contas_medicas.formulario import sem_formulario_em_branco
from app.services.contas_medicas.prontuario import Documento, Prontuario, ler_prontuario
from app.services.contas_medicas_extrator import extrair_paginas

CAIXA_VAZIA = (14, 14, 0.27)
CAIXA_MARCADA = (14, 14, 0.39)
BOTAO_VAZIO = (140, 160, 0.48)
BOTAO_MARCADO = (140, 160, 0.61)


def _pixels(largura: int, altura: int, fracao_escura: float) -> bytes:
    escuros = round(largura * altura * fracao_escura)
    return bytes([0] * escuros + [255] * (largura * altura - escuros))


def _pdf(textos: list[tuple[int, int, str]], imagens: list[tuple[int, int, int, int, tuple]]) -> bytes:
    """Uma página A4. `textos`: (x, y, texto); `imagens`: (x, y, largura e altura
    desenhadas em pontos, (largura, altura, fração escura) da imagem). Origem embaixo."""
    conteudo = [f"BT /F1 10 Tf {x} {y} Td ({t}) Tj ET" for x, y, t in textos]
    conteudo += [f"q {w} 0 0 {h} {x} {y} cm /Im{i} Do Q" for i, (x, y, w, h, _) in enumerate(imagens)]
    stream = "\n".join(conteudo).encode("latin-1")
    xobjetos = " ".join(f"/Im{i} {6 + i} 0 R" for i in range(len(imagens)))
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            f"/Resources << /Font << /F1 5 0 R >> /XObject << {xobjetos} >> >> >>"
        ).encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for *_, (largura, altura, fracao) in imagens:
        dados = zlib.compress(_pixels(largura, altura, fracao))
        objetos.append(
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
            b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n"
            % (largura, altura, len(dados))
            + dados
            + b"\nendstream"
        )
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    inicio_da_xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicao in posicoes:
        saida += b"%010d 00000 n \n" % posicao
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_da_xref)
    return bytes(saida)


# Um formulário do editor de documentos do MV (Família DOC_EDITOR): cabeçalho com
# PACIENTE e ATENDIMENTO, título, texto livre e duas perguntas. A ventilação tem o
# rótulo na linha de cima e caixas; a dieta tem o rótulo na mesma linha e botões.
FORMULARIO = _pdf(
    [
        (50, 800, "PACIENTE: PACIENTE FICTICIA"),
        (50, 788, "ATENDIMENTO: 31245"),
        (50, 760, "EVOLUCAO DE FONOAUDIOLOGIA"),
        (50, 745, "Paciente colaborativa, alerta, responde a comandos simples durante a sessao."),
        (50, 730, "Degluticao avaliada com consistencia pastosa, sem sinais de aspiracao."),
        (50, 700, "Suporte ventilat\xf3rio:"),
        (62, 685, "VMI"),
        (122, 685, "VNI"),
        (50, 660, "Dieta:"),
        (100, 660, "VO"),
        (160, 660, "SNE"),
    ],
    [
        (50, 684, 8, 8, CAIXA_VAZIA),
        (110, 684, 8, 8, CAIXA_MARCADA),
        (88, 659, 8, 9, BOTAO_MARCADO),
        (148, 659, 8, 9, BOTAO_VAZIO),
    ],
)


def _linhas(texto: str) -> list[str]:
    return [" ".join(linha.split()) for linha in texto.split("\n") if linha.strip()]


def test_caixa_e_botao_viram_x_ou_colchete_vazio_na_linha_da_opcao():
    paginas = extrair_paginas(FORMULARIO)

    linhas = _linhas(paginas[0].texto)
    assert "Suporte ventilatório:" in linhas
    assert "[ ] VMI [X] VNI" in linhas
    assert "Dieta: [X] VO [ ] SNE" in linhas


def test_leitura_das_marcacoes_que_falha_deixa_o_texto_sem_elas_e_sem_conteudo_no_log(tmp_path, monkeypatch, caplog):
    quebrado = tmp_path / "marcacoes_quebradas.py"
    quebrado.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(extrator, "_CAMINHO_DAS_MARCACOES", str(quebrado))

    paginas = extrair_paginas(FORMULARIO)

    linhas = _linhas(paginas[0].texto)
    assert "VMI VNI" in linhas
    assert "Dieta: VO SNE" in linhas
    assert "segue sem elas" in caplog.text
    assert "31245" not in caplog.text


def _linhas_para_a_ia() -> list[str]:
    """O formulário extraído, lido como página de um Prontuário: as linhas que vão à IA."""
    pagina = extrair_paginas(FORMULARIO)[0].texto
    prontuario = ler_prontuario(montar(CAPA_QUE_BATE, [pagina]), ATENDIMENTO)
    (documento,) = prontuario.documentos
    assert documento.familia == "DOC_EDITOR"
    return list(documento.linhas)


def test_so_a_opcao_a_direita_do_x_fica_no_texto_que_vai_a_ia():
    linhas = _linhas_para_a_ia()

    assert "Dieta: [X] VO" in linhas
    texto = "\n".join(linhas)
    assert "SNE" not in texto
    assert "VMI" not in texto
    assert "[ ]" not in texto


def test_rotulo_na_linha_de_cima_com_dois_pontos_vai_junto_da_opcao_marcada():
    linhas = _linhas_para_a_ia()

    assert "Suporte ventilatório: [X] VNI" in linhas
    assert "Suporte ventilatório:" not in linhas


# ═══════════════════════════════════════════════════════════════════════════
# Formulário em branco aprendido
# ═══════════════════════════════════════════════════════════════════════════


class _Banco:
    """Dublê do Supabase só com o que o aprendizado usa de `cm_linha_formulario`."""

    def __init__(self):
        self.linhas: list[dict] = []

    def table(self, nome: str):
        assert nome == "cm_linha_formulario"
        return _Consulta(self)


class _Consulta:
    def __init__(self, banco: _Banco):
        self._banco = banco
        self._filtro = lambda _linha: True
        self._upsert: list[dict] | None = None

    def select(self, *_a, **_kw):
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtro = lambda linha: linha[coluna] in valores
        return self

    def upsert(self, linhas, on_conflict: str):
        assert on_conflict == "familia,linha"
        self._upsert = list(linhas)
        return self

    def execute(self):
        if self._upsert is not None:
            for nova in self._upsert:
                chave = (nova["familia"], nova["linha"])
                velha = next((v for v in self._banco.linhas if (v["familia"], v["linha"]) == chave), None)
                if velha:
                    velha.update(nova)
                else:
                    self._banco.linhas.append(dict(nova))
            return SimpleNamespace(data=self._upsert)
        return SimpleNamespace(data=[dict(linha) for linha in self._banco.linhas if self._filtro(linha)])


TITULO = "EVOLUÇÃO DE FISIOTERAPIA"
MODELO = [
    "Ausculta pulmonar:",
    "Padrão respiratório:",
    "Conduta fisioterapêutica:",
    "Orientações ao paciente e acompanhante:",
]
EM_TRES_DE_CINCO = "Paciente em ar ambiente."


def _documento(familia: str, linhas: list[str]) -> Documento:
    return Documento(familia, (1,), ATENDIMENTO, date(2026, 10, 3), None, None, None, None, tuple(linhas))


def _prontuario(*documentos: Documento) -> Prontuario:
    return Prontuario(ATENDIMENTO, 10, None, {}, None, None, tuple(documentos), (), ())


def _cinco_fisioterapias() -> Prontuario:
    """Cinco documentos da mesma Família: cada linha do modelo falta em um deles (está
    em 4 de 5, 80%); a de ar ambiente está em 3 de 5 (60%); cada um tem uma linha só dele."""
    documentos = []
    for i in range(5):
        linhas = [TITULO] + [linha for j, linha in enumerate(MODELO) if j != i]
        if i < 3:
            linhas.append(EM_TRES_DE_CINCO)
        linhas.append(f"Saturação {90 + i}% após a sessão.")
        documentos.append(_documento("FISIO_RESP", linhas))
    return _prontuario(*documentos)


def test_linha_em_80_por_cento_dos_documentos_da_familia_e_aprendida_e_sai_do_texto():
    banco = _Banco()
    prontuario = _cinco_fisioterapias()
    assert all(sum(linha in d.linhas for d in prontuario.documentos) == 4 for linha in MODELO)

    limpo = sem_formulario_em_branco(banco, prontuario, aprender=True)

    assert sorted((r["familia"], r["linha"], r["contagem"]) for r in banco.linhas) == sorted(
        ("FISIO_RESP", linha, 1) for linha in MODELO
    )
    for documento in limpo.documentos:
        assert not set(MODELO) & set(documento.linhas)
        assert documento.linhas[0] == TITULO
    assert sum(EM_TRES_DE_CINCO in d.linhas for d in limpo.documentos) == 3
    assert [d.linhas[-1] for d in limpo.documentos] == [f"Saturação {90 + i}% após a sessão." for i in range(5)]


def test_contagem_acumula_entre_prontuarios():
    banco = _Banco()

    sem_formulario_em_branco(banco, _cinco_fisioterapias(), aprender=True)
    sem_formulario_em_branco(banco, _cinco_fisioterapias(), aprender=True)

    assert {r["linha"]: r["contagem"] for r in banco.linhas} == dict.fromkeys(MODELO, 2)


def test_prontuario_com_um_formulario_so_perde_as_linhas_aprendidas_com_os_outros():
    banco = _Banco()
    sem_formulario_em_branco(banco, _cinco_fisioterapias(), aprender=True)
    sozinho = _prontuario(_documento("FISIO_RESP", [TITULO, *MODELO, "Paciente em VNI."]))

    limpo = sem_formulario_em_branco(banco, sozinho, aprender=True)

    assert limpo.documentos[0].linhas == (TITULO, "Paciente em VNI.")
    assert {r["contagem"] for r in banco.linhas} == {1}


# ═══════════════════════════════════════════════════════════════════════════
# Licença e tipografia
# ═══════════════════════════════════════════════════════════════════════════

BACKEND = Path(__file__).resolve().parents[1]


def _dependencias_do_pyproject() -> list[str]:
    projeto = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return [re.match(r"[A-Za-z0-9_.\-]+", d).group(0) for d in projeto["dependencies"]]


def _licenca(pacote: str) -> str:
    dados = metadata.metadata(pacote)
    classificadores = [c for c in dados.get_all("Classifier") or [] if c.startswith("License")]
    return " ".join([dados.get("License-Expression") or "", dados.get("License") or "", *classificadores])


def test_nenhuma_dependencia_do_pyproject_tem_licenca_agpl():
    dependencias = _dependencias_do_pyproject()
    assert {"pdfplumber", "pillow"} <= {d.lower() for d in dependencias}

    agpl = {d: _licenca(d) for d in dependencias if re.search(r"AGPL|Affero", _licenca(d), re.I)}

    assert agpl == {}
    assert not {"pymupdf", "fitz"} & {d.lower() for d in dependencias}


@pytest.mark.parametrize(
    "arquivo",
    [
        "app/services/contas_medicas/marcacoes.py",
        "app/services/contas_medicas/formulario.py",
        "app/services/contas_medicas_marcacoes_filho.py",
    ],
)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = (BACKEND / arquivo).read_text(encoding="utf-8")

    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
