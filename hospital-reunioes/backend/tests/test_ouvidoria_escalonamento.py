"""Escada de escalonamento e crítico imediato (issue #336, PRD #318, ADR 0034 decisão 12).

A cobrança sobe sozinha quando ninguém responde: véspera avisa o titular; no
vencimento, titular e substituto (degrau já entregue na issue #327); 24h úteis
depois, o gestor da área; 48h úteis depois, a Diretoria Executiva. Caso crítico
validado avisa a Diretoria na hora, sem esperar prazo nenhum.

Cobre os critérios de aceite pelo seam do service (a função que o scheduler
chama) e pelo seam HTTP da validação (o crítico imediato), mais o registro do
job no scheduler e a migration. O Resend nunca é chamado de verdade: o envio é
mockado no ponto único por onde todo email do app passa.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_escalonamento, ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

SEM_FERIADOS: frozenset[dt.date] = frozenset()

# O caso de referência tem a forma REAL de produção. A tabela de prazos
# seedada na 065 dá `area_resposta` em dias úteis para `alto` (2) e `medio` (4),
# e prazo em dias úteis vence sempre no FECHAMENTO, às 17h de Brasília. Testar
# com vencimento no meio da tarde esconderia a janela comercial, que é
# justamente o que decide o momento de cada degrau.
#
# Caso validado na quinta 20/08/2026 às 11h de Brasília, prazo vencendo na
# terça 25/08 às 17h. Os gatilhos do motor (issue #331) caem, então, todos no
# fechamento, e a janela comercial empurra cada email para a abertura seguinte:
#   véspera    = segunda 24/08, 17h  ->  entregue terça  25/08, 08h
#   vencimento = terça   25/08, 17h  (degrau da issue #327)
#   +24h       = quarta  26/08, 17h  ->  entregue quinta 27/08, 08h
#   +48h       = quinta  27/08, 17h  ->  entregue sexta  28/08, 08h
VALIDADA_EM = "2026-08-20T14:00:00+00:00"
VENCIMENTO = "2026-08-25T20:00:00+00:00"

ANTES_DA_VESPERA = dt.datetime(2026, 8, 24, 19, 0, tzinfo=dt.UTC)  # segunda, 16h de Brasília
NA_VESPERA = dt.datetime(2026, 8, 24, 20, 0, tzinfo=dt.UTC)  # segunda, 17h
NO_MAIS_24H = dt.datetime(2026, 8, 26, 20, 0, tzinfo=dt.UTC)  # quarta, 17h
NO_MAIS_48H = dt.datetime(2026, 8, 27, 20, 0, tzinfo=dt.UTC)  # quinta, 17h

# As aberturas de expediente em que cada degrau retido pela janela sai.
ABERTURA_DE_TERCA = dt.datetime(2026, 8, 25, 11, 0, tzinfo=dt.UTC)  # terça, 8h de Brasília
ABERTURA_DE_QUINTA = dt.datetime(2026, 8, 27, 11, 0, tzinfo=dt.UTC)  # quinta, 8h
ABERTURA_DE_SEXTA = dt.datetime(2026, 8, 28, 11, 0, tzinfo=dt.UTC)  # sexta, 8h

FORA_DO_EXPEDIENTE = dt.datetime(2026, 8, 26, 1, 30, tzinfo=dt.UTC)  # 22h30 de terça em Brasília


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção). Todo teste
    deste arquivo passa pelo mock, mesmo os que não olham o email."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
            }
        )
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "status": "aguardando_area",
        "categoria": "Demora no atendimento",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "extrato_para_o_setor": "Espera acima de duas horas na recepcao. Apurar e responder a Ouvidoria.",
        "manifestante_nome": "Joana da Silva",
        "anonimo": False,
        "tipo_manifestacao": None,
        "sigilo_reforcado": False,
        "gravidade": "medio",
        "prazo_area_em": VENCIMENTO,
        "prazo_rompido_em": None,
        "vespera_avisada_em": None,
        "escalonado_gestor_em": None,
        "escalonado_diretoria_em": None,
        # Carimbo do caso que não tem a quem escalonar (issue #373, migration 078).
        "escalonamento_impossivel_em": None,
        "critico_avisado_em": None,
        "validada_em": VALIDADA_EM,
        "validada_por": "P10",
    }
    row.update(overrides)
    return row


def _responsavel(papel: str = "titular", **overrides) -> dict:
    row = {
        "id": f"resp-{papel}",
        "setor": "Recepcao",
        "papel": papel,
        "nome": f"Carlos {papel.capitalize()}",
        "email": f"{papel}@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    row.update(overrides)
    return row


def _diretor(numero: int = 1) -> dict:
    return {
        "id": f"D{numero:02d}",
        "nome_completo": f"Diretor {numero}",
        "email": f"diretoria{numero}@hsm.br",
        "perfil_ouvidoria": "diretoria_executiva",
    }


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, o update filtra antes de gravar (inclusive IS NULL) e o insert
    devolve a linha com o id que o banco geraria."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._nulos: list[str] = []
        self._nao_nulos: list[str] = []
        self._negar_proximo = False
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    @property
    def not_(self):
        """Nega o próximo filtro, como no PostgREST (`q.not_.is_(col, "null")`)."""
        self._negar_proximo = True
        return self

    def is_(self, col, value):
        assert value in ("null", None)
        if self._negar_proximo:
            self._negar_proximo = False
            self._nao_nulos.append(col)
        else:
            self._nulos.append(col)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) is None for c in self._nulos)
            and all(r.get(c) is not None for c in self._nao_nulos)
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        if self._limite is not None:
            casadas = casadas[: self._limite]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _TabelaQueFalhaNoInsert(_TabelaFake):
    def execute(self):
        if self._insert is not None:
            raise RuntimeError("insert recusado (simulando CHECK antigo no banco)")
        return super().execute()


class _TabelaQueFalhaNoSelect(_TabelaFake):
    """Leitura que estoura, como um timeout do PostgREST. Existe para exercitar
    os `except` de verdade: monkeypatch da função que lê pula o bloco que a
    guarda protege, e a regressão passaria verde (issue #373).

    A falha é por COLUNA de filtro, não por tabela: `participantes` é lida por
    dois caminhos (a Diretoria Executiva e os super admins do alerta), e
    derrubar os dois provaria a guarda errada."""

    coluna_alvo: str | None = None

    def execute(self):
        if self._insert is None and self._update is None:
            if self.coluna_alvo is None or self.coluna_alvo in self._filters:
                raise RuntimeError("timeout na leitura (simulando PostgREST fora do ar)")
        return super().execute()


class _SupabaseFake:
    def __init__(
        self,
        manifestacoes: list[dict] | None = None,
        responsaveis: list[dict] | None = None,
        diretoria: list[dict] | None = None,
    ):
        self.falhar_inserts: set[str] = set()
        # {tabela: coluna_de_filtro ou None para falhar toda leitura da tabela}
        self.falhar_selects: dict[str, str | None] = {}
        participantes = [
            {
                "id": "P03",
                "nome_completo": "Pedro Admin",
                "email": "admin@hsm.br",
                # Quem recebe o alerta de cadastro incompleto (issue #373).
                "access_profile": "super_admin",
            }
        ]
        participantes.extend(diretoria if diretoria is not None else [_diretor(1)])
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_setor_responsaveis": (
                responsaveis
                if responsaveis is not None
                else [_responsavel("titular"), _responsavel("substituto"), _responsavel("gestor")]
            ),
            "participantes": participantes,
        }

    def table(self, nome: str):
        if nome in self.falhar_selects:
            tabela = _TabelaQueFalhaNoSelect(nome, self.tabelas.setdefault(nome, []))
            tabela.coluna_alvo = self.falhar_selects[nome]
            return tabela
        classe = _TabelaQueFalhaNoInsert if nome in self.falhar_inserts else _TabelaFake
        return classe(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, _nome, _args):
        return self

    def execute(self):  # pragma: no cover - só a validação usa a RPC
        return type("R", (), {"data": self.tabelas["ouvidoria_protocolos"][0]})()


DIRETORA = {
    "id": "D01",
    "nome_completo": "Diretor 1",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
}


def _client(monkeypatch, supabase: _SupabaseFake, agora: dt.datetime, participante: dict | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante if participante is not None else OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app)


def _emails_por_destinatario(enviados: list[dict]) -> set[str]:
    return {e["destinatario"] for e in enviados}


def _entregar_a_fila(supabase, quando: dt.datetime) -> int:
    """Roda o job de despacho, que é quem leva a notificação retida pela janela
    comercial quando o expediente abre. Com o prazo real (vencimento às 17h),
    todo degrau não crítico passa por aqui antes de virar email."""
    return ouvidoria_notificacoes.despachar_pendentes(supabase, quando, SEM_FERIADOS)


class TestVespera:
    """Degrau 1: a véspera do vencimento avisa só o titular."""

    def test_vespera_notifica_o_titular(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 1
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert [r["gatilho"] for r in registros] == [ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO]
        # O substituto e o gestor entram nos degraus seguintes, não neste.
        assert [r["destinatario_email"] for r in registros] == ["titular@hsm.br"]
        assert registros[0]["papel_destinatario"] == "titular"
        # O momento: o gatilho cai no fechamento, então o email espera a
        # abertura seguinte, e nada sai antes disso.
        assert _nunca_envia_email_de_verdade == []
        assert dt.datetime.fromisoformat(registros[0]["enviar_a_partir_de"]) == ABERTURA_DE_TERCA

        assert _entregar_a_fila(supabase, ABERTURA_DE_TERCA) == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"titular@hsm.br"}
        html = _nunca_envia_email_de_verdade[0]["html"]
        assert "2026-0007" in html
        assert "vence em" in html

    def test_assunto_da_vespera_nao_promete_o_dia_seguinte(self, _nunca_envia_email_de_verdade):
        """O lembrete da véspera CHEGA no dia do vencimento: o gatilho cai às
        17h e a janela comercial o segura até as 08h seguintes. Um assunto com
        "vence amanhã" mentiria sobre o dia. Quem diz quanto tempo sobra é a
        contagem regressiva do motor, no corpo."""
        supabase = _SupabaseFake()

        ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)
        _entregar_a_fila(supabase, ABERTURA_DE_TERCA)

        email = _nunca_envia_email_de_verdade[0]
        # A entrega acontece no próprio dia do vencimento.
        assert ABERTURA_DE_TERCA.date() == dt.datetime.fromisoformat(VENCIMENTO).date()
        for prometido in ("amanhã", "amanha"):
            assert prometido not in email["assunto"].lower()
            # O <title> sai do mesmo assunto: os dois não podem divergir.
            assert prometido not in email["html"].lower()

    def test_vespera_nao_dispara_antes_da_hora(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, ANTES_DA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vespera_avisada_em"] is None

    def test_prazo_curto_demais_nao_tem_vespera(self, _nunca_envia_email_de_verdade):
        """Caso validado depois do instante da véspera (prazo de horas, típico
        do crítico) não tem véspera a avisar: o motor devolve None e o degrau
        simplesmente não existe."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(validada_em="2026-08-25T13:00:00+00:00")],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert supabase.tabelas["ouvidoria_notificacoes"] == []

    def test_caso_ja_vencido_nao_recebe_o_lembrete_de_vespera(self, _nunca_envia_email_de_verdade):
        """O primeiro tick depois do deploy acha o histórico vencido inteiro
        sem carimbo nenhum. Lembrar do prazo que "está perto do fim" quem já
        estourou seria mentira: quem cobra o vencido é o degrau do vencimento
        (issue #327). A véspera caduca no vencimento."""
        supabase = _SupabaseFake()

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        registros = supabase.tabelas["ouvidoria_notificacoes"]
        gatilhos = {r["gatilho"] for r in registros}
        assert ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO not in gatilhos
        assert degraus == 1  # só o degrau do gestor
        assert [r["destinatario_email"] for r in registros] == ["gestor@hsm.br"]


class TestDegrauDoGestor:
    """Degrau 3: 24h úteis depois do vencimento, sem resposta, cobra o gestor."""

    def test_mais_24h_sem_resposta_notifica_o_gestor_da_area(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_GESTOR
        assert registro["papel_destinatario"] == "gestor"
        assert dt.datetime.fromisoformat(registro["enviar_a_partir_de"]) == ABERTURA_DE_QUINTA

        assert _entregar_a_fila(supabase, ABERTURA_DE_QUINTA) == 1
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"gestor@hsm.br"}

    def test_sem_gestor_cadastrado_o_degrau_alerta_a_diretoria(self, _nunca_envia_email_de_verdade):
        """Sem gestor no cadastro do setor, o degrau não some: vira o alerta à
        Diretoria (critério de aceite da issue #336)."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular"), _responsavel("substituto")],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        # Gatilho próprio desde a issue #373: o alerta de cadastro não pode ser
        # descartado pela guarda de retenção junto com o degrau real de 48h.
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ALERTA_CADASTRO_SETOR
        assert registro["papel_destinatario"] == "diretoria_executiva"
        # A Diretoria precisa saber POR QUE o caso chegou nela um dia antes.
        # Isso mora no CORPO do email desde a issue #373, e não no `detalhe`:
        # o gatilho ganhou montador próprio, cuja abertura já conta o motivo.
        assert not registro["detalhe"]

        _entregar_a_fila(supabase, ABERTURA_DE_QUINTA)
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"diretoria1@hsm.br"}
        corpo = _nunca_envia_email_de_verdade[0]["texto"]
        assert "gestor" in corpo.lower()
        # E diz uma vez só: a abertura já contava o motivo, e o `detalhe`
        # repetia a mesma frase logo abaixo.
        assert corpo.lower().count("nao tem gestor cadastrado") == 1
        # Os dois degraus que caem na Diretoria chegam com um dia útil de
        # intervalo: o assunto tem que distinguir um do outro na caixa de
        # entrada.
        assert "sem gestor cadastrado" in _nunca_envia_email_de_verdade[0]["assunto"].lower()

    def test_sem_gestor_e_sem_diretoria_o_caso_sai_da_varredura_e_volta_depois(self, _nunca_envia_email_de_verdade):
        """Nenhum destinatário não queima o degrau, mas desde a issue #373 tira
        o caso da varredura por carimbo próprio: voltar em toda rodada era o
        que entupia a janela de leitura do job. Limpo o carimbo, a escada sobe
        do degrau em que parou."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular")],
            diretoria=[],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 0
        assert supabase.tabelas["ouvidoria_notificacoes"] == []
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["escalonado_gestor_em"] is None
        assert caso["escalonamento_impossivel_em"] == NO_MAIS_24H.isoformat()

        supabase.tabelas["participantes"].append(_diretor(2))
        caso["escalonamento_impossivel_em"] = None
        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H + dt.timedelta(minutes=10), SEM_FERIADOS)
        assert degraus == 1
        assert [r["destinatario_email"] for r in supabase.tabelas["ouvidoria_notificacoes"]] == ["diretoria2@hsm.br"]


