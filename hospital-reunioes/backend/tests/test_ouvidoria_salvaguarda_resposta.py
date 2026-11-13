"""A salvaguarda da resposta no caso com o selo do Núcleo (issue #1627, PRD #1527).

No caso com o selo Em análise pelo NSP, o clique para enviar a resposta ao
manifestante pede antes ao agente de triagem (o mesmo serviço, com o texto
pseudonimizado) que aponte as frases que admitem ou negam falha (seção 4.8 do
anexo da Demanda, ADR 0087, decisão 6). O ouvidor vê os trechos e decide se
envia ou edita: o agente só aponta. Caso sem selo não chama o agente, e falha
do agente não trava o envio.

O banco e o app são os do envio ao Núcleo; o cliente da Anthropic é o
`ClienteFalso`: nada chega à IA de verdade.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anthropic_apoio import ClienteFalso  # noqa: E402
from test_ouvidoria_nucleo_seguranca_paciente import _banco, _caso, _client  # noqa: E402

from app.services import ouvidoria_agente_triagem  # noqa: E402

ROTA = "/api/ouvidoria/manifestacoes/uuid-7/salvaguarda-da-resposta"

RESPOSTA_QUE_ADMITE = (
    "Prezada Ana Maria Souza, verificamos que houve erro da enfermagem na grade do leito. "
    "Lamentamos o ocorrido e seguimos à disposição."
)

APONTAMENTO = json.dumps(
    {
        "trechos": [
            {
                "trecho": "verificamos que houve erro da enfermagem na grade do leito",
                "motivo": "Admite falha da equipe antes da conclusão do Núcleo.",
            }
        ]
    }
)


@pytest.fixture
def modelo(monkeypatch):
    """O agente simulado. O teste troca `modelo.texto` para mudar a resposta."""
    cliente = ClienteFalso(APONTAMENTO)
    monkeypatch.setattr(ouvidoria_agente_triagem, "_cliente", lambda: cliente)
    return cliente


def _pedir(client, texto: str = RESPOSTA_QUE_ADMITE):
    return client.post(ROTA, json={"texto": texto})


class TestOCasoComSeloMostraOTrecho:
    """Critério 1: caso com selo e resposta com frase de admissão de erro
    mostra o trecho apontado antes do envio."""

    def test_a_resposta_que_admite_erro_volta_com_o_trecho_apontado(self, monkeypatch, modelo):
        client, _ = _client(monkeypatch, _banco(_caso(nsp_decisao="confirmado")))

        r = _pedir(client)

        assert r.status_code == 200, r.text
        assert r.json() == {
            "analisada": True,
            "trechos": [
                {
                    "trecho": "verificamos que houve erro da enfermagem na grade do leito",
                    "motivo": "Admite falha da equipe antes da conclusão do Núcleo.",
                }
            ],
        }
        assert len(modelo.chamadas) == 1

    def test_o_texto_vai_ao_agente_pseudonimizado(self, monkeypatch, modelo):
        client, _ = _client(monkeypatch, _banco(_caso(nsp_decisao="confirmado")))

        _pedir(client)

        (chamada,) = modelo.chamadas
        enviado = json.dumps(chamada["messages"], ensure_ascii=False)
        assert "erro da enfermagem" in enviado
        assert "Ana Maria Souza" not in enviado
        assert "admitam ou neguem falha" in chamada["system"]


class TestOCasoSemSeloNaoChamaOAgente:
    """Critério 2: caso sem selo não chama o agente."""

    @pytest.mark.parametrize("decisao", [None, "descartado"])
    def test_caso_sem_selo_responde_sem_leitura(self, monkeypatch, modelo, decisao):
        client, _ = _client(monkeypatch, _banco(_caso(nsp_decisao=decisao, nsp_sugerido=True)))

        r = _pedir(client)

        assert r.status_code == 200, r.text
        assert r.json() == {"analisada": False, "trechos": []}
        assert modelo.chamadas == []


class TestAFalhaDoAgenteNaoTravaOEnvio:
    """Critério 3: falha do agente deixa enviar normalmente."""

    @pytest.mark.parametrize(
        "resposta",
        [RuntimeError("timeout"), "isto não é JSON", json.dumps({"sem": "trechos"})],
        ids=["erro", "texto", "formato"],
    )
    def test_falha_do_agente_responde_sem_leitura(self, monkeypatch, modelo, resposta):
        modelo.texto = resposta
        client, _ = _client(monkeypatch, _banco(_caso(nsp_decisao="confirmado")))

        r = _pedir(client)

        assert r.status_code == 200, r.text
        assert r.json() == {"analisada": False, "trechos": []}

    def test_o_caso_com_selo_encerra_com_a_resposta_depois_da_falha(self, monkeypatch, modelo):
        modelo.texto = RuntimeError("timeout")
        client, supabase = _client(monkeypatch, _banco(_caso(nsp_decisao="confirmado", status="respondido")))
        assert _pedir(client).json()["analisada"] is False

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "encerrado", "desfecho": "procedente", "desfecho_descricao": RESPOSTA_QUE_ADMITE},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"


class TestOKitDeConhecimento:
    """Critério 4: o texto do Produto Ouvidoria no kit de conhecimento diz o
    comportamento novo."""

    @pytest.fixture
    def paragrafo(self) -> str:
        from app.services.conhecimento import CONHECIMENTO_DIR

        texto = (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")
        achados = [linha for linha in texto.splitlines() if "admitem ou negam falha" in linha]
        assert len(achados) == 1
        return achados[0]

    def test_diz_quando_o_agente_le_a_resposta_e_quem_decide(self, paragrafo):
        assert "Em análise pelo NSP" in paragrafo
        assert "antes de a resposta sair" in paragrafo
        assert "o ouvidor decide se edita o texto ou envia assim mesmo" in paragrafo

    def test_diz_que_sem_selo_nao_le_e_que_a_falha_nao_trava(self, paragrafo):
        assert "Caso sem o selo não passa pelo agente" in paragrafo
        assert "a resposta sai normalmente" in paragrafo
