"""A tela de triagem do Núcleo (issue #1992, PRD #1979, ADR 0095 e 0107).

Um bloco por critério de aceite do backend:

1. a fila mostra as notificações sem triagem confirmada, da mais antiga para a
   mais nova, com a faixa sugerida e sem nome de paciente ou profissional;
2. nas faixas A e B e nos casos de revisão forçada, confirmar exige todos os
   campos conferidos; não existe "aceitar tudo";
3. nas faixas C, D e E, confirmar é um clique;
4. ajustar grava a linha da pessoa com as divergências, e a sugestão original
   continua gravada;
5. recorrência, casos parecidos, frequência e prioridade saem calculados; os
   cortes de frequência se editam na Configuração;
6. a notificação "classificar manualmente" abre sem sugestão.

O banco é o dublê em memória do teste da notificação, com o que a migration
188 e a 194 fazem no insert da triagem: a versão em sequência e uma decisão de
pessoa por notificação. Nenhum dado de pessoa real.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_seguranca_do_paciente_notificacoes import (  # noqa: E402
    DIRETOR_EXECUTIVO,
    MEMBRO,
    NUCLEO,
    PRESIDENTE,
    SETOR,
    SUPER_ADMIN,
    _Banco,
    _Consulta,
    _participacao,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import seguranca_do_paciente_triagem as triagem_router  # noqa: E402
from app.services.seguranca_do_paciente import triagem  # noqa: E402

OUTRO_SETOR = {"id": "44444444-4444-4444-4444-444444444444", "nome": "Centro Cirúrgico", "ativo": True}
RECUSA = {"detail": "Conteúdo restrito ao Núcleo de Segurança do Paciente"}
DIA = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ═══════════════════════════════════════════════════════════════════════════
# O dublê: o que a 188 e a 194 fazem no insert da triagem
# ═══════════════════════════════════════════════════════════════════════════


class _ConsultaDaTriagem(_Consulta):
    def _inserir(self) -> list[dict]:
        if self._nome == "nsp_triagens":
            novas = self._valores if isinstance(self._valores, list) else [self._valores]
            for valores in novas:
                mesmas = [t for t in self._linhas if t["notificacao_id"] == valores["notificacao_id"]]
                if valores.get("autor_tipo") == "pessoa" and any(t["autor_tipo"] == "pessoa" for t in mesmas):
                    raise APIError({"code": "23505", "message": "duplicate key value"})
                valores["versao"] = max((t["versao"] for t in mesmas), default=0) + 1
        return super()._inserir()


class _BancoDaTriagem(_Banco):
    def table(self, nome: str):
        return _ConsultaDaTriagem(self, nome)

    @property
    def triagens(self) -> list[dict]:
        return self.tabelas.setdefault("nsp_triagens", [])


def _notificacao(numero: int, **campos) -> dict[str, Any]:
    base = {
        "id": f"00000000-0000-0000-0000-{numero:012d}",
        "protocolo": f"NSP-2026-{numero:04d}",
        "ano": 2026,
        "numero": numero,
        "origem": "qr",
        "estado": "recebida",
        "relato": f"Relato de teste {numero}: a bomba de infusão alarmou sem ninguém ouvir.",
        "leito_ou_atendimento": "Leito 4",
        "setor_id": SETOR["id"],
        "data_ocorrencia": DIA.isoformat(),
        "turno": "noite",
        "hora_aproximada": None,
        "chegou_ao_paciente": "sem_dano",
        "grave_ou_morte": None,
        "percebido_ou_reclamacao": None,
        "anonimo": False,
        "notificante_id": None,
        "notificante_nome": "Profissional Notificante",
        "notificante_contato": "notificante@hsm.test",
        "manifestacao_id": None,
        "classificar_manualmente": False,
        "motivo_classificar_manualmente": None,
        "criado_em": f"2026-11-{numero:02d}T10:00:00+00:00",
    }
    return {**base, **campos}


def _sugestao(notificacao: dict, versao: int = 1, **campos) -> dict[str, Any]:
    base = {
        "id": f"tri-{notificacao['numero']}-{versao}",
        "notificacao_id": notificacao["id"],
        "versao": versao,
        "autor_tipo": "agente",
        "autor_id": None,
        "assunto": "Alarme de bomba de infusão sem resposta",
        "natureza": "incidente_sem_dano",
        "grau_de_dano": "nenhum",
        "categoria": "EQP",
        "incidente": "Alarme inoperante",
        "evento_situacao": "nao",
        "evento_item": None,
        "evento_motivo": "Nenhum item da lista.",
        "iras": False,
        "risco_de_imagem": False,
        "protocolo_basico": "nenhum",
        "canais": ["NSP"],
        "motivo_do_encaminhamento": None,
        "faixa": "D",
        "revisao": "confirmacao_simples",
        "justificativa": "O alarme não foi atendido e o paciente não teve dano.",
        "confianca": "alta",
        "motivo_da_confianca": "O relato é claro.",
        "alertas": [],
        "perguntas_ao_notificante": [],
        "prompt_versao": "1.1",
        "base_versao": "1.1",
        "modelo": "modelo-de-teste",
        "tentativas": 1,
        "divergencias": None,
        "frequencia": None,
        "prioridade": None,
        "criado_em": notificacao["criado_em"],
    }
    return {**base, **campos}


# Faixa A: óbito.
OBITO = {
    "natureza": "evento_adverso",
    "grau_de_dano": "obito",
    "faixa": "A",
    "revisao": "campo_a_campo",
}
# Faixa B: dano grave.
GRAVE = {"natureza": "evento_adverso", "grau_de_dano": "grave", "faixa": "B", "revisao": "campo_a_campo"}
# Faixa C: dano moderado.
MODERADO = {"natureza": "evento_adverso", "grau_de_dano": "moderado", "faixa": "C"}
# Faixa E: quase erro.
QUASE_ERRO = {"natureza": "quase_erro", "grau_de_dano": "nenhum", "faixa": "E"}


def _banco(notificacoes: list[dict] | None = None, triagens: list[dict] | None = None) -> _BancoDaTriagem:
    return _BancoDaTriagem(
        {
            "participantes": [dict(p) for p in (PRESIDENTE, MEMBRO, SUPER_ADMIN, DIRETOR_EXECUTIVO)],
            "colegiados": [dict(NUCLEO)],
            "participacoes": [_participacao("P1", "presidencia"), _participacao("P2", "membro")],
            "setores": [dict(SETOR), dict(OUTRO_SETOR)],
            "nsp_notificacoes": [dict(n) for n in (notificacoes or [])],
            "nsp_triagens": [dict(t) for t in (triagens or [])],
            "nsp_categorias": [
                {"codigo": "EQP", "nome": "Equipamentos e materiais", "ordem": 11},
                {"codigo": "MED", "nome": "Medicamentos e soluções", "ordem": 2},
            ],
            "nsp_eventos_que_nunca_deveriam_ocorrer": [
                {"item": 11, "evento": "Óbito associado a queda do paciente durante o atendimento"},
            ],
            "nsp_notificacoes_anexos": [],
        }
    )


def _cliente(banco: _BancoDaTriagem, pessoa: dict[str, Any] = PRESIDENTE) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(triagem_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


FILA = "/api/nsp/triagem"


def _caso(notificacao_id: str) -> str:
    return f"/api/nsp/triagem/{notificacao_id}"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A fila
# ═══════════════════════════════════════════════════════════════════════════


def test_a_fila_vem_da_mais_antiga_para_a_mais_nova_com_a_faixa_sugerida():
    nova, velha, do_meio = _notificacao(9), _notificacao(2), _notificacao(5)
    banco = _banco(
        [nova, velha, do_meio],
        [_sugestao(velha, **OBITO), _sugestao(do_meio, **MODERADO), _sugestao(nova)],
    )

    resposta = _cliente(banco).get(FILA)

    assert resposta.status_code == 200, resposta.text
    fila = resposta.json()["fila"]
    assert [(c["protocolo"], c["faixa"]) for c in fila] == [
        ("NSP-2026-0002", "A"),
        ("NSP-2026-0005", "C"),
        ("NSP-2026-0009", "D"),
    ]
    assert fila[0]["setor"] == "UTI Adulto"
    assert fila[0]["assunto"] == "Alarme de bomba de infusão sem resposta"


def test_a_fila_deixa_de_fora_o_que_ja_tem_triagem_confirmada():
    pendente, confirmada, classificada = _notificacao(1), _notificacao(2), _notificacao(3, estado="classificada")
    decisao = {**_sugestao(confirmada, versao=2), "autor_tipo": "pessoa", "autor_id": "P1", "divergencias": []}
    banco = _banco([pendente, confirmada, classificada], [_sugestao(pendente), _sugestao(confirmada), decisao])

    fila = _cliente(banco).get(FILA).json()["fila"]

    assert [c["protocolo"] for c in fila] == ["NSP-2026-0001"]


def test_a_fila_nao_traz_o_relato_nem_quem_notificou():
    caso = _notificacao(1, relato="O paciente Fulano Beltrano caiu do leito.")
    banco = _banco([caso], [_sugestao(caso)])

    corpo = _cliente(banco).get(FILA).text

    for dado in ("Fulano", "Beltrano", "Profissional Notificante", "notificante@hsm.test", "Leito 4"):
        assert dado not in corpo, dado


def test_a_notificacao_para_classificar_manualmente_entra_na_fila_sem_faixa():
    caso = _notificacao(1, classificar_manualmente=True, motivo_classificar_manualmente="agente_fora")
    banco = _banco([caso])

    [item] = _cliente(banco).get(FILA).json()["fila"]

    assert item["faixa"] is None
    assert item["assunto"] is None
    assert item["classificar_manualmente"] is True


@pytest.mark.parametrize("pessoa", [MEMBRO, SUPER_ADMIN], ids=["membro do Núcleo", "super admin sem Acesso pleno"])
def test_so_a_presidencia_e_o_acesso_pleno_abrem_a_fila(pessoa):
    banco = _banco([_notificacao(1)])

    assert _cliente(banco, pessoa).get(FILA).json() == RECUSA
    assert _cliente(banco, DIRETOR_EXECUTIVO).get(FILA).status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 2. Conferência campo a campo: faixas A e B e revisão forçada
# ═══════════════════════════════════════════════════════════════════════════

TODOS_OS_CAMPOS = list(triagem.CAMPOS_DA_CONFERENCIA)


def _confirmar(banco, caso, conferidos=(), pessoa=PRESIDENTE):
    return _cliente(banco, pessoa).post(_caso(caso["id"]), json={"conferidos": list(conferidos)})


def _decisoes(banco) -> list[dict]:
    return [t for t in banco.triagens if t["autor_tipo"] == "pessoa"]


@pytest.mark.parametrize(
    ("caso", "sugestao", "motivo"),
    [
        (_notificacao(1), OBITO, "faixa"),
        (_notificacao(1), GRAVE, "faixa"),
        (_notificacao(1, relato="O paciente foi a óbito depois da troca do soro."), MODERADO, "morte"),
        (
            _notificacao(1),
            {**MODERADO, "evento_situacao": "possivel", "evento_item": 11, "revisao": "campo_a_campo"},
            "evento_possivel",
        ),
        (_notificacao(1, chegou_ao_paciente="com_dano", grave_ou_morte=True), MODERADO, "grave_marcado"),
    ],
    ids=["faixa A", "faixa B", "menção a morte", "evento possível", "quem notificou marcou grave"],
)
def test_confirmar_o_caso_grave_exige_cada_campo_conferido(caso, sugestao, motivo):
    banco = _banco([caso], [_sugestao(caso, **sugestao)])

    tela = _cliente(banco).get(_caso(caso["id"])).json()
    assert tela["conferencia"]["campo_a_campo"] is True
    assert motivo in tela["conferencia"]["motivos"]

    sem_tudo = _confirmar(banco, caso, TODOS_OS_CAMPOS[:-1])
    assert sem_tudo.status_code == 422
    assert "Confira cada campo" in sem_tudo.json()["detail"]
    assert _decisoes(banco) == []
    assert banco.notificacoes[0]["estado"] == "recebida"

    com_tudo = _confirmar(banco, caso, TODOS_OS_CAMPOS)
    assert com_tudo.status_code == 201, com_tudo.text
    [decisao] = _decisoes(banco)
    assert decisao["revisao"] == "campo_a_campo"
    assert decisao["autor_id"] == "P1"


def test_nao_existe_aceitar_tudo_nem_pelo_ajuste():
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso, **GRAVE)])

    resposta = _cliente(banco).post(_caso(caso["id"]), json={"classificacao": _classificacao(GRAVE), "conferidos": []})

    assert resposta.status_code == 422
    assert _decisoes(banco) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. Faixas C, D e E: um clique
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("sugestao", "estado"),
    [
        (MODERADO, "classificada"),
        ({}, "em_analise_agregada"),
        ({"natureza": "evento_adverso", "grau_de_dano": "leve", "faixa": "D"}, "classificada"),
        (QUASE_ERRO, "em_analise_agregada"),
    ],
    ids=["faixa C", "faixa D sem dano", "faixa D com dano leve", "faixa E"],
)
def test_confirmar_nas_faixas_c_d_e_e_um_clique(sugestao, estado):
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso, **sugestao)])

    tela = _cliente(banco).get(_caso(caso["id"])).json()
    assert tela["conferencia"]["campo_a_campo"] is False

    resposta = _confirmar(banco, caso)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["estado"] == estado
    assert banco.notificacoes[0]["estado"] == estado
    [decisao] = _decisoes(banco)
    assert decisao["divergencias"] == []
    assert decisao["revisao"] == "confirmacao_simples"
    assert decisao["faixa"] == (sugestao.get("faixa") or "D")
    assert ("nsp_notificacoes", {"estado": estado, "editado_por": "P1"}) in banco.escritas


def test_a_triagem_confirmada_nao_se_confirma_de_novo():
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso)])
    assert _confirmar(banco, caso).status_code == 201

    segunda = _confirmar(banco, caso)

    assert segunda.status_code == 409
    assert len(_decisoes(banco)) == 1


@pytest.mark.parametrize(
    ("sugestao", "estado"),
    [(GRAVE, "classificada"), (QUASE_ERRO, "em_analise_agregada")],
    ids=["faixa B", "faixa E"],
)
@pytest.mark.parametrize(
    "falha",
    [APIError({"code": "57014", "message": "canceling statement"}), httpx.ReadTimeout("timeout")],
    ids=["APIError", "timeout do PostgREST"],
)
def test_a_nova_tentativa_conclui_a_mudanca_de_estado_que_falhou(sugestao, estado, falha, monkeypatch):
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso, **sugestao)])
    executar = _ConsultaDaTriagem.execute
    derrubados: list[str] = []

    def _derrubar_o_update_do_estado(self):
        if self._nome == "nsp_notificacoes" and self._acao == "update" and not derrubados:
            derrubados.append(self._nome)
            raise falha
        return executar(self)

    monkeypatch.setattr(_ConsultaDaTriagem, "execute", _derrubar_o_update_do_estado)
    conferidos = triagem.CAMPOS_DA_CONFERENCIA

    primeira = _confirmar(banco, caso, conferidos)

    assert primeira.status_code == 503, primeira.text
    assert derrubados == ["nsp_notificacoes"]
    assert len(_decisoes(banco)) == 1
    assert banco.notificacoes[0]["estado"] == "recebida"

    segunda = _confirmar(banco, caso, conferidos)

    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["estado"] == estado
    assert segunda.json()["triagem"]["faixa"] == sugestao["faixa"]
    assert banco.notificacoes[0]["estado"] == estado
    assert len(_decisoes(banco)) == 1
    assert _confirmar(banco, caso, conferidos).status_code == 409


@pytest.mark.parametrize("pessoa", [MEMBRO, SUPER_ADMIN], ids=["membro do Núcleo", "super admin sem Acesso pleno"])
def test_so_a_presidencia_e_o_acesso_pleno_confirmam(pessoa):
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso)])

    assert _confirmar(banco, caso, pessoa=pessoa).json() == RECUSA
    assert _cliente(banco, pessoa).get(_caso(caso["id"])).json() == RECUSA
    assert _decisoes(banco) == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. Ajustar: a linha da pessoa com as divergências, e a sugestão fica
# ═══════════════════════════════════════════════════════════════════════════


def _classificacao(sugestao: dict | None = None, **campos) -> dict[str, Any]:
    base = {
        "assunto": "Alarme de bomba de infusão sem resposta",
        "natureza": "incidente_sem_dano",
        "grau_de_dano": "nenhum",
        "categoria": "EQP",
        "incidente": "Alarme inoperante",
        "evento_situacao": "nao",
        "evento_item": None,
        "iras": False,
        "risco_de_imagem": False,
        "protocolo_basico": "nenhum",
        "canais": ["NSP"],
    }
    if sugestao:
        base.update({k: v for k, v in sugestao.items() if k in base})
    return {**base, **campos}


def test_ajustar_grava_as_divergencias_e_a_sugestao_continua_gravada():
    caso = _notificacao(1)
    sugestao = _sugestao(caso)
    banco = _banco([caso], [sugestao])

    resposta = _cliente(banco).post(
        _caso(caso["id"]),
        json={
            "classificacao": _classificacao(
                natureza="evento_adverso", grau_de_dano="moderado", categoria="MED", risco_de_imagem=True
            ),
            "conferidos": [],
        },
    )

    assert resposta.status_code == 201, resposta.text
    agente = [t for t in banco.triagens if t["autor_tipo"] == "agente"]
    assert agente == [sugestao]
    [decisao] = _decisoes(banco)
    assert sorted(decisao["divergencias"]) == sorted(
        ["natureza", "grau_de_dano", "categoria", "risco_de_imagem", "faixa"]
    )
    assert decisao["faixa"] == "C"
    assert decisao["categoria"] == "MED"
    assert decisao["versao"] == 2
    assert resposta.json()["estado"] == "classificada"


def test_ajustar_igual_a_sugestao_nao_tem_divergencia():
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso)])

    resposta = _cliente(banco).post(_caso(caso["id"]), json={"classificacao": _classificacao(), "conferidos": []})

    assert resposta.status_code == 201, resposta.text
    assert _decisoes(banco)[0]["divergencias"] == []


@pytest.mark.parametrize(
    "mudanca",
    [
        {"natureza": "quase_erro", "grau_de_dano": "leve"},
        {"natureza": "evento_adverso", "grau_de_dano": "nenhum"},
        {"categoria": "XYZ"},
        {"canais": []},
        {"canais": ["OUV"]},
        {"evento_situacao": "sim", "evento_item": None},
        {"evento_situacao": "nao", "evento_item": 11},
        {"assunto": "   "},
    ],
    ids=[
        "quase erro com dano",
        "evento adverso sem dano",
        "categoria fora da lista",
        "sem canal",
        "do Núcleo sem o canal NSP",
        "evento da lista sem item",
        "item sem evento",
        "sem assunto",
    ],
)
def test_o_ajuste_fora_das_regras_e_recusado_sem_gravar(mudanca):
    caso = _notificacao(1)
    banco = _banco([caso], [_sugestao(caso)])

    resposta = _cliente(banco).post(
        _caso(caso["id"]), json={"classificacao": _classificacao(**mudanca), "conferidos": []}
    )

    assert resposta.status_code == 422, resposta.text
    assert _decisoes(banco) == []
    assert banco.notificacoes[0]["estado"] == "recebida"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Recorrência, casos parecidos, frequência e prioridade; os cortes
# ═══════════════════════════════════════════════════════════════════════════


def _anterior(numero: int, dias_antes: int, **campos) -> dict[str, Any]:
    return _notificacao(numero, data_ocorrencia=(DIA - timedelta(days=dias_antes)).isoformat(), **campos)


def test_a_tela_mostra_a_recorrencia_e_os_casos_parecidos_de_60_dias():
    caso = _notificacao(50)
    ha_10_dias, ha_59_dias = _anterior(1, 10), _anterior(2, 59)
    fora_da_janela = _anterior(3, 61)
    outra_categoria = _anterior(4, 5)
    outro_setor = _anterior(5, 5, setor_id=OUTRO_SETOR["id"])
    depois = _notificacao(6, data_ocorrencia=(DIA + timedelta(days=1)).isoformat())
    banco = _banco(
        [caso, ha_10_dias, ha_59_dias, fora_da_janela, outra_categoria, outro_setor, depois],
        [
            _sugestao(caso),
            _sugestao(ha_10_dias),
            _sugestao(ha_59_dias, assunto="Monitor sem alarme sonoro"),
            _sugestao(fora_da_janela),
            _sugestao(outra_categoria, categoria="MED"),
            _sugestao(outro_setor),
            _sugestao(depois),
        ],
    )

    contexto = _cliente(banco).get(_caso(caso["id"])).json()["contexto"]

    assert contexto["recorrencia"] == 3
    assert [p["protocolo"] for p in contexto["parecidos"]] == ["NSP-2026-0001", "NSP-2026-0002"]
    assert contexto["parecidos"][1]["assunto"] == "Monitor sem alarme sonoro"


def test_a_categoria_confirmada_vale_mais_que_a_sugerida_na_contagem():
    caso, anterior = _notificacao(50), _anterior(1, 10)
    decisao = {**_sugestao(anterior, versao=2, categoria="MED"), "autor_tipo": "pessoa", "autor_id": "P1"}
    banco = _banco([caso, anterior], [_sugestao(caso), _sugestao(anterior), decisao])

    contexto = _cliente(banco).get(_caso(caso["id"])).json()["contexto"]

    assert contexto["recorrencia"] == 1
    assert contexto["parecidos"] == []


@pytest.mark.parametrize(
    ("anteriores", "frequencia", "prioridade_b", "prioridade_c"),
    [
        (0, "remoto", "moderada", "baixa"),
        (1, "incomum", "moderada", "baixa"),
        (2, "ocasional", "moderada", "baixa"),
        (3, "ocasional", "moderada", "baixa"),
        (4, "frequente", "alta", "moderada"),
    ],
)
def test_a_frequencia_conta_12_meses_e_a_prioridade_sai_da_matriz(anteriores, frequencia, prioridade_b, prioridade_c):
    caso = _notificacao(50)
    # Uma a mais, fora dos 12 meses, que não conta.
    outros = [_anterior(i + 1, 30 * (i + 1)) for i in range(anteriores)] + [_anterior(40, 370)]
    banco = _banco([caso, *outros], [_sugestao(n) for n in outros])
    banco.triagens.append(_sugestao(caso, **GRAVE))

    tela = _cliente(banco).get(_caso(caso["id"])).json()
    assert tela["contexto"]["anteriores"] == anteriores
    assert tela["contexto"]["frequencia"] == frequencia
    assert tela["contexto"]["prioridade"] == prioridade_b

    moderado = _cliente(banco).get(f"{_caso(caso['id'])}/contexto", params={"categoria": "EQP", "faixa": "C"})
    assert moderado.json()["prioridade"] == prioridade_c


def test_a_faixa_a_e_sempre_prioridade_alta():
    caso = _notificacao(50)
    banco = _banco([caso], [_sugestao(caso, **OBITO)])

    contexto = _cliente(banco).get(_caso(caso["id"])).json()["contexto"]

    assert (contexto["frequencia"], contexto["prioridade"]) == ("remoto", "alta")


def test_a_decisao_grava_a_frequencia_e_a_prioridade_calculadas():
    caso, anterior = _notificacao(50), _anterior(1, 10)
    banco = _banco([caso, anterior], [_sugestao(caso, **MODERADO), _sugestao(anterior)])

    assert _confirmar(banco, caso).status_code == 201

    [decisao] = _decisoes(banco)
    assert (decisao["frequencia"], decisao["prioridade"]) == ("incomum", "baixa")


CORTES = "/api/nsp/configuracao/cortes-de-frequencia"


def test_os_cortes_vem_com_o_padrao_da_sugestao_e_mudam_a_frequencia():
    caso = _notificacao(50)
    outros = [_anterior(1, 10), _anterior(2, 20)]
    banco = _banco([caso, *outros], [_sugestao(caso), *(_sugestao(n) for n in outros)])
    banco.tabelas["nsp_cortes_de_frequencia"] = [{"id": True, **triagem.CORTES_PADRAO}]
    cliente = _cliente(banco, SUPER_ADMIN)

    assert cliente.get(CORTES).json() == {
        "janela_meses": 12,
        "incomum_a_partir": 1,
        "ocasional_a_partir": 2,
        "frequente_a_partir": 4,
    }
    assert _cliente(banco).get(_caso(caso["id"])).json()["contexto"]["frequencia"] == "ocasional"

    novos = {"janela_meses": 6, "incomum_a_partir": 1, "ocasional_a_partir": 3, "frequente_a_partir": 5}
    resposta = cliente.put(CORTES, json=novos)

    assert resposta.status_code == 200, resposta.text
    assert banco.tabelas["nsp_cortes_de_frequencia"][0]["atualizado_por"] == SUPER_ADMIN["id"]
    assert _cliente(banco).get(_caso(caso["id"])).json()["contexto"]["frequencia"] == "incomum"


@pytest.mark.parametrize(
    "cortes",
    [
        {"janela_meses": 12, "incomum_a_partir": 2, "ocasional_a_partir": 2, "frequente_a_partir": 4},
        {"janela_meses": 12, "incomum_a_partir": 0, "ocasional_a_partir": 2, "frequente_a_partir": 4},
        {"janela_meses": 0, "incomum_a_partir": 1, "ocasional_a_partir": 2, "frequente_a_partir": 4},
    ],
    ids=["fora de ordem", "incomum sem ocorrência", "janela vazia"],
)
def test_os_cortes_fora_de_ordem_sao_recusados(cortes):
    banco = _banco()
    banco.tabelas["nsp_cortes_de_frequencia"] = [{"id": True, **triagem.CORTES_PADRAO}]

    resposta = _cliente(banco, SUPER_ADMIN).put(CORTES, json=cortes)

    assert resposta.status_code == 422
    assert banco.tabelas["nsp_cortes_de_frequencia"][0]["incomum_a_partir"] == 1


def test_so_quem_alcanca_a_configuracao_muda_os_cortes():
    banco = _banco()
    banco.tabelas["nsp_cortes_de_frequencia"] = [{"id": True, **triagem.CORTES_PADRAO}]

    resposta = _cliente(banco, MEMBRO).put(CORTES, json=triagem.CORTES_PADRAO)

    assert resposta.json() == RECUSA


# ═══════════════════════════════════════════════════════════════════════════
# 6. Classificar manualmente: a mesma tela, sem sugestão
# ═══════════════════════════════════════════════════════════════════════════


def test_a_notificacao_para_classificar_manualmente_abre_sem_sugestao():
    caso = _notificacao(1, classificar_manualmente=True, motivo_classificar_manualmente="agente_fora")
    banco = _banco([caso])

    tela = _cliente(banco).get(_caso(caso["id"])).json()

    assert tela["sugestao"] is None
    assert tela["classificar_manualmente"] is True
    assert tela["caso"]["protocolo"] == "NSP-2026-0001"
    assert tela["caso"]["relato"] == caso["relato"]
    assert [c["codigo"] for c in tela["opcoes"]["categorias"]] == ["MED", "EQP"]


def test_sem_sugestao_nao_ha_o_que_confirmar_e_a_pessoa_classifica():
    caso = _notificacao(1, classificar_manualmente=True, motivo_classificar_manualmente="teto")
    banco = _banco([caso])

    sem_classificacao = _confirmar(banco, caso)
    assert sem_classificacao.status_code == 422
    assert _decisoes(banco) == []

    resposta = _cliente(banco).post(
        _caso(caso["id"]), json={"classificacao": _classificacao(**QUASE_ERRO_CLASSIFICADO), "conferidos": []}
    )

    assert resposta.status_code == 201, resposta.text
    [decisao] = _decisoes(banco)
    assert decisao["divergencias"] is None
    assert decisao["faixa"] == "E"
    assert decisao["versao"] == 1
    assert resposta.json()["estado"] == "em_analise_agregada"


QUASE_ERRO_CLASSIFICADO = {"natureza": "quase_erro", "grau_de_dano": "nenhum"}


# ═══════════════════════════════════════════════════════════════════════════
# O texto do Produto no Kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


def _secao_do_kit(titulo: str) -> str:
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "seguranca-do-paciente.md").read_text(encoding="utf-8")
    partes = texto.split(f"## {titulo}\n", 1)
    assert len(partes) == 2, f"a seção {titulo!r} sumiu do kit"
    return partes[1].split("\n## ", 1)[0]


def test_o_kit_diz_como_a_presidencia_confirma_a_triagem():
    no_ar = _secao_do_kit("O que já está no ar")
    for termo in (
        "Fila de triagem",
        "da mais antiga para a mais nova",
        "Leia o relato, confira a sugestão e confirme.",
        "Caso grave: confirme cada campo.",
        'Não existe "aceitar tudo"',
        "Confirmar é um clique",
        "a sugestão do agente continua guardada",
        "3ª ocorrência desta categoria neste setor em 60 dias",
        "Configuração do módulo",
        "sem sugestão e com os campos em branco",
    ):
        assert termo in no_ar, termo
    assert "a tela de triagem" not in _secao_do_kit("O que ele ainda não faz")


# ═══════════════════════════════════════════════════════════════════════════
# A migration 194, lida como texto
# ═══════════════════════════════════════════════════════════════════════════

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "194_nsp_tela_de_triagem.sql"


def _sql() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))


def test_a_migration_guarda_uma_decisao_de_pessoa_por_notificacao():
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS \w+\s+ON nsp_triagens \(notificacao_id\) WHERE autor_tipo = 'pessoa'",
        _sql(),
    )


def test_os_cortes_do_banco_nascem_com_o_padrao_do_app():
    sql = _sql()
    for campo, valor in triagem.CORTES_PADRAO.items():
        assert re.search(rf"{campo}\s+SMALLINT NOT NULL DEFAULT {valor}\b", sql), campo


def test_a_tabela_nova_nasce_com_rls_e_o_recibo_e_o_194():
    sql = _sql()
    for tabela in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql):
        assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela
    assert "VALUES (194) ON CONFLICT" in sql
    assert "CREATE POLICY" not in sql.upper()


def test_a_tela_de_um_caso_que_nao_existe_e_404():
    banco = _banco()

    assert _cliente(banco).get(_caso("00000000-0000-0000-0000-000000000099")).status_code == 404
    assert _confirmar(banco, {"id": "00000000-0000-0000-0000-000000000099"}).status_code == 404
