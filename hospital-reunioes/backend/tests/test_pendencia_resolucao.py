"""Testes da issue #192: nascimento da Pendência usa a Resolução (ADR 0008).

O responsável de item SEM vínculo era resolvido por `ilike '%nome%' limit 1`
(substring, sem filtro de ativo, sem roster, sem tratamento de ambiguidade).
Com o fix, `liberar_pendencias` resolve pela semântica canônica da Resolução:

- Nome sem casamento exato/canônico nasce externo (sem vínculo, sem cobrança).
- Colaborador inativo nunca recebe vínculo.
- Roster da Reunião tem prioridade sobre o cadastro geral.
- `responsavel_id` pré-existente (Ata Guiada, validação) segue honrado.

Padrão de mock copiado de `test_vinculo_responsavel.py`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pendencia_service import liberar_pendencias  # noqa: E402

# ─── Mock Supabase ───────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: Any


class _TableQuery:
    """Mock fluente: select/insert + eq/ilike/order/limit."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._ilike: tuple[str, str] | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def ilike(self, col, pattern):
        self._ilike = (col, pattern)
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, r: dict) -> bool:
        for col, value in self._filters:
            if r.get(col) != value:
                return False
        if self._ilike is not None:
            col, pattern = self._ilike
            needle = pattern.strip("%").lower()
            if needle not in str(r.get(col) or "").lower():
                return False
        return True

    def execute(self):
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for it in items:
                self._rows.append(dict(it))
            return _Result(data=[dict(it) for it in items])

        matched = [r for r in self._rows if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            matched.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reuniao_participantes":
            return _TableQuery(self.reuniao_participantes)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        if name == "pendencias":
            return _TableQuery(self.pendencias)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Fixtures de domínio ─────────────────────────────────────────────────────


def _participante(pid: str, nome: str, cargo: str, ativo: bool = True) -> dict:
    return {"id": pid, "nome_completo": nome, "cargo": cargo, "setor": None, "ativo": ativo}


def _reuniao(quadro: list[dict]) -> dict:
    return {"id_reuniao": "R1", "status_ata": "ASSINADA", "json_ata": {"quadro_atribuicoes": quadro}}


def _no_roster(pid: str) -> dict:
    return {"id_reuniao": "R1", "participante_id": pid}


# ═══════════════════════════════════════════════════════════════════════════
# Critérios de aceite da issue #192
# ═══════════════════════════════════════════════════════════════════════════


class TestNascimentoUsaResolucao:
    def test_homonimo_por_substring_nao_vincula(self):
        """Regressão do homônimo: "Ana" citada com "Mariana" no cadastro NÃO
        vincula: o ilike por substring casava "%Ana%" com "Mariana Souza" e a
        cobrança ia pra pessoa errada."""
        sb = _SupabaseMock(
            participantes=[_participante("P_MARI", "Mariana Souza", "Enfermeira")],
            reunioes=[_reuniao([{"acao": "Revisar protocolo", "responsavel": "Ana", "prazo": None}])],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] is None
        assert sb.pendencias[0]["responsavel_nome"] == "Ana"

    def test_inativo_citado_nao_recebe_vinculo(self):
        """Colaborador desligado citado pelo nome exato não recebe vínculo (nem
        a cobrança por email que vem com ele): a Pendência nasce externa."""
        sb = _SupabaseMock(
            participantes=[_participante("P_ANA", "Ana Lima", "Coordenadora", ativo=False)],
            reunioes=[_reuniao([{"acao": "Revisar protocolo", "responsavel": "Ana Lima", "prazo": None}])],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] is None
        assert sb.pendencias[0]["responsavel_nome"] == "Ana Lima"

    def test_vinculo_pre_existente_de_inativo_e_descartado(self):
        """Vínculo gravado apontando pra Colaborador inativo é descartado: a
        Pendência não pode cobrar quem já saiu do hospital."""
        sb = _SupabaseMock(
            participantes=[_participante("P_ANA", "Ana Lima", "Coordenadora", ativo=False)],
            reunioes=[
                _reuniao(
                    [{"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": None}]
                )
            ],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] is None

    def test_roster_da_reuniao_vence_o_cadastro_geral(self):
        """ "Ana" citada casa com a Ana que ESTAVA na Reunião, mesmo com homônima
        no cadastro geral aparecendo antes (o ilike limit 1 pegava a primeira)."""
        sb = _SupabaseMock(
            participantes=[
                _participante("P_FORA", "Ana Souza", "Farmacêutica"),
                _participante("P_ROSTER", "Ana Lima", "Coordenadora"),
            ],
            reuniao_participantes=[_no_roster("P_ROSTER")],
            reunioes=[_reuniao([{"acao": "Revisar protocolo", "responsavel": "Ana", "prazo": None}])],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] == "P_ROSTER"
        assert sb.pendencias[0]["responsavel_nome"] == "Ana Lima"
        assert sb.pendencias[0]["cargo"] == "Coordenadora"

    def test_vinculo_pre_existente_continua_honrado(self):
        """Item que chega com `responsavel_id` gravado (Ata Guiada, validação)
        continua vinculado à mesma pessoa, sem rematch por nome."""
        sb = _SupabaseMock(
            participantes=[
                _participante("P1", "Lucas Silva", "Analista de TI"),
                _participante("P9", "Lucas Mendes", "Coordenador de RH"),
            ],
            reunioes=[
                _reuniao([{"acao": "Mapear escalas", "responsavel": "Lucas", "responsavel_id": "P9", "prazo": None}])
            ],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] == "P9"
        assert sb.pendencias[0]["responsavel_nome"] == "Lucas Mendes"
        assert sb.pendencias[0]["cargo"] == "Coordenador de RH"

    def test_sem_casamento_vira_pendencia_externa(self):
        """Nome que não casa com ninguém do cadastro vira Pendência externa:
        aparece no painel só com o nome, sem vínculo."""
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "Diretor")],
            reunioes=[_reuniao([{"acao": "Auditoria externa", "responsavel": "Dr. Visitante", "prazo": None}])],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] is None
        assert sb.pendencias[0]["responsavel_nome"] == "Dr. Visitante"

    def test_nome_ambiguo_no_cadastro_fica_sem_vinculo(self):
        """Duas Anas ativas no cadastro e nenhuma no roster: ambiguidade fica
        sem vínculo, pois vínculo errado é pior que sem vínculo (ADR 0008)."""
        sb = _SupabaseMock(
            participantes=[
                _participante("P_A", "Ana Souza", "Farmacêutica"),
                _participante("P_B", "Ana Lima", "Coordenadora"),
            ],
            reunioes=[_reuniao([{"acao": "Revisar protocolo", "responsavel": "Ana", "prazo": None}])],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] is None
        assert sb.pendencias[0]["responsavel_nome"] == "Ana"

    def test_nome_que_casa_vincula_com_nome_e_cargo_canonicos(self):
        """Casamento canônico único: a Pendência nasce com o nome completo e o
        cargo do cadastro, não com o texto que o LLM colocou no quadro."""
        sb = _SupabaseMock(
            participantes=[_participante("P1", "Pedro Rezende", "Diretor")],
            reunioes=[
                _reuniao([{"acao": "Comprar insumos", "responsavel": "Pedro", "cargo": "Estagiário", "prazo": None}])
            ],
        )

        total = liberar_pendencias(sb, "R1")

        assert total == 1
        assert sb.pendencias[0]["responsavel_id"] == "P1"
        assert sb.pendencias[0]["responsavel_nome"] == "Pedro Rezende"
        assert sb.pendencias[0]["cargo"] == "Diretor"
