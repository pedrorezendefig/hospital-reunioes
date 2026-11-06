"""O título da melhoria desde a primeira resposta e o selo Bug ou Melhoria na
lista (issue #1438, PRD #1436).

A saída do turno do Planejamento da Demanda ganha um título opcional, com o
mesmo limite e a mesma limpeza do título do bug, e a rota grava esse título na
Demanda a cada turno em que ele vier. A lista ao lado do chat devolve a
classificação de cada Demanda já traduzida do Tipo (Defeito é bug, Novo é
melhoria). Tudo pela ROTA, com o modelo dublado no molde de `test_tecnologia_chat`.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    DIRETOR,
    _cenario,
    _demandas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_vinculo import BASE, _demanda  # noqa: E402

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.prompt_loader import load_prompt  # noqa: E402

CHAT = f"{BASE}/chat"


def _abrir_a_melhoria(client, monkeypatch, **campos) -> str:
    _ia(monkeypatch, _pergunta(**campos))
    resposta = client.post(CHAT, json={"escolha": "melhoria"})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["demanda_id"]


def _titulo_na_lista(client, demanda_id: str) -> str:
    [item] = [d for d in client.get(CHAT).json() if d["id"] == demanda_id]
    return item["titulo"]


class TestTituloDaMelhoria:
    def test_a_primeira_resposta_da_melhoria_ja_da_o_titulo_da_demanda(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        demanda_id = _abrir_a_melhoria(client, monkeypatch, titulo="Aviso por e-mail quando a ata sair")

        assert _demandas(sb)[0]["titulo"] == "Aviso por e-mail quando a ata sair"
        assert _titulo_na_lista(client, demanda_id) == "Aviso por e-mail quando a ata sair"
