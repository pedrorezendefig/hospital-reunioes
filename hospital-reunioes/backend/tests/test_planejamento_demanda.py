"""Planejamento da Demanda: a primeira pergunta ponta a ponta (issue #1345, PRD #1344, ADR 0075).

A melhoria do chat (ADR 0077) segue por uma conversa em que a IA faz as
perguntas de negócio, uma por vez, com duas opções e a recomendada marcada. A
tela antiga do Planejamento, com as rotas dela, saiu na issue #1386; as rotas
do chat são provadas em `test_tecnologia_chat_melhoria.py`. Aqui:

* **A migration 123**, lida do disco: as duas tabelas e o RLS default-deny.
* **O turno**, direto no serviço, com o cliente da Anthropic dublado no molde
  de `test_assistente_tecnologia` (troca `ai_processor._get_llm`). Nenhum teste
  chega à API de verdade: o `_llm_provider` nasce em mock em todo teste, e a
  trava de rede da suíte (`conftest.py`) reprova quem tentar.
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

        assert {"demanda_id", "estado", "mensagens", "decisoes", "modelo", "criado_em", "atualizado_em"} <= set(colunas)
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


class TestOPedidoAIA:
    def test_o_bloco_fixo_vai_com_cache_e_antes_de_tudo_que_varia(self, monkeypatch):
        """A instrucao e o kit sao o `system`, com o `cache_control` no ultimo
        bloco dele; a Demanda, a conversa e a resposta vem DEPOIS, na mensagem
        do usuario, e nenhuma delas entra no prefixo em cache."""
        cliente = _ia(monkeypatch, _pergunta())
        conversa = [_pergunta_guardada(1), {"tipo": "resposta", "opcao": None, "texto": "S\u00f3 no turno da noite."}]

        _turno(conversa)

        enviado = cliente.chamadas[0]
        sistema = enviado["system"]
        assert [bloco.get("cache_control") for bloco in sistema] == [None, {"type": "ephemeral"}]
        fixo = "\n".join(bloco["text"] for bloco in sistema)
        assert "Planejamento da Demanda" in fixo  # a instrucao
        assert "A Etapa nunca \u00e9 digitada \u00e0 m\u00e3o" in fixo  # uma frase que so existe no kit
        variavel = enviado["messages"][0]["content"]
        for o_que_varia in (DEMANDA["titulo"], DEMANDA["descricao"], "Pergunta 1?", "S\u00f3 no turno da noite."):
            assert o_que_varia not in fixo
            assert o_que_varia in variavel
        # Depois do bloco fixo vem texto puro, sem marca de cache nenhuma.
        assert isinstance(variavel, str)

    def test_o_bloco_fixo_e_o_mesmo_para_qualquer_demanda_e_qualquer_turno(self, monkeypatch):
        cliente = _ia(monkeypatch, _pergunta())

        planejamento_demanda.turno(demanda=DEMANDA, mensagens=[], kit=carregar_kit())
        outra = {**DEMANDA, "id": "d-2", "titulo": "Outra coisa", "descricao": "Outro texto"}
        planejamento_demanda.turno(demanda=outra, mensagens=_conversa_com(4), kit=carregar_kit())

        assert cliente.chamadas[0]["system"] == cliente.chamadas[1]["system"]

    def test_usa_o_modelo_do_planejamento_sem_mexer_no_thinking_nem_no_effort(self, monkeypatch):
        cliente = _ia(monkeypatch, _pergunta())

        _turno()

        enviado = cliente.chamadas[0]
        assert settings.llm_model_planejamento == "claude-opus-5-5"
        assert enviado["model"] == "claude-opus-5-5"
        assert "thinking" not in enviado
        assert "effort" not in json.dumps(enviado.get("output_config", {}))

    def test_a_variavel_troca_o_modelo(self, monkeypatch):
        cliente = _ia(monkeypatch, _pergunta())
        monkeypatch.setattr(settings, "llm_model_planejamento", "claude-sonnet-5-5")

        _turno()

        assert cliente.chamadas[0]["model"] == "claude-sonnet-5-5"


class TestOCustoDaChamada:
    def test_grava_modelo_tokens_custo_duracao_e_sucesso(self, monkeypatch):
        # Opus 5.5: US$ 4 entrada, US$ 20 saida, US$ 0,20 leitura e US$ 5 escrita de cache por milhao.
        _ia(monkeypatch, _pergunta(), usage=_uso(entrada=1000, saida=500, lidos=20000, escritos=2000))

        chamada = _turno().chamada

        assert chamada["demanda_id"] == "d-1"
        assert chamada["passo"] == "pergunta"
        assert chamada["modelo"] == "claude-opus-5-5"
        assert chamada["tokens_entrada"] == 23000
        assert chamada["tokens_saida"] == 500
        assert chamada["tokens_cache"] == 20000
        # 1000*4 + 500*20 + 20000*0,20 + 2000*5 = 28000 por milhao
        assert chamada["custo_usd"] == 0.028
        assert isinstance(chamada["duracao_ms"], int)
        assert chamada["sucesso"] is True

    def test_modelo_fora_da_tabela_grava_custo_zero(self, monkeypatch):
        _ia(monkeypatch, _pergunta())
        monkeypatch.setattr(settings, "llm_model_planejamento", "modelo-sem-preco")

        assert _turno().chamada["custo_usd"] == 0


def _erro_do_provedor() -> anthropic.APIStatusError:
    requisicao = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.InternalServerError("fora do ar", response=httpx.Response(500, request=requisicao), body=None)


class TestFalhaDoTurno:
    @pytest.mark.parametrize(
        "texto",
        [
            pytest.param("isto n\u00e3o \u00e9 JSON", id="nao-e-json"),
            pytest.param(_pergunta(opcao_b=None), id="pergunta-sem-a-opcao-b"),
            pytest.param(_pergunta(recomendada="C"), id="recomendada-fora-de-A-e-B"),
            pytest.param(json.dumps({"encerrou": False}), id="sem-contexto"),
        ],
    )
    def test_saida_que_nao_valida_contra_o_esquema_vira_erro_claro(self, monkeypatch, texto):
        _ia(monkeypatch, texto, usage=_uso(entrada=900, saida=300))

        resultado = _turno(_conversa_com(1))

        assert resultado.mensagem is None
        assert resultado.erro == planejamento_demanda.MOTIVO_TURNO_FALHOU
        # A resposta fora do formato foi cobrada: a chamada fica, sem sucesso.
        assert resultado.chamada["sucesso"] is False
        assert resultado.chamada["tokens_saida"] == 300

    def test_erro_do_provedor_vira_erro_claro(self, monkeypatch):
        _ia(monkeypatch, _erro_do_provedor())

        resultado = _turno()

        assert resultado.mensagem is None
        assert resultado.erro == planejamento_demanda.MOTIVO_TURNO_FALHOU
        assert resultado.chamada["sucesso"] is False
        assert resultado.chamada["tokens_entrada"] == 0

    def test_recusa_do_modelo_vira_erro_claro(self, monkeypatch):
        _ia(monkeypatch, _pergunta(), stop_reason="refusal")

        assert _turno().erro == planejamento_demanda.MOTIVO_TURNO_FALHOU


# ═══════════════════════════════════════════════════════════════════════════
# 2b. O resumo (issue #1347): Fechar e resumir
# ═══════════════════════════════════════════════════════════════════════════


def _resumo(decisoes: list[dict] | None = None, em_aberto: list[str] | None = None) -> str:
    if decisoes is None:
        decisoes = [{"pergunta": 1, "porque": "A recepção marca o retorno."}]
    if em_aberto is None:
        em_aberto = ["Quem confirma o retorno com o paciente."]
    return json.dumps({"decisoes": decisoes, "em_aberto": em_aberto}, ensure_ascii=False)


def _resumir(mensagens: list[dict] | None = None):
    return planejamento_demanda.resumir(demanda=DEMANDA, mensagens=mensagens or [], kit=carregar_kit())


class TestResumo:
    def test_a_decisao_traz_a_pergunta_a_escolha_do_diretor_e_o_porque(self, monkeypatch):
        _ia(monkeypatch, _resumo())

        resultado = _resumir(_conversa_com(1))

        assert resultado.erro is None
        assert resultado.resumo == {
            "decisoes": [{"pergunta": "Pergunta 1?", "escolha": "A1", "porque": "A recepção marca o retorno."}],
            "em_aberto": ["Quem confirma o retorno com o paciente."],
            "termos": [],
            "candidatas_a_adr": [],
        }

    def test_o_que_o_agente_nao_perguntou_nunca_vira_decisao(self, monkeypatch):
        """O modelo inventa uma decisao para a pergunta 5 (que nao existe) e
        outra para a 2 (feita, mas sem resposta): nenhuma das duas entra."""
        _ia(
            monkeypatch,
            _resumo(
                decisoes=[
                    {"pergunta": 1, "porque": "Dito pelo diretor."},
                    {"pergunta": 2, "porque": "Inventado sobre a pergunta sem resposta."},
                    {"pergunta": 5, "porque": "Inventado sobre pergunta que nao houve."},
                ]
            ),
        )

        resultado = _resumir([*_conversa_com(1), _pergunta_guardada(2)])

        assert [d["escolha"] for d in resultado.resumo["decisoes"]] == ["A1"]

    def test_a_escolha_e_a_resposta_do_diretor_e_nao_o_que_o_modelo_escreve(self, monkeypatch):
        _ia(monkeypatch, _resumo(decisoes=[{"pergunta": 1, "escolha": "Outra coisa", "porque": "Porque sim."}]))
        conversa = [_pergunta_guardada(1), {"tipo": "resposta", "opcao": None, "texto": "Só no plantão da noite."}]

        assert _resumir(conversa).resumo["decisoes"][0]["escolha"] == "Só no plantão da noite."

    def test_na_primeira_pergunta_o_resumo_sai_sem_decisao(self, monkeypatch):
        _ia(monkeypatch, _resumo(decisoes=[], em_aberto=["Quem usa a agenda."]))

        resultado = _resumir([_pergunta_guardada(1)])

        assert resultado.resumo == {
            "decisoes": [],
            "em_aberto": ["Quem usa a agenda."],
            "termos": [],
            "candidatas_a_adr": [],
        }

    def test_o_pedido_numera_as_perguntas_e_leva_o_que_nao_bateu(self, monkeypatch):
        cliente = _ia(monkeypatch, _resumo())
        conversa = [*_conversa_com(2), {"tipo": "nao_bateu", "texto": "A enfermagem também usa."}]

        _resumir(conversa)

        enviado = cliente.chamadas[0]
        variavel = enviado["messages"][0]["content"]
        assert "PEDIDO: RESUMO" in variavel
        assert "[Pergunta 2] Pergunta 2?" in variavel
        assert "A enfermagem também usa." in variavel
        # Mesmo bloco fixo do turno: o cache do prefixo vale para o resumo.
        assert [bloco.get("cache_control") for bloco in enviado["system"]] == [None, {"type": "ephemeral"}]

    def test_o_custo_do_resumo_e_gravado_como_passo_resumo(self, monkeypatch):
        _ia(monkeypatch, _resumo(), usage=_uso(entrada=1000, saida=500, lidos=20000, escritos=2000))

        chamada = _resumir(_conversa_com(1)).chamada

        assert chamada["passo"] == "resumo"
        assert chamada["modelo"] == "claude-opus-5-5"
        assert chamada["tokens_cache"] == 20000
        assert chamada["custo_usd"] == 0.028
        assert chamada["sucesso"] is True

    def test_tira_o_travessao_do_que_o_modelo_escreveu(self, monkeypatch):
        _ia(
            monkeypatch,
            _resumo(decisoes=[{"pergunta": 1, "porque": "Porque \u2014 sim."}], em_aberto=["Prazo \u2013 qual?"]),
        )

        resumo = json.dumps(_resumir(_conversa_com(1)).resumo, ensure_ascii=False)

        assert "\u2014" not in resumo
        assert "\u2013" not in resumo

    @pytest.mark.parametrize(
        "texto",
        [
            pytest.param("isto não é JSON", id="nao-e-json"),
            pytest.param(json.dumps({"decisoes": [{"pergunta": "um"}], "em_aberto": []}), id="decisao-fora"),
            pytest.param(json.dumps({"decisoes": []}), id="sem-em-aberto"),
            pytest.param(_erro_do_provedor(), id="provedor-fora"),
        ],
    )
    def test_falha_vira_erro_claro_e_a_chamada_fica_sem_sucesso(self, monkeypatch, texto):
        _ia(monkeypatch, texto)

        resultado = _resumir(_conversa_com(1))

        assert resultado.resumo is None
        assert resultado.erro == planejamento_demanda.MOTIVO_TURNO_FALHOU
        assert resultado.chamada["sucesso"] is False


class TestOPromptDoPlanejamento:
    def test_manda_citar_o_que_ja_foi_decidido_ao_recusar_ou_redirecionar(self, monkeypatch):
        """A instrucao (o primeiro bloco), e nao o kit: o kit ja traz o titulo
        da secao em todo arquivo, e um teste que lesse os dois passaria sem
        instrucao nenhuma."""
        cliente = _ia(monkeypatch, _pergunta())

        _turno()

        instrucao = cliente.chamadas[0]["system"][0]["text"]
        trecho = re.search(r"[^\n]*O que já foi decidido[^\n]*", instrucao)
        assert trecho, "a instrucao nao cita a secao O que já foi decidido"
        assert "recusar" in trecho.group(0)
        assert "redirecionar" in trecho.group(0)
