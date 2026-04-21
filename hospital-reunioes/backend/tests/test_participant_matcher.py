"""
Testes unitários para participant_matcher.match_participants.

Cobre a cascata de estratégias:
- exato
- invertido ("Sobrenome, Nome")
- primeiro nome único
- primeiro nome + cargo/setor (desambiguação)
- fuzzy (threshold)
- não reconhecido
- regressão: pré-vinculados + prefixos honoríficos
"""
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.participant_matcher import (
    DEFAULT_AUTO_THRESHOLD,
    MatchResult,
    match_participants,
    match_single_name,
    match_single_name_scored,
)


@dataclass
class _Result:
    data: list


class _Query:
    """Mock do chain fluente do supabase-py: table().select().eq().execute()."""

    def __init__(self, rows):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        filtered = self._rows
        for col, value in self._filters.items():
            filtered = [r for r in filtered if r.get(col) == value]
        return _Result(data=filtered)

    def upsert(self, row, on_conflict=None):  # noqa: ARG002
        return _UpsertExec(self._rows, row)


class _UpsertExec:
    def __init__(self, rows, row):
        self._rows = rows
        self._row = row

    def execute(self):
        self._rows.append(self._row)
        return _Result(data=[self._row])


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)

    def table(self, name):
        if name == "participantes":
            return _Query(self.participantes)
        if name == "reuniao_participantes":
            return _Query(self.reuniao_participantes)
        raise AssertionError(f"Tabela inesperada: {name}")


def _mk_participante(pid, nome, cargo="", setor=None, ativo=True):
    return {
        "id": pid,
        "nome_completo": nome,
        "cargo": cargo,
        "setor": setor,
        "ativo": ativo,
    }


class TestExactMatch:
    def test_nome_identico(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P001", "Caroline Soares", "Diretora")])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Caroline Soares", "cargo": "Diretora"}
        ])
        assert matched == ["P001"]
        assert nao_reco == []

    def test_com_prefixo_honorifico(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P002", "Ricardo Mendes", "Médico")])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Dr. Ricardo Mendes", "cargo": "Médico"}
        ])
        assert matched == ["P002"]
        assert nao_reco == []


class TestPrimeiroNomeUnico:
    def test_bate_quando_so_existe_um(self):
        sb = _SupabaseMock(participantes=[
            _mk_participante("P010", "Caroline Soares Lima", "Diretora", "Diretoria"),
            _mk_participante("P011", "Joao Silva", "Tecnico", "TI"),
        ])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Caroline", "cargo": "Diretora"}
        ])
        assert matched == ["P010"]
        assert nao_reco == []


class TestDesambiguacaoPorCargoSetor:
    def test_dois_fernandos_desambigua_por_cargo(self):
        sb = _SupabaseMock(participantes=[
            _mk_participante("P020", "Fernando Bastos", "Gerente de Manutenção", "Manutenção"),
            _mk_participante("P021", "Fernando Costa", "Técnico de Enfermagem", "Enfermagem"),
        ])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Fernando", "cargo": "Gerente", "setor": None}
        ])
        assert matched == ["P020"]
        assert nao_reco == []

    def test_dois_fernandos_desambigua_por_setor(self):
        sb = _SupabaseMock(participantes=[
            _mk_participante("P030", "Fernando Bastos", "Gerente", "Manutenção"),
            _mk_participante("P031", "Fernando Costa", "Gerente", "Enfermagem"),
        ])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Fernando", "cargo": "Gerente", "setor": "Manutenção"}
        ])
        assert matched == ["P030"]
        assert nao_reco == []

    def test_multiplos_sem_contexto_vai_para_nao_reconhecido(self):
        sb = _SupabaseMock(participantes=[
            _mk_participante("P040", "Fernando Bastos", "Gerente", "Manutenção"),
            _mk_participante("P041", "Fernando Costa", "Tecnico", "Enfermagem"),
        ])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Fernando", "cargo": "", "setor": None}
        ])
        assert matched == []
        assert len(nao_reco) == 1
        assert nao_reco[0]["nome"] == "Fernando"


