"""A Manifestação guiada em cinco passos (issue #1620, PRD #1527, ADR 0086).

O formulário público deixa de ser uma tela só e vira os passos M1 a M5 da
seção 4.2 da especificação da Diretoria: identificação, sobre o quê, quando e
onde, o que aconteceu e contato. O que muda no servidor:

- o caso guarda quando e onde foi (data, período, hora aproximada, o local que
  a pessoa escolheu e o quarto), os profissionais citados, a data de
  nascimento do paciente e o que a pessoa espera da Ouvidoria;
- o telefone ganha coluna própria, e o e-mail continua no contato de hoje,
  que é o que o acuse lê;
- quem se identifica deixa nome e ao menos um dos dois.

Os testes sobem a rota real com o mesmo banco falso do formulário público.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from test_ouvidoria_formulario_publico import CARTAZ, _BancoFake, _make_app  # noqa: E402

ROTA = "/api/ouvidoria/publico/manifestacoes"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _guiada(**overrides) -> dict:
    """O envio do passo a passo com o mínimo que a especificação exige, de quem
    se identifica e deixa só o e-mail."""
    payload = {
        "anonimo": False,
        "sobre": "mim",
        "data_ocorrencia": "2026-11-10",
        "periodo": "tarde",
        "local_informado": "Emergência adulta",
        "relato": "Esperei duas horas na emergência sem nenhuma informação.",
        "expectativa": "resposta",
        "nome": "Maria Souza",
        "contato": "maria@exemplo.com",
    }
    payload.update(overrides)
    return {chave: valor for chave, valor in payload.items() if valor is not None}


class TestOCasoGuardaQuandoEOnde:
    def test_o_envio_guiado_grava_quando_onde_e_o_que_a_pessoa_espera(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(hora_aprox="14:30"))

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["data_ocorrencia"] == "2026-11-10"
        assert gravado["periodo"] == "tarde"
        assert gravado["hora_aprox"] == "14:30:00"
        assert gravado["local_informado"] == "Emergência adulta"
        assert gravado["expectativa"] == "resposta"