class TestDegrauDaDiretoria:
    """Degrau 4: 48h úteis depois do vencimento, a Diretoria Executiva."""

    def test_mais_48h_sem_resposta_notifica_a_diretoria_executiva(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(
                    vespera_avisada_em=NA_VESPERA.isoformat(),
                    escalonado_gestor_em=NO_MAIS_24H.isoformat(),
                )
            ],
            diretoria=[_diretor(1), _diretor(2)],
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert degraus == 1
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert {r["gatilho"] for r in registros} == {ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA}
        assert all(dt.datetime.fromisoformat(r["enviar_a_partir_de"]) == ABERTURA_DE_SEXTA for r in registros)

        assert _entregar_a_fila(supabase, ABERTURA_DE_SEXTA) == 2
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {
            "diretoria1@hsm.br",
            "diretoria2@hsm.br",
        }
        for email in _nunca_envia_email_de_verdade:
            # A Diretoria tem painel: o email dela não carrega link tokenizado
            # do portal do setor.
            assert "/ouvidoria-setor/" not in email["html"]
            # Este degrau não é o do gestor ausente: o assunto não fala disso.
            assert "sem gestor cadastrado" not in email["assunto"].lower()


class TestIdempotencia:
    """Rodar o job duas vezes não duplica nenhum degrau."""

    def test_rodar_o_job_duas_vezes_nao_duplica_degrau(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()

        primeira = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        segunda = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H + dt.timedelta(minutes=10), SEM_FERIADOS)

        # Caso abandonado: os degraus atrasados sobem na mesma rodada, cada um
        # uma vez. A véspera fica de fora porque o prazo já venceu.
        assert primeira == 2
        assert segunda == 0
        gatilhos = [r["gatilho"] for r in supabase.tabelas["ouvidoria_notificacoes"]]
        assert sorted(gatilhos) == sorted(
            [
                ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_GESTOR,
                ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA,
            ]
        )
        assert _nunca_envia_email_de_verdade == []

        assert _entregar_a_fila(supabase, ABERTURA_DE_SEXTA) == 2
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"gestor@hsm.br", "diretoria1@hsm.br"}

    def test_degrau_cuja_notificacao_nao_grava_volta_para_a_proxima_rodada(self, _nunca_envia_email_de_verdade):
        """Cenário do deploy antes da migration: o CHECK antigo recusa o
        gatilho novo. O degrau não pode ficar carimbado sem cobrança nenhuma."""
        supabase = _SupabaseFake()
        supabase.falhar_inserts = {"ouvidoria_notificacoes"}

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        assert degraus == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vespera_avisada_em"] is None
        assert supabase.tabelas["ouvidoria_movimentos"] == []

        supabase.falhar_inserts = set()
        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA + dt.timedelta(minutes=10), SEM_FERIADOS)
        assert degraus == 1
        assert [r["destinatario_email"] for r in supabase.tabelas["ouvidoria_notificacoes"]] == ["titular@hsm.br"]

    def test_caso_com_a_escada_completa_sai_da_varredura(self, _nunca_envia_email_de_verdade):
        """Caso abandonado em aguardando área com a escada toda subida não pode
        ocupar a janela de leitura para sempre. Passando do teto, nenhum caso
        novo entraria e a escada pararia em silêncio."""
        antigo = dt.datetime(2026, 8, 3, 12, 0, tzinfo=dt.UTC)
        esgotados = [
            _manifestacao(
                n,
                prazo_area_em=(antigo + dt.timedelta(hours=n)).isoformat(),
                vespera_avisada_em=antigo.isoformat(),
                escalonado_gestor_em=antigo.isoformat(),
                escalonado_diretoria_em=antigo.isoformat(),
            )
            for n in range(1, ouvidoria_escalonamento.LEITURA_POR_RODADA + 1)
        ]
        supabase = _SupabaseFake(manifestacoes=[*esgotados, _manifestacao(999)])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert [r["destinatario_email"] for r in registros] == ["gestor@hsm.br"]
        assert [r["manifestacao_id"] for r in registros] == ["uuid-999"]

    def test_caso_que_respondeu_nao_escala(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(status="respondido")])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert degraus == 0
        assert _nunca_envia_email_de_verdade == []

    def test_area_que_responde_antes_do_envio_nao_recebe_o_escalonamento(self, _nunca_envia_email_de_verdade):
        """Degrau retido pela janela comercial: se a área responde durante a
        noite, o job da fila não manda a cobrança de manhã."""
        supabase = _SupabaseFake()
        ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)
        assert _nunca_envia_email_de_verdade == []

        supabase.tabelas["ouvidoria_protocolos"][0]["status"] = "respondido"
        entregues = _entregar_a_fila(supabase, ABERTURA_DE_TERCA)

        assert entregues == 0
        assert _nunca_envia_email_de_verdade == []
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["status"] == "falha"
        assert "respondeu antes" in registro["ultimo_erro"]


