"""O registro rápido do Núcleo (issue #1998, PRD #1979).

A Presidência e o membro com Termo lançam, numa tela só, o incidente que o
próprio Núcleo achou em busca ativa, ronda, reunião rápida ou auditoria:
relato, setor, data e origem (CONTEXT.md, "Registro rápido"). Um bloco por
critério de aceite do backend:

1. Presidência e membro com Termo registram com os quatro campos; membro sem
   Termo e pessoa de fora recebem recusa;
2. a origem escolhida fica gravada, e a notificação segue o mesmo caminho de
   qualquer outra (a mesma gravação, que é onde o agente de triagem entra);
3. o kit de conhecimento diz o comportamento novo.

O banco é o dublê em memória do teste da notificação (#1987).
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_seguranca_do_paciente_notificacoes import (  # noqa: E402
    ANO,
    DIRETOR,
    DIRETOR_EXECUTIVO,
    HOJE,
    MEMBRO,
    PRESIDENTE,
    RECUSA_DO_CONTEUDO,
    SETOR,
    SETOR_DESATIVADO,
    SO_REUNIOES,
    SUPER_ADMIN,
    _banco,
    _cliente,
    _participacao,
    _pessoa,
    _secao_do_kit,
)

from app.limiter import limiter  # noqa: E402
from app.services.seguranca_do_paciente import notificacoes as servico  # noqa: E402

REGISTRO_RAPIDO = "/api/nsp/notificacoes/registro-rapido"
LISTA = "/api/nsp/notificacoes"

REGISTRO = {
    "relato": "Na ronda, a pulseira de identificação do leito 7 estava sem o nome da mãe.",
    "setor_id": SETOR["id"],
    "data_ocorrencia": HOJE.isoformat(),
    "origem": "ronda",
}

MEMBRO_SEM_TERMO = _pessoa("P7")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _banco_com_membro_sem_termo():
    banco = _banco()
    banco.tabelas["participantes"].append(dict(MEMBRO_SEM_TERMO))
    banco.tabelas["participacoes"].append(_participacao("P7", "membro", termo=False))
    return banco


# ═══════════════════════════════════════════════════════════════════════════
# 1. Quem registra e quem recebe recusa
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pessoa", [PRESIDENTE, MEMBRO], ids=["Presidência", "membro com Termo"])
def test_a_presidencia_e_o_membro_com_termo_registram_com_os_quatro_campos(pessoa):
    banco = _banco()

    resposta = _cliente(banco, pessoa).post(REGISTRO_RAPIDO, json=REGISTRO)

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["protocolo"] == f"NSP-{ANO}-0001"
    [gravada] = banco.notificacoes
    assert gravada["relato"] == REGISTRO["relato"]
    assert gravada["setor_id"] == SETOR["id"]
    assert gravada["data_ocorrencia"] == HOJE.isoformat()
    assert gravada["origem"] == "ronda"
    assert gravada["anonimo"] is False
    assert gravada["notificante_id"] == pessoa["id"]
    assert gravada["notificante_nome"] == pessoa["nome_completo"]
    assert gravada["notificante_contato"] == pessoa["email"]


@pytest.mark.parametrize(
    "pessoa",
    [MEMBRO_SEM_TERMO, SO_REUNIOES, DIRETOR, SUPER_ADMIN],
    ids=["membro sem Termo", "só nas Reuniões", "diretoria", "super admin sem Acesso pleno"],
)
def test_membro_sem_termo_e_pessoa_de_fora_recebem_recusa(pessoa):
    banco = _banco_com_membro_sem_termo()

    resposta = _cliente(banco, pessoa).post(REGISTRO_RAPIDO, json=REGISTRO)

    assert resposta.status_code == 403
    assert resposta.json() == RECUSA_DO_CONTEUDO
    assert banco.notificacoes == []


def test_sem_login_nao_registra():
    banco = _banco()

    resposta = _cliente(banco).post(REGISTRO_RAPIDO, json=REGISTRO)

    assert resposta.status_code in (401, 403)
    assert banco.notificacoes == []


@pytest.mark.parametrize(
    "mudanca",
    [
        {"relato": "   "},
        {"setor_id": None},
        {"setor_id": SETOR_DESATIVADO["id"]},
        {"data_ocorrencia": None},
        {"data_ocorrencia": (HOJE + timedelta(days=1)).isoformat()},
        {"origem": None},
    ],
    ids=["relato vazio", "sem setor", "setor desativado", "sem data", "data futura", "sem origem"],
)
def test_registro_sem_um_dos_quatro_campos_e_recusado_sem_gravar(mudanca):
    banco = _banco()

    resposta = _cliente(banco, PRESIDENTE).post(REGISTRO_RAPIDO, json={**REGISTRO, **mudanca})

    assert resposta.status_code == 422, resposta.text
    assert banco.notificacoes == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. A origem fica gravada, e o caminho é o de toda notificação
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("origem", ["busca_ativa", "ronda", "reuniao_rapida", "auditoria", "outra"])
def test_a_origem_escolhida_fica_gravada(origem):
    banco = _banco()

    resposta = _cliente(banco, MEMBRO).post(REGISTRO_RAPIDO, json={**REGISTRO, "origem": origem})

    assert resposta.status_code == 201, resposta.text
    assert [n["origem"] for n in banco.notificacoes] == [origem]


@pytest.mark.parametrize("origem", ["qr", "endereco", "modulo", "ouvidoria"])
def test_o_registro_rapido_nao_aceita_a_origem_de_outra_porta(origem):
    banco = _banco()

    resposta = _cliente(banco, PRESIDENTE).post(REGISTRO_RAPIDO, json={**REGISTRO, "origem": origem})

    assert resposta.status_code == 422
    assert banco.notificacoes == []


def test_o_registro_rapido_passa_pela_mesma_gravacao_de_toda_notificacao(monkeypatch):
    """A gravação do serviço é o caminho único das portas (#1987); o agente de
    triagem (#1990) entra por ele, então roda aqui como em qualquer outra."""
    chamadas: list[str] = []
    gravar = servico.registrar

    def _espiar(supabase, relato, **kwargs):
        chamadas.append(kwargs["origem"])
        return gravar(supabase, relato, **kwargs)

    monkeypatch.setattr(servico, "registrar", _espiar)
    banco = _banco()

    resposta = _cliente(banco, PRESIDENTE).post(REGISTRO_RAPIDO, json={**REGISTRO, "origem": "auditoria"})

    assert resposta.status_code == 201, resposta.text
    assert chamadas == ["auditoria"]


def test_o_registro_rapido_entra_na_lista_como_qualquer_caso_recebido():
    banco = _banco()
    cliente = _cliente(banco, DIRETOR_EXECUTIVO)
    _cliente(banco, PRESIDENTE).post(REGISTRO_RAPIDO, json={**REGISTRO, "origem": "busca_ativa"})

    [caso] = cliente.get(LISTA).json()["notificacoes"]

    assert caso["estado"] == "recebida"
    assert caso["origem"] == "busca_ativa"
    assert caso["setor"] == SETOR["nome"]
    assert caso["notificante"] == {"nome": PRESIDENTE["nome_completo"], "contato": PRESIDENTE["email"]}


# ═══════════════════════════════════════════════════════════════════════════
# 3. O texto do Produto no Kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDeConhecimento:
    def test_o_registro_rapido_esta_no_que_ja_esta_no_ar(self):
        secao = _secao_do_kit("O que já está no ar")
        [item] = [linha for linha in secao.splitlines() if "Registro rápido" in linha]
        for termo in (
            "Presidência",
            "membro com o Termo",
            "relato, o setor, a data e a origem",
            "busca ativa",
            "ronda",
            "reunião rápida",
            "auditoria",
            "autor",
            "membro sem o Termo",
        ):
            assert termo in item, termo
