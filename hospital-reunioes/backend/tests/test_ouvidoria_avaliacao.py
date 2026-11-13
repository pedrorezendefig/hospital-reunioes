"""A Avaliação do QR (issue #1622, PRD #1527, ADR 0086).

O cartaz deixa de abrir direto o formulário: a pessoa dá uma nota de 1 a 5,
marca os motivos se quiser e deixa um comentário opcional. A nota é gravada no
envio, não vira protocolo e não guarda nada de quem avaliou. Quem pede retorno
(ou quer deixar um elogio) segue para a Manifestação guiada, e o caso fica
ligado à avaliação, menos no anonimato.

Os testes sobem a rota real com um banco falso que conhece a tabela nova.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_formulario_publico import (  # noqa: E402
    CLIENTE_DIRETO,
    _BancoFake,
    _make_app,
    _Query,
)

from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria_publica  # noqa: E402

CODIGO = "AB2CD3"
OUTRO_CODIGO = "XY7ZW8"
ROTA_AVALIACAO = f"/api/ouvidoria/publico/pontos/{CODIGO}/avaliacoes"
ROTA_MANIFESTACAO = "/api/ouvidoria/publico/manifestacoes"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _ponto(codigo: str, *, ativo: bool = True, titulo: str = "atendimento_hoje") -> dict:
    return {
        "id": f"ponto-{codigo}",
        "codigo": codigo,
        "setor": "Pronto Socorro",
        "ponto": "Hall da emergência",
        "ativo": ativo,
        "criado_em": "2026-11-01T12:00:00+00:00",
        "nome_publico": "Emergência adulta",
        "descricao_local": "Hall, parede ao lado da passagem",
        "titulo_cartaz": titulo,
        "codigo_controle": None,
        "ala_internacao": False,
    }


class _BancoComAvaliacoes(_BancoFake):
    """O banco do formulário público, mais a tabela da Avaliação."""

    def __init__(self, **kwargs):
        kwargs.setdefault("pontos", [_ponto(CODIGO), _ponto(OUTRO_CODIGO)])
        super().__init__(**kwargs)
        self.avaliacoes: list[dict] = []

    def inserir_avaliacao(self, payload: dict) -> dict:
        linha = {
            "id": f"avaliacao-{len(self.avaliacoes) + 1}",
            "criada_em": "2026-11-12T15:00:00+00:00",
            "pediu_retorno": False,
            **payload,
        }
        self.avaliacoes.append(linha)
        return linha


class _QueryComAvaliacoes(_Query):
    def __init__(self, banco, tabela):
        super().__init__(banco, tabela)
        self._pending_update: dict | None = None

    def update(self, payload: dict):
        self._pending_update = payload
        return self

    def execute(self):
        if self._tabela != "ouvidoria_avaliacoes":
            return super().execute()
        banco = self._banco
        if self._pending_insert is not None:
            return type("R", (), {"data": [banco.inserir_avaliacao(self._pending_insert)]})()
        alvo = [a for a in banco.avaliacoes if all(a.get(c) == v for c, v in self._filters.items())]
        if self._pending_update is not None:
            for linha in alvo:
                linha.update(self._pending_update)
        data = [dict(a) for a in alvo]
        if self._colunas:
            data = [{c: row.get(c) for c in self._colunas} for row in data]
        return type("R", (), {"data": data})()


def _app(banco: _BancoComAvaliacoes | None = None, **kwargs):
    """O app do formulário público com o banco que conhece a avaliação."""
    banco = banco or _BancoComAvaliacoes()
    client, _ = _make_app(banco, **kwargs)
    app = client.app
    from app.dependencies import get_supabase_client

    class _Supabase:
        def table(self, name: str):
            return _QueryComAvaliacoes(banco, name)

    app.dependency_overrides[get_supabase_client] = _Supabase
    return client, banco


class TestANotaNaoViraProtocolo:
    """Critério 1: enviar uma nota não cria manifestação nem protocolo."""

    def test_a_nota_e_gravada_como_avaliacao_e_nao_cria_caso(self):
        client, banco = _app()

        r = client.post(
            ROTA_AVALIACAO,
            json={"nota": 2, "motivos": ["tempo_espera", "limpeza"], "comentario": "Demorou muito."},
        )

        assert r.status_code == 201, r.text
        assert banco.inserts == []
        assert banco.rows == []
        assert len(banco.avaliacoes) == 1
        gravada = banco.avaliacoes[0]
        assert gravada["ponto_id"] == f"ponto-{CODIGO}"
        assert gravada["canal"] == "qr"
        assert gravada["nota"] == 2
        assert gravada["motivos"] == ["tempo_espera", "limpeza"]
        assert gravada["comentario"] == "Demorou muito."
        # O recibo diz só o que a tela precisa para seguir, e nunca protocolo.
        assert r.json() == {"id": gravada["id"], "nota": 2}

    def test_pular_grava_so_a_nota(self):
        """O Pular da tela N2 também grava: a nota já foi dada."""
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json={"nota": 5})

        assert r.status_code == 201, r.text
        assert banco.avaliacoes[0]["nota"] == 5
        assert banco.avaliacoes[0]["motivos"] == []
        assert banco.avaliacoes[0]["comentario"] is None

    @pytest.mark.parametrize(
        "corpo",
        [
            {"nota": 0},
            {"nota": 6},
            {"nota": "3"},
            {"nota": 3, "motivos": ["comida"]},
            {"nota": 3, "comentario": "x" * 501},
        ],
    )
    def test_nota_fora_da_regra_e_recusada_sem_gravar(self, corpo):
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json=corpo)

        assert r.status_code == 422
        assert banco.avaliacoes == []

    def test_cartaz_aposentado_nao_recebe_nota(self):
        """A página abre a Manifestação guiada sem origem nesse caso."""
        client, banco = _app(_BancoComAvaliacoes(pontos=[_ponto(CODIGO, ativo=False)]))

        r = client.post(ROTA_AVALIACAO, json={"nota": 4})

        assert r.status_code == 404
        assert banco.avaliacoes == []

    def test_a_avaliacao_nao_grava_nada_de_quem_avaliou(self):
        """ADR 0086, decisão 2: sem IP, sem aparelho, sem contato, nem quando o
        corpo tenta mandar."""
        client, banco = _app(cliente=CLIENTE_DIRETO)

        r = client.post(
            ROTA_AVALIACAO,
            json={"nota": 1, "nome": "Maria", "contato": "maria@exemplo.com", "ip": "1.2.3.4"},
            headers={"User-Agent": "Celular da Maria"},
        )

        assert r.status_code == 201, r.text
        gravada = banco.avaliacoes[0]
        assert set(gravada) - {"id", "criada_em", "pediu_retorno"} == {
            "ponto_id",
            "canal",
            "nota",
            "motivos",
            "comentario",
        }
        valores = " ".join(str(v) for v in gravada.values())
        for rastro in (CLIENTE_DIRETO[0], "Maria", "Celular"):
            assert rastro not in valores


class TestOLimiteDeNotas:
    """Critério 2: a quarta nota em 10 minutos do mesmo endereço e cartaz é
    recusada, sem gravar nada que identifique quem avaliou."""

    def test_a_quarta_nota_do_mesmo_endereco_e_cartaz_e_recusada(self):
        client, banco = _app(cliente=CLIENTE_DIRETO)

        respostas = [client.post(ROTA_AVALIACAO, json={"nota": 3}) for _ in range(4)]

        assert [r.status_code for r in respostas] == [201, 201, 201, 429]
        assert len(banco.avaliacoes) == 3

    def test_outro_cartaz_do_mesmo_endereco_tem_conta_propria(self):
        client, banco = _app(cliente=CLIENTE_DIRETO)
        for _ in range(3):
            client.post(ROTA_AVALIACAO, json={"nota": 3})

        r = client.post(f"/api/ouvidoria/publico/pontos/{OUTRO_CODIGO}/avaliacoes", json={"nota": 3})

        assert r.status_code == 201, r.text
        assert banco.avaliacoes[-1]["ponto_id"] == f"ponto-{OUTRO_CODIGO}"

    @pytest.mark.parametrize("grafia", [CODIGO.lower(), "Ab2cD3", f"{CODIGO}%20"])
    def test_outra_grafia_do_codigo_nao_abre_conta_nova(self, grafia):
        """O limitador conta pelo caminho da URL. Se `ab2cd3` gravasse, cada
        grafia do mesmo código seria um balde novo, e o limite viraria 3 vezes
        64 para o mesmo cartaz. A nota só entra pela grafia do cartaz, e a
        página manda o código em maiúscula."""
        client, banco = _app(cliente=CLIENTE_DIRETO)
        for _ in range(3):
            client.post(ROTA_AVALIACAO, json={"nota": 3})

        r = client.post(f"/api/ouvidoria/publico/pontos/{grafia}/avaliacoes", json={"nota": 3})

        assert r.status_code in (404, 429)
        assert len(banco.avaliacoes) == 3

    def test_a_recusa_nao_escreve_o_endereco_no_log(self, caplog):
        """O slowapi escreve a chave do limite no log quando ele estoura. A
        chave é endereço e cartaz resumidos, e o IP não aparece."""
        client, _banco = _app(cliente=CLIENTE_DIRETO)
        caplog.set_level(logging.DEBUG)

        respostas = [client.post(ROTA_AVALIACAO, json={"nota": 3}) for _ in range(4)]

        assert respostas[-1].status_code == 429
        assert any("exceeded" in registro.getMessage() for registro in caplog.records)
        assert CLIENTE_DIRETO[0] not in caplog.text