class TestTrilhaERegistro:
    """Cada degrau é registrado, reenviável e aparece na trilha do caso."""

    def test_cada_degrau_vira_movimento_na_trilha(self):
        supabase = _SupabaseFake()

        # A escada sobe degrau a degrau, como no relógio real: um tick do job
        # em cada instante da escada, e mais um depois de tudo.
        for tick in (NA_VESPERA, NO_MAIS_24H, NO_MAIS_48H, NO_MAIS_48H + dt.timedelta(minutes=10)):
            ouvidoria_escalonamento.escalar_prazos(supabase, tick, SEM_FERIADOS)

        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 3
        for movimento in movimentos:
            # Escalonamento não muda o estado do caso: a trilha registra o fato
            # com o caso parado em aguardando_area.
            assert movimento["estado_anterior"] == "aguardando_area"
            assert movimento["estado_novo"] == "aguardando_area"
            assert movimento["autor_id"] is None
        observacoes = " | ".join(m["observacao"] for m in movimentos).lower()
        assert "véspera" in observacoes
        assert "gestor" in observacoes
        assert "diretoria" in observacoes

    def test_degrau_e_reenviavel_pelo_botao_da_ouvidoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake()
        ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]

        client = _client(monkeypatch, supabase, NA_VESPERA)
        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{registro['id']}/reenviar")

        assert resposta.status_code == 201
        assert resposta.json()["gatilho"] == ouvidoria_notificacoes.GATILHO_VESPERA_VENCIMENTO
        assert resposta.json()["entregue"] is True
        # O degrau original continua retido pela janela: o reenvio é decisão de
        # uma pessoa da Ouvidoria e sai na hora, sozinho.
        assert len(_nunca_envia_email_de_verdade) == 1

    def test_alerta_a_diretoria_por_falta_de_gestor_e_reenviavel_com_o_mesmo_motivo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O reenvio remonta o email pelo GATILHO, e o gatilho do alerta de
        cadastro tem montador próprio: o email refeito explica de novo que o
        setor não tem gestor, sem depender de um `detalhe` copiado."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[_responsavel("titular")],
        )
        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]

        client = _client(monkeypatch, supabase, NO_MAIS_24H)
        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{registro['id']}/reenviar")

        assert resposta.status_code == 201
        assert supabase.tabelas["ouvidoria_notificacoes"][-1]["gatilho"] == (
            ouvidoria_notificacoes.GATILHO_ALERTA_CADASTRO_SETOR
        )
        assert len(_nunca_envia_email_de_verdade) == 1
        assert "sem gestor cadastrado" in _nunca_envia_email_de_verdade[0]["assunto"].lower()
        assert "gestor" in _nunca_envia_email_de_verdade[0]["texto"].lower()


class TestJanelaComercial:
    """Notificação não crítica respeita o horário comercial; crítica ignora."""

    def test_degrau_nao_critico_no_fechamento_espera_a_abertura(self, _nunca_envia_email_de_verdade):
        """É o caso comum, não a exceção: prazo em dias úteis vence às 17h, o
        degrau cai às 17h e o email só sai na abertura seguinte."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())])

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        assert _nunca_envia_email_de_verdade == []
        registro = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert registro["status"] == "agendada"
        assert dt.datetime.fromisoformat(registro["enviar_a_partir_de"]) == ABERTURA_DE_QUINTA

    def test_degrau_de_caso_critico_ignora_a_janela(self, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(
            manifestacoes=[
                _manifestacao(gravidade="critico", vespera_avisada_em=NA_VESPERA.isoformat()),
            ]
        )

        degraus = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert degraus == 1
        # Nada de esperar a abertura: o email do caso crítico sai no fechamento
        # em que o degrau caiu.
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"gestor@hsm.br"}


class TestCriticoImediato:
    """Caso crítico validado notifica a Diretoria na hora, sem esperar prazo."""

    def _pedido(self, gravidade: str) -> dict:
        return {
            "tipo_manifestacao": "reclamacao",
            "categoria": "Demora no atendimento",
            "setor": "Recepcao",
            "gravidade": gravidade,
            "extrato_para_o_setor": "Apurar a espera relatada e responder a Ouvidoria.",
        }

    def _caso_novo(self) -> dict:
        return _manifestacao(
            status="em_classificacao",
            gravidade=None,
            prazo_area_em=None,
            validada_em=None,
            validada_por=None,
            extrato_para_o_setor=None,
        )

    def test_caso_critico_validado_avisa_a_diretoria_na_hora(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()], diretoria=[_diretor(1), _diretor(2)])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("critico"))

        assert resposta.status_code == 200
        criticos = [
            r
            for r in supabase.tabelas["ouvidoria_notificacoes"]
            if r["gatilho"] == ouvidoria_notificacoes.GATILHO_CRITICO_IMEDIATO
        ]
        assert {r["destinatario_email"] for r in criticos} == {"diretoria1@hsm.br", "diretoria2@hsm.br"}
        # Fora do expediente e mesmo assim entregue: crítico não espera a janela.
        assert all(r["status"] == "enviada" for r in criticos)
        assert {"diretoria1@hsm.br", "diretoria2@hsm.br"} <= _emails_por_destinatario(_nunca_envia_email_de_verdade)
        assert supabase.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] is not None

    def test_caso_nao_critico_validado_nao_aciona_a_diretoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("medio"))

        assert resposta.status_code == 200
        gatilhos = {r["gatilho"] for r in supabase.tabelas["ouvidoria_notificacoes"]}
        assert ouvidoria_notificacoes.GATILHO_CRITICO_IMEDIATO not in gatilhos
        assert supabase.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] is None

    def test_aviso_critico_entra_na_trilha_do_caso(self, monkeypatch):
        supabase = _SupabaseFake(manifestacoes=[self._caso_novo()])
        client = _client(monkeypatch, supabase, FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=self._pedido("critico"))

        observacoes = " | ".join((m.get("observacao") or "") for m in supabase.tabelas["ouvidoria_movimentos"]).lower()
        assert "crítico" in observacoes
        assert "diretoria" in observacoes


class TestMigration:
    """A 072 abre o CHECK de gatilho para a escada e dá ao caso os carimbos de
    idempotência, reaplicável sem quebrar (padrão da casa)."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "072_ouvidoria_escalonamento.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def test_gatilhos_da_escada_entram_no_check(self):
        ddl = self._ddl()
        for gatilho in (
            "vespera_vencimento",
            "escalonamento_gestor",
            "escalonamento_diretoria",
            "critico_imediato",
        ):
            assert f"'{gatilho}'" in ddl
        # Os gatilhos anteriores continuam válidos.
        for gatilho in ("nova_demanda", "alerta_sem_titular", "prazo_rompido"):
            assert f"'{gatilho}'" in ddl
        assert "drop constraint if exists ouvidoria_notificacoes_gatilho_check" in ddl

    def test_cada_degrau_ganha_o_proprio_carimbo(self):
        ddl = self._ddl()
        for coluna in (
            "vespera_avisada_em",
            "escalonado_gestor_em",
            "escalonado_diretoria_em",
            "critico_avisado_em",
        ):
            assert f"add column if not exists {coluna}" in ddl

    def test_migration_e_idempotente(self):
        ddl = self._ddl()
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl

    def test_indice_e_reaplicavel(self):
        """CREATE INDEX IF NOT EXISTS não REDEFINE índice que já existe: quem
        aplicou uma versão anterior desta migration ficaria com o WHERE antigo,
        sem erro e sem aviso. O DROP tem que vir antes."""
        ddl = self._ddl()
        drop = ddl.index("drop index if exists idx_ouvidoria_protocolos_escalonamento")
        create = ddl.index("create index if not exists idx_ouvidoria_protocolos_escalonamento")
        assert drop < create


