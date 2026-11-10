"""A planilha no chat da Tecnologia (issue #1521, PRD #1519, ADR 0069).

O diretor anexa um `.xlsx` ou um `.csv` pelo mesmo botão do documento, e a
planilha segue o caminho dele (issue #1520): a mesma rota, a mesma fala com
nome e tamanho, o mesmo Anexo da Demanda e o mesmo teto de 100 mil caracteres.
O `.csv` é decodificação de bytes; o `.xlsx` é lido pelo `openpyxl` dentro do
processo isolado do extrator, e cada aba vira um bloco com o nome dela.

Tudo pela ROTA, com o modelo e o GitHub dublados no molde de
`test_tecnologia_documento.py`, e com planilhas de verdade.
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest
from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(__file__))

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
from test_tecnologia_documento import URL_DO_DOCUMENTO, _dentro_da_cerca, _ia, _ler  # noqa: E402

from app.services import assistente_tecnologia, tecnologia_anexos, transcricao_extractor  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

# O valor que so existe na SEGUNDA aba: se ele chega ao prompt, o parser leu
# alem da aba ativa.
SO_NA_SEGUNDA = "glosa do convenio Petrobras em outubro"

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(abas: dict[str, list[list]]) -> bytes:
    """Planilha de verdade, uma aba por chave, na ordem do dicionario."""
    livro = Workbook()
    livro.remove(livro.active)
    for nome, linhas in abas.items():
        aba = livro.create_sheet(nome)
        for linha in linhas:
            aba.append(linha)
    buf = io.BytesIO()
    livro.save(buf)
    return buf.getvalue()


DUAS_ABAS = {
    "Resumo": [["Convenio", "Total"], ["Unimed", 1200]],
    "Glosas de outubro": [["Motivo", "Valor"], [SO_NA_SEGUNDA, 350.5]],
}


@pytest.fixture(autouse=True)
def _memoria_limpa():
    tecnologia_anexos.esquecer_prints()
    yield
    tecnologia_anexos.esquecer_prints()


def _prompt_do_turno(client, monkeypatch, demanda_id: str, documento_id: str) -> str:
    llm = _ia(monkeypatch, _turno(mensagem="Li a planilha. Onde isso acontece?"))
    resposta = client.post(f"{CHAT}/{demanda_id}", json={"documentos": [documento_id]})
    assert resposta.status_code == 200, resposta.text
    return json.dumps(llm.chamadas[-1]["messages"], ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A planilha entra e o agente le
# ═══════════════════════════════════════════════════════════════════════════


class TestOAgenteLeAPlanilha:
    def test_o_prompt_traz_as_duas_abas_cercadas_com_o_nome_do_arquivo_e_de_cada_aba(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        lido = _ler(client, "glosas.xlsx", _xlsx(DUAS_ABAS))
        assert lido.status_code == 200, lido.text

        prompt = _prompt_do_turno(client, monkeypatch, demanda_id, lido.json()["documento_id"])

        [cercado] = [d for d in _dentro_da_cerca(prompt) if SO_NA_SEGUNDA in d]
        assert "Nome do arquivo: glosas.xlsx" in cercado
        assert "Aba: Resumo" in cercado
        assert "Aba: Glosas de outubro" in cercado
        assert "Unimed" in cercado
        # A aba vem antes das linhas dela: o agente sabe de onde e cada valor.
        assert cercado.index("Aba: Resumo") < cercado.index("Unimed") < cercado.index("Aba: Glosas de outubro")
        assert cercado.index("Aba: Glosas de outubro") < cercado.index(SO_NA_SEGUNDA)

    def test_o_csv_entra_como_texto_com_o_nome_do_arquivo(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        csv = f"Motivo;Valor\n{SO_NA_SEGUNDA};350,50\n".encode()
        lido = _ler(client, "glosas.csv", csv)
        assert lido.status_code == 200, lido.text

        prompt = _prompt_do_turno(client, monkeypatch, demanda_id, lido.json()["documento_id"])

        [cercado] = [d for d in _dentro_da_cerca(prompt) if SO_NA_SEGUNDA in d]
        assert "Nome do arquivo: glosas.csv" in cercado

    def test_csv_salvo_pelo_excel_em_latin_1_mantem_os_acentos(self, monkeypatch):
        """O Excel em português salva `.csv` em Windows-1252: decodificar como
        UTF-8 trocaria "Convênio" por um losango."""
        client, _, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        lido = _ler(client, "glosas.csv", "Convênio;Situação\nUnimed;Glosa parcial\n".encode("cp1252"))
        assert lido.status_code == 200, lido.text

        prompt = _prompt_do_turno(client, monkeypatch, demanda_id, lido.json()["documento_id"])

        [cercado] = [d for d in _dentro_da_cerca(prompt) if "Unimed" in d]
        assert "Convênio;Situação" in cercado

    @pytest.mark.parametrize(("nome", "tipo"), [("glosas.xlsx", XLSX), ("glosas.csv", "text/csv")])
    def test_a_fala_mostra_nome_e_tamanho_e_a_planilha_vira_anexo_da_demanda(self, monkeypatch, nome, tipo):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        conteudo = _xlsx(DUAS_ABAS) if nome.endswith(".xlsx") else f"Motivo\n{SO_NA_SEGUNDA}\n".encode()
        lido = _ler(client, nome, conteudo).json()
        _ia(monkeypatch, _turno(mensagem="Onde isso acontece?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"documentos": [lido["documento_id"]]})

        assert resposta.status_code == 200, resposta.text
        fala = resposta.json()["mensagens"][-2]
        assert fala["documentos"] == [{"nome": nome, "tamanho_bytes": len(conteudo)}]
        assert SO_NA_SEGUNDA not in resposta.text
        assert SO_NA_SEGUNDA in _conversas(sb)[0]["mensagens"][-2]["documentos"][0]["texto"]
        [anexo] = sb.tabelas["tecnologia_anexos"]
        assert anexo["content_type"] == tipo
