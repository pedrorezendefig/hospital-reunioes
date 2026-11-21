"""A triagem, os ritos, os prazos e a MINHA VEZ do Canal de Conduta (issue #1824).

Cada classe é um critério de aceite da issue. As pessoas e os casos são de
teste; o banco é o dublê de `conduta_apoio`, e o relato é cifrado de verdade,
com uma chave gerada na hora.
"""

from __future__ import annotations

import base64
import os
import secrets
import sys
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from conduta_apoio import Banco
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import conduta_comite  # noqa: E402
from app.services.conduta import casos  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

BASE = "/api/comite-de-conduta"
RELATO = "O supervisor Fulano de Tal grita com a equipe do almoxarifado e ameaça cortar as horas."
HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}

COORDENACAO, SEGUNDO_LEITOR, MEMBRO, DE_FORA = "COORD", "LEITOR", "MEMB", "FORA"

DENTRO_RAPIDO = {"escopo": "dentro", "categoria": "A", "rito": "rapido"}
DENTRO_COMPLETO = {"escopo": "dentro", "categoria": "A", "rito": "completo"}
FORA_DP = {"escopo": "fora", "categoria": "F", "rito": "encaminhamento", "destino": "dp"}


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())


def _pessoa(pid: str) -> dict[str, Any]:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": f"Pessoa {pid}",
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
    }


def _participacao(pid: str, papel: str) -> dict:
    return {
        "id": f"part-{pid}",
        "colegiado_id": COMITE["id"],
        "participante_id": pid,
        "papel": papel,
        "vigencia_inicio": (HOJE - timedelta(days=30)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=600)).isoformat(),
        "termo_assinado_em": "2026-10-01T12:00:00+00:00",
    }


class Comite:
    """O Comitê inteiro: coordenação, segundo leitor e membro, mais alguém de
    fora dele."""

    def __init__(self):
        self.banco = Banco(
            {
                "participantes": [_pessoa(p) for p in (COORDENACAO, SEGUNDO_LEITOR, MEMBRO, DE_FORA)],
                "colegiados": [dict(COMITE)],
                "participacoes": [
                    _participacao(COORDENACAO, "coordenacao"),
                    _participacao(SEGUNDO_LEITOR, "segundo_leitor"),
                    _participacao(MEMBRO, "membro"),
                ],
            }
        )

    def caso(self, *, dias_atras: int = 0) -> str:
        novo = casos.registrar_caso(self.banco, relato=RELATO, categoria=None)
        if dias_atras:
            linha = self._linha(novo["id"])
            linha["recebido_em"] = (datetime.now().astimezone() - timedelta(days=dias_atras)).isoformat()
        else:
            self._linha(novo["id"])["recebido_em"] = datetime.now().astimezone().isoformat()
        return novo["id"]

    def _linha(self, caso_id: str) -> dict:
        return next(c for c in self.banco.tabelas["conduta_casos"] if c["id"] == caso_id)

    def cliente(self, pid: str) -> TestClient:
        app = FastAPI()
        app.include_router(conduta_comite.router, prefix="/api")
        pessoa = next(p for p in self.banco.tabelas["participantes"] if p["id"] == pid)

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def agir(self, pid: str, caso_id: str, acao: str, corpo: dict | None = None):
        return self.cliente(pid).post(f"{BASE}/casos/{caso_id}/{acao}", json=corpo or {})

    def ok(self, pid: str, caso_id: str, acao: str, corpo: dict | None = None) -> dict:
        resposta = self.agir(pid, caso_id, acao, corpo)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["caso"]

    def abrir(self, pid: str, caso_id: str) -> dict:
        resposta = self.cliente(pid).get(f"{BASE}/casos/{caso_id}")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def minha_vez(self, pid: str) -> list[dict]:
        resposta = self.cliente(pid).get(f"{BASE}/minha-vez")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["itens"]

    def trilha(self, caso_id: str) -> list[str]:
        return [linha["acao"] for linha in self.banco.tabelas["conduta_trilha"] if linha["caso_id"] == caso_id]


@pytest.fixture
def comite() -> Comite:
    return Comite()


# ═══════════════════════════════════════════════════════════════════════════
# MINHA VEZ: só o que depende da pessoa, do mais urgente ao menos urgente
# ═══════════════════════════════════════════════════════════════════════════