class TestInvertido:
    def test_sobrenome_virgula_nome(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P050", "Caroline Soares")])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Soares, Caroline"}
        ])
        assert matched == ["P050"]
        assert nao_reco == []


class TestFuzzy:
    def test_grafia_proxima(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P060", "Caroline Soares")])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Carolina Soares"}  # typo: Carolina vs Caroline
        ])
        assert matched == ["P060"]
        assert nao_reco == []


class TestNaoReconhecido:
    def test_desconhecido(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P070", "Caroline Soares")])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Rafael", "cargo": "Sustentador"}
        ])
        assert matched == []
        assert len(nao_reco) == 1
        assert nao_reco[0]["nome"] == "Rafael"
        assert nao_reco[0]["cargo"] == "Sustentador"


class TestCenarioTranscricaoReal:
    """Reproduz o cenário da transcrição real que quebrou em produção."""

    def test_caroline_e_fernando_batem_rafael_pedro_nao(self):
        sb = _SupabaseMock(participantes=[
            _mk_participante("P100", "Caroline Soares", "Diretora", "Diretoria"),
            _mk_participante("P101", "Fernando Bastos", "Gerente de Manutenção", "Manutenção"),
            _mk_participante("P102", "Outro Colaborador", "Tecnico", "TI"),
        ])
        extraidos = [
            {"nome": "Caroline", "cargo": "Diretora de investidura"},
            {"nome": "Fernando", "cargo": "Gerente de manutenção"},
            {"nome": "Rafael", "cargo": "Sustentador administrativo"},
            {"nome": "Pedro Augusto", "cargo": "Técnico em segurança do trabalho"},
        ]
        matched, nao_reco = match_participants(sb, "R1", extraidos)
        assert set(matched) == {"P100", "P101"}
        nomes_nao_reco = sorted(n["nome"] for n in nao_reco)
        assert nomes_nao_reco == ["Pedro Augusto", "Rafael"]

    def test_nome_composto_nao_colapsa_para_primeiro_nome(self):
        """
        Regressão: 'Pedro Augusto' NÃO deve bater em 'Pedro Rezende'
        só porque Pedro é único no banco. Nome extraído com múltiplos
        tokens é um nome distinto.
        """
        sb = _SupabaseMock(participantes=[
            _mk_participante("P200", "Pedro Rezende", "Diretor", "Diretoria"),
        ])
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Pedro Augusto", "cargo": "Técnico de segurança"},
        ])
        assert matched == []
        assert len(nao_reco) == 1
        assert nao_reco[0]["nome"] == "Pedro Augusto"


class TestMatchSingleName:
    """Cascata aplicada a um nome avulso — usada na resolução de responsável
    de ações durante a importação de ATA migrada."""

    def test_prefixo_unico_resolve_nome_abreviado(self):
        rows = [
            _mk_participante("G1", "Gisele Nunes de Vasconcellos", "Enfermeira", "UTI"),
            _mk_participante("P1", "Pedro Rezende", "Dev", "TI"),
        ]
        assert match_single_name("Gisele Nunes", rows) == "G1"

    def test_ambiguidade_retorna_none(self):
        rows = [
            _mk_participante("G1", "Gisele Nunes de Vasconcellos", "Enfermeira", "UTI"),
            _mk_participante("G2", "Gisele Nunes Silva", "Medica", "CC"),
        ]
        assert match_single_name("Gisele Nunes", rows) is None

    def test_exato(self):
        rows = [_mk_participante("P1", "Pedro Rezende", "Dev", "TI")]
        assert match_single_name("Pedro Rezende", rows) == "P1"

    def test_primeiro_nome_unico(self):
        rows = [_mk_participante("P1", "Pedro Rezende", "Dev", "TI")]
        assert match_single_name("Pedro", rows) == "P1"

    def test_sem_rows_ou_nome_vazio(self):
        rows = [_mk_participante("P1", "Pedro Rezende")]
        assert match_single_name("", rows) is None
        assert match_single_name("Qualquer", []) is None

    def test_sem_match(self):
        rows = [_mk_participante("P1", "Pedro Rezende")]
        assert match_single_name("Maria Silva", rows) is None


