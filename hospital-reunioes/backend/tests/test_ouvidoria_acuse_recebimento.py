"""Acuse de recebimento ao manifestante (issue #493, PRD #471, ADR 0042).

Três coisas nascem juntas nesta fatia, e cada uma tem a sua seção aqui:

1. o marco `acusar_recebimento` na tabela de prazos, em HORAS CORRIDAS. É o
   único prazo do módulo fora do Calendário útil: acuse é promessa ao paciente
   e corre em relógio de parede (ADR 0042, decisão 1). Quem manifesta sexta à
   noite tem o aviso prometido para sábado à noite, não para terça de manhã;
2. o helper único que decide se um contato em texto livre tem email utilizável.
   O contato do manifestante é campo aberto (telefone, endereço, recado), e é
   ele que decide se existe para quem mandar;
3. o envio automático na abertura, pelos três caminhos de criação, sem janela
   comercial e sem poder derrubar o registro da manifestação.

A regra que mais importa aqui é a última: **se o acuse falhar, a manifestação
ainda tem que existir**. Quem manifestou já recebeu o número do protocolo na
tela; perder o caso por causa de um email é o pior desfecho possível.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.services import ouvidoria_acuse, ouvidoria_notificacoes  # noqa: E402
from app.services.ouvidoria_contato import email_utilizavel  # noqa: E402
from app.services.ouvidoria_prazos import (  # noqa: E402
    FUSO,
    HORAS_CORRIDAS,
    Prazo,
    calcular_vencimento,
)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION_ACUSE = "094_ouvidoria_acuse_recebimento.sql"

# O feriado e o fim de semana que o calendário útil pula e o relógio de parede
# não: 07/09/2026 (Independência) cai numa segunda-feira.
FERIADOS = frozenset({dt.date(2026, 9, 7)})


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _ddl(nome: str = MIGRATION_ACUSE) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


class TestEmailUtilizavel:
    """O contato é texto livre: o helper diz se há para quem mandar.

    Função única no app inteiro (critério de aceite), porque o aviso de
    encerramento (RN-80) responde a mesma pergunta sobre o mesmo campo: duas
    regras diferentes fariam um caso receber o acuse e não receber o desfecho.
    """

    def test_email_sozinho_e_utilizavel(self):
        assert email_utilizavel("joana.silva@exemplo.com.br") == "joana.silva@exemplo.com.br"

    def test_email_dentro_de_recado_e_utilizavel(self):
        """O balcão digita o contato como a pessoa fala."""
        assert email_utilizavel("Falar com a filha, email joana@exemplo.com") == "joana@exemplo.com"

    def test_telefone_nao_e_email(self):
        assert email_utilizavel("(21) 99999-0000") is None

    def test_texto_solto_nao_e_email(self):
        assert email_utilizavel("prefiro ser chamada pelo telefone de casa") is None

    def test_email_pela_metade_nao_serve(self):
        """Sem domínio não há para onde mandar, e mandar assim queima uma
        tentativa e sujaria o registro de notificações com uma falha do
        provedor que nada tem a ver com o provedor."""
        assert email_utilizavel("joana@") is None
        assert email_utilizavel("@exemplo.com") is None

    @pytest.mark.parametrize("vazio", [None, "", "   ", "\n"])
    def test_vazio_e_ausencia(self, vazio):
        assert email_utilizavel(vazio) is None

    def test_o_endereco_volta_normalizado(self):
        """Espaço em volta e caixa alta são de quem digitou, não do endereço."""
        assert email_utilizavel("  JOANA@Exemplo.COM  ") == "joana@exemplo.com"


class TestMotorEmHorasCorridas:
    """O acuse corre em relógio de parede (ADR 0042, decisão 1).

    Estes testes existem porque a unidade nova entra num motor cujo default é o
    contrário: todo o resto do módulo pula noite, fim de semana e feriado.
    """

    def test_vinte_e_quatro_horas_corridas_atravessam_a_noite(self):
        sexta_22h = dt.datetime(2026, 9, 4, 22, 0, tzinfo=FUSO)

        vencimento = calcular_vencimento(sexta_22h, Prazo(24, HORAS_CORRIDAS), FERIADOS)

        assert vencimento.astimezone(FUSO) == dt.datetime(2026, 9, 5, 22, 0, tzinfo=FUSO)

    def test_feriado_nao_empurra_o_acuse(self):
        """Domingo véspera de feriado: o calendário útil jogaria o vencimento
        para terça de manhã, e o paciente esperaria dois dias pelo aviso de que
        a manifestação dele chegou."""
        domingo = dt.datetime(2026, 9, 6, 9, 0, tzinfo=FUSO)

        vencimento = calcular_vencimento(domingo, Prazo(24, HORAS_CORRIDAS), FERIADOS)

        assert vencimento.astimezone(FUSO) == dt.datetime(2026, 9, 7, 9, 0, tzinfo=FUSO)

    def test_mesmo_dia_vence_no_fim_do_dia_da_entrada(self):
        """O crítico da tabela: zero hora corrida é "ainda hoje"."""
        manha = dt.datetime(2026, 9, 4, 7, 30, tzinfo=FUSO)

        vencimento = calcular_vencimento(manha, Prazo(0, HORAS_CORRIDAS), FERIADOS)

        no_hospital = vencimento.astimezone(FUSO)
        assert no_hospital.date() == dt.date(2026, 9, 4)
        assert (no_hospital.hour, no_hospital.minute) == (23, 59)

    def test_mesmo_dia_nao_vira_o_dia_de_madrugada(self):
        """Quem manifesta 23h50 tem dez minutos de prazo, e não mais um dia: a
        promessa é o mesmo dia, e o motor não a estica."""
        quase_meia_noite = dt.datetime(2026, 9, 4, 23, 50, tzinfo=FUSO)

        vencimento = calcular_vencimento(quase_meia_noite, Prazo(0, HORAS_CORRIDAS), FERIADOS)

        assert vencimento.astimezone(FUSO).date() == dt.date(2026, 9, 4)


class TestTabelaDePrazos:
    """A migration que abre a tabela de prazos para o marco novo."""

    def test_o_marco_entra_no_check_da_tabela(self):
        assert "'acusar_recebimento'" in _ddl()

    def test_a_unidade_corrida_entra_no_check(self):
        assert "'horas_corridas'" in _ddl()

    def test_o_seed_traz_as_quatro_gravidades(self):
        ddl = _ddl().lower()
        for gravidade in ("critico", "alto", "medio", "baixo"):
            assert f"('{gravidade}', 'acusar_recebimento'" in ddl, (
                f"Gravidade sem célula de acuse na tabela de prazos: {gravidade}"
            )

    def test_o_check_vigente_de_gatilhos_cobre_o_catalogo_inteiro(self):
        """Esta é a migration mais recente a redefinir o CHECK de gatilhos, e
        o último CHECK criado é o que vale: gatilho do catálogo que ficar de
        fora desta lista tem o insert recusado pelo banco em produção, e o
        destinatário nunca recebe nada."""
        ddl = _ddl().lower()
        assert "drop constraint if exists ouvidoria_notificacoes_gatilho_check" in ddl
        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl, f"O CHECK vigente perdeu o gatilho {gatilho}"

    def test_os_carimbos_do_caso_sao_reaplicaveis(self):
        ddl = _ddl().lower()
        assert "add column if not exists acuse_recebimento_em timestamptz" in ddl
        assert "add column if not exists acuse_sem_contato_em timestamptz" in ddl


# ---------------------------------------------------------------------------
# O envio na abertura
# ---------------------------------------------------------------------------

SABADO_DE_MADRUGADA = dt.datetime(2026, 9, 5, 3, 20, tzinfo=FUSO)


class _TabelaFake:
    def __init__(self, banco: _BancoFake, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: dict = {}
        self._insert: dict | None = None
        self._update: dict | None = None
        # O que o Postgres preenche sozinho na linha nova (sequence, coluna
        # gerada, defaults). Vazio nas tabelas em que o teste não precisa.
        self.defaults_do_insert = dict

    def select(self, *_a, **_kw):
        return self

    def insert(self, payload: dict):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, coluna, valor):
        self._filtros[coluna] = valor
        return self

    def limit(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        """A leitura em páginas do PostgREST (issue #430). Recorta de verdade,
        senão o laço de paginação giraria até o teto."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        linhas = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            if self._nome in self._banco.insert_quebra:
                raise self._banco.insert_quebra[self._nome]
            linha = {
                "id": f"{self._nome}-{len(linhas) + 1}",
                **self.defaults_do_insert(),
                **self._insert,
            }
            linhas.append(linha)
            return type("R", (), {"data": [dict(linha)]})()
        casadas = [linha for linha in linhas if all(linha.get(c) == v for c, v in self._filtros.items())]
        if self._update is not None:
            for linha in casadas:
                linha.update(self._update)
        inicio, fim = getattr(self, "_janela", None) or (0, len(casadas))
        return type("R", (), {"data": [dict(linha) for linha in casadas[inicio : fim + 1]]})()


class _BancoFake:
    def __init__(self, casos: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_notificacoes": [],
        }
        self.insert_quebra: dict[str, Exception] = {}

    def table(self, nome: str):
        return _TabelaFake(self, nome)

    @property
    def notificacoes(self) -> list[dict]:
        return self.tabelas["ouvidoria_notificacoes"]

    @property
    def casos(self) -> list[dict]:
        return self.tabelas["ouvidoria_protocolos"]


def _caso(**overrides) -> dict:
    caso = {
        "id": "uuid-7",
        "protocolo": "2026-0007",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com",
        "anonimo": False,
        "gravidade": None,
        "status": "em_classificacao",
    }
    caso.update(overrides)
    return caso


@pytest.fixture
def emails(monkeypatch) -> list[tuple]:
    """Toda saída de email do módulo passa por `_enviar_email`. Nenhum teste
    deste arquivo pode encostar em provedor de verdade."""
    enviados: list[tuple] = []

    def _fake(destinatario, assunto, html, texto=None, **_kw):
        enviados.append((destinatario, assunto, html, texto))
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


class TestAcuseNaAbertura:
    def test_caso_com_email_gera_a_notificacao_com_o_protocolo(self, emails):
        banco = _BancoFake([_caso()])

        ouvidoria_acuse.acusar_recebimento(banco, _caso(), SABADO_DE_MADRUGADA)

        assert len(banco.notificacoes) == 1
        registro = banco.notificacoes[0]
        assert registro["gatilho"] == ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO
        assert registro["destinatario_email"] == "joana@exemplo.com"
        assert registro["papel_destinatario"] == ouvidoria_acuse.PAPEL_MANIFESTANTE
        assert len(emails) == 1
        destinatario, assunto, html, texto = emails[0]
        assert destinatario == "joana@exemplo.com"
        assert "2026-0007" in assunto
        assert "2026-0007" in texto

    def test_o_acuse_nao_espera_o_expediente_abrir(self, emails):
        """Sábado 3h20 da manhã. A janela comercial das notificações internas
        empurraria para segunda de manhã, e as 24 horas corridas já teriam
        vencido antes de o email sair (ADR 0042, decisão 2)."""
        banco = _BancoFake([_caso()])

        ouvidoria_acuse.acusar_recebimento(banco, _caso(), SABADO_DE_MADRUGADA)

        registro = banco.notificacoes[0]
        assert registro["enviar_a_partir_de"] == SABADO_DE_MADRUGADA.isoformat()
        assert len(emails) == 1, "O acuse ficou preso na fila até a próxima abertura do expediente"

    def test_o_caso_fica_carimbado_com_o_acuse(self, emails):
        banco = _BancoFake([_caso()])

        ouvidoria_acuse.acusar_recebimento(banco, _caso(), SABADO_DE_MADRUGADA)

        assert banco.casos[0]["acuse_recebimento_em"] == SABADO_DE_MADRUGADA.isoformat()
        assert banco.casos[0].get("acuse_sem_contato_em") is None

    def test_anonimo_nao_recebe_acuse_e_fica_marcado(self, emails):
        """Anônimo é escolha de quem manifestou: não há a quem escrever, e o
        caso não pode ficar parecendo que o hospital deixou de avisar."""
        anonimo = _caso(anonimo=True, manifestante_nome=None, manifestante_contato=None)
        banco = _BancoFake([anonimo])

        ouvidoria_acuse.acusar_recebimento(banco, anonimo, SABADO_DE_MADRUGADA)

        assert banco.notificacoes == []
        assert emails == []
        assert banco.casos[0]["acuse_sem_contato_em"] == SABADO_DE_MADRUGADA.isoformat()

    def test_anonimo_com_email_no_contato_continua_sem_acuse(self, emails):
        """O pedido de anonimato vence o dado que sobrou no corpo: escrever
        para aquele endereço quebraria a promessa da tela."""
        anonimo = _caso(anonimo=True, manifestante_contato="joana@exemplo.com")
        banco = _BancoFake([anonimo])

        ouvidoria_acuse.acusar_recebimento(banco, anonimo, SABADO_DE_MADRUGADA)

        assert banco.notificacoes == []
        assert emails == []
        assert banco.casos[0]["acuse_sem_contato_em"] == SABADO_DE_MADRUGADA.isoformat()

    def test_contato_sem_email_fica_marcado(self, emails):
        so_telefone = _caso(manifestante_contato="(21) 99999-0000")
        banco = _BancoFake([so_telefone])

        ouvidoria_acuse.acusar_recebimento(banco, so_telefone, SABADO_DE_MADRUGADA)

        assert banco.notificacoes == []
        assert banco.casos[0]["acuse_sem_contato_em"] == SABADO_DE_MADRUGADA.isoformat()
        assert banco.casos[0].get("acuse_recebimento_em") is None

    def test_falha_do_banco_no_registro_nao_sobe(self, emails):
        """A manifestação já existe quando esta função é chamada."""
        banco = _BancoFake([_caso()])
        banco.insert_quebra["ouvidoria_notificacoes"] = APIError(
            {"code": "23514", "message": "violates check constraint"}
        )

        ouvidoria_acuse.acusar_recebimento(banco, _caso(), SABADO_DE_MADRUGADA)

        assert emails == []


# ---------------------------------------------------------------------------
# Os três caminhos de criação
# ---------------------------------------------------------------------------

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "perfil_ouvidoria": "ouvidor"}
RELATO = "Esperei duas horas na recepcao sem nenhuma informacao sobre a demora."


