"""O Início com as Atas e as próximas Reuniões (issue #1936, PRD #1932, ADR 0104).

A fonte de Atas traz a Ata a assinar (a Reunião em assinatura em que a pessoa é
Signatária e ainda não deu ciência, pela ClickSign ou pelo Aceite interno) e a
Ata parada (a que espera o Facilitador na validação). As duas entram no grupo
"Sem prazo", com há quantos dias esperam; a Ata parada passa a contar como
vencida a partir do quarto dia. O trilho traz as próximas Reuniões em que a
pessoa é Facilitadora ou Participante.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import inicio as inicio_router  # noqa: E402
from app.services.inicio import fonte_nucleo, fonte_pendencias, fonte_reunioes  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)
HOJE = AGORA.date()


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def neq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and linha.get(coluna) != valor)
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and str(linha.get(coluna)) >= str(valor))
        return self

    def in_(self, coluna, valores):
        valores = set(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def ilike(self, coluna, padrao):
        alvo = padrao.replace("\\", "").lower()
        self._filtros.append(lambda linha: (linha.get(coluna) or "").lower() == alvo)
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim + 1)
        return self

    def execute(self):
        linhas = [dict(linha) for linha in self._linhas if all(f(linha) for f in self._filtros)]
        recorte = getattr(self, "_recorte", None)
        return _Result(linhas[recorte[0] : recorte[1]] if recorte else linhas)


@dataclass
class _Banco:
    pendencias: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reuniao_aceites: list = field(default_factory=list)
    # A fonte da Ouvidoria (#1937) também lê o banco; vazia aqui.
    ouvidoria_setor_responsaveis: list = field(default_factory=list)
    ouvidoria_protocolos: list = field(default_factory=list)
    ouvidoria_prorrogacoes: list = field(default_factory=list)
    # A fonte das Rotinas (#1874) também lê o banco; vazia aqui.
    rotinas: list = field(default_factory=list)
    # A fonte das Contestações (#1870) lê o histórico; vazio aqui.
    pendencia_historico: list = field(default_factory=list)

    def table(self, nome):
        return _Consulta(getattr(self, nome))


def _reuniao(id_reuniao: str, **campos) -> dict:
    base = {
        "id_reuniao": id_reuniao,
        "titulo": f"Reunião {id_reuniao}",
        "data": "2026-11-10",
        "hora_inicio": "09:00:00",
        "hora_fim": "10:00:00",
        "facilitador_id": "P_FACI",
        "status_ata": "PROGRAMADA",
        "deleted_at": None,
        "updated_at": "2026-11-12T15:00:00+00:00",
    }
    return {**base, **campos}


def _na_reuniao(id_reuniao: str, *pessoas: str) -> list[dict]:
    return [{"id_reuniao": id_reuniao, "participante_id": p, "sequence_assinatura": 2} for p in pessoas]


def _quando(dias_atras: int) -> str:
    """O `updated_at` de quem entrou no estado há N dias, às 15h de Brasília."""
    return datetime.combine(HOJE - timedelta(days=dias_atras), datetime.min.time().replace(hour=15), BRT).isoformat()


AURORA = {"id": "P_AURORA", "nome_completo": "Aurora Lima", "email": "aurora@exemplo.org", "access_profile": "regular"}
FACILITADOR = {
    "id": "P_FACI",
    "nome_completo": "Fabio Castro",
    "email": "fabio@exemplo.org",
    "access_profile": "regular",
}
DE_FORA = {"id": "P_FORA", "nome_completo": "Olga Reis", "email": "olga@exemplo.org", "access_profile": "regular"}


@pytest.fixture
def nucleo(monkeypatch):
    """As reuniões do Núcleo que a pessoa não alcança: nenhuma, por padrão. A
    regra de verdade mora em `dependencies` e tem teste próprio; aqui ela é a
    entrada."""
    estado = {"ocultas": [], "recursos": frozenset()}
    for modulo in (fonte_pendencias, fonte_reunioes):
        monkeypatch.setattr(modulo, "reunioes_ocultas", lambda _sb, _me: list(estado["ocultas"]))
    for modulo in (fonte_pendencias, fonte_nucleo):
        monkeypatch.setattr(modulo, "recursos_nsp_da_pessoa", lambda _sb, _me: estado["recursos"])
    return estado


def _rota(monkeypatch, me: dict | None, banco: _Banco, agora: datetime = AGORA):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: agora)
    return asyncio.run(inicio_router.get_inicio(current_user={"id": "u1"}, supabase=banco))


def _atas(resposta) -> list[tuple[str, str, str | None]]:
    return [(item.tipo, item.id, item.grupo) for item in resposta.itens if item.tipo.startswith("ata_")]


# ═══════════════════════════════════════════════════════════════════════════
# 1. A Ata a assinar, para o Signatário que ainda não deu ciência
# ═══════════════════════════════════════════════════════════════════════════


class TestAtaAAssinar:
    def test_signatario_ve_a_ata_em_assinatura_sem_prazo_com_os_dias_de_espera(self, monkeypatch, nucleo):
        banco = _Banco(
            reunioes=[
                _reuniao(
                    "R2",
                    titulo="Reunião de Enfermagem",
                    data="2026-11-09",
                    status_ata="AGUARDANDO_ASSINATURA",
                    updated_at=_quando(5),
                )
            ],
            reuniao_participantes=_na_reuniao("R2", "P_AURORA", "P_FACI"),
        )

        resposta = _rota(monkeypatch, AURORA, banco)

        assert _atas(resposta) == [("ata_a_assinar", "R2", "sem_prazo")]
        item = resposta.itens[0]
        assert item.prazo is None
        assert item.dias_esperando == 5
        assert item.titulo == "Ata a assinar: Reunião de Enfermagem"
        assert item.origem == "Reunião de Enfermagem, de 09/11/2026."
        assert item.area == "Reuniões"
        assert item.acao == "Assinar a Ata"
        assert item.destino == "/reunioes/R2"
        # Sem prazo não é vencido nem entra na frase.
        assert resposta.contadores.passou_do_prazo == 0
        assert resposta.frase.titulo == "Aurora, você está em dia."

    def test_depois_da_ciencia_pela_clicksign_a_ata_sai(self, monkeypatch, nucleo):
        """O webhook da ClickSign às vezes só casa o Signatário pelo email: o
        aceite fica sem `participante_id`, e a Ata sai do mesmo jeito."""
        banco = _Banco(
            reunioes=[_reuniao("R3", status_ata="AGUARDANDO_ASSINATURA")],
            reuniao_participantes=_na_reuniao("R3", "P_AURORA", "P_FACI"),
            reuniao_aceites=[
                {"id_reuniao": "R3", "participante_id": None, "email": "aurora@exemplo.org", "origem": "clicksign"}
            ],
        )

        assert _atas(_rota(monkeypatch, AURORA, banco)) == []

    def test_depois_do_aceite_interno_a_ata_sai(self, monkeypatch, nucleo):
        banco = _Banco(
            reunioes=[_reuniao("R4", status_ata="AGUARDANDO_ASSINATURA")],
            reuniao_participantes=_na_reuniao("R4", "P_AURORA", "P_FACI"),
            reuniao_aceites=[
                {"id_reuniao": "R4", "participante_id": "P_AURORA", "email": None, "origem": "aceite_interno"},
                {"id_reuniao": "R4", "participante_id": "P_FACI", "email": "fabio@exemplo.org", "origem": "clicksign"},
            ],
        )

        assert _atas(_rota(monkeypatch, AURORA, banco)) == []

    def test_aceite_de_outro_signatario_nao_tira_a_ata_dela(self, monkeypatch, nucleo):
        banco = _Banco(
            reunioes=[_reuniao("R5", status_ata="AGUARDANDO_ASSINATURA")],
            reuniao_participantes=_na_reuniao("R5", "P_AURORA", "P_FACI"),
            reuniao_aceites=[
                {"id_reuniao": "R5", "participante_id": "P_FACI", "email": "fabio@exemplo.org", "origem": "clicksign"}
            ],
        )

        assert _atas(_rota(monkeypatch, AURORA, banco)) == [("ata_a_assinar", "R5", "sem_prazo")]

    def test_so_a_ata_em_assinatura_e_viva(self, monkeypatch, nucleo):
        banco = _Banco(
            reunioes=[
                _reuniao("R6", status_ata="ASSINADA"),
                _reuniao("R7", status_ata="APROVADA"),
                _reuniao("R8", status_ata="AGUARDANDO_ASSINATURA", deleted_at="2026-11-15T00:00:00+00:00"),
            ],
            reuniao_participantes=(
                _na_reuniao("R6", "P_AURORA") + _na_reuniao("R7", "P_AURORA") + _na_reuniao("R8", "P_AURORA")
            ),
        )

        assert _atas(_rota(monkeypatch, AURORA, banco)) == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. A Ata parada, só para o Facilitador
# ═══════════════════════════════════════════════════════════════════════════


class TestAtaParada:
    def _banco(self, dias_em_validacao: int) -> _Banco:
        return _Banco(
            reunioes=[
                _reuniao(
                    "R10",
                    titulo="Reunião de Farmácia",
                    data="2026-11-05",
                    status_ata="AGUARDANDO_VALIDACAO",
                    updated_at=_quando(dias_em_validacao),
                )
            ],
            reuniao_participantes=_na_reuniao("R10", "P_AURORA", "P_FACI"),
        )

    def test_ate_o_terceiro_dia_a_ata_parada_fica_sem_prazo(self, monkeypatch, nucleo):
        resposta = _rota(monkeypatch, FACILITADOR, self._banco(3))

        assert _atas(resposta) == [("ata_parada", "R10", "sem_prazo")]
        item = resposta.itens[0]
        assert item.dias_esperando == 3
        assert item.dias_de_atraso is None
        assert item.titulo == "Ata em validação: Reunião de Farmácia"
        assert item.origem == "Reunião de Farmácia, de 05/11/2026."
        assert item.acao == "Revisar a Ata"
        assert item.destino == "/reunioes/R10"
        assert resposta.contadores.passou_do_prazo == 0
        assert resposta.contadores.ate_48_horas == 0
        assert resposta.frase.titulo == "Fabio, você está em dia."

    def test_do_quarto_dia_em_diante_a_ata_parada_passou_do_prazo(self, monkeypatch, nucleo):
        resposta = _rota(monkeypatch, FACILITADOR, self._banco(4))

        assert _atas(resposta) == [("ata_parada", "R10", "passou_do_prazo")]
        assert resposta.itens[0].dias_de_atraso == 1
        assert resposta.itens[0].dias_esperando is None
        assert resposta.contadores.passou_do_prazo == 1
        assert resposta.frase.titulo == "Fabio, um prazo seu venceu."

    def test_participante_que_ja_assinou_nao_ve_a_ata_parada_do_facilitador(self, monkeypatch, nucleo):
        banco = self._banco(10)
        banco.reuniao_aceites = [{"id_reuniao": "R10", "participante_id": "P_AURORA", "email": None}]

        assert _atas(_rota(monkeypatch, AURORA, banco)) == []

    def test_pessoa_de_fora_da_reuniao_nao_ve_nada(self, monkeypatch, nucleo):
        banco = self._banco(10)
        banco.reunioes.append(_reuniao("R11", status_ata="AGUARDANDO_ASSINATURA"))
        banco.reuniao_participantes += _na_reuniao("R11", "P_AURORA", "P_FACI")

        assert _atas(_rota(monkeypatch, DE_FORA, banco)) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. O sigilo do Núcleo e o portão das Reuniões
# ═══════════════════════════════════════════════════════════════════════════


class TestSigiloDoNucleo:
    def _banco(self) -> _Banco:
        return _Banco(
            reunioes=[
                _reuniao("RN2", status_ata="AGUARDANDO_VALIDACAO", facilitador_id="P_AURORA", colegiado_id="C_NUCLEO"),
                _reuniao("R20", status_ata="AGUARDANDO_ASSINATURA"),
            ],
            reuniao_participantes=_na_reuniao("R20", "P_AURORA"),
        )

    def test_ata_do_nucleo_fora_do_alcance_nao_aparece(self, monkeypatch, nucleo):
        nucleo["ocultas"] = ["RN2"]

        assert _atas(_rota(monkeypatch, AURORA, self._banco())) == [("ata_a_assinar", "R20", "sem_prazo")]

    def test_quem_o_nucleo_deixa_ver_ve_a_ata_do_nucleo(self, monkeypatch, nucleo):
        ids = sorted(id_reuniao for _tipo, id_reuniao, _grupo in _atas(_rota(monkeypatch, AURORA, self._banco())))

        assert ids == ["R20", "RN2"]

    def test_ata_do_nucleo_em_assinatura_nao_vira_ata_a_assinar(self, monkeypatch, nucleo):
        """A Ata do Núcleo vai num envelope próprio (`json_ata.assinatura`) e
        a assinatura dela não grava o Registro de Aceites: o Início não sabe
        quem já assinou. A Presidência, única na `reuniao_participantes`, já
        assinou e não pode ficar com a Ata na fila até o encerramento."""
        banco = _Banco(
            reunioes=[
                _reuniao(
                    "RN1",
                    status_ata="AGUARDANDO_ASSINATURA",
                    facilitador_id="P_AURORA",
                    colegiado_id="C_NUCLEO",
                    json_ata={
                        "assinatura": {
                            "envelope_id": "ENV1",
                            "enviada_em": "2026-11-12T15:00:00+00:00",
                            "signatarios": [
                                {"participante_id": "P_AURORA", "nome": "Aurora Lima", "email": "aurora@exemplo.org"}
                            ],
                        }
                    },
                )
            ],
            reuniao_participantes=_na_reuniao("RN1", "P_AURORA"),
        )

        assert _atas(_rota(monkeypatch, AURORA, banco)) == []

    def test_sem_perfil_das_reunioes_nao_recebe_ata(self, monkeypatch, nucleo):
        sem_reunioes = {**AURORA, "access_profile": None}

        assert _atas(_rota(monkeypatch, sem_reunioes, self._banco())) == []

    def test_reuniao_do_nucleo_fora_do_alcance_nao_entra_no_trilho(self, monkeypatch, nucleo):
        nucleo["ocultas"] = ["RN3"]
        banco = _Banco(
            reunioes=[_reuniao("RN3", data="2026-11-20"), _reuniao("R21", data="2026-11-21")],
            reuniao_participantes=_na_reuniao("RN3", "P_AURORA") + _na_reuniao("R21", "P_AURORA"),
        )

        assert [r.id for r in _rota(monkeypatch, AURORA, banco).trilho] == ["R21"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. O trilho: as próximas Reuniões da pessoa
# ═══════════════════════════════════════════════════════════════════════════


class TestTrilho:
    def _banco(self) -> _Banco:
        return _Banco(
            reunioes=[
                _reuniao("R30", titulo="Reunião de Qualidade", data="2026-11-24", hora_inicio="14:00:00"),
                _reuniao("R31", titulo="Reunião de Diretoria", data="2026-11-18", hora_inicio="16:30:00"),
                _reuniao("R32", titulo="Reunião cancelada", data="2026-11-19", status_ata="CANCELADA"),
                _reuniao("R33", titulo="Reunião passada", data="2026-11-17"),
                _reuniao("R34", titulo="Reunião apagada", data="2026-11-20", deleted_at="2026-11-16T00:00:00+00:00"),
                _reuniao("R35", titulo="Reunião que ela conduz", data="2026-11-19", facilitador_id="P_AURORA"),
                _reuniao("R36", titulo="Reunião dos outros", data="2026-11-19"),
            ],
            reuniao_participantes=(
                _na_reuniao("R30", "P_AURORA")
                + _na_reuniao("R31", "P_AURORA")
                + _na_reuniao("R32", "P_AURORA")
                + _na_reuniao("R33", "P_AURORA")
                + _na_reuniao("R34", "P_AURORA")
                + _na_reuniao("R36", "P_FACI")
            ),
        )

    def test_trilho_mostra_as_proximas_reunioes_com_data_hora_e_link(self, monkeypatch, nucleo):
        trilho = _rota(monkeypatch, AURORA, self._banco()).trilho

        assert [(r.id, r.data, r.hora, r.papel) for r in trilho] == [
            ("R31", date(2026, 11, 18), "16:30", "participante"),
            ("R35", date(2026, 11, 19), "09:00", "facilitador"),
            ("R30", date(2026, 11, 24), "14:00", "participante"),
        ]
        assert trilho[2].titulo == "Reunião de Qualidade"
        assert trilho[2].destino == "/reunioes/R30"

    def test_trilho_nao_mostra_reuniao_cancelada(self, monkeypatch, nucleo):
        ids = [r.id for r in _rota(monkeypatch, AURORA, self._banco()).trilho]

        assert "R32" not in ids

    def test_pessoa_de_fora_da_reuniao_tem_o_trilho_vazio(self, monkeypatch, nucleo):
        banco = self._banco()
        for reuniao in banco.reunioes:
            reuniao["facilitador_id"] = "P_FACI"

        assert _rota(monkeypatch, DE_FORA, banco).trilho == []

    def test_trilho_que_falha_vira_aviso_e_a_fila_segue(self, monkeypatch, nucleo):
        def _quebrado(*_a, **_kw):
            raise RuntimeError("timeout")

        monkeypatch.setattr(fonte_reunioes, "proximas", _quebrado)
        banco = _Banco(
            reunioes=[_reuniao("R40", status_ata="AGUARDANDO_ASSINATURA")],
            reuniao_participantes=_na_reuniao("R40", "P_AURORA"),
        )

        resposta = _rota(monkeypatch, AURORA, banco)

        assert resposta.trilho == []
        assert _atas(resposta) == [("ata_a_assinar", "R40", "sem_prazo")]
        assert [(a.fonte, a.mensagem) for a in resposta.avisos] == [
            ("trilho", "Não foi possível carregar as próximas Reuniões agora. Tente de novo em instantes.")
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDeConhecimento:
    def test_o_produto_reunioes_explica_atas_e_trilho_no_inicio(self):
        caminho = Path(fonte_reunioes.__file__).parents[2] / "conhecimento" / "reunioes.md"
        texto = " ".join(caminho.read_text(encoding="utf-8").split())

        assert "a ata que falta assinar aparece no Início de cada signatário" in texto
        assert "sai da lista assim que a pessoa assina ou dá o" in texto
        assert "só para o facilitador" in texto
        assert "a partir do quarto dia, como prazo vencido" in texto
        assert "sem prazo" in texto
        assert "as próximas reuniões da pessoa, como facilitador ou participante" in texto
        assert "a reunião cancelada não aparece" in texto
        assert "Atas a assinar, casos da Ouvidoria" not in texto
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto
