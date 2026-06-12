"""Testes do serviço de Resolução de responsável (issue #77, ADR 0008).

Módulo profundo com duas portas: `montar_candidatos` (roster da Reunião
anotado + cadastro de participantes ativos, com cargo/setor) e
`resolver_quadro` (anota em cada item do Quadro de Atribuições o
`responsavel_id` + nome/cargo canônicos do cadastro). Esconde a cascata de
matching do Pipeline, o threshold de auto-match, a prioridade roster →
cadastro e a revalidação de ids. Determinístico e idempotente; nome ambíguo
ou não encontrado fica **sem vínculo**, com o nome livre preservado.

Nenhum endpoint usa o serviço nesta fatia — os consumidores (chat ao vivo e
conclusão da Ata Guiada) chegam nas fatias seguintes. Sem LLM, sem rede;
mock Supabase fluente espelhado de `test_extracao_pendencias_nota.py`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import resolucao_service as resolucao  # noqa: E402

# ─── Mock Supabase (só as duas tabelas que o serviço consulta) ───────────────


@dataclass
class _Result:
    data: Any
    count: int | None = None


class _TableQuery:
    """Mock fluente mínimo: select + eq, espelhado dos testes análogos."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._filters: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        return _Result(data=[dict(r) for r in matched])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reuniao_participantes":
            return _TableQuery(self.reuniao_participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


# ─── Fixtures de domínio ─────────────────────────────────────────────────────


def _colaborador(pid: str, nome: str, cargo: str | None = None, setor: str | None = None, ativo: bool = True) -> dict:
    return {"id": pid, "nome_completo": nome, "cargo": cargo, "setor": setor, "ativo": ativo}


def _no_roster(pid: str, id_reuniao: str = "r1") -> dict:
    return {"id_reuniao": id_reuniao, "participante_id": pid}


def _item(acao: str = "Revisar protocolo", responsavel: str | None = None, **extras) -> dict:
    return {"acao": acao, "responsavel": responsavel, "cargo": None, "prazo": None, "entregavel": None, **extras}


# ═══════════════════════════════════════════════════════════════════════════
# resolver_quadro: o vínculo nasce na Resolução (roster primeiro)
# ═══════════════════════════════════════════════════════════════════════════


class TestResolverQuadro:
    def test_nome_do_roster_casa_com_id_e_nome_cargo_canonicos(self):
        """Critério 1: nome presente no roster da Reunião volta com id e
        nome/cargo canônicos desse Participante — o roster vence o cadastro
        geral mesmo havendo homônimo fora da Reunião."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P5", "Lucas Mendes", cargo="Analista de RH", setor="RH"),  # homônimo fora do roster
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
            ],
            reuniao_participantes=[_no_roster("P2")],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        quadro = [_item("Comprar monitores", responsavel="Lucas")]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert len(resolvido) == 1
        item = resolvido[0]
        assert item["responsavel_id"] == "P2"
        assert item["responsavel"] == "Lucas Silva"
        assert item["cargo"] == "Coordenador de TI"
        assert item["acao"] == "Comprar monitores"

    def test_nome_fora_do_roster_mas_unico_no_cadastro_casa_via_fallback(self):
        """Critério 2: quem não estava na Reunião mas é único no cadastro
        ativo casa pelo fallback — com nome e cargo canônicos do cadastro."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
                _colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro", setor="Financeiro"),
            ],
            reuniao_participantes=[_no_roster("P2")],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Carlos")], candidatos)

        assert resolvido[0]["responsavel_id"] == "P7"
        assert resolvido[0]["responsavel"] == "Carlos Ferreira"
        assert resolvido[0]["cargo"] == "Coordenador Financeiro"

    def test_nome_com_dois_candidatos_plausiveis_fica_sem_vinculo(self):
        """Critério 3: dois "Lucas" plausíveis no cadastro → o item volta sem
        vínculo, com o nome livre preservado — desambiguar é conversa do
        agente com o Facilitador, nunca chute do matcher."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
                _colaborador("P5", "Lucas Mendes", cargo="Analista de RH", setor="RH"),
            ],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Lucas")], candidatos)

        assert resolvido[0]["responsavel_id"] is None
        assert resolvido[0]["responsavel"] == "Lucas"

    def test_nome_inexistente_fica_sem_vinculo_com_nome_preservado(self):
        """Critério 4: nome que não existe em lugar nenhum (alguém de fora)
        volta sem vínculo e com a grafia exata que veio da conversa — externo
        fica só como nome, sem cobrança."""
        sb = _SupabaseMock(
            participantes=[_colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI")],
            reuniao_participantes=[_no_roster("P2")],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Fernanda Externa", cargo="Consultora")], candidatos)

        assert resolvido[0]["responsavel_id"] is None
        assert resolvido[0]["responsavel"] == "Fernanda Externa"
        assert resolvido[0]["cargo"] == "Consultora"

    def test_variacao_de_grafia_com_candidato_unico_casa(self):
        """Critério 5: a transcrição de voz come letra — "Luca" por "Lucas".
        Com um único candidato plausível, casa; a variação pequena não pode
        mandar o vínculo pro espaço."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
                _colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro", setor="Financeiro"),
            ],
            reuniao_participantes=[_no_roster("P2")],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Luca")], candidatos)

        assert resolvido[0]["responsavel_id"] == "P2"
        assert resolvido[0]["responsavel"] == "Lucas Silva"

    def test_variacao_de_grafia_com_dois_candidatos_plausiveis_fica_sem_vinculo(self):
        """Critério 5 (borda): "Luca" com dois Lucas plausíveis é tão ambíguo
        quanto "Lucas" — sem vínculo, sem chute."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
                _colaborador("P5", "Lucas Mendes", cargo="Analista de RH", setor="RH"),
            ],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Luca")], candidatos)

        assert resolvido[0]["responsavel_id"] is None
        assert resolvido[0]["responsavel"] == "Luca"

    def test_nome_parecido_mas_distinto_nao_casa(self):
        """Regressão (code review do PR): "Mario" e "Maria" são pessoas
        diferentes — primeiro nome PARECIDO (ratio 0.800) não é variação de
        grafia, e vínculo na pessoa errada é pior que sem vínculo."""
        sb = _SupabaseMock(
            participantes=[_colaborador("P3", "Maria Santos", cargo="Gerente de Compras", setor="Suprimentos")],
        )
        candidatos = resolucao.montar_candidatos(sb, "r1")

        resolvido = resolucao.resolver_quadro([_item(responsavel="Mario")], candidatos)

        assert resolvido[0]["responsavel_id"] is None
        assert resolvido[0]["responsavel"] == "Mario"


class TestRevalidacaoEIdempotencia:
    CADASTRO = [
        _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
        _colaborador("P5", "Lucas Mendes", cargo="Analista de RH", setor="RH"),
        _colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro", setor="Financeiro"),
        _colaborador("P9", "Beatriz Gomes", cargo="Enfermeira Chefe", setor="Enfermagem", ativo=False),
    ]

    def _candidatos(self, roster_ids: list[str] = ()) -> list[dict]:
        sb = _SupabaseMock(
            participantes=[dict(c) for c in self.CADASTRO],
            reuniao_participantes=[_no_roster(pid) for pid in roster_ids],
        )
        return resolucao.montar_candidatos(sb, "r1")

    def test_id_valido_pre_existente_e_honrado_mesmo_com_nome_apelidado(self):
        """Critério 6: o vínculo viaja no quadro — id válido anotado num turno
        anterior vence o nome reescrito pela conversa ("Lu" não casa sozinho);
        nome e cargo voltam aos canônicos do cadastro."""
        candidatos = self._candidatos(roster_ids=["P5"])

        quadro = [_item(responsavel="Lu", responsavel_id="P5")]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert resolvido[0]["responsavel_id"] == "P5"
        assert resolvido[0]["responsavel"] == "Lucas Mendes"
        assert resolvido[0]["cargo"] == "Analista de RH"

    def test_id_forjado_e_descartado_e_re_resolvido_pelo_nome(self):
        """Critério 6: id que não existe no cadastro (forjado/alucinado) é
        descartado — a Resolução recomeça do nome e casa no candidato real."""
        candidatos = self._candidatos()

        quadro = [_item(responsavel="Carlos Ferreira", responsavel_id="P999")]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert resolvido[0]["responsavel_id"] == "P7"
        assert resolvido[0]["responsavel"] == "Carlos Ferreira"

    def test_id_de_participante_inativo_e_descartado(self):
        """Critério 6: Participante desligado não recebe Pendência — id de
        inativo cai, e o nome (sem candidato ativo plausível) fica sem
        vínculo, preservado como texto."""
        candidatos = self._candidatos()

        quadro = [_item(responsavel="Beatriz Gomes", responsavel_id="P9")]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert resolvido[0]["responsavel_id"] is None
        assert resolvido[0]["responsavel"] == "Beatriz Gomes"

    def test_resolver_quadro_ja_resolvido_nao_muda_nada(self):
        """Critério 6: idempotência — resolver de novo um quadro já resolvido
        (vínculo feito, ambíguo sem vínculo e externo) devolve exatamente o
        mesmo quadro, sem rematch surpresa."""
        candidatos = self._candidatos(roster_ids=["P2"])

        quadro = [
            _item("Comprar monitores", responsavel="Lucas"),  # casa no roster
            _item("Escalar plantão", responsavel="Lucas", cargo=None),  # segue casado (roster vence)
            _item("Treinar equipe", responsavel="Fernanda Externa"),  # sem vínculo
            _item("Definir pauta", responsavel=None),  # sem responsável
        ]
        primeira = resolucao.resolver_quadro(quadro, candidatos)
        segunda = resolucao.resolver_quadro(primeira, candidatos)

        assert segunda == primeira

    def test_cargo_anotado_e_o_canonico_do_cadastro_nao_o_da_conversa(self):
        """Critério 7: o cargo ouvido na conversa ("o Lucas do RH") serve de
        contexto para desambiguar dois Lucas, mas o que fica anotado é o cargo
        canônico do cadastro — cargo falado é pista, não dado."""
        candidatos = self._candidatos()

        quadro = [_item(responsavel="Lucas", cargo="RH")]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert resolvido[0]["responsavel_id"] == "P5"
        assert resolvido[0]["responsavel"] == "Lucas Mendes"
        assert resolvido[0]["cargo"] == "Analista de RH"


class TestBordas:
    def test_responsavel_vazio_ou_null_like_nao_roda_matching(self):
        """Ação ainda sem responsável (None, vazio ou a string "null" que o
        LLM escorrega) atravessa a Resolução intacta, sem vínculo."""
        sb = _SupabaseMock(participantes=[_colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro")])
        candidatos = resolucao.montar_candidatos(sb, "r1")

        quadro = [
            _item("Definir pauta", responsavel=None),
            _item("Agendar revisão", responsavel="   "),
            _item("Comprar insumos", responsavel="null", cargo="Comprador"),
        ]
        resolvido = resolucao.resolver_quadro(quadro, candidatos)

        assert [i["responsavel_id"] for i in resolvido] == [None, None, None]
        assert resolvido[2]["responsavel"] == "null"
        assert resolvido[2]["cargo"] == "Comprador"

    def test_quadro_vazio_ou_ausente_devolve_lista_vazia(self):
        resolvido_vazio = resolucao.resolver_quadro([], [])
        resolvido_none = resolucao.resolver_quadro(None, [])
        assert resolvido_vazio == []
        assert resolvido_none == []

    def test_entrada_nao_e_mutada_e_demais_campos_atravessam_intactos(self):
        """`resolver_quadro` é puro: o quadro de entrada segue sem
        `responsavel_id` e prazo/entregável/ação chegam intactos do outro
        lado — o rascunho é do chamador, a cópia é do serviço."""
        sb = _SupabaseMock(participantes=[_colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro")])
        candidatos = resolucao.montar_candidatos(sb, "r1")

        original = _item("Fechar orçamento", responsavel="Carlos", prazo="2026-06-19", entregavel="Planilha")
        resolvido = resolucao.resolver_quadro([original], candidatos)

        assert "responsavel_id" not in original
        assert original["responsavel"] == "Carlos"
        assert resolvido[0]["prazo"] == "2026-06-19"
        assert resolvido[0]["entregavel"] == "Planilha"
        assert resolvido[0]["acao"] == "Fechar orçamento"


class TestMontarCandidatos:
    def test_roster_anotado_na_frente_e_inativo_fora(self):
        """Os candidatos saem com `na_reuniao` marcando o roster (roster na
        frente da lista), cargo/setor presentes, e inativo não entra — nem
        quando ainda vinculado à Reunião."""
        sb = _SupabaseMock(
            participantes=[
                _colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI"),
                _colaborador("P7", "Carlos Ferreira", cargo="Coordenador Financeiro", setor="Financeiro"),
                _colaborador("P9", "Beatriz Gomes", cargo="Enfermeira Chefe", setor="Enfermagem", ativo=False),
            ],
            reuniao_participantes=[_no_roster("P7"), _no_roster("P9")],
        )

        candidatos = resolucao.montar_candidatos(sb, "r1")

        assert [c["id"] for c in candidatos] == ["P7", "P2"]
        assert candidatos[0] == {
            "id": "P7",
            "nome_completo": "Carlos Ferreira",
            "cargo": "Coordenador Financeiro",
            "setor": "Financeiro",
            "na_reuniao": True,
        }
        assert candidatos[1]["na_reuniao"] is False

    def test_roster_de_outra_reuniao_nao_vaza(self):
        """A anotação `na_reuniao` respeita a Reunião pedida — vínculo de
        outra Reunião não marca ninguém."""
        sb = _SupabaseMock(
            participantes=[_colaborador("P2", "Lucas Silva", cargo="Coordenador de TI", setor="TI")],
            reuniao_participantes=[_no_roster("P2", id_reuniao="r2")],
        )

        candidatos = resolucao.montar_candidatos(sb, "r1")

        assert [c["na_reuniao"] for c in candidatos] == [False]