class _BancoDaCriacao(_BancoFake):
    """O banco das rotas: numeração do protocolo como o Postgres faz (sequence
    mais coluna gerada) e a taxonomia de setores que as portas conferem."""

    def __init__(self):
        super().__init__([])
        self.tabelas["setores"] = [{"nome": "Recepção", "ativo": True}]
        self.tabelas["ouvidoria_movimentos"] = []
        self.tabelas["ouvidoria_pontos"] = []
        self.proximo = 7

    def table(self, nome: str):
        tabela = _TabelaFake(self, nome)
        if nome == "ouvidoria_protocolos":
            tabela.defaults_do_insert = self._defaults_do_protocolo
        return tabela

    def _defaults_do_protocolo(self) -> dict:
        numero = self.proximo
        self.proximo += 1
        return {
            "numero": numero,
            "protocolo": f"2026-{numero:04d}",
            "data_abertura": "2026-09-05",
            "prazo_resposta": "2026-09-12",
            "status": "em_classificacao",
        }


def _app_publico(banco):
    from app.routers import ouvidoria_publica

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_publica.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app, follow_redirects=False)


CHAVE_DA_ANA = "chave-teste-ana-para-pytest"


def _app_da_ana(banco, monkeypatch):
    from app.config import settings
    from app.routers import ana

    monkeypatch.setattr(settings, "ana_api_key", CHAVE_DA_ANA)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ana.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: banco
    client = TestClient(app)
    client.headers["X-API-Key"] = CHAVE_DA_ANA
    return client