class TestPreVinculados:
    def test_nao_duplica_upsert_para_pre_vinculado(self):
        sb = _SupabaseMock(
            participantes=[_mk_participante("P200", "Caroline Soares", "Diretora")],
            reuniao_participantes=[{"id_reuniao": "R1", "participante_id": "P200"}],
        )
        matched, nao_reco = match_participants(sb, "R1", [
            {"nome": "Caroline Soares"}
        ])
        # Pré-vinculado já conta como vinculado final
        assert matched == ["P200"]
        assert nao_reco == []


class TestMatchResultScore:
    """Cascata com score — estratégias retornam score correto."""

    def test_exato_100(self):
        rows = [_mk_participante("P1", "Caroline Soares")]
        r = match_single_name_scored("Caroline Soares", rows)
        assert r.participante_id == "P1"
        assert r.score == 100
        assert r.strategy == "exato"

    def test_exato_com_prefixo_honorifico_100(self):
        rows = [_mk_participante("P1", "Ricardo Mendes")]
        r = match_single_name_scored("Dr. Ricardo Mendes", rows)
        assert r.participante_id == "P1"
        assert r.score == 100

    def test_invertido_100(self):
        rows = [_mk_participante("P1", "Caroline Soares")]
        r = match_single_name_scored("Soares, Caroline", rows)
        assert r.participante_id == "P1"
        assert r.score == 100
        assert r.strategy == "invertido"

    def test_prefixo_unico_95(self):
        rows = [
            _mk_participante("G1", "Gisele Nunes de Vasconcellos", "Enfermeira"),
            _mk_participante("P1", "Pedro Rezende"),
        ]
        r = match_single_name_scored("Gisele Nunes", rows)
        assert r.participante_id == "G1"
        assert r.score == 95
        assert r.strategy == "prefixo_unico"

    def test_primeiro_nome_unico_90(self):
        rows = [_mk_participante("P1", "Pedro Rezende")]
        r = match_single_name_scored("Pedro", rows)
        assert r.participante_id == "P1"
        assert r.score == 90
        assert r.strategy == "primeiro_nome"

    def test_primeiro_nome_desambig_cargo_setor_85(self):
        rows = [
            _mk_participante("F1", "Fernando Bastos", "Gerente", "Manutenção"),
            _mk_participante("F2", "Fernando Costa", "Técnico", "Enfermagem"),
        ]
        r = match_single_name_scored(
            "Fernando", rows, cargo_ia="Gerente", setor_ia="Manutenção"
        )
        assert r.participante_id == "F1"
        assert r.score == 85
        assert r.strategy == "primeiro_nome+cargo+setor"

    def test_primeiro_nome_desambig_so_cargo_82(self):
        rows = [
            _mk_participante("F1", "Fernando Bastos", "Gerente"),
            _mk_participante("F2", "Fernando Costa", "Técnico"),
        ]
        r = match_single_name_scored("Fernando", rows, cargo_ia="Gerente")
        assert r.participante_id == "F1"
        # Score acima do threshold de auto-match (80) — preserva comportamento legado.
        assert r.score == 82
        assert r.score >= DEFAULT_AUTO_THRESHOLD

    def test_primeiro_nome_desambig_so_setor_80(self):
        rows = [
            _mk_participante("F1", "Fernando Bastos", "Gerente", "Manutenção"),
            _mk_participante("F2", "Fernando Costa", "Gerente", "Enfermagem"),
        ]
        r = match_single_name_scored("Fernando", rows, setor_ia="Manutenção")
        assert r.participante_id == "F1"
        assert r.score == 80
        assert r.score >= DEFAULT_AUTO_THRESHOLD