class TestJobNoScheduler:
    """A escada sobe sozinha, de tempos em tempos, junto dos demais jobs."""

    def test_job_de_escalonamento_esta_registrado(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("escalonamento_ouvidoria") is not None
        finally:
            cron.stop_scheduler()


class TestCasoSemNinguemParaAvisar:
    """Issue #373, defeito 2: caso cujo setor não tem ninguém E cuja Diretoria
    Executiva está vazia nunca carimbava degrau nenhum. Ele voltava em toda
    rodada e, por ser o mais antigo, vinha primeiro na ordenação. Passando de
    `LEITURA_POR_RODADA`, o job parava de escalonar qualquer caso."""

    def _sem_ninguem(self, manifestacoes: list[dict] | None = None) -> _SupabaseFake:
        return _SupabaseFake(manifestacoes=manifestacoes, responsaveis=[], diretoria=[])

    def test_caso_sem_destinatario_possivel_e_carimbado_como_impossivel(self, _nunca_envia_email_de_verdade):
        supabase = self._sem_ninguem()

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_o_carimbo_de_impossivel_nao_queima_degrau_nenhum(self, _nunca_envia_email_de_verdade):
        """O caso não é perdido: quando o cadastro for corrigido, a escada sobe
        do degrau em que parou, e não do fim dela."""
        supabase = self._sem_ninguem()

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["vespera_avisada_em"] is None
        assert caso["escalonado_gestor_em"] is None
        assert caso["escalonado_diretoria_em"] is None
        assert supabase.tabelas["ouvidoria_notificacoes"] == []

    def test_caso_travado_alerta_o_admin_tecnico_por_email(self, _nunca_envia_email_de_verdade):
        """Sinal operacional de verdade, e não só `logger.warning`: um job que
        roda a cada 10 minutos enche o log de aviso que ninguém lê."""
        supabase = self._sem_ninguem()

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"admin@hsm.br"}
        aviso = _nunca_envia_email_de_verdade[0]
        assert "cadastro incompleto" in aviso["assunto"].lower()
        assert "2026-0007" in aviso["texto"]
        assert "Recepcao" in aviso["texto"]
        # O texto tem que ser verdadeiro: só chega aqui quem não tem NENHUMA
        # das duas pontas, e o conserto vale pelas duas.
        assert "Diretoria Executiva" in aviso["texto"]
        assert "perfil de Diretoria Executiva" in aviso["texto"]

    def test_o_email_nomeia_o_degrau_mais_alto_que_ficou_sem_ninguem(self, _nunca_envia_email_de_verdade):
        """Caso abandonado desde a véspera trava nos três degraus. Nomear o
        primeiro mandaria o admin olhar a véspera, que é o degrau que menos
        importa: quem parou de verdade foi o último."""
        supabase = self._sem_ninguem(manifestacoes=[_manifestacao(prazo_area_em=VENCIMENTO)])

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        corpo = _nunca_envia_email_de_verdade[0]["texto"]
        assert ouvidoria_escalonamento.DIRETORIA.nome in corpo
        assert ouvidoria_escalonamento.GESTOR.nome not in corpo

    def test_o_admin_nao_e_alertado_de_novo_a_cada_rodada(self, _nunca_envia_email_de_verdade):
        """O carimbo é condicional (`IS NULL`), então o alerta sai uma vez só."""
        supabase = self._sem_ninguem()
        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        _nunca_envia_email_de_verdade.clear()

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H + dt.timedelta(minutes=10), SEM_FERIADOS)

        assert _nunca_envia_email_de_verdade == []

    def test_falha_na_leitura_do_cadastro_nao_trava_o_caso(self, _nunca_envia_email_de_verdade, monkeypatch):
        """Cadastro vazio e leitura falha não são a mesma coisa. Tirar o caso
        da varredura por causa de um timeout o deixaria parado esperando um
        cadastro que já existe."""
        # A Diretoria PRECISA estar vazia: com ela viva o caso não travaria de
        # qualquer jeito, e o teste passaria mesmo com a distinção quebrada.
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[],
            diretoria=[],
        )
        monkeypatch.setattr(ouvidoria_escalonamento, "_carregar_responsaveis", lambda *_a: None)

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None

    def test_caso_travado_nao_ocupa_a_janela_de_leitura_do_job(self, _nunca_envia_email_de_verdade):
        """O critério que dói: `LEITURA_POR_RODADA` casos sem destinatário, e
        um caso normal atrás deles na ordenação por prazo. Antes do carimbo, os
        travados voltavam em toda rodada e o caso novo nunca era lido."""
        # Os travados são mais antigos, então vêm primeiro na ordenação.
        travados = [
            _manifestacao(numero=n, setor="Setor Orfao", prazo_area_em="2026-08-24T20:00:00+00:00")
            for n in range(ouvidoria_escalonamento.LEITURA_POR_RODADA)
        ]
        atendivel = _manifestacao(numero=900, setor="Recepcao")
        # Sem Diretoria Executiva cadastrada: é o que fecha a última saída dos
        # casos do setor órfão. O caso da Recepcao ainda tem gestor a cobrar.
        supabase = _SupabaseFake(
            manifestacoes=[*travados, atendivel],
            responsaveis=[_responsavel("titular"), _responsavel("gestor")],
            diretoria=[],
        )

        # Primeira rodada: só os travados cabem na janela, e todos são carimbados.
        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        assert all(c["escalonamento_impossivel_em"] for c in supabase.tabelas["ouvidoria_protocolos"][:-1])

        # Segunda rodada: a janela está livre e o caso novo é cobrado.
        subidos = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H + dt.timedelta(minutes=10), SEM_FERIADOS)

        assert subidos > 0
        cobrados = {r["manifestacao_id"] for r in supabase.tabelas["ouvidoria_notificacoes"]}
        assert cobrados == {"uuid-900"}

    def test_o_carimbo_so_e_gravado_depois_de_o_alerta_sair(self, _nunca_envia_email_de_verdade, monkeypatch):
        """O carimbo tira o caso da varredura, e é condicional: gravado antes
        do alerta, um restart no meio da rodada (deploy, OOM) deixaria o caso
        sem cobrança E sem sinal, para sempre. O alerta vem primeiro."""
        supabase = self._sem_ninguem()

        def _alerta_falha(*_a, **_kw):
            raise RuntimeError("provedor de email fora do ar")

        monkeypatch.setattr(ouvidoria_escalonamento, "avisar_admins_tecnicos", _alerta_falha)

        with pytest.raises(RuntimeError):
            ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        # Nada carimbado: a rodada seguinte tenta de novo, alerta e tudo.
        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None

    def test_o_carimbo_nao_sai_quando_o_alerta_nao_foi_entregue(self, _nunca_envia_email_de_verdade, monkeypatch):
        """Inverter a ordem cobre o crash, não a entrega. Sem super admin com
        email, ou com a leitura de `participantes` falhando, o alerta não sai e
        carimbar assim mesmo produz o desfecho que esta fatia existe para
        impedir: caso sem cobrança E sem sinal, para sempre."""
        supabase = self._sem_ninguem()
        # Nenhum super admin a quem avisar: `avisar_admins_tecnicos` devolve 0.
        supabase.tabelas["participantes"] = []

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None

    def test_caso_que_saiu_de_aguardando_area_nao_e_carimbado(self, _nunca_envia_email_de_verdade):
        """Mesma guarda do carimbo de degrau: entre a leitura e a escrita o
        caso pode ter sido respondido, e travar um caso que já andou o deixaria
        fora da varredura se ele voltasse à área depois."""
        supabase = self._sem_ninguem()
        caso = supabase.tabelas["ouvidoria_protocolos"][0]

        real = ouvidoria_escalonamento._reivindicar_impossivel

        def _muda_o_status_antes(sb, manifestacao_id, agora):
            caso["status"] = "respondida"
            return real(sb, manifestacao_id, agora)

        ouvidoria_escalonamento._reivindicar_impossivel = _muda_o_status_antes
        try:
            ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)
        finally:
            ouvidoria_escalonamento._reivindicar_impossivel = real

        assert caso["escalonamento_impossivel_em"] is None

    def test_o_caso_devolvido_a_area_volta_a_escalonar(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Devolução (#334) e reabertura (#335) põem o caso de volta em
        aguardando área com prazo novo. O carimbo velho não pode mantê-lo fora
        da varredura.

        O teste bate na ROTA de devolução, não na constante: assertar a lista
        de carimbos ficaria verde se a rota parasse de usá-la."""
        travado = _manifestacao(
            status="respondido",
            escalonamento_impossivel_em=NO_MAIS_48H.isoformat(),
            resposta_da_area="Resposta curta demais.",
            respondida_em=NO_MAIS_24H.isoformat(),
        )
        supabase = _SupabaseFake(manifestacoes=[travado])
        supabase.tabelas["ouvidoria_prazos"] = [
            {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"}
        ]
        supabase.tabelas["ouvidoria_feriados"] = []
        client = _client(monkeypatch, supabase, NO_MAIS_48H)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/devolucoes",
            json={"motivo": "A resposta nao diz o que foi apurado nem o que muda."},
        )

        assert resposta.status_code == 201, resposta.text
        assert travado["escalonamento_impossivel_em"] is None

    def test_a_rodada_le_o_cadastro_de_cada_setor_uma_vez_so(self, _nunca_envia_email_de_verdade, monkeypatch):
        """O cenário da issue é 200 casos travados, quase sempre do mesmo setor
        órfão. Reconsultar o cadastro por caso e por degrau seria centenas de
        idas ao banco numa rodada que existe justamente para destravar o job."""
        travados = [_manifestacao(numero=n, setor="Setor Orfao") for n in range(30)]
        supabase = _SupabaseFake(manifestacoes=travados, responsaveis=[], diretoria=[])

        leituras: list[str] = []
        real = ouvidoria_escalonamento._carregar_responsaveis
        monkeypatch.setattr(
            ouvidoria_escalonamento,
            "_carregar_responsaveis",
            lambda sb, setor: (leituras.append(setor), real(sb, setor))[1],
        )

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert leituras == ["Setor Orfao"]

    def test_a_rodada_manda_um_alerta_so_com_todos_os_travados(self, _nunca_envia_email_de_verdade):
        """O primeiro tick depois do deploy acha todo o histórico travado de
        uma vez. Um email por caso seria a rajada que `LOTE_POR_RODADA` existe
        para evitar; um teto de emails deixaria os que sobrassem sem sinal
        nenhum, para sempre, porque o carimbo é condicional."""
        travados = [_manifestacao(numero=n, setor="Setor Orfao") for n in range(40)]
        supabase = _SupabaseFake(manifestacoes=travados, responsaveis=[], diretoria=[])

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert all(c["escalonamento_impossivel_em"] for c in supabase.tabelas["ouvidoria_protocolos"])
        assert len(_nunca_envia_email_de_verdade) == 1
        aviso = _nunca_envia_email_de_verdade[0]
        assert "40 caso(s)" in aviso["assunto"]
        # Todo caso travado aparece no corpo: nenhum fica só no log.
        for caso in supabase.tabelas["ouvidoria_protocolos"]:
            assert caso["protocolo"] in aviso["texto"]

    def test_falha_na_leitura_da_diretoria_nao_trava_o_caso(self, _nunca_envia_email_de_verdade, monkeypatch):
        """O degrau da Diretoria tem o mesmo contrato do degrau do setor: um
        timeout na leitura adia, não carimba. Sem esta distinção, uma falha
        transitória tiraria o caso da varredura para sempre, e quem conserta é
        um cadastro que já existe."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())])

        # None é como `ler_diretoria_executiva` diz "a leitura falhou", em
        # oposição à lista vazia de "ninguém tem o perfil".
        monkeypatch.setattr(ouvidoria_escalonamento, "ler_diretoria_executiva", lambda *_a: None)
        monkeypatch.setattr(ouvidoria_escalonamento, "_carregar_responsaveis", lambda *_a: [])

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None
        assert _nunca_envia_email_de_verdade == []

    def test_leitura_da_diretoria_que_estoura_de_verdade_nao_trava_o_caso(self, _nunca_envia_email_de_verdade):
        """O `except` REAL de `ler_diretoria_executiva`, sem monkeypatch: quem
        troca o `return None` dele por `return []` reintroduz a regressão de
        carimbar caso por timeout, e um teste que substitui a função nunca
        chega a executar o bloco que a guarda protege."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[],
            diretoria=[],
        )
        # Só a leitura da Diretoria cai. A dos super admins (`access_profile`)
        # continua de pé, senão o carimbo deixaria de sair pelo outro motivo e
        # o teste provaria a guarda errada.
        supabase.falhar_selects = {"participantes": "perfil_ouvidoria"}

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None
        assert _nunca_envia_email_de_verdade == []

    def test_leitura_do_cadastro_que_estoura_de_verdade_nao_trava_o_caso(self, _nunca_envia_email_de_verdade):
        """O par do teste acima, pela outra porta: o `except` real de
        `_carregar_responsaveis`. Sem os dois separados, apagar uma das duas
        guardas num refactor passaria despercebido."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())],
            responsaveis=[],
            diretoria=[],
        )
        supabase.falhar_selects = {"ouvidoria_setor_responsaveis": None}

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None

    def test_o_carimbo_nao_sai_quando_o_provedor_de_email_recusa(self, _nunca_envia_email_de_verdade, monkeypatch):
        """O braço mais provável em produção do carimbo condicional: existe
        super admin com email, mas o provedor recusa a mensagem. Sem este
        teste, contar destinatários em vez de entregas ficaria verde."""
        supabase = self._sem_ninguem()
        monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", lambda *_a, **_kw: False)

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None

    def test_a_falha_de_leitura_nao_fica_no_cache_da_rodada(self, _nunca_envia_email_de_verdade, monkeypatch):
        """O cache guarda cadastro, não erro. Memorizar a falha contaminaria
        todos os casos seguintes do mesmo setor na mesma rodada."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(numero=n, vespera_avisada_em=NA_VESPERA.isoformat()) for n in range(3)],
            responsaveis=[],
            diretoria=[],
        )

        tentativas: list[str] = []
        real = ouvidoria_escalonamento._carregar_responsaveis

        def _falha_uma_vez(sb, setor):
            tentativas.append(setor)
            return None if len(tentativas) == 1 else real(sb, setor)

        monkeypatch.setattr(ouvidoria_escalonamento, "_carregar_responsaveis", _falha_uma_vez)

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        # A segunda leitura aconteceu: a falha da primeira não virou cache.
        assert len(tentativas) > 1

    def test_vespera_sem_titular_nao_trava_o_caso_que_ainda_pode_subir(self, _nunca_envia_email_de_verdade):
        """A pergunta certa é sobre o CASO, não sobre o degrau devido agora. O
        job roda a cada 10 minutos, então quase sempre só um degrau está
        vencido. Setor sem ninguém na véspera ainda escalona: o degrau do
        gestor cai na Diretoria um dia depois."""
        supabase = _SupabaseFake(responsaveis=[], diretoria=[_diretor(1)])

        ouvidoria_escalonamento.escalar_prazos(supabase, NA_VESPERA, SEM_FERIADOS)

        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["escalonamento_impossivel_em"] is None

        # E o degrau seguinte de fato sobe, pela Diretoria.
        subidos = ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_24H, SEM_FERIADOS)
        assert subidos == 1
        assert [r["destinatario_email"] for r in supabase.tabelas["ouvidoria_notificacoes"]] == ["diretoria1@hsm.br"]

    def test_setor_com_responsaveis_nao_trava_por_diretoria_vazia(self, _nunca_envia_email_de_verdade):
        """O caso ainda tem a quem falar pela outra ponta: o carimbo é para
        quem não tem NENHUMA saída, e este tem titular e gestor."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(vespera_avisada_em=NA_VESPERA.isoformat())], diretoria=[])

        ouvidoria_escalonamento.escalar_prazos(supabase, NO_MAIS_48H, SEM_FERIADOS)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["escalonamento_impossivel_em"] is None


class TestCadastroCorrigidoDestravaOCaso:
    """Issue #373, defeito 2, segunda metade: o caso não é perdido. Cadastrar
    responsável no setor limpa o carimbo, e a escada volta a subir do degrau em
    que parou."""

    def test_cadastrar_responsavel_destrava_os_casos_do_setor(self, monkeypatch, _nunca_envia_email_de_verdade):
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)
        supabase.tabelas["setores"] = [{"id": "s1", "nome": "Recepcao", "ativo": True}]

        resposta = client.post(
            "/api/ouvidoria/responsaveis",
            json={"setor": "Recepcao", "papel": "titular", "nome": "Carlos Titular", "email": "titular@hsm.br"},
        )

        assert resposta.status_code == 201, resposta.text
        assert travado["escalonamento_impossivel_em"] is None

    def test_cadastro_de_outro_setor_nao_destrava_este(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O carimbo é por caso, e o buraco de cadastro é por setor: destravar
        o hospital inteiro a cada cadastro devolveria à varredura casos que
        seguem sem ninguém."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)
        supabase.tabelas["setores"] = [
            {"id": "s1", "nome": "Recepcao", "ativo": True},
            {"id": "s2", "nome": "Farmacia", "ativo": True},
        ]

        client.post(
            "/api/ouvidoria/responsaveis",
            json={"setor": "Farmacia", "papel": "titular", "nome": "Ana Farmacia", "email": "ana@hsm.br"},
        )

        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_encerrar_a_vigencia_nao_destrava_o_setor(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Encerrar vigência é o caminho documentado de entregar um setor: ele
        piora o cadastro, não corrige. Destravar aqui devolveria os casos à
        varredura só para eles serem re-carimbados na rodada seguinte, com
        alerta novo ao admin a cada troca de responsável."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        vigente = _responsavel("titular")
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[vigente], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)

        resposta = client.put(
            f"/api/ouvidoria/responsaveis/{vigente['id']}",
            json={"nome": "Carlos Titular", "email": "titular@hsm.br", "vigencia_fim": "2026-01-31"},
        )

        assert resposta.status_code == 200, resposta.text
        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_cadastrar_substituto_nao_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O substituto é vigente, mas nenhum degrau DESTA escada fala com ele:
        quem o cobra é o degrau do vencimento, que mora em `ouvidoria_cobranca`.
        Destravar aqui só produziria re-carimbo e alerta novo ao admin."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)
        supabase.tabelas["setores"] = [{"id": "s1", "nome": "Recepcao", "ativo": True}]

        resposta = client.post(
            "/api/ouvidoria/responsaveis",
            json={"setor": "Recepcao", "papel": "substituto", "nome": "Ana Substituta", "email": "ana@hsm.br"},
        )

        assert resposta.status_code == 201, resposta.text
        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_cadastro_com_vigencia_que_comeca_amanha_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O cadastro foi corrigido, só ainda não vigora. Nada roda quando a
        vigência começa, então não destravar aqui deixaria o caso preso mesmo
        depois de o setor voltar a ter titular."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)
        supabase.tabelas["setores"] = [{"id": "s1", "nome": "Recepcao", "ativo": True}]

        resposta = client.post(
            "/api/ouvidoria/responsaveis",
            json={
                "setor": "Recepcao",
                "papel": "titular",
                "nome": "Carlos Novo",
                "email": "novo@hsm.br",
                "vigencia_inicio": "2026-09-15",
            },
        )

        assert resposta.status_code == 201, resposta.text
        assert travado["escalonamento_impossivel_em"] is None

    def test_cadastro_com_vigencia_ja_encerrada_nao_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Cadastrar quem já saiu não dá ao setor ninguém a quem falar hoje."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)
        supabase.tabelas["setores"] = [{"id": "s1", "nome": "Recepcao", "ativo": True}]

        resposta = client.post(
            "/api/ouvidoria/responsaveis",
            json={
                "setor": "Recepcao",
                "papel": "titular",
                "nome": "Carlos Antigo",
                "email": "antigo@hsm.br",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": "2026-01-31",
            },
        )

        assert resposta.status_code == 201, resposta.text
        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_dar_perfil_de_diretoria_executiva_destrava_todo_caso_travado(self, _nunca_envia_email_de_verdade):
        """A outra ponta do cadastro. Caso travado num setor que TEM gente só
        volta a escalonar quando alguém ganha o perfil de Diretoria: cadastrar
        responsável no setor não conserta esse."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        outro = _manifestacao(numero=8, setor="Farmacia", escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado, outro], diretoria=[])

        ouvidoria_escalonamento.destravar_todos(supabase)

        assert travado["escalonamento_impossivel_em"] is None
        assert outro["escalonamento_impossivel_em"] is None

    async def _conceder_perfil(self, supabase, monkeypatch, perfil: str | None):
        """Chama a rota real de concessão de perfil, com o mínimo mockado: só o
        audit e o provisionamento de login, que não são o assunto aqui."""
        from app.models.admin_schemas import PerfilOuvidoriaUpdate
        from app.routers.admin import usuarios as usuarios_router
        from app.services import audit

        monkeypatch.setattr(audit, "log_action", lambda *_a, **_kw: None)
        monkeypatch.setattr(usuarios_router.audit, "log_action", lambda *_a, **_kw: None)
        return await usuarios_router.definir_perfil_ouvidoria(
            participante_id="P12",
            body=PerfilOuvidoriaUpdate(perfil_ouvidoria=perfil, reason="teste"),
            request=None,
            actor={"id": "P03", "nome_completo": "Pedro Admin", "email": "admin@hsm.br"},
            supabase=supabase,
        )

    def _com_participante_sem_perfil(self, travado: dict) -> _SupabaseFake:
        supabase = _SupabaseFake(manifestacoes=[travado], diretoria=[])
        supabase.tabelas["participantes"].append(
            {
                "id": "P12",
                "nome_completo": "Sofia Secretaria",
                "email": "sofia@hsm.br",
                "perfil_ouvidoria": None,
                "auth_user_id": "auth-12",
            }
        )
        return supabase

    @pytest.mark.asyncio
    async def test_a_rota_de_perfil_destrava_ao_conceder_diretoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A fiação, não só a função: apagar a chamada da rota tem que deixar
        este teste vermelho."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = self._com_participante_sem_perfil(travado)

        await self._conceder_perfil(supabase, monkeypatch, "diretoria_executiva")

        assert travado["escalonamento_impossivel_em"] is None

    @pytest.mark.asyncio
    async def test_a_rota_de_perfil_nao_destrava_ao_conceder_ouvidor(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O caminho oposto, que é o que impede este par de testes de passar
        por acidente: ouvidor não é a ponta que faltava no cadastro, e o caso
        segue sem ninguém a quem escalonar."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = self._com_participante_sem_perfil(travado)

        await self._conceder_perfil(supabase, monkeypatch, "ouvidor")

        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    @pytest.mark.asyncio
    async def test_conceder_diretoria_a_quem_nao_tem_email_nao_destrava(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """A escada só fala por email. Destravar aqui devolveria os casos à
        varredura só para serem re-carimbados na rodada seguinte."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = self._com_participante_sem_perfil(travado)
        supabase.tabelas["participantes"][-1]["email"] = ""

        await self._conceder_perfil(supabase, monkeypatch, "diretoria_executiva")

        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    @pytest.mark.asyncio
    async def test_preencher_o_email_de_quem_ja_e_diretoria_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Diretor cadastrado sem email não destrava nada, e preencher o email
        pela edição do usuário é o caminho natural de consertar. Sem isso os
        casos ficavam fora da varredura em silêncio: o alerta ao admin é uma
        vez só."""
        from app.models.admin_schemas import AdminUsuarioUpdate
        from app.routers.admin import usuarios as usuarios_router
        from app.services import audit

        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], diretoria=[])
        supabase.tabelas["participantes"].append(
            {
                "id": "P20",
                "nome_completo": "Dra. Diretora",
                "email": "",
                "perfil_ouvidoria": "diretoria_executiva",
                "auth_user_id": None,
            }
        )
        monkeypatch.setattr(usuarios_router.audit, "log_action", lambda *_a, **_kw: None)
        monkeypatch.setattr(audit, "log_action", lambda *_a, **_kw: None)

        await usuarios_router.update_usuario(
            participante_id="P20",
            body=AdminUsuarioUpdate(email="diretora@hsm.br"),
            request=None,
            actor={"id": "P03", "nome_completo": "Pedro Admin"},
            supabase=supabase,
        )

        assert travado["escalonamento_impossivel_em"] is None

    @pytest.mark.asyncio
    async def test_editar_quem_nao_e_diretoria_nao_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O par que impede o teste acima de passar por acidente: trocar o
        email de um ouvidor não dá à escada ninguém novo a quem falar."""
        from app.models.admin_schemas import AdminUsuarioUpdate
        from app.routers.admin import usuarios as usuarios_router
        from app.services import audit

        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        supabase = _SupabaseFake(manifestacoes=[travado], diretoria=[])
        supabase.tabelas["participantes"].append(
            {
                "id": "P21",
                "nome_completo": "Marta Ouvidora",
                "email": "marta@hsm.br",
                "perfil_ouvidoria": "ouvidor",
                "auth_user_id": None,
            }
        )
        monkeypatch.setattr(usuarios_router.audit, "log_action", lambda *_a, **_kw: None)
        monkeypatch.setattr(audit, "log_action", lambda *_a, **_kw: None)

        await usuarios_router.update_usuario(
            participante_id="P21",
            body=AdminUsuarioUpdate(email="marta.nova@hsm.br"),
            request=None,
            actor={"id": "P03", "nome_completo": "Pedro Admin"},
            supabase=supabase,
        )

        assert travado["escalonamento_impossivel_em"] == NO_MAIS_48H.isoformat()

    def test_o_destrave_so_toca_os_casos_carimbados(self, _nunca_envia_email_de_verdade):
        """O update é filtrado: sem isso ele reescreve todo o histórico de
        protocolos do setor a cada cadastro de responsável."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        limpo = _manifestacao(numero=9)
        supabase = _SupabaseFake(manifestacoes=[travado, limpo], responsaveis=[], diretoria=[])

        tocados = ouvidoria_escalonamento.destravar_setor(supabase, "Recepcao")

        assert tocados == 1
        assert travado["escalonamento_impossivel_em"] is None

    def test_reabrir_a_vigencia_de_um_responsavel_tambem_destrava(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O outro caminho de corrigir o cadastro: a vigência encerrada por
        engano volta pela edição, e é ela que faz o setor ter gente de novo."""
        travado = _manifestacao(escalonamento_impossivel_em=NO_MAIS_48H.isoformat())
        vencido = _responsavel("titular", vigencia_fim="2026-01-31")
        supabase = _SupabaseFake(manifestacoes=[travado], responsaveis=[vencido], diretoria=[])
        client = _client(monkeypatch, supabase, NO_MAIS_48H, participante=DIRETORA)

        resposta = client.put(
            f"/api/ouvidoria/responsaveis/{vencido['id']}",
            json={"nome": "Carlos Titular", "email": "titular@hsm.br", "vigencia_fim": None},
        )

        assert resposta.status_code == 200, resposta.text
        assert travado["escalonamento_impossivel_em"] is None


class TestGuardaDeRetencao:
    """Issue #373, defeito 3: a guarda do `despachar` cancela toda notificação
    de `GATILHOS_QUE_COBRAM_A_AREA` quando o caso sai de aguardando área. Ela
    está certa para o degrau real (a área respondeu, não há o que cobrar) e
    errada para o alerta de cadastro: o buraco continua lá."""

    def _retido_ate_a_abertura(self, gatilho: str, detalhe: str | None = None):
        """Um degrau que subiu à noite e ficou na fila até o expediente abrir.
        Nesse meio tempo a área respondeu."""
        supabase = _SupabaseFake()
        notificacao = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id="uuid-7",
            gatilho=gatilho,
            destinatario_nome="Diretor 1",
            destinatario_email="diretoria1@hsm.br",
            papel_destinatario="diretoria_executiva",
            enviar_a_partir_de=ABERTURA_DE_SEXTA,
            detalhe=detalhe,
        )
        supabase.tabelas["ouvidoria_protocolos"][0]["status"] = "respondida"
        return supabase, notificacao

    def test_alerta_de_setor_sem_gestor_sai_mesmo_com_a_area_tendo_respondido(self, _nunca_envia_email_de_verdade):
        """O buraco de cadastro não some porque a área respondeu a tempo: ele
        volta no próximo caso daquele setor."""
        supabase, notificacao = self._retido_ate_a_abertura(
            ouvidoria_notificacoes.GATILHO_ALERTA_CADASTRO_SETOR,
            detalhe=ouvidoria_escalonamento.SEM_GESTOR.format(setor="Recepcao"),
        )

        saiu = ouvidoria_notificacoes.despachar(supabase, notificacao, ABERTURA_DE_SEXTA, SEM_FERIADOS)

        assert saiu is True
        assert _emails_por_destinatario(_nunca_envia_email_de_verdade) == {"diretoria1@hsm.br"}
        assert supabase.tabelas["ouvidoria_notificacoes"][0]["status"] == "enviada"

        # O email não pode acusar de silêncio quem respondeu: é justamente o
        # caso que este gatilho existe para atravessar. O assunto e o corpo
        # falam do buraco de cadastro, não da falta de resposta.
        email = _nunca_envia_email_de_verdade[0]
        assert "nao respondeu" not in email["texto"]
        assert "sem resposta" not in email["assunto"].lower()
        assert "gestor" in email["texto"].lower()
        assert "cadastr" in email["texto"].lower()

    def test_o_degrau_real_de_48h_continua_falando_de_falta_de_resposta(self, _nunca_envia_email_de_verdade):
        """O par do teste acima: o degrau real cobra o silêncio, e o texto dele
        tem que continuar dizendo isso. Sem este par, o teste de cima passaria
        com qualquer texto genérico."""
        supabase = _SupabaseFake()
        notificacao = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA,
            destinatario_nome="Diretor 1",
            destinatario_email="diretoria1@hsm.br",
            papel_destinatario="diretoria_executiva",
            enviar_a_partir_de=ABERTURA_DE_SEXTA,
        )

        ouvidoria_notificacoes.despachar(supabase, notificacao, ABERTURA_DE_SEXTA, SEM_FERIADOS)

        email = _nunca_envia_email_de_verdade[0]
        assert "nao respondeu" in email["texto"]

    def test_degrau_real_de_48h_continua_sendo_descartado(self, _nunca_envia_email_de_verdade):
        """O outro caminho da mesma guarda, e o motivo de ela existir: cobrar
        agora seria acusar quem já respondeu."""
        supabase, notificacao = self._retido_ate_a_abertura(ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA)

        saiu = ouvidoria_notificacoes.despachar(supabase, notificacao, ABERTURA_DE_SEXTA, SEM_FERIADOS)

        assert saiu is False
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_notificacoes"][0]["status"] == "falha"

    def test_o_alerta_de_cadastro_esta_fora_do_conjunto_que_cobra_a_area(self):
        """A prova pela regra, não pelo efeito: separar o gatilho é o que faz a
        guarda distinguir os dois, e a alternativa de olhar o `detalhe` some na
        primeira mudança de texto."""
        assert (
            ouvidoria_notificacoes.GATILHO_ALERTA_CADASTRO_SETOR
            not in ouvidoria_notificacoes.GATILHOS_QUE_COBRAM_A_AREA
        )
        assert (
            ouvidoria_notificacoes.GATILHO_ESCALONAMENTO_DIRETORIA in ouvidoria_notificacoes.GATILHOS_QUE_COBRAM_A_AREA
        )


