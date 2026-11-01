"""Descartar um envio em Contas médicas (issue #1338, PRD #1335).

Quem enviou, ou quem tem o Painel completo, tira da lista a conta em Erro ou
Aguardando arquivo: a conta sai do banco e os PDFs dela (e o texto extraído)
saem do bucket na hora. Tudo pela rota de verdade, com o dublê do banco e do
bucket da suíte do envio.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_contas_medicas_envio import (  # noqa: E402
    ROTA_ENVIO,
    ROTA_MEUS_ENVIOS,
    _cenario,
    _cliente,
    _conta,
    _extrator_de_texto,  # noqa: F401 (fixture autouse do envio)
    _fila_semeada,
    _prontuario,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse do envio)
)

from app.services.contas_medicas_retencao import chave_do_texto  # noqa: E402

BUCKET = "contas-medicas"


def _rota(conta_id: str) -> str:
    return f"/api/contas-medicas/contas/{conta_id}/descartar"


def _enviado(*arquivos, quem: str = "faturista", banco=None):
    banco = banco or _cenario()
    resposta = _cliente(quem, banco).post(ROTA_ENVIO, files=list(arquivos))
    assert resposta.status_code == 200, resposta.text
    return banco


def _chaves(banco) -> set[str]:
    return {chave for (bucket, chave) in banco.bucket if bucket == BUCKET}


def _em_erro(banco) -> dict:
    [conta] = banco.tabelas["cm_conta"]
    conta["situacao"] = "ERRO"
    conta["erro_motivo"] = "Não consegui ler a conta inteira"
    return conta


class TestDescartar:
    def test_quem_enviou_descarta_a_conta_em_erro_e_ela_some_do_banco_e_os_pdfs_do_bucket(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)
        chaves = [a["chave_bucket"] for a in banco.tabelas["cm_arquivo"]]
        assert len(chaves) == 2

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert banco.tabelas["cm_conta"] == []
        assert banco.tabelas["cm_arquivo"] == []
        for chave in chaves:
            assert chave not in _chaves(banco)
            assert chave_do_texto(chave) not in _chaves(banco)

    def test_falta_o_prontuario_e_falta_a_conta_tambem_se_descartam(self):
        so_a_conta = _enviado(_conta("31302", "48001"))
        so_o_prontuario = _enviado(_prontuario("31318"))

        for banco in (so_a_conta, so_o_prontuario):
            [conta] = banco.tabelas["cm_conta"]
            assert conta["situacao"] == "AGUARDANDO_ARQUIVO"

            resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

            assert resposta.status_code == 200, resposta.text
            assert banco.tabelas["cm_conta"] == []
            assert banco.tabelas["cm_arquivo"] == []
            assert _chaves(banco) == set()


class TestQuemPode:
    def test_outra_pessoa_recebe_403_e_nada_sai(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)
        chaves = _chaves(banco)

        resposta = _cliente("outra_faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 403
        assert [c["id"] for c in banco.tabelas["cm_conta"]] == [conta["id"]]
        assert len(banco.tabelas["cm_arquivo"]) == 2
        assert _chaves(banco) == chaves

    def test_a_gestao_com_o_painel_completo_descarta_o_envio_de_outra_pessoa(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)

        resposta = _cliente("coordenadora", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert banco.tabelas["cm_conta"] == []
        assert _chaves(banco) == set()

    def test_o_prontuario_que_outra_pessoa_enviou_fica_para_a_retencao(self):
        banco = _enviado(_prontuario("31302"), quem="outra_faturista")
        _enviado(_conta("31302", "48001"), banco=banco)
        conta = _em_erro(banco)
        do_prontuario = next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == "PRONTUARIO")
        da_conta = next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == "CONTA")

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert banco.tabelas["cm_conta"] == []
        assert banco.tabelas["cm_arquivo"] == [do_prontuario]
        assert do_prontuario["chave_bucket"] in _chaves(banco)
        assert da_conta["chave_bucket"] not in _chaves(banco)

    def test_prontuario_de_mais_de_uma_pessoa_sem_conta_so_a_gestao_descarta(self):
        banco = _enviado(_prontuario("31318"))
        _enviado(_prontuario("31318"), quem="outra_faturista", banco=banco)
        [conta] = banco.tabelas["cm_conta"]
        chaves = _chaves(banco)

        for quem in ("faturista", "outra_faturista"):
            resposta = _cliente(quem, banco).post(_rota(conta["id"]))

            assert resposta.status_code == 403, quem
            assert resposta.json()["detail"] == (
                "Mais de uma pessoa enviou o prontuário deste atendimento. Peça à gestão para descartar."
            )
            assert [c["id"] for c in banco.tabelas["cm_conta"]] == [conta["id"]]
            assert _chaves(banco) == chaves

        assert _cliente("coordenadora", banco).post(_rota(conta["id"])).status_code == 200
        assert banco.tabelas["cm_conta"] == []
        assert banco.tabelas["cm_arquivo"] == []
        assert _chaves(banco) == set()


class TestRecusa:
    @pytest.mark.parametrize("situacao", ["NA_FILA", "PROCESSANDO", "A_FAZER", "CONCLUIDA", "CONCLUIDA_COM_PENDENCIA"])
    def test_conta_processando_na_fila_ou_concluida_e_recusada_e_nada_sai(self, situacao):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        [conta] = banco.tabelas["cm_conta"]
        conta["situacao"] = situacao
        chaves = _chaves(banco)

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "Só a conta em Erro ou aguardando arquivo pode ser descartada."
        assert [c["id"] for c in banco.tabelas["cm_conta"]] == [conta["id"]]
        assert _chaves(banco) == chaves

    def test_conta_em_erro_que_ja_tem_guia_e_recusada(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)
        banco.tabelas["cm_guia_linha"].append({"id": "l-1", "conta_id": conta["id"], "acao": "INCLUIR"})
        chaves = _chaves(banco)

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "A conta já tem Guia e não pode ser descartada."
        assert [c["id"] for c in banco.tabelas["cm_conta"]] == [conta["id"]]
        assert _chaves(banco) == chaves

    def test_conta_que_nao_existe_da_404(self):
        resposta = _cliente("faturista", _cenario()).post(_rota(str(uuid.uuid4())))

        assert resposta.status_code == 404


class TestParcial:
    def test_descartar_uma_parcial_mantem_o_prontuario_que_a_outra_conta_usa(self):
        banco = _enviado(
            _conta("31310", "48010", "01/10/2026", "10/10/2026"),
            _conta("31310", "48011", "11/10/2026", "20/10/2026"),
            _prontuario("31310"),
        )
        contas = {c["numero_conta"]: c for c in banco.tabelas["cm_conta"]}
        descartada, fica = contas["48010"], contas["48011"]
        descartada["situacao"] = "ERRO"
        prontuario = next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == "PRONTUARIO")
        pdf_da_descartada = next(a for a in banco.tabelas["cm_arquivo"] if a["id"] == descartada["arquivo_id"])

        resposta = _cliente("faturista", banco).post(_rota(descartada["id"]))

        assert resposta.status_code == 200, resposta.text
        assert [c["id"] for c in banco.tabelas["cm_conta"]] == [fica["id"]]
        assert prontuario in banco.tabelas["cm_arquivo"]
        assert prontuario["chave_bucket"] in _chaves(banco)
        assert chave_do_texto(prontuario["chave_bucket"]) in _chaves(banco)
        assert fica["arquivo_id"] in {a["id"] for a in banco.tabelas["cm_arquivo"]}
        assert pdf_da_descartada["chave_bucket"] not in _chaves(banco)


class TestCustoDaIa:
    def test_o_custo_da_ia_da_conta_descartada_continua_gravado(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        conta = _em_erro(banco)
        chamada = {"id": "ch-1", "conta_id": conta["id"], "passo": "A", "modelo": "m", "custo_usd": 0.4213}
        banco.tabelas["cm_chamada_ia"] = [dict(chamada)]

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        # O banco solta a conta da chamada (ON DELETE SET NULL); a linha e o custo ficam.
        assert banco.tabelas["cm_chamada_ia"] == [chamada]


class TestReenviar:
    def test_reenviar_o_atendimento_descartado_cria_uma_conta_nova(self):
        banco = _enviado(_conta("31302", "48001"), _prontuario("31302"))
        antiga = _em_erro(banco)
        _cliente("faturista", banco).post(_rota(antiga["id"]))

        _enviado(_conta("31302", "48001"), _prontuario("31302"), banco=banco)

        [nova] = banco.tabelas["cm_conta"]
        assert nova["id"] != antiga["id"]
        assert nova["situacao"] == "NA_FILA"
        assert nova["erro_motivo"] is None
        assert len(banco.tabelas["cm_arquivo"]) == 2


class TestNaLista:
    def test_meus_envios_diz_quais_contas_podem_ser_descartadas(self):
        banco = _fila_semeada()
        erro = next(c for c in banco.tabelas["cm_conta"] if c["id"] == "erro")
        banco.tabelas["cm_conta"].append({**erro, "id": "erro-com-guia", "ordem_fila": 22})
        banco.tabelas["cm_guia_linha"].append({"id": "l-erro", "conta_id": "erro-com-guia", "acao": "INCLUIR"})

        envios = _cliente("faturista", banco).get(ROTA_MEUS_ENVIOS).json()["meus_envios"]

        assert {c["id"]: c["pode_descartar"] for c in envios} == {
            "na-fila": False,
            "falta-prontuario": True,
            "erro": True,
            "erro-com-guia": False,
            "processando": False,
            "falta-conta": True,
        }


KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestKitDeConhecimento:
    def test_diz_quem_descarta_o_que_sai_e_o_que_fica(self):
        secao = KIT.read_text(encoding="utf-8").split("## O envio e a fila", 1)[1].split("\n## ", 1)[0]

        for trecho in (
            "Descartar",
            "Descartar o atendimento 31302? Os arquivos serão apagados.",
            "Erro",
            "Falta o prontuário",
            "Falta a conta",
            "quem enviou",
            "Painel completo",
            "na hora",
            "outra conta do mesmo atendimento",
            "custo da IA",
            "conta nova",
            "Guia",
        ):
            assert trecho in secao, trecho


@pytest.mark.parametrize(
    "arquivo",
    [
        Path(__file__).resolve().parents[1] / "app" / "services" / "contas_medicas" / "descarte.py",
        Path(__file__).resolve(),
    ],
    ids=lambda a: a.name,
)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