def _app_do_ouvidor(banco, monkeypatch):
    from app.routers import ouvidoria as ouvidoria_router

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _registro_manual(**overrides) -> dict:
    corpo = {
        "canal": "telefone",
        # Sábado de madrugada, e no passado: o T0 é a hora em que a
        # manifestação chegou ao hospital, e a rota recusa data no futuro.
        "contato_em": "2026-08-29T03:20:00-03:00",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepção",
        "resumo": "Espera longa na recepcao.",
        "relato_integral": RELATO,
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com",
    }
    corpo.update(overrides)
    return corpo


def _registro_da_ana(**overrides) -> dict:
    corpo = {
        "categoria": "Demora",
        "setor": "Recepção",
        "resumo": "Espera longa na recepcao.",
        "relato_integral": RELATO,
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com",
    }
    corpo.update(overrides)
    return corpo


class TestOsTresCaminhosDeCriacao:
    """O acuse é do CASO, não do canal: quem manifesta pelo cartaz da parede
    recebe o mesmo aviso de quem liga para o balcão (ADR 0042, decisão 2)."""

    def test_formulario_publico_gera_o_acuse(self, emails):
        banco = _BancoDaCriacao()
        client = _app_publico(banco)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": RELATO, "nome": "Joana da Silva", "contato": "joana@exemplo.com"},
        )

        assert r.status_code == 201
        assert [n["gatilho"] for n in banco.notificacoes] == [ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO]
        assert r.json()["protocolo"] in emails[0][3]

    def test_api_da_ana_gera_o_acuse(self, emails, monkeypatch):
        banco = _BancoDaCriacao()
        client = _app_da_ana(banco, monkeypatch)

        r = client.post("/api/ana/ouvidoria/protocolos", json=_registro_da_ana())

        assert r.status_code == 201
        assert [n["gatilho"] for n in banco.notificacoes] == [ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO]

    def test_registro_manual_gera_o_acuse(self, emails, monkeypatch):
        banco = _BancoDaCriacao()
        client = _app_do_ouvidor(banco, monkeypatch)

        r = client.post("/api/ouvidoria/manifestacoes", json=_registro_manual())

        assert r.status_code == 201
        assert [n["gatilho"] for n in banco.notificacoes] == [ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO]

    def test_formulario_publico_anonimo_marca_e_nao_avisa(self, emails):
        banco = _BancoDaCriacao()
        client = _app_publico(banco)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": RELATO, "anonimo": True, "contato": "joana@exemplo.com"},
        )

        assert r.status_code == 201
        assert banco.notificacoes == []
        assert emails == []
        assert banco.casos[0]["acuse_sem_contato_em"] is not None


class TestFalhaDoAcuseNaoDerrubaAManifestacao:
    """O contrato desta fatia. A manifestação já foi prometida a quem
    manifestou: o email é o acessório, o caso é o principal.

    A falha é REAL (o insert da notificação recusado pelo banco), e não a
    função inteira trocada por uma que levanta: assim o teste continua valendo
    o dia em que a blindagem mudar de lugar."""

    def _quebrar(self, banco):
        banco.insert_quebra["ouvidoria_notificacoes"] = APIError(
            {"code": "23514", "message": "violates check constraint"}
        )

    def test_formulario_publico_registra_mesmo_com_o_acuse_quebrado(self, emails):
        banco = _BancoDaCriacao()
        self._quebrar(banco)
        client = _app_publico(banco)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": RELATO, "contato": "joana@exemplo.com"},
        )

        assert r.status_code == 201
        assert r.json()["protocolo"] == "2026-0007"
        assert len(banco.casos) == 1

    def test_api_da_ana_registra_mesmo_com_o_acuse_quebrado(self, emails, monkeypatch):
        banco = _BancoDaCriacao()
        self._quebrar(banco)
        client = _app_da_ana(banco, monkeypatch)

        r = client.post("/api/ana/ouvidoria/protocolos", json=_registro_da_ana())

        assert r.status_code == 201
        assert len(banco.casos) == 1

    def test_registro_manual_registra_mesmo_com_o_acuse_quebrado(self, emails, monkeypatch):
        banco = _BancoDaCriacao()
        self._quebrar(banco)
        client = _app_do_ouvidor(banco, monkeypatch)

        r = client.post("/api/ouvidoria/manifestacoes", json=_registro_manual())

        assert r.status_code == 201
        assert len(banco.casos) == 1


# ---------------------------------------------------------------------------
# A célula do acuse na tabela de prazos
# ---------------------------------------------------------------------------

DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "perfil_ouvidoria": "diretoria_executiva",
}


class TestEdicaoDaCelulaDoAcuse:
    """O acuse é o ÚNICO marco fora do Calendário útil (ADR 0042, decisão 1).

    A tela é editável pela Diretoria, e sem estas duas guardas ela poderia
    trocar o relógio de parede do acuse pelo calendário útil (a promessa de
    sábado viraria terça) ou tirar a resposta da área do calendário útil (o
    setor passaria a ser cobrado no domingo).
    """

    def _banco(self):
        banco = _BancoDaCriacao()
        banco.tabelas["ouvidoria_prazos"] = [
            {"gravidade": "alto", "marco": "acusar_recebimento", "valor": 24, "unidade": "horas_corridas"},
            {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
        ]
        banco.tabelas["ouvidoria_prazos_historico"] = []
        return banco

    def _client(self, banco, monkeypatch):
        from app.routers import ouvidoria as ouvidoria_router

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(RequestContextMiddleware)
        app.include_router(ouvidoria_router.router, prefix="/api")

        async def _fake_participante(_user, _sb, fields=None):
            return DIRETORIA

        monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
        app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
        app.dependency_overrides[get_supabase_client] = lambda: banco
        return TestClient(app)

    def test_a_diretoria_edita_o_acuse_em_horas_corridas(self, monkeypatch):
        banco = self._banco()
        client = self._client(banco, monkeypatch)

        r = client.put(
            "/api/ouvidoria/prazos/alto/acusar_recebimento",
            json={"valor": 12, "unidade": "horas_corridas"},
        )

        assert r.status_code == 200
        assert banco.tabelas["ouvidoria_prazos"][0]["valor"] == 12

    def test_o_acuse_nao_volta_para_o_calendario_util(self, monkeypatch):
        banco = self._banco()
        client = self._client(banco, monkeypatch)

        r = client.put(
            "/api/ouvidoria/prazos/alto/acusar_recebimento",
            json={"valor": 24, "unidade": "horas_uteis"},
        )

        assert r.status_code == 422
        assert banco.tabelas["ouvidoria_prazos"][0]["unidade"] == "horas_corridas"

    def test_nenhum_outro_marco_sai_do_calendario_util(self, monkeypatch):
        banco = self._banco()
        client = self._client(banco, monkeypatch)

        r = client.put(
            "/api/ouvidoria/prazos/alto/area_resposta",
            json={"valor": 24, "unidade": "horas_corridas"},
        )

        assert r.status_code == 422
        assert banco.tabelas["ouvidoria_prazos"][1]["unidade"] == "dias_uteis"


# ---------------------------------------------------------------------------
# O marco no detalhe do caso
# ---------------------------------------------------------------------------


class TestMarcoNoDetalheDoCaso:
    """A promessa ao paciente aparece na página do caso (RN-56).

    Sem ela, o ouvidor não tem como responder "o senhor recebeu o aviso?" sem
    abrir o registro de notificações, e o caso anônimo ficaria indistinguível
    de um caso em que o hospital deixou de avisar.
    """

    def _acuse(self, **campos) -> dict:
        from app.services.ouvidoria_marcos import marcos_do_caso

        caso = {"status": "em_classificacao", "contato_em": "2026-08-29T06:20:00+00:00", **campos}
        return marcos_do_caso(caso, dt.datetime(2026, 8, 31, 12, 0, tzinfo=FUSO), frozenset())["acuse"]

    def test_caso_avisado_mostra_quando(self):
        acuse = self._acuse(acuse_recebimento_em="2026-08-29T06:21:00+00:00")

        assert acuse["situacao"] == "enviado"
        assert acuse["em"] is not None

    def test_caso_sem_canal_mostra_a_marcacao_propria(self):
        acuse = self._acuse(acuse_sem_contato_em="2026-08-29T06:21:00+00:00")

        assert acuse["situacao"] == "sem_contato"
        assert acuse["em"] is not None
        assert acuse["nota"], "A tela precisa dizer POR QUE ninguém foi avisado"

    def test_caso_antigo_fica_pendente_sem_inventar_data(self):
        """Todo caso aberto antes desta fatia: nem avisado, nem marcado."""
        acuse = self._acuse()

        assert acuse["situacao"] == "pendente"
        assert acuse["em"] is None

    def test_o_dossie_entrega_o_acuse_e_os_carimbos(self, monkeypatch, emails):
        banco = _BancoDaCriacao()
        client = _app_do_ouvidor(banco, monkeypatch)
        criado = client.post("/api/ouvidoria/manifestacoes", json=_registro_manual())
        assert criado.status_code == 201

        # A porta que a página do caso usa: é ela que devolve o Dossiê com os
        # marcos e os prazos já contados no servidor.
        r = client.get(f"/api/ouvidoria/manifestacoes/por-protocolo/{criado.json()['protocolo']}")

        assert r.status_code == 200
        dossie = r.json()
        assert dossie["acuse"]["situacao"] == "enviado"
        assert dossie["acuse_recebimento_em"] is not None