class TestNomeSobrenomePair:
    """Nova estratégia 5: par primeiro+último bate em nome com tokens internos."""

    def test_basico_maria_silva_casa_maria_fernanda_silva_souza(self):
        rows = [
            _mk_participante("M1", "Maria Fernanda Silva Souza", "Analista"),
            _mk_participante("J1", "João Pedro Silva"),
        ]
        r = match_single_name_scored("Maria Silva", rows)
        assert r.participante_id == "M1"
        assert r.score == 85
        assert r.strategy == "nome_sobrenome_pair"

    def test_ambiguo_duas_marias_silva(self):
        rows = [
            _mk_participante("M1", "Maria Fernanda Silva Souza"),
            _mk_participante("M2", "Maria Clara Silva Pereira"),
        ]
        r = match_single_name_scored("Maria Silva", rows)
        assert r.participante_id is None
        assert r.score == 0
        assert set(r.candidates_ambiguos) == {"M1", "M2"}

    def test_nao_colapsa_quando_sobrenome_nao_bate(self):
        """Regressão: 'Pedro Augusto' NÃO bate em 'Pedro Rezende'."""
        rows = [_mk_participante("P1", "Pedro Rezende", "Diretor")]
        r = match_single_name_scored("Pedro Augusto", rows)
        # Nem primeiro-nome (tokens!=1) nem sobrenome bate.
        # Fuzzy fica abaixo de 80 — resolucao externo pelo caller.
        assert r.score < DEFAULT_AUTO_THRESHOLD


class TestFuzzyThresholdNovo:
    """Fuzzy agora retorna score entre 60 e 100 (antes só >= 85)."""

    def test_fuzzy_alto_passa_threshold(self):
        # "Carolina Soares" vs "Caroline Soares" — ratio alto, deve casar
        rows = [_mk_participante("P1", "Caroline Soares")]
        r = match_single_name_scored("Carolina Soares", rows)
        assert r.participante_id == "P1"
        assert r.score >= DEFAULT_AUTO_THRESHOLD
        assert r.strategy == "fuzzy"

    def test_fuzzy_medio_retorna_sugestao(self):
        # Grafia distante mas acima de 60% — deve devolver id com score baixo
        rows = [_mk_participante("P1", "Anabela Rodrigues")]
        r = match_single_name_scored("Anabel Rodrigez", rows)
        assert r.participante_id == "P1"
        assert 60 <= r.score < 100

    def test_fuzzy_baixo_retorna_nenhum(self):
        # Nomes completamente diferentes — abaixo de 0.60
        rows = [_mk_participante("P1", "Caroline Soares")]
        r = match_single_name_scored("Joao Silva", rows)
        assert r.participante_id is None
        assert r.strategy == "nenhum"


class TestRetrocompatMatchSingleName:
    """API antiga (sem score) continua devolvendo o id quando score >= 80."""

    def test_retorna_id_quando_score_alto(self):
        rows = [_mk_participante("P1", "Pedro Rezende")]
        assert match_single_name("Pedro", rows) == "P1"

    def test_retorna_none_quando_score_baixo(self):
        # match fuzzy com score < 80 deve dar None na API legada
        rows = [_mk_participante("P1", "Anabela Rodrigues")]
        result = match_single_name("Anabel Rodrigez", rows)
        scored = match_single_name_scored("Anabel Rodrigez", rows)
        if scored.score < DEFAULT_AUTO_THRESHOLD:
            assert result is None
        else:
            assert result == "P1"

    def test_threshold_custom(self):
        """Quem chamar explicitamente com threshold menor aceita sugestão."""
        rows = [_mk_participante("P1", "Anabela Rodrigues")]
        scored = match_single_name_scored("Anabel Rodrigez", rows)
        # Força threshold baixo e espera o id
        if scored.participante_id:
            assert (
                match_single_name("Anabel Rodrigez", rows, auto_threshold=scored.score)
                == scored.participante_id
            )


class TestMatchParticipantsSemVinculo:
    """match_participants com link_on_match=False só devolve ids, não toca DB."""

    def test_preview_stateless_sem_upsert(self):
        sb = _SupabaseMock(participantes=[_mk_participante("P001", "Caroline Soares")])
        matched, nao_reco = match_participants(
            sb,
            "__preview__",
            [{"nome": "Caroline Soares"}],
            link_on_match=False,
        )
        assert matched == ["P001"]
        assert nao_reco == []
        # Nada foi inserido em reuniao_participantes
        assert sb.reuniao_participantes == []