class TestMigration078:
    """A 078 dá ao caso o carimbo de escalonamento impossível, abre o CHECK
    para o gatilho do alerta de cadastro e ensina o índice parcial a pular o
    caso travado (issue #373)."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "078_ouvidoria_escada_de_prazo.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def test_o_carimbo_do_caso_travado_e_criado_de_forma_reaplicavel(self):
        ddl = self._ddl()
        assert "add column if not exists escalonamento_impossivel_em timestamptz" in ddl
        assert "comment on column ouvidoria_protocolos.escalonamento_impossivel_em" in ddl

    def test_o_gatilho_do_alerta_de_cadastro_entra_no_check(self):
        ddl = self._ddl()
        assert "drop constraint if exists ouvidoria_notificacoes_gatilho_check" in ddl
        assert f"'{ouvidoria_notificacoes.GATILHO_ALERTA_CADASTRO_SETOR}'" in ddl
        # O CHECK recriado é a lista INTEIRA: o último criado é o que vale, e
        # esquecer um gatilho antigo derrubaria o insert dele em produção.
        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl, f"O CHECK da 078 perdeu o gatilho {gatilho}"

    def test_o_indice_da_varredura_pula_o_caso_travado(self):
        ddl = self._ddl()
        assert "drop index if exists idx_ouvidoria_protocolos_escalonamento" in ddl
        assert "escalonamento_impossivel_em is null" in ddl