class TestMinhaVez:
    def test_a_coordenacao_ve_a_triagem_e_o_membro_nao_tem_nada(self, comite):
        caso = comite.caso()

        (item,) = comite.minha_vez(COORDENACAO)
        assert (item["id"], item["acao"]) == (caso, "Confirmar a triagem")
        assert comite.minha_vez(MEMBRO) == []
        assert comite.minha_vez(SEGUNDO_LEITOR) == []

    def test_depois_da_triagem_a_vez_e_do_segundo_leitor(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        assert [i["acao"] for i in comite.minha_vez(SEGUNDO_LEITOR)] == ["Conferir a triagem"]
        assert comite.minha_vez(COORDENACAO) == []

    def test_do_mais_urgente_ao_menos_urgente(self, comite):
        """Completo de 2 dias atrás vence em 28; Rápido de 15 dias atrás vence
        em 5; sem rito há 1 dia entra pelo Encaminhamento (5 dias úteis)."""
        completo = comite.caso(dias_atras=2)
        rapido = comite.caso(dias_atras=15)
        comite.ok(COORDENACAO, completo, "triagem", DENTRO_COMPLETO)
        comite.ok(COORDENACAO, rapido, "triagem", DENTRO_RAPIDO)
        sem_rito = comite.caso(dias_atras=1)

        ordem = [i["id"] for i in comite.minha_vez(SEGUNDO_LEITOR)]
        assert ordem == [rapido, completo]
        assert [i["id"] for i in comite.minha_vez(COORDENACAO)] == [sem_rito]

        prazos = {i["id"]: i["faltam_dias"] for i in comite.minha_vez(SEGUNDO_LEITOR)}
        assert prazos == {rapido: 5, completo: 28}

    def test_a_lista_nao_leva_nome_nem_trecho_de_relato(self, comite):
        comite.caso()

        resposta = comite.cliente(COORDENACAO).get(f"{BASE}/minha-vez")
        assert "Fulano" not in resposta.text and "almoxarifado" not in resposta.text
        assert "relato" not in resposta.text

    def test_quem_nao_esta_no_comite_recebe_403(self, comite):
        comite.caso()
        assert comite.cliente(DE_FORA).get(f"{BASE}/minha-vez").status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# Casos: filtro por situação e rito, sem nome e sem trecho
# ═══════════════════════════════════════════════════════════════════════════


class TestCasos:
    def _cenario(self, comite):
        em_triagem = comite.caso()
        rapido = comite.caso()
        comite.ok(COORDENACAO, rapido, "triagem", DENTRO_RAPIDO)
        encaminhado = comite.caso()
        comite.ok(COORDENACAO, encaminhado, "triagem", FORA_DP)
        comite.ok(SEGUNDO_LEITOR, encaminhado, "conferencia")
        comite.ok(COORDENACAO, encaminhado, "encaminhamento")
        return em_triagem, rapido, encaminhado

    def _ids(self, comite, consulta: str) -> set[str]:
        resposta = comite.cliente(MEMBRO).get(f"{BASE}/casos{consulta}")
        assert resposta.status_code == 200, resposta.text
        return {c["id"] for c in resposta.json()["casos"]}

    def test_filtra_por_situacao_e_por_rito(self, comite):
        em_triagem, rapido, encaminhado = self._cenario(comite)

        assert self._ids(comite, "") == {em_triagem, rapido, encaminhado}
        assert self._ids(comite, "?situacao=em_triagem") == {em_triagem}
        assert self._ids(comite, "?situacao=em_andamento") == {rapido}
        assert self._ids(comite, "?situacao=encerrado") == {encaminhado}
        assert self._ids(comite, "?rito=rapido") == {rapido}
        assert self._ids(comite, "?rito=sem_rito") == {em_triagem}
        assert self._ids(comite, "?situacao=encerrado&rito=rapido") == set()

    def test_a_lista_nao_leva_nome_nem_trecho_de_relato(self, comite):
        self._cenario(comite)

        resposta = comite.cliente(MEMBRO).get(f"{BASE}/casos")
        assert "Fulano" not in resposta.text and "almoxarifado" not in resposta.text
        assert all("relato" not in chave and "cifrad" not in chave for c in resposta.json()["casos"] for chave in c)


# ═══════════════════════════════════════════════════════════════════════════
# A caixa "O QUE FAZER AGORA" e o botão bloqueado com o motivo
# ═══════════════════════════════════════════════════════════════════════════


class TestOQueFazerAgora:
    def test_a_coordenacao_ve_a_caixa_da_triagem_com_os_textos_da_especificacao(self, comite):
        caixa = comite.abrir(COORDENACAO, comite.caso())["o_que_fazer_agora"]

        assert caixa == {
            "frase": "Leia o resumo. Confirme se o caso é do canal e qual o rito.",
            "botao": "CONFIRMAR TRIAGEM",
            "como_fazer": [
                "Leia o relato original",
                "Confira cada sugestão",
                "Se faltar informação, pergunte ao denunciante",
            ],
            "acao": "confirmar_triagem",
            "bloqueio": None,
        }

    def test_o_membro_ve_o_botao_bloqueado_com_o_motivo(self, comite):
        caixa = comite.abrir(MEMBRO, comite.caso())["o_que_fazer_agora"]

        assert caixa["botao"] == "CONFIRMAR TRIAGEM"
        assert caixa["bloqueio"] == "Só a coordenação confirma a triagem."

    def test_fora_do_canal_a_caixa_e_a_da_orientacao_e_espera_a_conferencia(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", FORA_DP)

        caixa = comite.abrir(COORDENACAO, caso)["o_que_fazer_agora"]
        assert caixa["frase"] == "Este relato parece não ser do canal. Confira e envie a orientação."
        assert caixa["botao"] == "ENVIAR ORIENTAÇÃO"
        assert caixa["bloqueio"] == "Falta o segundo leitor conferir a triagem."

    def test_a_apuracao_mostra_o_texto_da_especificacao(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        caixa = comite.abrir(COORDENACAO, caso)["o_que_fazer_agora"]
        assert caixa["frase"] == "Ouça o acusado e até duas pessoas. Sempre em dupla."
        assert caixa["botao"] == "ADICIONAR PESSOA A OUVIR"
        # Os depoimentos chegaram (issue #1830): o botão abre o cartão.
        assert caixa["bloqueio"] is None

    def test_o_trilho_destaca_a_etapa_atual(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        trilho = comite.abrir(MEMBRO, caso)["trilho"]
        assert [(e["nome"], e["estado"]) for e in trilho[:3]] == [
            ("Triagem", "concluida"),
            ("Apuração", "atual"),
            ("Voto", "pendente"),
        ]


# ═══════════════════════════════════════════════════════════════════════════
# A coordenação confirma a triagem
# ═══════════════════════════════════════════════════════════════════════════


class TestTriagem:
    def test_a_coordenacao_confirma_dentro_categoria_e_rito(self, comite):
        caso = comite.caso()

        gravado = comite.ok(
            COORDENACAO, caso, "triagem", {"escopo": "misto", "categoria": "C", "rito": "completo", "destino": "dp"}
        )

        assert (gravado["escopo"], gravado["categoria"], gravado["rito"], gravado["destino"]) == (
            "misto",
            "C",
            "completo",
            "dp",
        )
        assert gravado["etapa"] == "apuracao"
        assert "triagem" in comite.trilha(caso)

    @pytest.mark.parametrize("quem", [SEGUNDO_LEITOR, MEMBRO])
    def test_so_a_coordenacao_confirma(self, comite, quem):
        caso = comite.caso()

        resposta = comite.agir(quem, caso, "triagem", DENTRO_RAPIDO)
        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Só a coordenação confirma a triagem."

    def test_fora_do_canal_so_vai_ao_encaminhamento(self, comite):
        resposta = comite.agir(COORDENACAO, comite.caso(), "triagem", {**FORA_DP, "rito": "rapido"})
        assert resposta.status_code == 422

    def test_a_triagem_confirmada_nao_se_confirma_de_novo(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)
        assert comite.agir(COORDENACAO, caso, "triagem", DENTRO_COMPLETO).status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# A contestação do segundo leitor vai à decisão dos três
# ═══════════════════════════════════════════════════════════════════════════


class TestContestacao:
    CONTESTACAO = {"motivo": "Há ameaça de demissão, cabe o rito completo.", **DENTRO_COMPLETO}

    def _contestado(self, comite) -> str:
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)
        comite.ok(SEGUNDO_LEITOR, caso, "contestacao", self.CONTESTACAO)
        return caso

    def test_a_contestacao_leva_a_decisao_aos_tres(self, comite):
        caso = self._contestado(comite)

        acoes = {pid: [i["acao"] for i in comite.minha_vez(pid)] for pid in (COORDENACAO, SEGUNDO_LEITOR, MEMBRO)}
        assert acoes == {pid: ["Decidir a contestação da triagem"] for pid in acoes}
        assert comite.abrir(MEMBRO, caso)["contestacao"]["motivo"] == self.CONTESTACAO["motivo"]

    def test_dois_dos_tres_acatam_e_vale_a_triagem_contestada(self, comite):
        caso = self._contestado(comite)

        depois_de_um = comite.ok(MEMBRO, caso, "contestacao/decisao", {"escolha": "acatar"})
        assert depois_de_um["etapa"] == "contestada"
        assert [i["acao"] for i in comite.minha_vez(MEMBRO)] == []

        decidido = comite.ok(SEGUNDO_LEITOR, caso, "contestacao/decisao", {"escolha": "acatar"})
        assert (decidido["rito"], decidido["etapa"]) == ("completo", "apuracao")
        assert comite.abrir(COORDENACAO, caso)["contestacao"]["resultado"] == "acatada"

    def test_dois_dos_tres_mantem_e_vale_a_triagem_da_coordenacao(self, comite):
        caso = self._contestado(comite)
        comite.ok(COORDENACAO, caso, "contestacao/decisao", {"escolha": "manter"})

        decidido = comite.ok(MEMBRO, caso, "contestacao/decisao", {"escolha": "manter"})
        assert (decidido["rito"], decidido["etapa"]) == ("rapido", "apuracao")

    def test_cada_um_decide_uma_vez(self, comite):
        caso = self._contestado(comite)
        comite.ok(MEMBRO, caso, "contestacao/decisao", {"escolha": "acatar"})

        assert comite.agir(MEMBRO, caso, "contestacao/decisao", {"escolha": "acatar"}).status_code == 409

    def test_so_o_segundo_leitor_contesta(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        assert comite.agir(MEMBRO, caso, "contestacao", self.CONTESTACAO).status_code == 403

    def test_a_contestacao_exige_o_motivo_e_fica_cifrada(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)
        assert comite.agir(SEGUNDO_LEITOR, caso, "contestacao", {**self.CONTESTACAO, "motivo": " "}).status_code == 422

        comite.ok(SEGUNDO_LEITOR, caso, "contestacao", self.CONTESTACAO)
        assert "ameaça de demissão" not in repr(comite.banco.tabelas["conduta_contestacoes"])


# ═══════════════════════════════════════════════════════════════════════════
# O prazo conta do envio, e o vencido fica registrado
# ═══════════════════════════════════════════════════════════════════════════


class TestPrazo:
    def test_o_prazo_conta_do_envio_e_nao_da_triagem(self, comite):
        caso = comite.caso(dias_atras=10)

        gravado = comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        assert date.fromisoformat(gravado["prazo_em"]) == HOJE + timedelta(days=10)

    def test_o_prazo_vencido_fica_registrado_e_a_prorrogacao_nao_o_apaga(self, comite):
        caso = comite.caso(dias_atras=31)
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_COMPLETO)
        comite.ok(SEGUNDO_LEITOR, caso, "conferencia")

        assert comite.abrir(MEMBRO, caso)["prazo_vencido"] is True
        comite.ok(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam dois depoimentos."})

        assert comite.abrir(MEMBRO, caso)["prazo_vencido"] is True
        (vencido,) = comite.banco.tabelas["conduta_prazos_vencidos"]
        assert (vencido["caso_id"], vencido["rito"]) == (caso, "completo")
        assert comite.trilha(caso).count("prazo_vencido") == 1

    def test_ver_a_lista_de_novo_nao_registra_o_vencido_duas_vezes(self, comite):
        caso = comite.caso(dias_atras=25)
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        for _ in range(3):
            casos_listados = comite.cliente(MEMBRO).get(f"{BASE}/casos").json()["casos"]
        assert casos_listados[0]["prazo_vencido"] is True
        assert len(comite.banco.tabelas["conduta_prazos_vencidos"]) == 1

    def test_prazo_em_dia_nao_e_vencido(self, comite):
        caso = comite.caso(dias_atras=5)
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        assert comite.abrir(MEMBRO, caso)["prazo_vencido"] is False
        assert comite.banco.tabelas.get("conduta_prazos_vencidos", []) == []


# ═══════════════════════════════════════════════════════════════════════════
# O Completo prorroga uma única vez, com justificativa
# ═══════════════════════════════════════════════════════════════════════════


class TestProrrogacao:
    def _completo(self, comite) -> str:
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_COMPLETO)
        comite.ok(SEGUNDO_LEITOR, caso, "conferencia")
        return caso

    def test_nao_prorroga_antes_da_conferencia(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_COMPLETO)

        falta = "Falta o segundo leitor conferir a triagem."
        assert comite.abrir(COORDENACAO, caso)["prorrogacao"]["bloqueio"] == falta
        resposta = comite.agir(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam dois depoimentos."})
        assert resposta.status_code == 409
        assert resposta.json()["detail"] == falta

    def test_nao_prorroga_com_a_contestacao_aberta_e_o_rito_acatado_vale_sem_prorrogacao(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_COMPLETO)
        comite.ok(SEGUNDO_LEITOR, caso, "contestacao", {"motivo": "Cabe o rito rápido.", **DENTRO_RAPIDO})

        resposta = comite.agir(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam dois depoimentos."})
        assert resposta.status_code == 409
        assert comite.trilha(caso).count("prorrogacao") == 0

        comite.ok(MEMBRO, caso, "contestacao/decisao", {"escolha": "acatar"})
        decidido = comite.ok(SEGUNDO_LEITOR, caso, "contestacao/decisao", {"escolha": "acatar"})
        assert (decidido["rito"], decidido["etapa"], decidido.get("prorrogado_em")) == ("rapido", "apuracao", None)

    def test_prorroga_por_trinta_dias_uma_vez_so(self, comite):
        caso = self._completo(comite)

        gravado = comite.ok(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam dois depoimentos."})
        assert date.fromisoformat(gravado["prazo_em"]) == HOJE + timedelta(days=60)

        segunda = comite.agir(COORDENACAO, caso, "prorrogacao", {"justificativa": "De novo."})
        assert segunda.status_code == 409
        assert segunda.json()["detail"] == "O prazo já foi prorrogado uma vez."
        assert comite.abrir(MEMBRO, caso)["prorrogacao"]["justificativa"] == "Faltam dois depoimentos."

    def test_sem_justificativa_nao_prorroga(self, comite):
        caso = self._completo(comite)
        assert comite.agir(COORDENACAO, caso, "prorrogacao", {"justificativa": "  "}).status_code == 422

    def test_o_rapido_nao_prorroga(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", DENTRO_RAPIDO)

        resposta = comite.agir(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam depoimentos."})
        assert resposta.status_code == 409

    def test_a_justificativa_fica_cifrada(self, comite):
        caso = self._completo(comite)
        comite.ok(COORDENACAO, caso, "prorrogacao", {"justificativa": "Faltam dois depoimentos."})

        assert "depoimentos" not in repr(comite.banco.tabelas["conduta_casos"])


# ═══════════════════════════════════════════════════════════════════════════
# No Encaminhamento, a resposta padrão num clique e o caso encerra
# ═══════════════════════════════════════════════════════════════════════════


class TestEncaminhamento:
    ORIENTACAO = (
        "Seu relato foi lido pelo Comitê. O assunto não é tratado neste canal. "
        "Procure o Departamento Pessoal. Se houver assédio, ameaça ou retaliação envolvidos, "
        "registre um novo relato contando essa parte."
    )

    def test_a_coordenacao_confirma_num_clique_e_o_caso_encerra_como_encaminhado(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", FORA_DP)
        comite.ok(SEGUNDO_LEITOR, caso, "conferencia")
        assert comite.abrir(COORDENACAO, caso)["orientacao"] == self.ORIENTACAO
        assert [i["acao"] for i in comite.minha_vez(COORDENACAO)] == ["Enviar a orientação"]

        encerrado = comite.ok(COORDENACAO, caso, "encaminhamento")

        assert (encerrado["desfecho"], encerrado["etapa"]) == ("encaminhado", "encerrado")
        assert encerrado["encerrado_em"]
        aberto = comite.abrir(MEMBRO, caso)
        assert aberto["orientacao"] == self.ORIENTACAO
        assert aberto["situacao"] == "encerrado"
        assert comite.minha_vez(COORDENACAO) == []

    def test_antes_da_conferencia_do_segundo_leitor_nao_encerra(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", FORA_DP)

        resposta = comite.agir(COORDENACAO, caso, "encaminhamento")
        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "Falta o segundo leitor conferir a triagem."

    def test_so_a_coordenacao_envia_a_orientacao(self, comite):
        caso = comite.caso()
        comite.ok(COORDENACAO, caso, "triagem", FORA_DP)
        comite.ok(SEGUNDO_LEITOR, caso, "conferencia")

        assert comite.agir(SEGUNDO_LEITOR, caso, "encaminhamento").status_code == 403
