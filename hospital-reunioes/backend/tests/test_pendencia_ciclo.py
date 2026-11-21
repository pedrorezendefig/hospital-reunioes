"""A regra do ciclo de vida da Pendência (ADR 0098, decisões 4 e 5; issue #1862).

Função pura: quem pode, qual transição e se conta atraso. Nenhum banco aqui.
Os valores esperados saem da issue, não do código.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.pendencia_ciclo import (
    AcaoRecusada,
    Comando,
    Papel,
    acoes_disponiveis,
    decidir,
    esta_atrasada,
    situacao,
)

HOJE = date(2026, 11, 19)
ONTEM = date(2026, 11, 18)
AMANHA = date(2026, 11, 20)
DAQUI_A_UMA_SEMANA = date(2026, 11, 26)

RESP = {Papel.RESPONSAVEL}
CORESP = {Papel.CO_RESPONSAVEL}
FACIL = {Papel.FACILITADOR}
ADMIN = {Papel.SUPER_ADMIN}
OUTRO: set = set()


def _decidir(comando, papeis, status="PENDENTE", prazo=AMANHA, prazo_novo=None, anotacao="feito o combinado", **ctx):
    return decidir(
        comando,
        papeis,
        status=status,
        prazo=prazo,
        hoje=HOJE,
        anotacao=anotacao,
        prazo_novo=prazo_novo,
        **ctx,
    )


# ── Permissão: cada comando por papel (o que a issue lista) ─────────────────

# (comando, status de partida, prazo_novo, momento) que é uma transição válida.
# A Contestação e a resposta a ela (issue #1870) pedem o momento certo.
CENARIO = {
    Comando.INICIAR: ("PENDENTE", None, {}),
    Comando.ANOTAR: ("EM_PROGRESSO", None, {}),
    Comando.CONCLUIR: ("EM_PROGRESSO", None, {}),
    Comando.REPACTUAR: ("PENDENTE", DAQUI_A_UMA_SEMANA, {}),
    Comando.CANCELAR: ("PENDENTE", None, {}),
    Comando.REABRIR: ("CONCLUIDO", DAQUI_A_UMA_SEMANA, {}),
    Comando.CONTESTAR: ("PENDENTE", None, {"ata_em_assinatura": True}),
    Comando.AJUSTAR: ("PENDENTE", DAQUI_A_UMA_SEMANA, {"contestada": True}),
    Comando.RECUSAR: ("PENDENTE", None, {"contestada": True}),
}

PODE = {
    "responsavel": {Comando.INICIAR, Comando.ANOTAR, Comando.CONCLUIR, Comando.REPACTUAR, Comando.CONTESTAR},
    "co_responsavel": {Comando.INICIAR, Comando.ANOTAR, Comando.CONCLUIR, Comando.REPACTUAR},
    "facilitador": {Comando.REPACTUAR, Comando.CANCELAR, Comando.REABRIR, Comando.AJUSTAR, Comando.RECUSAR},
    "super_admin": set(Comando) - {Comando.CONTESTAR},
    "outro": set(),
}
PAPEIS = {"responsavel": RESP, "co_responsavel": CORESP, "facilitador": FACIL, "super_admin": ADMIN, "outro": OUTRO}


@pytest.mark.parametrize("nome_papel", list(PAPEIS))
@pytest.mark.parametrize("comando", list(Comando))
def test_cada_comando_respeita_o_papel_de_quem_age(nome_papel, comando):
    status, prazo_novo, momento = CENARIO[comando]
    if comando in PODE[nome_papel]:
        mudanca = _decidir(comando, PAPEIS[nome_papel], status=status, prazo_novo=prazo_novo, **momento)
        assert mudanca is not None
    else:
        with pytest.raises(AcaoRecusada) as erro:
            _decidir(comando, PAPEIS[nome_papel], status=status, prazo_novo=prazo_novo, **momento)
        assert erro.value.tipo == "permissao"


def test_quem_tem_dois_papeis_soma_as_permissoes():
    # O facilitador que também é responsável conclui (pelo papel de responsável).
    mudanca = _decidir(Comando.CONCLUIR, FACIL | RESP, status="PENDENTE")
    assert mudanca.status == "CONCLUIDO"


def test_acoes_disponiveis_cruzam_papel_e_estado():
    assert acoes_disponiveis(RESP, "PENDENTE") == [
        Comando.INICIAR,
        Comando.ANOTAR,
        Comando.CONCLUIR,
        Comando.REPACTUAR,
    ]
    assert acoes_disponiveis(FACIL, "CONCLUIDO") == [Comando.REABRIR]
    assert acoes_disponiveis(RESP, "CANCELADO") == []
    assert acoes_disponiveis(OUTRO, "PENDENTE") == []


# ── Anotação obrigatória ────────────────────────────────────────────────────


@pytest.mark.parametrize("anotacao", ["", "   ", None])
def test_toda_acao_pede_anotacao(anotacao):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.INICIAR, RESP, anotacao=anotacao)
    assert erro.value.tipo == "dados"


# ── Transições ──────────────────────────────────────────────────────────────


def test_iniciar_leva_de_pendente_a_em_progresso():
    assert _decidir(Comando.INICIAR, RESP).status == "EM_PROGRESSO"


def test_iniciar_o_que_ja_esta_em_progresso_e_recusado():
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.INICIAR, RESP, status="EM_PROGRESSO")
    assert erro.value.tipo == "transicao"


def test_anotar_nao_muda_o_estado_nem_o_prazo():
    mudanca = _decidir(Comando.ANOTAR, RESP, status="EM_PROGRESSO")
    assert (mudanca.status, mudanca.prazo, mudanca.concluida) == ("EM_PROGRESSO", AMANHA, None)


def test_concluir_grava_a_data_de_conclusao():
    mudanca = _decidir(Comando.CONCLUIR, RESP)
    assert mudanca.status == "CONCLUIDO"
    assert mudanca.concluida is True


@pytest.mark.parametrize("status", ["CONCLUIDO", "CANCELADO"])
def test_pendencia_fechada_so_reabre(status):
    for comando in (Comando.INICIAR, Comando.ANOTAR, Comando.CONCLUIR, Comando.REPACTUAR, Comando.CANCELAR):
        with pytest.raises(AcaoRecusada) as erro:
            _decidir(comando, ADMIN, status=status, prazo_novo=DAQUI_A_UMA_SEMANA)
        assert erro.value.tipo == "transicao", comando


def test_cancelar_fecha_a_pendencia():
    assert _decidir(Comando.CANCELAR, FACIL).status == "CANCELADO"


def test_reabrir_volta_a_pendente_com_prazo_novo_e_apaga_a_conclusao():
    mudanca = _decidir(Comando.REABRIR, FACIL, status="CONCLUIDO", prazo_novo=DAQUI_A_UMA_SEMANA)
    assert (mudanca.status, mudanca.prazo, mudanca.concluida) == ("PENDENTE", DAQUI_A_UMA_SEMANA, False)


@pytest.mark.parametrize("status", ["PENDENTE", "EM_PROGRESSO"])
def test_reabrir_pendencia_aberta_e_recusado(status):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.REABRIR, FACIL, status=status, prazo_novo=DAQUI_A_UMA_SEMANA)
    assert erro.value.tipo == "transicao"


@pytest.mark.parametrize("comando,status", [(Comando.REPACTUAR, "PENDENTE"), (Comando.REABRIR, "CANCELADO")])
def test_repactuar_e_reabrir_pedem_prazo_novo_de_hoje_em_diante(comando, status):
    with pytest.raises(AcaoRecusada) as sem_prazo:
        _decidir(comando, ADMIN, status=status, prazo_novo=None)
    assert sem_prazo.value.tipo == "dados"
    with pytest.raises(AcaoRecusada) as no_passado:
        _decidir(comando, ADMIN, status=status, prazo_novo=ONTEM)
    assert no_passado.value.tipo == "dados"
    assert _decidir(comando, ADMIN, status=status, prazo_novo=HOJE).prazo == HOJE


def test_prazo_novo_fora_de_repactuar_reabrir_e_ajustar_e_recusado():
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.CONCLUIR, RESP, prazo_novo=DAQUI_A_UMA_SEMANA)
    assert erro.value.tipo == "dados"


# ── Repactuação e atraso ────────────────────────────────────────────────────


def test_repactuar_antes_do_vencimento_nao_conta_atraso_e_o_prazo_novo_vale_na_hora():
    mudanca = _decidir(Comando.REPACTUAR, RESP, prazo=AMANHA, prazo_novo=DAQUI_A_UMA_SEMANA)
    assert mudanca.prazo == DAQUI_A_UMA_SEMANA
    assert mudanca.status == "PENDENTE"
    assert mudanca.conta_atraso is False


def test_repactuar_no_dia_do_prazo_ainda_nao_conta_atraso():
    # O prazo de um dia só vence quando esse dia acaba.
    assert _decidir(Comando.REPACTUAR, RESP, prazo=HOJE, prazo_novo=AMANHA).conta_atraso is False


def test_repactuar_depois_do_vencimento_conta_atraso_e_o_prazo_novo_vale_na_hora():
    mudanca = _decidir(Comando.REPACTUAR, RESP, prazo=ONTEM, prazo_novo=DAQUI_A_UMA_SEMANA)
    assert mudanca.prazo == DAQUI_A_UMA_SEMANA
    assert mudanca.conta_atraso is True
    # O prazo novo vale na hora: a Pendência deixa de estar atrasada.
    assert esta_atrasada(mudanca.status, mudanca.prazo, HOJE) is False


def test_repactuar_pendencia_sem_prazo_nao_conta_atraso():
    assert _decidir(Comando.REPACTUAR, RESP, prazo=None, prazo_novo=AMANHA).conta_atraso is False


def test_reabrir_depois_do_vencimento_fica_marcado():
    vencida = _decidir(Comando.REABRIR, FACIL, status="CONCLUIDO", prazo=ONTEM, prazo_novo=AMANHA)
    no_prazo = _decidir(Comando.REABRIR, FACIL, status="CONCLUIDO", prazo=AMANHA, prazo_novo=AMANHA)
    assert vencida.conta_atraso is True
    assert no_prazo.conta_atraso is False


@pytest.mark.parametrize("comando", [Comando.INICIAR, Comando.ANOTAR, Comando.CONCLUIR, Comando.CANCELAR])
def test_so_repactuar_e_reabrir_contam_atraso(comando):
    status = "EM_PROGRESSO" if comando is not Comando.INICIAR else "PENDENTE"
    assert _decidir(comando, ADMIN, status=status, prazo=ONTEM).conta_atraso is False


# ── Atrasada é calculada ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,prazo,esperado",
    [
        ("PENDENTE", ONTEM, True),
        ("EM_PROGRESSO", ONTEM, True),
        ("PENDENTE", HOJE, False),
        ("PENDENTE", AMANHA, False),
        ("PENDENTE", None, False),
        ("CONCLUIDO", ONTEM, False),
        ("CANCELADO", ONTEM, False),
    ],
)
def test_pendencia_aberta_com_prazo_vencido_esta_atrasada(status, prazo, esperado):
    assert esta_atrasada(status, prazo, HOJE) is esperado


@pytest.mark.parametrize(
    "status,prazo,repactuada,esperado",
    [
        ("PENDENTE", ONTEM, False, "ATRASADO"),
        ("EM_PROGRESSO", ONTEM, True, "ATRASADO"),
        ("PENDENTE", AMANHA, True, "REPACTUADA"),
        ("EM_PROGRESSO", AMANHA, False, "EM_PROGRESSO"),
        ("CONCLUIDO", ONTEM, True, "CONCLUIDO"),
        ("CANCELADO", None, False, "CANCELADO"),
    ],
)
def test_situacao_mostrada_vem_do_estado_do_prazo_e_do_historico(status, prazo, repactuada, esperado):
    assert situacao(status, prazo, HOJE, repactuada=repactuada) == esperado
