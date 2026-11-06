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

    def test_o_turno_seguinte_que_traz_titulo_ajusta_o_da_demanda(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_a_melhoria(client, monkeypatch, titulo="Aviso da ata")
        _ia(monkeypatch, _pergunta(contexto="Quem recebe o aviso?", titulo="Aviso por e-mail quando a ata sair"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        assert resposta.status_code == 200, resposta.text
        assert _demandas(sb)[0]["titulo"] == "Aviso por e-mail quando a ata sair"
        assert _titulo_na_lista(client, demanda_id) == "Aviso por e-mail quando a ata sair"

    def test_o_titulo_tem_a_limpeza_do_titulo_do_bug(self, monkeypatch):
        """Uma linha só, sem travessão e no teto de 200 caracteres."""
        client, sb, _ = _cenario(monkeypatch)

        _abrir_a_melhoria(client, monkeypatch, titulo="Aviso  da ata\n— por e-mail " + "x" * 300)

        titulo = _demandas(sb)[0]["titulo"]
        assert titulo.startswith("Aviso da ata")
        assert "\n" not in titulo
        assert "—" not in titulo
        assert len(titulo) == 200


class TestTurnoSemTitulo:
    def test_o_turno_sem_titulo_mantem_o_titulo_atual(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        demanda_id = _abrir_a_melhoria(client, monkeypatch, titulo="Aviso da ata")
        _ia(monkeypatch, _pergunta(contexto="Quem recebe o aviso?"))

        resposta = client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})

        assert resposta.status_code == 200, resposta.text
        assert _demandas(sb)[0]["titulo"] == "Aviso da ata"
        assert _titulo_na_lista(client, demanda_id) == "Aviso da ata"

    def test_a_primeira_pergunta_sem_titulo_nasce_com_o_provisorio(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)

        _abrir_a_melhoria(client, monkeypatch)

        assert _demandas(sb)[0]["titulo"] == "Conversa na aba Tecnologia"


class TestClassificacaoNaLista:
    def test_a_lista_devolve_bug_para_defeito_e_melhoria_para_novo(self, monkeypatch):
        demandas = [
            _demanda("d-bug", tipo="defeito", autor_id=DIRETOR["id"], criado_em="2026-11-02T10:00:00Z"),
            _demanda("d-melhoria", tipo="novo", autor_id=DIRETOR["id"], criado_em="2026-11-01T10:00:00Z"),
            _demanda("d-antiga", tipo="consultoria", autor_id=DIRETOR["id"], criado_em="2026-10-01T10:00:00Z"),
        ]
        client, _, _ = _cenario(monkeypatch, demandas=demandas)

        resposta = client.get(CHAT)

        assert resposta.status_code == 200, resposta.text
        assert [(d["id"], d["classificacao"]) for d in resposta.json()] == [
            ("d-bug", "bug"),
            ("d-melhoria", "melhoria"),
            # O Tipo de antes do chat nao e bug nem melhoria: fica sem selo.
            ("d-antiga", None),
        ]
