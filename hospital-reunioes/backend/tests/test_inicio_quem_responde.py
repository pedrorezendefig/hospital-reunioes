"""Quem responde a você (issue #1943, PRD #1932, ADR 0104 decisão 9).

O bloco do Início de quem acompanha outras pessoas, em pedido separado do
resto do Início. Quem aparece segue o vínculo da ADR 0098, decisão 7: o Super
admin vê todas as pessoas com item aberto, e o Facilitador vê os responsáveis
das Pendências das Reuniões que conduziu. Cada linha traz nome, cargo,
vencidos agora, em aberto e o último acesso (Registro de acesso, issue #1941).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import inicio as inicio_router  # noqa: E402
from app.services.inicio import entregas, quem_responde  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)
HOJE = AGORA.date()


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Consulta:
    """A consulta de mentira. `teto` imita o `max_rows` do PostgREST: corta
    a resposta em silêncio, com HTTP 200. Recorte sem `order` é recusado,
    porque o PostgREST não garante a ordem e a página seguinte pularia linha."""

    def __init__(self, linhas: list[dict], teto: int | None = None):
        self._linhas = linhas
        self._teto = teto
        self._filtros: list = []
        self._ordem: list[str] = []
        self._recorte: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, *_a, **_kw):
        self._ordem.append(coluna)
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = set(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def execute(self):
        linhas = [dict(linha) for linha in self._linhas if all(f(linha) for f in self._filtros)]
        if self._ordem:
            linhas.sort(key=lambda linha: tuple(str(linha.get(c)) for c in self._ordem))
        if self._recorte:
            assert self._ordem, "recorte sem order: a página seguinte pode repetir ou pular linha"
            linhas = linhas[self._recorte[0] : self._recorte[1] + 1]
        if self._teto is not None:
            linhas = linhas[: self._teto]
        return _Result(linhas)


@dataclass
class _Banco:
    pendencias: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    participantes: list = field(default_factory=list)
    registro_de_acesso: list = field(default_factory=list)
    pendencia_historico: list = field(default_factory=list)
    teto: int | None = None

    def table(self, nome):
        return _Consulta(getattr(self, nome), self.teto)


def _pendencia(id_acao: str, responsavel_id: str, **campos) -> dict:
    base = {
        "id_acao": id_acao,
        "descricao_acao": f"Ação {id_acao}",
        "responsavel_id": responsavel_id,
        "co_responsavel_id": None,
        "id_reuniao": "R1",
        "prazo": (HOJE + timedelta(days=3)).isoformat(),
        "status": "PENDENTE",
        "deleted_at": None,
    }
    return {**base, **campos}


def _vencida(id_acao: str, responsavel_id: str, dias: int, **campos) -> dict:
    return _pendencia(id_acao, responsavel_id, prazo=(HOJE - timedelta(days=dias)).isoformat(), **campos)


def _pessoa(pid: str, nome: str, cargo: str) -> dict:
    return {"id": pid, "nome_completo": nome, "cargo": cargo, "role": "gerente", "email": f"{pid}@hsm"}


SUPER = {"id": "P_SUPER", "nome_completo": "Sara Admin", "access_profile": "super_admin"}
FACILITADOR = {"id": "P_FAC", "nome_completo": "Fábio Lima", "access_profile": "regular"}
NINGUEM = {"id": "P_NADA", "nome_completo": "Nara Silva", "access_profile": "regular"}
SECRETARIA = {"id": "P_SEC", "nome_completo": "Selma Souza", "access_profile": "secretaria"}

ANA = _pessoa("P_ANA", "Ana Souza", "Enfermeira")
BRUNO = _pessoa("P_BRUNO", "Bruno Reis", "Farmacêutico")
CAIO = _pessoa("P_CAIO", "Caio Melo", "Coordenador de Hotelaria")

REUNIOES = [
    {"id_reuniao": "R1", "titulo": "Reunião de Atendimento", "data": "2026-10-28", "facilitador_id": "P_FAC"},
    {"id_reuniao": "R2", "titulo": "Reunião de Hotelaria", "data": "2026-10-29", "facilitador_id": "P_OUTRO"},
    {"id_reuniao": "RN", "titulo": "Reunião do Núcleo", "data": "2026-10-21", "facilitador_id": "P_OUTRO"},
]


def _banco(*pendencias, acessos=(), historico=()) -> _Banco:
    return _Banco(
        pendencias=list(pendencias),
        reunioes=[dict(r, deleted_at=None) for r in REUNIOES],
        participantes=[ANA, BRUNO, CAIO],
        registro_de_acesso=[{"participante_id": pid, "dia": dia} for pid, dia in acessos],
        pendencia_historico=list(historico),
    )


@pytest.fixture
def nucleo(monkeypatch):
    """O que a pessoa alcança do Núcleo: nada, por padrão. A regra de verdade
    mora em `dependencies` e tem teste próprio; aqui ela é a entrada."""
    estado = {"ocultas": ["RN"], "recursos": frozenset()}
    monkeypatch.setattr(quem_responde, "reunioes_ocultas", lambda _sb, _me: list(estado["ocultas"]))
    monkeypatch.setattr(quem_responde, "recursos_nsp_da_pessoa", lambda _sb, _me: estado["recursos"])
    return estado


def _rota(monkeypatch, me: dict | None, banco: _Banco):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: AGORA)
    return asyncio.run(inicio_router.get_quem_responde(current_user={"id": "u1"}, supabase=banco))


async def _async(valor):
    return valor


def _nomes(resposta) -> list[str]:
    return [pessoa.nome for pessoa in resposta.pessoas]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Quem aparece, por papel
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemAparece:
    def test_super_admin_ve_todas_as_pessoas_com_item_aberto(self, monkeypatch, nucleo):
        banco = _banco(
            _pendencia("A1", "P_ANA", id_reuniao="R1"),
            _pendencia("B1", "P_BRUNO", id_reuniao="R2"),
            _pendencia("C1", "P_CAIO", id_reuniao="R2", status="CONCLUIDO"),
        )

        resposta = _rota(monkeypatch, SUPER, banco)

        assert sorted(_nomes(resposta)) == ["Ana Souza", "Bruno Reis"]

    def test_facilitador_ve_so_os_responsaveis_das_pendencias_das_reunioes_dele(self, monkeypatch, nucleo):
        banco = _banco(
            _pendencia("A1", "P_ANA", id_reuniao="R1"),
            _pendencia("A2", "P_ANA", id_reuniao="R2"),
            _pendencia("B1", "P_BRUNO", id_reuniao="R1", co_responsavel_id="P_CAIO"),
            _pendencia("C1", "P_CAIO", id_reuniao="R2"),
        )

        resposta = _rota(monkeypatch, FACILITADOR, banco)

        assert sorted(_nomes(resposta)) == ["Ana Souza", "Bruno Reis", "Caio Melo"]
        # De cada pessoa, só os itens das Reuniões que ele conduziu.
        assert {p.id: p.em_aberto for p in resposta.pessoas} == {"P_ANA": 1, "P_BRUNO": 1, "P_CAIO": 1}

    def test_quem_nao_e_super_admin_nem_facilitador_nao_recebe_o_bloco(self, monkeypatch, nucleo):
        banco = _banco(_pendencia("A1", "P_ANA", id_reuniao="R1"))

        assert _rota(monkeypatch, NINGUEM, banco) is None

    def test_quem_nao_tem_perfil_das_reunioes_nao_recebe_o_bloco(self, monkeypatch, nucleo):
        sem_perfil = {"id": "P_FAC", "nome_completo": "Fábio Lima", "access_profile": None}
        banco = _banco(_pendencia("A1", "P_ANA", id_reuniao="R1"))

        assert _rota(monkeypatch, sem_perfil, banco) is None

    def test_a_secretaria_e_recusada(self, monkeypatch, nucleo):
        with pytest.raises(HTTPException) as erro:
            _rota(monkeypatch, SECRETARIA, _banco(_pendencia("A1", "P_ANA")))
        assert erro.value.status_code == 403

    def test_quem_pede_nao_aparece_na_propria_lista(self, monkeypatch, nucleo):
        banco = _banco(_pendencia("F1", "P_FAC", id_reuniao="R1"), _pendencia("A1", "P_ANA", id_reuniao="R1"))

        assert _nomes(_rota(monkeypatch, FACILITADOR, banco)) == ["Ana Souza"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. A linha de cada pessoa e a ordem
# ═══════════════════════════════════════════════════════════════════════════


class TestLinhaDaPessoa:
    def test_a_linha_traz_nome_cargo_vencidos_em_aberto_e_ultimo_acesso_sem_role(self, monkeypatch, nucleo):
        banco = _banco(
            _vencida("A1", "P_ANA", 4),
            _vencida("A2", "P_ANA", 1),
            _pendencia("A3", "P_ANA"),
            # Prazo de hoje ainda não venceu: só vence quando o dia acaba.
            _pendencia("A4", "P_ANA", prazo=HOJE.isoformat()),
            acessos=[("P_ANA", "2026-11-10"), ("P_ANA", "2026-11-15")],
        )

        resposta = _rota(monkeypatch, SUPER, banco)

        ana = resposta.pessoas[0]
        assert (ana.nome, ana.cargo, ana.vencidos, ana.em_aberto, ana.ultimo_acesso) == (
            "Ana Souza",
            "Enfermeira",
            2,
            4,
            "há 3 dias",
        )
        corpo = json.dumps(resposta.model_dump(mode="json"))
        assert "role" not in corpo
        assert "gerente" not in corpo

    @pytest.mark.parametrize(
        ("acessos", "texto"),
        [
            ([("P_ANA", "2026-11-18")], "hoje"),
            ([("P_ANA", "2026-11-17")], "há 1 dia"),
            ([("P_ANA", "2026-11-08")], "há 10 dias"),
            ([], "nunca entrou"),
        ],
    )
    def test_o_ultimo_acesso_diz_hoje_ha_n_dias_ou_nunca_entrou(self, monkeypatch, nucleo, acessos, texto):
        banco = _banco(_pendencia("A1", "P_ANA"), acessos=acessos)

        assert _rota(monkeypatch, SUPER, banco).pessoas[0].ultimo_acesso == texto

    def test_o_ultimo_acesso_sai_certo_quando_o_banco_corta_a_resposta_no_teto(self, monkeypatch, nucleo):
        # Ana abriu o Início nos últimos 30 dias, hoje por último; Bruno só
        # hoje. Com o banco cortando cada resposta em 5 linhas, uma leitura só
        # perderia o dia de hoje da Ana e a única marca do Bruno.
        acessos = [("P_ANA", (HOJE - timedelta(days=n)).isoformat()) for n in reversed(range(30))]
        banco = _banco(
            _pendencia("A1", "P_ANA"),
            _pendencia("B1", "P_BRUNO"),
            acessos=[*acessos, ("P_BRUNO", HOJE.isoformat())],
        )
        banco.teto = 5

        resposta = _rota(monkeypatch, SUPER, banco)

        assert {p.nome: p.ultimo_acesso for p in resposta.pessoas} == {"Ana Souza": "hoje", "Bruno Reis": "hoje"}

    def test_a_lista_vem_ordenada_por_prazos_vencidos(self, monkeypatch, nucleo):
        banco = _banco(
            # Ana: muito em aberto, um vencido. Bruno: três vencidos. Caio: nenhum.
            _vencida("A1", "P_ANA", 2),
            *[_pendencia(f"A{n}", "P_ANA") for n in range(2, 8)],
            _vencida("B1", "P_BRUNO", 1),
            _vencida("B2", "P_BRUNO", 1),
            _vencida("B3", "P_BRUNO", 9),
            _pendencia("C1", "P_CAIO"),
        )

        assert _nomes(_rota(monkeypatch, SUPER, banco)) == ["Bruno Reis", "Ana Souza", "Caio Melo"]

    def test_a_linha_traz_as_entregas_de_90_dias_com_os_mesmos_numeros_que_a_pessoa_ve(self, monkeypatch, nucleo):
        # Issue #1946. Ana: uma entrega no prazo, uma fora e uma depois de
        # Repactuação vencida (fora). Bruno: uma no prazo.
        def concluir(id_acao, dia, prazo, n):
            return {
                "id": n,
                "id_acao": id_acao,
                "comando": "concluir",
                "criado_em": f"{dia}T13:00:00+00:00",
                "prazo_antes": prazo,
                "conta_atraso": False,
            }

        banco = _banco(
            _pendencia("A1", "P_ANA"),
            _pendencia("A2", "P_ANA", status="CONCLUIDO"),
            _pendencia("A3", "P_ANA", status="CONCLUIDO"),
            _pendencia("A4", "P_ANA", status="CONCLUIDO"),
            _pendencia("B1", "P_BRUNO"),
            _pendencia("B2", "P_BRUNO", status="CONCLUIDO"),
            historico=[
                concluir("A2", "2026-11-09", "2026-11-10", 1),
                concluir("A3", "2026-11-12", "2026-11-10", 2),
                {
                    "id": 3,
                    "id_acao": "A4",
                    "comando": "repactuar",
                    "criado_em": "2026-11-08T13:00:00+00:00",
                    "prazo_antes": "2026-11-05",
                    "conta_atraso": True,
                },
                concluir("A4", "2026-11-14", "2026-11-15", 4),
                concluir("B2", "2026-11-14", "2026-11-15", 5),
            ],
        )

        resposta = _rota(monkeypatch, SUPER, banco)

        por_nome = {p.nome: (p.entregas_90_dias.no_prazo, p.entregas_90_dias.fora_do_prazo) for p in resposta.pessoas}
        assert por_nome == {"Ana Souza": (1, 2), "Bruno Reis": (1, 0)}
        # A mesma conta que a Ana vê no Início dela.
        monkeypatch.setattr(entregas, "reunioes_ocultas", lambda _sb, _me: ["RN"])
        ana = {"id": "P_ANA", "nome_completo": "Ana Souza", "access_profile": "regular"}
        monkeypatch.setattr(inicio_router, "get_participante_for_user", lambda *_a, **_kw: _async(ana))
        propria = asyncio.run(inicio_router.get_meus_numeros(current_user={"id": "u1"}, supabase=banco))
        assert (propria.numeros_90_dias.no_prazo, propria.numeros_90_dias.fora_do_prazo) == por_nome["Ana Souza"]

    def test_o_que_venceu_e_nao_foi_entregue_vem_com_ha_quantos_dias(self, monkeypatch, nucleo):
        banco = _banco(
            _vencida("B1", "P_BRUNO", 2, descricao_acao="Trocar o filtro da farmácia"),
            _vencida("B2", "P_BRUNO", 12, descricao_acao="Revisar o estoque"),
            _pendencia("B3", "P_BRUNO", descricao_acao="Ainda no prazo"),
        )

        bruno = _rota(monkeypatch, SUPER, banco).pessoas[0]

        assert [(i.titulo, i.dias_de_atraso, i.origem) for i in bruno.itens_vencidos] == [
            ("Revisar o estoque", 12, "Reunião de Atendimento, de 28/10/2026."),
            ("Trocar o filtro da farmácia", 2, "Reunião de Atendimento, de 28/10/2026."),
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 3. O sigilo do Núcleo e o último acesso
# ═══════════════════════════════════════════════════════════════════════════


class TestSigilo:
    def test_super_admin_sem_acesso_ao_nucleo_nao_ve_itens_do_nucleo(self, monkeypatch, nucleo):
        banco = _banco(
            _pendencia("A1", "P_ANA", id_reuniao="R1"),
            _pendencia("A2", "P_ANA", id_reuniao="RN"),
            _pendencia("B1", "P_BRUNO", id_reuniao="RN"),
            # O lembrete da Agenda regulatória, Pendência sem Reunião.
            _pendencia("C1", "P_CAIO", id_reuniao=None),
        )

        resposta = _rota(monkeypatch, SUPER, banco)

        assert _nomes(resposta) == ["Ana Souza"]
        assert resposta.pessoas[0].em_aberto == 1

    def test_super_admin_com_acesso_ao_nucleo_ve_os_itens_do_nucleo(self, monkeypatch, nucleo):
        nucleo["ocultas"] = []
        nucleo["recursos"] = frozenset({"reunioes", "agenda"})
        banco = _banco(_pendencia("B1", "P_BRUNO", id_reuniao="RN"), _pendencia("C1", "P_CAIO", id_reuniao=None))

        assert sorted(_nomes(_rota(monkeypatch, SUPER, banco))) == ["Bruno Reis", "Caio Melo"]

    def test_o_ultimo_acesso_so_sai_de_quem_tem_item_visivel(self, monkeypatch, nucleo):
        # Bruno só tem item do Núcleo, que o Super admin não alcança; Caio não
        # tem item aberto nenhum. Os dois abriram o Início hoje.
        banco = _banco(
            _pendencia("A1", "P_ANA", id_reuniao="R1"),
            _pendencia("B1", "P_BRUNO", id_reuniao="RN"),
            acessos=[("P_ANA", "2026-11-18"), ("P_BRUNO", "2026-11-18"), ("P_CAIO", "2026-11-18")],
        )

        corpo = json.dumps(_rota(monkeypatch, SUPER, banco).model_dump(mode="json"))

        assert "P_ANA" in corpo
        assert "P_BRUNO" not in corpo
        assert "P_CAIO" not in corpo
        assert corpo.count("hoje") == 1


class TestKitDeConhecimento:
    def test_o_kit_de_conhecimento_explica_quem_responde_a_voce(self):
        caminho = Path(quem_responde.__file__).parents[2] / "conhecimento" / "reunioes.md"
        texto = " ".join(caminho.read_text(encoding="utf-8").split())

        assert "Quem acompanha outras pessoas vê, abaixo da lista, o bloco Quem responde a você" in texto
        assert "quem administra o aplicativo vê todas as pessoas com pendência aberta" in texto
        assert "o facilitador vê os responsáveis das pendências das reuniões que conduziu" in texto
        assert "Quem não é nenhum dos dois não vê o bloco" in texto
        assert "o nome, o cargo, os prazos vencidos agora, os itens em aberto e o último acesso" in texto
        assert '"hoje", "há tantos dias" ou "nunca entrou"' in texto
        assert "quem tem mais prazos vencidos vem primeiro" in texto
        assert "abre ali mesmo, só para leitura, o que venceu e não foi entregue" in texto
        assert "O último acesso de uma pessoa só aparece para quem vê alguma pendência dela" in texto
        assert "Se esse bloco não carregar, o resto do Início continua" in texto
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto
