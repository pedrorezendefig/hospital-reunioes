"""Planejamento da Demanda: a primeira pergunta ponta a ponta (issue #1345, PRD #1344, ADR 0075).

O botão "Planejar com a IA" abre uma conversa em que a IA faz as perguntas de
negócio, uma por vez, com duas opções e a recomendada marcada. Aqui:

* **A migration 123**, lida do disco: as duas tabelas e o RLS default-deny.
* **O turno**, direto no serviço, com o cliente da Anthropic dublado no molde
  de `test_assistente_tecnologia` (troca `ai_processor._get_llm`). Nenhum teste
  chega à API de verdade: o `_llm_provider` nasce em mock em todo teste, e a
  trava de rede da suíte (`conftest.py`) reprova quem tentar.
* **As rotas**, pelo router de verdade, com o Supabase dublado do
  `test_tecnologia_vinculo` (o mesmo cenário que os testes dos Anexos usam).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.services import planejamento_demanda  # noqa: E402
from app.services.conhecimento import carregar_kit  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_123 = MIGRATIONS / "123_tecnologia_planejamento.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 123
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_123.read_text(encoding="utf-8")


def _colunas_da_tabela(sql: str, tabela: str) -> dict[str, str]:
    """Coluna -> o resto da linha que a declara."""
    bloco = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\);", sql, flags=re.DOTALL)
    assert bloco, f"a 123 nao cria {tabela}"
    colunas = {}
    for linha in bloco.group(1).splitlines():
        partes = linha.strip().split(None, 1)
        if partes and partes[0][0].isalpha() and partes[0].upper() != "CHECK":
            colunas[partes[0]] = partes[1] if len(partes) > 1 else ""
    return colunas


class TestMigracao:
    def test_cria_o_planejamento_um_por_demanda(self):
        colunas = _colunas_da_tabela(_sql(), "tecnologia_planejamentos")

        assert {"demanda_id", "estado", "mensagens", "decisoes", "modelo", "criado_em", "atualizado_em"} <= set(
            colunas
        )
        # Um planejamento por Demanda: a unicidade mora no banco.
        assert "UNIQUE" in colunas["demanda_id"]
        assert "REFERENCES tecnologia_demandas(id)" in colunas["demanda_id"]
        assert colunas["mensagens"].startswith("JSONB")
        assert colunas["decisoes"].startswith("JSONB")

    def test_cria_a_chamada_de_ia_da_tecnologia_no_molde_de_contas_medicas(self):
        colunas = _colunas_da_tabela(_sql(), "tecnologia_chamadas_ia")

        assert {
            "demanda_id",
            "modelo",
            "tokens_entrada",
            "tokens_saida",
            "tokens_cache",
            "custo_usd",
            "duracao_ms",
            "sucesso",
            "criado_em",
        } <= set(colunas)
        # O custo fica, mesmo que a Demanda saia.
        assert "ON DELETE SET NULL" in colunas["demanda_id"]

    def test_rls_default_deny_nas_duas_tabelas(self):
        sql = _sql()

        for tabela in ("tecnologia_planejamentos", "tecnologia_chamadas_ia"):
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela
        # Default-deny: quem le e escreve e o backend com a service_role.
        assert "CREATE POLICY" not in sql.upper()

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = "\n".join(linha for linha in _sql().splitlines() if not linha.startswith("--")).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (123) ON CONFLICT (numero) DO NOTHING;")


@pytest.fixture(autouse=True)
def _llm_em_mock(monkeypatch):
    """O pytest carrega o `.env` real (chave de PROD). Sem isto, qualquer teste
    que chegasse ao servico bateria no provedor de verdade."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


# ═══════════════════════════════════════════════════════════════════════════
# 2. O turno (o servico, sem estado)
# ═══════════════════════════════════════════════════════════════════════════


def _uso(entrada: int = 1000, saida: int = 200, lidos: int = 0, escritos: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=entrada,
        output_tokens=saida,
        cache_read_input_tokens=lidos,
        cache_creation_input_tokens=escritos,
    )


class _ClienteFalso:
    """A Anthropic de mentira: guarda os argumentos de cada chamada e devolve o
    texto dado, com o `usage` dado. `texto` pode ser uma excecao."""

    def __init__(self, texto: str | BaseException, usage: SimpleNamespace | None = None, stop_reason="end_turn"):
        self.texto = texto
        self.usage = usage or _uso()
        self.stop_reason = stop_reason
        self.chamadas: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        if isinstance(self.texto, BaseException):
            raise self.texto
        # Com o thinking ligado, o bloco de texto vem depois do de pensamento.
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.texto)],
            stop_reason=self.stop_reason,
            usage=self.usage,
        )


def _ia(monkeypatch, texto: str | BaseException, **kw) -> _ClienteFalso:
    """Troca o cliente do `ai_processor`, que e o mesmo do Assistente."""
    from app.services import ai_processor

    cliente = _ClienteFalso(texto, **kw)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "anthropic")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (cliente, "modelo-do-resto-do-app"))
    return cliente


