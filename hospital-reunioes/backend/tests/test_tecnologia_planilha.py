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
    CAMPOS_RESPONDIDOS,
    CHAT,
    CRITERIOS,
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


# ═══════════════════════════════════════════════════════════════════════════
# 2. O parser do .xlsx roda isolado
# ═══════════════════════════════════════════════════════════════════════════


class TestOParserIsolado:
    """O orcamento do filho so morde quem roda no filho: lido aqui dentro, o
    `.xlsx` passaria pelos dois tetos encolhidos e voltaria 200."""

    @pytest.mark.parametrize("estouro", ["memoria", "prazo"])
    def test_xlsx_que_estoura_o_orcamento_vira_recusa_e_o_worker_segue_atendendo(self, monkeypatch, estouro):
        client, _, _ = _cenario(monkeypatch)
        # O vigia olha o filho a cada 10 ms: nenhum interpretador sobe o
        # `openpyxl` nesse tempo, entao o teto encolhido morde sempre.
        monkeypatch.setattr(transcricao_extractor, "INTERVALO_DE_VIGIA", 0.01)
        if estouro == "memoria":
            monkeypatch.setattr(transcricao_extractor, "TETO_DE_MEMORIA_DO_FILHO", 1)
            monkeypatch.setattr(transcricao_extractor, "PRAZO_DA_EXTRACAO", 300.0)
        else:
            monkeypatch.setattr(transcricao_extractor, "PRAZO_DA_EXTRACAO", 0.0)

        resposta = _ler(client, "glosas.xlsx", _xlsx(DUAS_ABAS))

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == tecnologia_anexos.MOTIVO_DOCUMENTO_COMPLEXO
        assert tecnologia_anexos._prints == {}
        # O worker nao caiu: a proxima leitura, sem parser, entra.
        assert _ler(client, "glosas.csv", b"Motivo\nGlosa\n").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 3. Os tetos e as recusas
# ═══════════════════════════════════════════════════════════════════════════


class TestRecusas:
    @pytest.mark.parametrize(("nome", "teto_em_mb"), [("a.csv", 5), ("a.xlsx", 15)])
    def test_planilha_acima_do_teto_do_tipo_e_recusada_com_413(self, monkeypatch, nome, teto_em_mb):
        client, _, _ = _cenario(monkeypatch)

        resposta = _ler(client, nome, b"x" * (teto_em_mb * 1024 * 1024 + 1))

        assert resposta.status_code == 413
        assert resposta.json()["detail"] == (
            f"O arquivo {nome[1:]} passou do limite de {teto_em_mb} MB. "
            "Divida o documento em partes menores e mande uma de cada vez."
        )

    def test_csv_no_teto_cravado_nao_e_recusado_pelo_tamanho(self, monkeypatch):
        """5 MB cravados passam pelo tamanho e caem no teto de caracteres, que
        e outra frase e outro status."""
        client, _, _ = _cenario(monkeypatch)

        resposta = _ler(client, "a.csv", b"x" * (5 * 1024 * 1024))

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == tecnologia_anexos.MOTIVO_TEXTO_GRANDE

    def test_xlsx_com_mais_de_cem_mil_caracteres_pede_para_dividir(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        grande = _xlsx({"Linhas": [[f"linha {i:06d}", "x" * 40] for i in range(2500)]})

        resposta = _ler(client, "grande.xlsx", grande)

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == tecnologia_anexos.MOTIVO_TEXTO_GRANDE

    def test_xlsx_que_nao_abre_tem_a_frase_do_arquivo_ilegivel(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)

        resposta = _ler(client, "quebrada.xlsx", b"isto nao e um zip")

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == tecnologia_anexos.MOTIVO_DOCUMENTO_ILEGIVEL

    @pytest.mark.parametrize("nome", ["antiga.xls", "ANTIGA.XLS"])
    def test_xls_antigo_e_recusado_com_a_frase_que_pede_para_salvar_como_xlsx(self, monkeypatch, nome):
        client, _, _ = _cenario(monkeypatch)

        resposta = client.post(URL_DO_DOCUMENTO, files={"documento": (nome, b"\xd0\xcf\x11\xe0", XLSX)})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == (
            "Planilha no formato antigo (.xls) não entra. Abra no Excel, salve como .xlsx e anexe de novo."
        )

    def test_a_frase_do_tipo_fora_da_lista_diz_que_a_planilha_entra(self):
        frase = assistente_tecnologia.MOTIVO_TIPO_FORA_DA_LISTA

        assert "documento (.md, .txt, .pdf, .docx, .csv ou .xlsx)" in frase


# ═══════════════════════════════════════════════════════════════════════════
# 4. A frase da issue conta a planilha como documento
# ═══════════════════════════════════════════════════════════════════════════


class TestAFraseDaIssue:
    def test_o_card_do_bug_conta_as_planilhas_como_documento_e_nao_leva_trecho_delas(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        planilhas = [
            _ler(client, "glosas.xlsx", _xlsx(DUAS_ABAS)).json()["documento_id"],
            _ler(client, "glosas.csv", f"Motivo\n{SO_NA_SEGUNDA}\n".encode()).json()["documento_id"],
        ]
        _ia(monkeypatch, _turno(mensagem="Como repetir?"))
        assert client.post(f"{CHAT}/{demanda_id}", json={"documentos": planilhas}).status_code == 200
        _ia(monkeypatch, _turno(pronto=True, campos=CAMPOS_RESPONDIDOS, criterios=CRITERIOS))
        assert client.post(f"{CHAT}/{demanda_id}", json={"texto": "Abrindo o caso"}).status_code == 200

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        assert "Anexos: 2 documentos na Demanda" in corpo
        for vestigio in (SO_NA_SEGUNDA, "glosas.xlsx", "glosas.csv", "Glosas de outubro"):
            assert vestigio not in corpo, vestigio


# ═══════════════════════════════════════════════════════════════════════════
# 5. O Kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDaTecnologia:
    def test_o_kit_diz_que_a_planilha_entra_com_o_teto_e_o_que_fazer_com_o_xls(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## Os anexos da Demanda", 1)[1].split("\n## ", 1)[0]
        for trecho in (
            "planilha em .csv, de até 5 MB, e em .xlsx (Excel), de até 15 MB",
            "lê todas as abas",
            "A planilha no formato antigo (.xls) não entra; salve como .xlsx",
        ):
            assert trecho in secao, trecho

    def test_o_kit_diz_na_conversa_que_a_planilha_entra_pelo_mesmo_botao(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## A conversa com o Assistente", 1)[1].split("\n## ", 1)[0]
        assert "uma planilha do Excel" in secao
