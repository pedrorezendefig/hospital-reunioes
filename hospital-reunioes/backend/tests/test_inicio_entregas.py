"""Os números de 90 dias e o que foi entregue (issue #1946, PRD #1932, ADR 0104 decisões 7 e 9).

Cada pessoa vê no Início os próprios números dos últimos 90 dias (entregas no
prazo e fora), e quem está em dia vê o que entregou nos últimos 7 dias. O
bloco Quem responde a você ganha a mesma conta, por pessoa. A régua é a do
ranking do painel de Reuniões: a data de conclusão sai do Histórico da
Pendência, então só conta a conclusão feita depois que o ciclo novo entrou, e
a Repactuação feita depois do vencimento pesa como atraso.
"""

from __future__ import annotations

import asyncio
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
from app.services import inicio  # noqa: E402
from app.services.inicio import entregas  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)
HOJE = AGORA.date()


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Consulta:
    """`teto` imita o `max_rows` do PostgREST: corta a resposta em silêncio.
    Recorte sem `order` é recusado, porque a página seguinte pularia linha."""

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
    pendencia_historico: list = field(default_factory=list)
    teto: int | None = None

    def table(self, nome):
        return _Consulta(getattr(self, nome), self.teto)


def _pendencia(id_acao: str, responsavel_id: str = "P_ANA", **campos) -> dict:
    base = {
        "id_acao": id_acao,
        "descricao_acao": f"Ação {id_acao}",
        "responsavel_id": responsavel_id,
        "co_responsavel_id": None,
        "id_reuniao": "R1",
        "status": "CONCLUIDO",
        "deleted_at": None,
    }
    return {**base, **campos}


_IDS = iter(range(1, 10_000))


def _evento(id_acao: str, comando: str, dia: str, *, prazo_antes: str | None, conta_atraso: bool = False) -> dict:
    """Um evento do Histórico às 10h de Brasília (13h em UTC) do `dia`."""
    return {
        "id": next(_IDS),
        "id_acao": id_acao,
        "comando": comando,
        "criado_em": f"{dia}T13:00:00+00:00",
        "prazo_antes": prazo_antes,
        "conta_atraso": conta_atraso,
    }


def _concluida(id_acao: str, dia: str, prazo: str) -> dict:
    return _evento(id_acao, "concluir", dia, prazo_antes=prazo)


ANA = {"id": "P_ANA", "nome_completo": "Ana Souza", "access_profile": "regular"}
BRUNO = {"id": "P_BRUNO", "nome_completo": "Bruno Reis", "access_profile": "regular"}
SECRETARIA = {"id": "P_SEC", "nome_completo": "Selma Souza", "access_profile": "secretaria"}


@pytest.fixture
def nucleo(monkeypatch):
    """As Reuniões do Núcleo que a pessoa não alcança: nenhuma, por padrão."""
    estado = {"ocultas": []}
    monkeypatch.setattr(entregas, "reunioes_ocultas", lambda _sb, _me: list(estado["ocultas"]))
    return estado


def _rota(monkeypatch, me: dict | None, banco: _Banco):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: AGORA)
    return asyncio.run(inicio_router.get_meus_numeros(current_user={"id": "u1"}, supabase=banco))


def _numeros(resposta) -> tuple[int, int]:
    return resposta.numeros_90_dias.no_prazo, resposta.numeros_90_dias.fora_do_prazo


# ═══════════════════════════════════════════════════════════════════════════
# 1. Os próprios números de 90 dias
# ═══════════════════════════════════════════════════════════════════════════


class TestProprioNumero:
    def test_a_pessoa_ve_as_proprias_entregas_no_prazo_e_fora_e_nao_as_de_outra(self, monkeypatch, nucleo):
        banco = _Banco(
            pendencias=[
                _pendencia("A1"),
                _pendencia("A2"),
                _pendencia("A3"),
                _pendencia("B1", "P_BRUNO"),
                _pendencia("B2", "P_BRUNO"),
            ],
            pendencia_historico=[
                # No dia do prazo ainda é no prazo; no dia seguinte, fora.
                _concluida("A1", "2026-11-10", "2026-11-10"),
                _concluida("A2", "2026-11-11", "2026-11-10"),
                _concluida("A3", "2026-10-01", "2026-10-05"),
                _concluida("B1", "2026-11-12", "2026-11-01"),
                _concluida("B2", "2026-11-12", "2026-11-01"),
            ],
        )

        assert _numeros(_rota(monkeypatch, ANA, banco)) == (2, 1)
        assert _numeros(_rota(monkeypatch, BRUNO, banco)) == (0, 2)

    def test_a_secretaria_e_recusada(self, monkeypatch, nucleo):
        with pytest.raises(HTTPException) as erro:
            _rota(monkeypatch, SECRETARIA, _Banco())
        assert erro.value.status_code == 403

    def test_quem_nao_tem_perfil_das_reunioes_nao_recebe_numeros(self, monkeypatch, nucleo):
        sem_perfil = {"id": "P_ANA", "nome_completo": "Ana Souza", "access_profile": None}

        assert _rota(monkeypatch, sem_perfil, _Banco()) is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. A conta: no prazo, fora, e a Repactuação antes e depois do vencimento
