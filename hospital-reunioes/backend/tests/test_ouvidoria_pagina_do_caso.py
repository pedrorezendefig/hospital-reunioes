"""O caso endereçável pelo protocolo (issue #476, PRD #468, RN-53).

A página do caso deixa de ser um modal sem endereço e passa a viver em
`/ouvidoria/m/{protocolo}`. Quem alimenta essa página é a rota desta suíte: o
Dossiê procurado pelo protocolo, que é o identificador público do caso (ele vai
no email do manifestante e no do setor).

Endereço público não é permissão. O protocolo na URL é adivinhável por
construção (ano e sequência), então a porta precisa se comportar igual para
quem está fora da Ouvidoria diante de um caso que existe e de um que não
existe: se a recusa mudasse de forma, a URL viraria um oráculo de quantas
manifestações o hospital recebeu e quais delas são sigilosas.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import httpx
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

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

AGORA = dt.datetime(2026, 9, 1, 17, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "em_classificacao",
        "tipo_manifestacao": None,
        "categoria": "A classificar",
        "setor": "A definir",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
        "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "gravidade": None,
        "prazo_area_em": None,
        "prazo_conclusivo_em": None,
        "validada_em": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa aqui: o select projeta só as
    colunas pedidas e o filtro casa linha por igualdade."""

    def __init__(self, nome: str, rows: list[dict], consultas: list[tuple[str, dict]], falhas: set[str] | None = None):
        self.nome = nome
        self.rows = rows
        self.consultas = consultas
        self.falhas = falhas if falhas is not None else set()
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        """Abrir o Dossiê escreve: é aqui que o visto da Ouvidoria é carimbado
        (issue #484)."""
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def limit(self, _quantas):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        # O calendário de feriados é lido em páginas (`ler_tudo`), e o recorte
        # precisa recortar de verdade: fake que devolve a página inteira toda
        # volta deixaria o laço girando até o teto de páginas.
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self.nome in self.falhas:
            raise httpx.ReadTimeout(f"o PostgREST nao respondeu por {self.nome}")
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = [dict(n) for n in novos]
            self.rows.extend(gravados)
            return type("R", (), {"data": gravados})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        self.consultas.append((self.nome, dict(self._filters)))
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, feriados: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [],
            "ouvidoria_acessos": [],
            "ouvidoria_movimentos": [],
            # O calendário útil, que a página do caso lê para contar o tempo
            # decorrido de cada trecho em dias úteis (issue #480).
            "ouvidoria_feriados": feriados if feriados is not None else [],
        }
        # A trilha das leituras: é por ela que se prova o que NÃO foi ao banco.
        self.consultas: list[tuple[str, dict]] = []
        # As tabelas cuja leitura está fora do ar, para provar o fail-open do
        # calendário sem derrubar a leitura do caso junto.
        self.falhas: set[str] = set()

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.consultas, self.falhas)


_SESSAO: dict = {"participante": None}


def _entrar_como(participante: dict | None) -> None:
    _SESSAO["participante"] = participante


def _client(monkeypatch, participante: dict | None, supabase: _SupabaseFake | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()
    _entrar_como(participante)

    async def _fake_participante(_user, _sb, fields=None):
        return _SESSAO["participante"]

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _abrir(client, protocolo: str):
    return client.get(f"/api/ouvidoria/manifestacoes/por-protocolo/{protocolo}")


class TestProtocoloValido:
    """O caminho feliz: a página do caso pede o Dossiê pelo endereço que o
    manifestante tem em mãos."""

    def test_ouvidor_abre_o_dossie_completo_pelo_protocolo(self, monkeypatch):
        caso = _manifestacao()
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = _abrir(client, "2026-0007")

        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["id"] == "uuid-7"
        assert corpo["protocolo"] == "2026-0007"
        # O que separa o Dossiê do índice: relato e identificação do
        # manifestante só existem aqui.
        assert corpo["relato_integral"] == caso["relato_integral"]
        assert corpo["manifestante_nome"] == "Joana da Silva"

    def test_a_diretoria_executiva_tambem_abre(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA, _SupabaseFake([_manifestacao()]))

        assert _abrir(client, "2026-0007").status_code == 200

    def test_abrir_pelo_protocolo_deixa_rastro_no_log_de_acesso(self, monkeypatch):
        """RN-53: quem leu o caso e quando. O endereço novo não pode ser a
        porta que entra sem assinar o livro."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao()]))

        _abrir(client, "2026-0007")

        acessos = supabase.tabelas["ouvidoria_acessos"]
        assert len(acessos) == 1
        assert acessos[0]["manifestacao_id"] == "uuid-7"
        assert acessos[0]["ator_id"] == "P10"
        assert acessos[0]["acao"] == "abrir_dossie"


class TestProtocoloInexistente:
    def test_protocolo_que_nao_existe_da_nao_encontrado(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao()]))

        r = _abrir(client, "2026-9999")

        assert r.status_code == 404
        # Não é 404 de rota inexistente: a busca aconteceu e não achou.
        assert ("ouvidoria_protocolos", {"protocolo": "2026-9999"}) in supabase.consultas

    def test_protocolo_malformado_nao_chega_ao_banco(self, monkeypatch):
        """O protocolo tem forma fixa (ano e sequência). Texto que não é
        protocolo é recusado antes de virar filtro do PostgREST, e a resposta é
        a mesma do caso inexistente: quem sonda não descobre nem a régua."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao()]))

        r = _abrir(client, "2026-0007) or protocolo=neq.x")

        assert r.status_code == 404
        assert supabase.consultas == []

    def test_o_caso_inexistente_nao_deixa_rastro_no_log(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao()]))

        _abrir(client, "2026-9999")

        assert supabase.tabelas["ouvidoria_acessos"] == []


class TestBancoIndisponivel:
    """Falha de leitura não é caso inexistente."""

    def test_falha_do_postgrest_nao_vira_nao_encontrado(self, monkeypatch):
        """O timeout do PostgREST sobe como erro do httpx, e não como APIError
        (a APIError só nasce depois de haver resposta). Se ele escapasse, a
        página mostraria erro genérico; se virasse 404, o ouvidor concluiria
        que o protocolo do email está errado e iria atrás do manifestante."""
        supabase = _SupabaseFake([_manifestacao()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        def _cai(*_a, **_kw):
            raise httpx.ReadTimeout("o PostgREST nao respondeu")

        monkeypatch.setattr(_TabelaFake, "execute", _cai)

        r = _abrir(client, "2026-0007")

        assert r.status_code == 503


class TestSemPerfilDaOuvidoria:
    """A rota nova é uma superfície de acesso nova: o gate dela é o mesmo do
    Dossiê, e vale para o super admin das Reuniões também (ADR 0034)."""

    def test_secretaria_e_recusada(self, monkeypatch):
        client, _ = _client(monkeypatch, SECRETARIA, _SupabaseFake([_manifestacao()]))

        r = _abrir(client, "2026-0007")

        assert r.status_code == 403
        # A recusa não pode carregar pedaço do caso junto.
        assert "Joana" not in r.text
        assert "recepcao" not in r.text.lower()

    def test_super_admin_das_reunioes_nao_herda_a_ouvidoria(self, monkeypatch):
        client, _ = _client(monkeypatch, SUPER_ADMIN, _SupabaseFake([_manifestacao()]))

        assert _abrir(client, "2026-0007").status_code == 403

    def test_quem_e_recusado_nao_entra_no_log_de_acesso(self, monkeypatch):
        client, supabase = _client(monkeypatch, SECRETARIA, _SupabaseFake([_manifestacao()]))

        _abrir(client, "2026-0007")

        assert supabase.tabelas["ouvidoria_acessos"] == []
        # O gate corre ANTES da leitura: o caso nem foi procurado.
        assert supabase.consultas == []


# O caso inteiro, marco a marco, em UTC (o expediente é 08h às 17h de Brasília,
# ou seja, 11h às 20h aqui).
ENTRADA = "2026-08-14T19:00:00+00:00"  # sexta, 16h
VALIDACAO = "2026-08-17T12:00:00+00:00"  # segunda, 9h
RESPOSTA = "2026-08-18T13:00:00+00:00"  # terça, 10h
CONCLUSAO = "2026-08-20T14:00:00+00:00"  # quinta, 11h


def _caso_percorrido(**overrides) -> dict:
    return _manifestacao(
        status="encerrado",
        contato_em=ENTRADA,
        gravidade="medio",
        validada_em=VALIDACAO,
        respondida_em=RESPOSTA,
        encerrada_em=CONCLUSAO,
        prazo_area_em="2026-08-19T20:00:00+00:00",
        prazo_conclusivo_em="2026-08-25T20:00:00+00:00",
        **overrides,
    )


class TestOsQuatroMarcos:
    """Os quatro marcos com tempo decorrido na página do caso (issue #480).

    A régua vive no módulo puro `ouvidoria_marcos`, com testes próprios. O que
    só existe aqui é a fiação: a rota que alimenta a página precisa entregar os
    marcos JÁ contados, e contados com o calendário do hospital, que só ela
    sabe carregar (D-05, RN-55).
    """

    def test_a_rota_entrega_os_quatro_marcos_e_os_dois_prazos(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_caso_percorrido()]))

        corpo = _abrir(client, "2026-0007").json()

        assert [m["chave"] for m in corpo["marcos"]] == ["T0", "T1", "T2", "T3"]
        assert [m["em"] for m in corpo["marcos"]] == [ENTRADA, VALIDACAO, RESPOSTA, CONCLUSAO]
        assert [p["chave"] for p in corpo["prazos"]] == ["area", "conclusivo"]

    def test_o_feriado_cadastrado_entra_na_conta_do_tempo_decorrido(self, monkeypatch):
        """O trecho da conclusão atravessa uma quarta-feira. Com ela cadastrada
        como feriado, o caso levou 9 horas úteis a menos. Se a rota contasse com
        o calendário vazio, o número sairia maior e a Ouvidoria apareceria mais
        lenta do que foi, sem nada na tela dizendo que faltou calendário."""
        supabase = _SupabaseFake([_caso_percorrido()], feriados=[{"data": "2026-08-19"}])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _abrir(client, "2026-0007").json()

        assert corpo["marcos"][3]["minutos_uteis"] == 600
        assert corpo["degradado"] == []

    def test_sem_feriado_cadastrado_a_quarta_conta_como_dia_de_trabalho(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_caso_percorrido()]))

        corpo = _abrir(client, "2026-0007").json()

        assert corpo["marcos"][3]["minutos_uteis"] == 1140

    def test_calendario_fora_do_ar_abre_a_pagina_e_declara_a_degradacao(self, monkeypatch):
        """Fail-open com a marca junto (issue #449): o caso abre, mas a tela
        precisa poder dizer "sem confirmação do calendário" em vez de afirmar
        dias úteis que saíram de uma leitura que falhou."""
        supabase = _SupabaseFake([_caso_percorrido()], feriados=[{"data": "2026-08-19"}])
        supabase.falhas.add("ouvidoria_feriados")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = _abrir(client, "2026-0007")

        assert r.status_code == 200, r.text
        assert r.json()["degradado"] == ["feriados"]
        # E o número saiu contado sem o feriado, que é justamente o que a marca
        # acima avisa.
        assert r.json()["marcos"][3]["minutos_uteis"] == 1140

    def test_o_caso_ainda_na_fila_nao_inventa_marco_nem_prazo(self, monkeypatch):
        """Sem data inventada e sem prazo inventado: o caso que ainda não foi
        validado tem só a entrada, e os dois prazos saem do despacho."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(contato_em=ENTRADA)]))

        corpo = _abrir(client, "2026-0007").json()

        assert corpo["marcos"][0]["em"] == ENTRADA
        assert all(m["pendente"] is True for m in corpo["marcos"][1:])
        assert all(p["situacao"] == "aguardando_validacao" for p in corpo["prazos"])


class TestSigiloReforcado:
    def test_caso_sigiloso_abre_para_a_ouvidoria_e_vai_para_o_log(self, monkeypatch):
        sigiloso = _manifestacao(numero=8, tipo_manifestacao="denuncia", sigilo_reforcado=True)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([sigiloso]))

        r = _abrir(client, "2026-0008")

        assert r.status_code == 200, r.text
        assert r.json()["sigilo_reforcado"] is True
        assert supabase.tabelas["ouvidoria_acessos"][0]["manifestacao_id"] == "uuid-8"

    def test_o_protocolo_na_url_nao_diz_se_o_caso_existe(self, monkeypatch):
        """O teste do oráculo. Para quem está fora da Ouvidoria, o caso
        sigiloso que EXISTE e o protocolo que NÃO existe precisam responder a
        mesma coisa, byte a byte: status, corpo e a ausência de rastro no log.

        Se um deles respondesse 404 e o outro 403, bastaria varrer a sequência
        do ano para saber quantas manifestações o hospital recebeu.
        """
        sigiloso = _manifestacao(numero=8, tipo_manifestacao="denuncia", sigilo_reforcado=True)
        client, supabase = _client(monkeypatch, SUPER_ADMIN, _SupabaseFake([sigiloso]))

        existente = _abrir(client, "2026-0008")
        inexistente = _abrir(client, "2026-9999")

        assert existente.status_code == inexistente.status_code == 403
        assert existente.json() == inexistente.json()
        assert supabase.tabelas["ouvidoria_acessos"] == []
        assert supabase.consultas == []