def _pergunta(**campos) -> str:
    base = {
        "encerrou": False,
        "decisao_fechada": None,
        "contexto": "Preciso saber quem vai usar a tela nova.",
        "opcao_a": "Só a recepção.",
        "opcao_b": "A recepção e a enfermagem.",
        "recomendada": "A",
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


def _encerrou(**campos) -> str:
    base = {
        "encerrou": True,
        "decisao_fechada": "A enfermagem também usa.",
        "contexto": "Já tenho o que preciso para a Vitta planejar.",
        "opcao_a": None,
        "opcao_b": None,
        "recomendada": None,
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


DEMANDA = {
    "id": "d-1",
    "titulo": "Agenda de retorno na recepção",
    "tipo": "novo",
    "descricao": "O que precisa: marcar o retorno do paciente na saída",
}


def _pergunta_guardada(n: int) -> dict:
    return {
        "tipo": "pergunta",
        "contexto": f"Pergunta {n}?",
        "opcoes": [{"letra": "A", "texto": f"A{n}"}, {"letra": "B", "texto": f"B{n}"}],
        "recomendada": "A",
    }


def _resposta_guardada(n: int) -> dict:
    return {"tipo": "resposta", "opcao": "A", "texto": f"A{n}"}


def _conversa_com(perguntas: int) -> list[dict]:
    """`perguntas` perguntas da IA, todas respondidas pelo diretor."""
    conversa: list[dict] = []
    for n in range(1, perguntas + 1):
        conversa += [_pergunta_guardada(n), _resposta_guardada(n)]
    return conversa


def _turno(mensagens: list[dict] | None = None):
    return planejamento_demanda.turno(demanda=DEMANDA, mensagens=mensagens or [], kit=carregar_kit())


class TestTurno:
    def test_devolve_a_pergunta_estruturada(self, monkeypatch):
        _ia(monkeypatch, _pergunta(decisao_fechada=None))

        resultado = _turno()

        assert resultado.erro is None
        assert resultado.mensagem == {
            "tipo": "pergunta",
            "contexto": "Preciso saber quem vai usar a tela nova.",
            "opcoes": [
                {"letra": "A", "texto": "Só a recepção."},
                {"letra": "B", "texto": "A recepção e a enfermagem."},
            ],
            "recomendada": "A",
        }
        assert resultado.decisao is None

    def test_a_decisao_que_a_resposta_fechou_volta_a_parte(self, monkeypatch):
        _ia(monkeypatch, _pergunta(decisao_fechada="Só a recepção usa a tela nova."))

        resultado = _turno(_conversa_com(1))

        assert resultado.decisao == "Só a recepção usa a tela nova."

    def test_devolve_encerrou_quando_o_modelo_tem_o_bastante(self, monkeypatch):
        _ia(monkeypatch, _encerrou())

        resultado = _turno(_conversa_com(3))

        assert resultado.mensagem == {"tipo": "encerrou", "contexto": "Já tenho o que preciso para a Vitta planejar."}
        assert resultado.decisao == "A enfermagem também usa."

    def test_nunca_passa_de_doze_perguntas(self, monkeypatch):
        """Com a 12a respondida, o modelo ainda quer perguntar: o turno encerra
        assim mesmo, e a decisao da 12a resposta nao se perde."""
        _ia(monkeypatch, _pergunta(decisao_fechada="Decidido na 12a."))

        resultado = _turno(_conversa_com(12))

        assert resultado.mensagem["tipo"] == "encerrou"
        assert resultado.mensagem["contexto"] == planejamento_demanda.TEXTO_DO_TETO
        assert resultado.decisao == "Decidido na 12a."

    def test_com_onze_perguntas_ainda_pergunta_a_decima_segunda(self, monkeypatch):
        _ia(monkeypatch, _pergunta())

        assert _turno(_conversa_com(11)).mensagem["tipo"] == "pergunta"

    def test_o_prompt_diz_quantas_perguntas_restam(self, monkeypatch):
        cliente = _ia(monkeypatch, _pergunta())

        _turno(_conversa_com(9))

        assert "PERGUNTAS QUE AINDA RESTAM: 3" in cliente.chamadas[0]["messages"][0]["content"]

    def test_o_servico_e_sem_estado_e_nao_mexe_na_conversa_que_recebeu(self, monkeypatch):
        _ia(monkeypatch, _pergunta())
        conversa = _conversa_com(2)
        antes = json.dumps(conversa)

        _turno(conversa)

        assert json.dumps(conversa) == antes

    def test_tira_o_travessao_do_que_o_modelo_escreveu(self, monkeypatch):
        _ia(monkeypatch, _pergunta(contexto="Quem usa \u2014 a recepção?", opcao_a="Só ela \u2013 sempre."))

        mensagem = _turno().mensagem

        assert "\u2014" not in json.dumps(mensagem, ensure_ascii=False)
        assert "\u2013" not in json.dumps(mensagem, ensure_ascii=False)
