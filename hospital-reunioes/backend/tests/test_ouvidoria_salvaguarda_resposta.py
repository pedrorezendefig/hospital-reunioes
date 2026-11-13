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
