"""Analisar de novo a conta em Erro sem anexar o PDF (issue #1339, PRD #1335).

Quando o erro foi da IA, da configuração ou do app (a ação do Código do erro é
Analisar de novo) e os PDFs ainda estão no bucket, quem enviou, ou quem tem o
Painel completo, devolve a conta para a fila com um clique. Erro de arquivo e
PDF vencido continuam com "Enviar de novo", e a rota recusa com a frase. Tudo
pela rota de verdade, com o dublê do banco e do bucket da suíte do envio.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_contas_medicas_envio import (  # noqa: E402
    KIT,
    ROTA_ENVIO,
    ROTA_MEUS_ENVIOS,
    _cenario,
    _cliente,
    _conta,
    _extrator_de_texto,  # noqa: F401 (fixture autouse do envio)
    _prontuario,
    _reset_rate_limiter,  # noqa: F401 (fixture autouse do envio)
)

from app.services.contas_medicas.processamento import pegar_da_fila  # noqa: E402


def _rota(conta_id: str) -> str:
    return f"/api/contas-medicas/contas/{conta_id}/analisar-de-novo"


def _em_erro(codigo: str, frase: str = "A IA está fora do ar ou sobrecarregada agora.", quem: str = "faturista"):
    """A conta e o prontuário enviados por `quem`, e a análise parada em Erro
    com o `codigo`, na terceira tentativa."""
    banco = _cenario()
    resposta = _cliente(quem, banco).post(ROTA_ENVIO, files=[_conta("31302", "48001"), _prontuario("31302")])
    assert resposta.status_code == 200, resposta.text
    [conta] = banco.tabelas["cm_conta"]
    conta.update(
        {
            "situacao": "ERRO",
            "erro_motivo": frase,
            "erro_codigo": codigo,
            "erro_detalhe": {"tipo": "APIStatusError", "http": 529, "etapa": "passo_b", "em": "2026-11-01T10:00:00"},
            "tentativas": 3,
        }
    )
    return banco, conta


def _cartao(banco, quem: str = "faturista") -> dict:
    resposta = _cliente(quem, banco).get(ROTA_MEUS_ENVIOS)
    assert resposta.status_code == 200, resposta.text
    [cartao] = resposta.json()["meus_envios"]
    return cartao


def _arquivo(banco, tipo: str) -> dict:
    return next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == tipo)


class TestOCartao:
    @pytest.mark.parametrize("codigo", ["CM-IA-FORA-DO-AR", "CM-CFG-MEMORIA", "CM-IA-ANTIGO"])
    def test_erro_da_ia_da_configuracao_ou_antigo_com_pdf_guardado_mostra_analisar_de_novo(self, codigo):
        banco, _ = _em_erro(codigo)

        assert _cartao(banco)["erro_acao"] == "analisar_de_novo"
        assert _cartao(banco, "coordenadora")["erro_acao"] == "analisar_de_novo"

    def test_erro_de_arquivo_mostra_enviar_de_novo(self):
        banco, _ = _em_erro("CM-ARQ-SOMA", "Não consegui ler a conta inteira")

        assert _cartao(banco)["erro_acao"] == "enviar_de_novo"

    @pytest.mark.parametrize("tipo", ["CONTA", "PRONTUARIO"])
    def test_pdf_que_saiu_do_bucket_mostra_enviar_de_novo(self, tipo):
        banco, _ = _em_erro("CM-IA-FORA-DO-AR")
        _arquivo(banco, tipo)["apagado_em"] = "2026-11-01T03:00:00+00:00"

        assert _cartao(banco)["erro_acao"] == "enviar_de_novo"

    def test_pdf_que_passou_dos_7_dias_mostra_enviar_de_novo_antes_da_retencao_rodar(self):
        banco, _ = _em_erro("CM-IA-FORA-DO-AR")
        _arquivo(banco, "PRONTUARIO")["apagar_em"] = "2026-10-01T10:00:00+00:00"

        assert _cartao(banco)["erro_acao"] == "enviar_de_novo"


class TestAnalisarDeNovo:
    def test_quem_enviou_poe_a_conta_na_fila_zerada_e_a_analise_roda_sem_novo_upload(self):
        banco, conta = _em_erro("CM-IA-FORA-DO-AR")
        arquivos = [dict(a) for a in banco.tabelas["cm_arquivo"]]

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert conta["situacao"] == "NA_FILA"
        assert conta["tentativas"] == 0
        assert conta["erro_codigo"] is None
        assert conta["erro_detalhe"] is None
        assert conta["erro_motivo"] is None
        assert _cartao(banco)["situacao"] == "NA_FILA"
        # Nenhum arquivo novo: a análise usa os PDFs que já estão no bucket.
        assert banco.tabelas["cm_arquivo"] == arquivos
        pega = pegar_da_fila(banco, datetime.now(UTC))
        assert pega is not None and pega["id"] == conta["id"]
        assert conta["situacao"] == "PROCESSANDO"
        assert conta["tentativas"] == 1

    def test_a_gestao_com_o_painel_completo_analisa_de_novo_o_envio_de_outra_pessoa(self):
        banco, conta = _em_erro("CM-IA-ANTIGO", "Tente de novo em alguns minutos")

        resposta = _cliente("coordenadora", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 200, resposta.text
        assert conta["situacao"] == "NA_FILA"

    def test_outra_pessoa_recebe_403_e_a_conta_fica_em_erro(self):
        banco, conta = _em_erro("CM-IA-FORA-DO-AR")

        resposta = _cliente("outra_faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Só quem enviou a conta ou a gestão pode analisar de novo."
        assert conta["situacao"] == "ERRO"
        assert conta["erro_codigo"] == "CM-IA-FORA-DO-AR"

    def test_pdf_vencido_recusa_com_a_frase_e_a_conta_fica_em_erro(self):
        banco, conta = _em_erro("CM-IA-FORA-DO-AR")
        _arquivo(banco, "CONTA")["apagado_em"] = "2026-11-01T03:00:00+00:00"

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "O PDF já passou dos 7 dias e saiu do sistema. Envie de novo."
        assert conta["situacao"] == "ERRO"
        assert conta["tentativas"] == 3

    def test_erro_de_arquivo_recusa_com_a_frase_e_a_conta_fica_em_erro(self):
        banco, conta = _em_erro("CM-ARQ-SOMA", "Não consegui ler a conta inteira")

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "O problema está no PDF. Envie o arquivo de novo."
        assert conta["situacao"] == "ERRO"
        assert conta["erro_codigo"] == "CM-ARQ-SOMA"

    def test_conta_fora_do_erro_recusa(self):
        banco, conta = _em_erro("CM-IA-FORA-DO-AR")
        conta["situacao"] = "PROCESSANDO"

        resposta = _cliente("faturista", banco).post(_rota(conta["id"]))

        assert resposta.status_code == 409
        assert conta["situacao"] == "PROCESSANDO"

    def test_conta_que_nao_existe_da_404(self):
        banco, _ = _em_erro("CM-IA-FORA-DO-AR")

        resposta = _cliente("faturista", banco).post(_rota("00000000-0000-0000-0000-000000000000"))

        assert resposta.status_code == 404


class TestKitDeConhecimento:
    def test_diz_quando_aparece_analisar_de_novo_e_quando_fica_enviar_de_novo(self):
        secao = KIT.read_text(encoding="utf-8").split("## O envio e a fila", 1)[1].split("\n## ", 1)[0]

        for trecho in ("Analisar de novo", "sem anexar", "7 dias", "Na fila", "Tente de novo em alguns minutos"):
            assert trecho in secao, trecho
