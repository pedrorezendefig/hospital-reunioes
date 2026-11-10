"""O documento no chat da Tecnologia (issue #1520, PRD #1519, ADR 0069, emenda de 09/11/2026).

O diretor anexa um `.md`, `.txt`, `.pdf` ou `.docx` pelo mesmo botão do print.
A rota do documento extrai o texto pelo extrator da Ata Guiada (parser em
processo isolado, issue #758), guarda os bytes só na memória com um
identificador efêmero e devolve nome, tamanho e contagem de caracteres, sem IA.
A fala do chat leva o identificador: o original vira Anexo da Demanda, e o
texto extraído fica guardado junto da fala, cercado no prompt de todo turno
seguinte e fora da tela.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de
`test_tecnologia_chat.py`. Cada tipo aceito tem um arquivo de verdade, e a prova
é um trecho que só existe dentro dele.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_extracao_isolada import _montar_pdf, _pdf_sem_texto  # noqa: E402
from test_planejamento_demanda import _ia  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    CHAT,
    _cenario,
    _comecar,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import BASE  # noqa: E402

from app.services import assistente_tecnologia, tecnologia_anexos  # noqa: E402

URL_DO_DOCUMENTO = f"{BASE}/assistente/ler-documento"

# O trecho que so existe dentro do arquivo: se ele chega ao prompt, foi o
# documento que chegou, e nao o nome nem a fala.
TRECHO = "auditoria das glosas do terceiro trimestre"


def _pdf_com_texto(*linhas: str) -> bytes:
    """PDF de verdade, com texto que o `pdfplumber` le: uma linha por `Tj`."""
    stream = b"BT /F1 11 Tf 72 720 Td 14 TL " + b" ".join(f"({linha}) '".encode("latin-1") for linha in linhas) + b" ET"
    return _montar_pdf(stream, b"")


def _docx_com_texto(*paragrafos: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        corpo = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragrafos)
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            f'wordprocessingml/2006/main"><w:body>{corpo}</w:body></w:document>',
        )
    return buf.getvalue()


# O PDF precisa de 200 bytes de texto para nao passar por escaneado (o filtro
# do extrator), entao ele leva o trecho no meio de um texto de verdade.
_LINHAS_DO_PDF = (
    "Melhorias pedidas pela diretoria para o modulo de Contas medicas.",
    f"Primeiro ponto: {TRECHO}, com o total por convenio.",
    "Segundo ponto: o relatorio sai em PDF para a reuniao de segunda.",
    "Terceiro ponto: o auditor ve o motivo da glosa na mesma tela.",
)

ARQUIVOS = {
    ".md": ("melhorias.md", f"# Melhorias\n\n- {TRECHO}\n".encode()),
    ".txt": ("melhorias.txt", f"Melhorias\n{TRECHO}\n".encode()),
    ".pdf": ("melhorias.pdf", _pdf_com_texto(*_LINHAS_DO_PDF)),
    ".docx": ("melhorias.docx", _docx_com_texto("Melhorias", TRECHO)),
}


@pytest.fixture(autouse=True)
def _memoria_limpa():
    tecnologia_anexos.esquecer_prints()
    yield
    tecnologia_anexos.esquecer_prints()


def _ler(client, nome: str, conteudo: bytes):
    # O content-type do cliente vai errado de proposito: quem decide e a extensao.
    return client.post(URL_DO_DOCUMENTO, files={"documento": (nome, conteudo, "image/png")})


def _lido(client, extensao: str = ".md") -> dict:
    nome, conteudo = ARQUIVOS[extensao]
    resposta = _ler(client, nome, conteudo)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _dentro_da_cerca(prompt: str) -> list[str]:
    partes = prompt.split(assistente_tecnologia.MARCA_INICIO_DE_FORA)[1:]
    return [p.split(assistente_tecnologia.MARCA_FIM_DE_FORA)[0] for p in partes]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O documento entra e o agente le
# ═══════════════════════════════════════════════════════════════════════════


class TestOAgenteLeODocumento:
    @pytest.mark.parametrize("extensao", list(ARQUIVOS))
    def test_o_prompt_do_turno_seguinte_traz_o_texto_cercado_com_o_nome(self, monkeypatch, extensao):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        lido = _lido(client, extensao)
        llm = _ia(monkeypatch, _turno(mensagem="Entendi o documento. Onde isso acontece?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"documentos": [lido["documento_id"]]})

        assert resposta.status_code == 200, resposta.text
        prompt = json.dumps(llm.chamadas[-1]["messages"], ensure_ascii=False)
        [cercado] = [d for d in _dentro_da_cerca(prompt) if TRECHO in d]
        assert f"Nome do arquivo: melhorias{extensao}" in cercado