# ═══════════════════════════════════════════════════════════════════════════


def _conta(*eventos, pendencias=None) -> tuple[int, int]:
    pendencias = pendencias or [_pendencia(e["id_acao"]) for e in eventos]
    lista = entregas.calcular(pendencias, list(eventos), HOJE).get("P_ANA", [])
    n = entregas.numeros(lista)
    return n.no_prazo, n.fora_do_prazo


class TestConta:
    def test_entrega_no_prazo(self):
        assert _conta(_concluida("A1", "2026-11-09", "2026-11-10")) == (1, 0)

    def test_entrega_fora_do_prazo(self):
        assert _conta(_concluida("A1", "2026-11-11", "2026-11-10")) == (0, 1)

    def test_a_conclusao_no_ultimo_minuto_do_dia_do_prazo_ainda_e_no_prazo(self):
        # 23h50 de 10/11 em Brasília é 02h50 de 11/11 em UTC.
        evento = _concluida("A1", "2026-11-10", "2026-11-10")
        evento["criado_em"] = "2026-11-11T02:50:00+00:00"

        assert _conta(evento) == (1, 0)

    def test_repactuacao_antes_do_vencimento_e_entrega_no_prazo_novo_conta_no_prazo(self):
        # O prazo era 05/11; em 03/11, antes de vencer, foi para 15/11.
        assert _conta(
            _evento("A1", "repactuar", "2026-11-03", prazo_antes="2026-11-05", conta_atraso=False),
            _concluida("A1", "2026-11-14", "2026-11-15"),
        ) == (1, 0)

    def test_repactuacao_depois_do_vencimento_faz_a_entrega_contar_fora_do_prazo(self):
        # O prazo era 05/11; em 08/11, já vencido, foi para 15/11. A entrega
        # dentro do prazo novo ainda é fora: o ranking conta essa Repactuação
        # como atraso.
        assert _conta(
            _evento("A1", "repactuar", "2026-11-08", prazo_antes="2026-11-05", conta_atraso=True),
            _concluida("A1", "2026-11-14", "2026-11-15"),
        ) == (0, 1)

    def test_repactuacao_vencida_de_antes_dos_90_dias_pesa_na_entrega_dentro_deles(self):
        assert _conta(
            _evento("A1", "repactuar", "2026-08-01", prazo_antes="2026-07-30", conta_atraso=True),
            _concluida("A1", "2026-11-14", "2026-11-15"),
        ) == (0, 1)

    def test_a_repactuacao_vencida_nao_pesa_na_entrega_depois_de_uma_reabertura(self):
        assert _conta(
            _evento("A1", "repactuar", "2026-11-08", prazo_antes="2026-11-05", conta_atraso=True),
            _concluida("A1", "2026-11-09", "2026-11-15"),
            _concluida("A1", "2026-11-16", "2026-11-20"),
        ) == (1, 1)

    def test_a_janela_e_hoje_e_os_89_dias_antes(self):
        # 18/11 menos 89 dias é 21/08: entra; 20/08 fica de fora.
        assert _conta(
            _concluida("A1", "2026-08-21", "2026-08-30"),
            _concluida("A2", "2026-08-20", "2026-08-30"),
        ) == (1, 0)

    def test_cancelada_e_lembrete_sem_reuniao_nao_contam(self):
        assert _conta(
            _concluida("A1", "2026-11-09", "2026-11-10"),
            _concluida("A2", "2026-11-09", "2026-11-10"),
            _concluida("A3", "2026-11-09", "2026-11-10"),
            pendencias=[_pendencia("A1"), _pendencia("A2", status="CANCELADO"), _pendencia("A3", id_reuniao=None)],
        ) == (1, 0)

    def test_a_entrega_conta_para_o_responsavel_e_nao_para_o_co_responsavel(self):
        pendencias = [_pendencia("B1", "P_BRUNO", co_responsavel_id="P_ANA")]

        lista = entregas.calcular(pendencias, [_concluida("B1", "2026-11-09", "2026-11-10")], HOJE)

        assert list(lista) == ["P_BRUNO"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Só contam as conclusões do ciclo novo
# ═══════════════════════════════════════════════════════════════════════════


class TestCicloNovo:
    def test_pendencia_concluida_antes_do_ciclo_novo_nao_conta(self, monkeypatch, nucleo):
        # A1 foi concluída antes do Histórico existir: está CONCLUIDO, com
        # data de conclusão, e não tem o evento `concluir`. Só A2 conta.
        banco = _Banco(
            pendencias=[_pendencia("A1", concluida_em="2026-11-10T13:00:00+00:00"), _pendencia("A2")],
            pendencia_historico=[
                _evento("A1", "migracao", "2026-11-01", prazo_antes="2026-10-30"),
                _concluida("A2", "2026-11-11", "2026-11-10"),
            ],
        )

        assert _numeros(_rota(monkeypatch, ANA, banco)) == (0, 1)

    def test_a_reuniao_do_nucleo_que_a_pessoa_nao_alcanca_fica_fora(self, monkeypatch, nucleo):
        nucleo["ocultas"] = ["RN"]
        banco = _Banco(
            pendencias=[_pendencia("A1"), _pendencia("A2", id_reuniao="RN")],
            pendencia_historico=[
                _concluida("A1", "2026-11-09", "2026-11-10"),
                _concluida("A2", "2026-11-09", "2026-11-10"),
            ],
        )

        assert _numeros(_rota(monkeypatch, ANA, banco)) == (1, 0)

    def test_a_conta_sai_certa_quando_o_banco_corta_a_resposta_no_teto(self, monkeypatch, nucleo):
        pendencias = [_pendencia(f"A{n:02d}") for n in range(12)]
        historico = [_concluida(p["id_acao"], "2026-11-09", "2026-11-10") for p in pendencias]
        banco = _Banco(pendencias=pendencias, pendencia_historico=historico, teto=5)

        assert _numeros(_rota(monkeypatch, ANA, banco)) == (12, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 4. O que foi entregue nos últimos 7 dias
# ═══════════════════════════════════════════════════════════════════════════


class TestEntregueEm7Dias:
    def test_a_lista_traz_as_entregas_de_hoje_e_dos_6_dias_antes_da_mais_recente_para_a_mais_antiga(
        self, monkeypatch, nucleo
    ):
        banco = _Banco(
            pendencias=[
                _pendencia("A1", descricao_acao="Trocar o filtro"),
                _pendencia("A2", descricao_acao="Revisar o estoque"),
                _pendencia("A3", descricao_acao="Entregue há sete dias"),
                _pendencia("B1", "P_BRUNO", descricao_acao="Do Bruno"),
            ],
            pendencia_historico=[
                _concluida("A1", "2026-11-12", "2026-11-20"),
                _concluida("A2", "2026-11-17", "2026-11-15"),
                _concluida("A3", "2026-11-11", "2026-11-20"),
                _concluida("B1", "2026-11-17", "2026-11-20"),
            ],
        )

        resposta = _rota(monkeypatch, ANA, banco)

        assert [(e.titulo, e.concluida_em.isoformat(), e.no_prazo) for e in resposta.entregues_7_dias] == [
            ("Revisar o estoque", "2026-11-17", False),
            ("Trocar o filtro", "2026-11-12", True),
        ]
        assert _numeros(resposta) == (2, 1)

    @pytest.mark.parametrize(
        ("dias_ate_o_prazo", "em_dia"),
        [(None, True), (5, True), (1, False), (-2, False)],
    )
    def test_o_inicio_diz_se_a_pessoa_esta_em_dia_como_a_frase(self, dias_ate_o_prazo, em_dia):
        # Em dia é não ter nada vencido nem para as próximas 48 horas: só
        # quem está em dia vê a lista do que entregou (PRD #1932).
        def itens(_sb, _me, _agora):
            if dias_ate_o_prazo is None:
                return []
            return [
                {
                    "tipo": "pendencia",
                    "id": "A1",
                    "titulo": "Trocar o filtro",
                    "origem": "Reunião.",
                    "prazo": HOJE + timedelta(days=dias_ate_o_prazo),
                    "area": "Reuniões",
                    "acao": "Abrir",
                    "destino": "/pendencias",
                }
            ]

        resposta = inicio.montar_inicio(
            _Banco(), ANA, AGORA, fontes=(inicio.Fonte("pendencias", "as Pendências", itens),), filas_do_papel=()
        )

        assert resposta.em_dia is em_dia
        assert resposta.frase.titulo.endswith("você está em dia.") is em_dia


# ═══════════════════════════════════════════════════════════════════════════
# 5. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDeConhecimento:
    def test_o_kit_de_conhecimento_explica_os_numeros_de_90_dias_e_o_que_foi_entregue(self):
        caminho = Path(entregas.__file__).parents[2] / "conhecimento" / "reunioes.md"
        texto = " ".join(caminho.read_text(encoding="utf-8").split())

        assert "vê embaixo a lista do que entregou nos últimos 7 dias" in texto
        assert "Cada pessoa vê no Início os próprios números dos últimos 90 dias" in texto
        assert "e não vê os de outra pessoa" in texto
        assert "a mesma régua do ranking do painel de Reuniões" in texto
        assert "só conta a conclusão feita depois que o histórico da pendência passou a guardar a data" in texto
        assert "a repactuação feita depois de o prazo vencer faz a entrega seguinte contar fora do prazo" in texto
        assert "a repactuação feita antes de o prazo vencer não pesa" in texto
        assert "as entregas dos últimos 90 dias, no prazo e fora, com os mesmos números que a pessoa vê" in texto
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto
