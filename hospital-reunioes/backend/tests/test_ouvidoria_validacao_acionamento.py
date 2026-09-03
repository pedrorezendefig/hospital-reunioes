"""Validação, responsáveis do setor e email de acionamento (issue #325, PRD #317).

O coração da tramitação: o ouvidor confere tipo, área e gravidade, o motor de
prazos (issue #322) calcula o vencimento, o sistema acha o titular vigente do
setor e dispara o email NOVA_DEMANDA. Nenhum processo automático despacha
(ADR 0034, decisão 3).

Cobre os critérios de aceite da issue #325 pelo seam HTTP, mais as regras de
vigência e de janela de envio como funções puras. O Resend nunca é chamado de
verdade: o envio é mockado no ponto único por onde todo email do app passa.
"""

from __future__ import annotations

import datetime as dt
import os
import re
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
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

# O relato cru de quem manifestou, com nome e leito. Nasce assim no canal
# aberto (o #348 grava os primeiros ~200 caracteres do formulário público) e é
# exatamente o que não pode sair da Ouvidoria por email.
RELATO_CRU = "Sou a Maria Silva, do leito 302, e o enfermeiro Joao me destratou na madrugada de ontem."
EXTRATO = "Conduta da equipe de enfermagem no plantao noturno. Apurar e responder a Ouvidoria."

# Todo acionamento leva o extrato escrito pelo ouvidor, sem exceção, então ele
# faz parte do pedido de validação em qualquer cenário.
VALIDACAO = {
    # O tipo é lista fechada e é ele que decide o sigilo (issue #372); a
    # categoria continua existindo, como rótulo humano do caso.
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "gravidade": "medio",
    "extrato_para_o_setor": EXTRATO,
}
SEM_EXTRATO = {campo: valor for campo, valor in VALIDACAO.items() if campo != "extrato_para_o_setor"}

# Terça-feira, 14h de Brasília: dentro do expediente e longe de feriado. O
# relógio é congelado porque a janela comercial e o cálculo do prazo dependem
# dele; sem congelar, o mesmo teste passaria de manhã e falharia de madrugada.
DENTRO_DO_EXPEDIENTE = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
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
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "em_classificacao",
        "categoria": "A classificar",
        "setor": "A definir",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
        "contato_em": "2026-08-14T19:50:00+00:00",
        "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "gravidade": None,
        "prazo_area_em": None,
        "prazo_conclusivo_em": None,
        "validada_em": None,
        "validada_por": None,
    }
    row.update(overrides)
    return row


def _responsavel(papel: str = "titular", **overrides) -> dict:
    row = {
        "id": f"resp-{papel}",
        "setor": "Recepcao",
        "papel": papel,
        "nome": "Carlos Titular",
        "email": "carlos@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    row.update(overrides)
    return row


# Seed da migration 065, as doze células. A tabela inteira, e não só a coluna
# da área, porque a validação lê duas delas: `area_resposta` para o prazo do
# setor e `conclusiva` para o prazo do caso (issue #479). Com só uma coluna
# aqui, trocar o marco no código não mudaria número nenhum e o teste passaria
# verde por engano.
PRAZOS = [
    {"gravidade": "critico", "marco": "triagem", "valor": 0, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "critico", "marco": "conclusiva", "valor": None, "unidade": "dias_uteis"},
    {"gravidade": "alto", "marco": "triagem", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "alto", "marco": "conclusiva", "valor": 5, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "conclusiva", "valor": 7, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "triagem", "valor": 1, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "conclusiva", "valor": 2, "unidade": "dias_uteis"},
]


# O teto de linhas que uma resposta do PostgREST traz sem paginação.
TETO_POSTGREST = 1000


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido e o insert devolve a linha com o id que o banco geraria."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None

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

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        self._filters[col] = None if value in ("null", None) else value
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, _n):
        return self

    def range(self, inicio, fim):
        # O PostgREST corta a resposta na faixa pedida (e num teto próprio de
        # linhas). Quem lê o banco inteiro pagina; o fake corta igual, senão o
        # teste de paginação passaria sem paginação nenhuma (issue #419).
        self._faixa = (inicio, fim)
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
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        if self._delete:
            for r in casadas:
                self.rows.remove(r)
            # O PostgREST devolve as linhas REMOVIDAS (return=representation),
            # e é por elas que a rota sabe se apagou alguma (issue #375).
            return type("R", (), {"data": [self._projetar(r) for r in casadas]})()
        faixa = getattr(self, "_faixa", None)
        if faixa is not None:
            casadas = casadas[faixa[0] : faixa[1] + 1]
        # O PostgREST tem teto próprio de linhas por resposta (`db-max-rows`):
        # quem quer a tabela inteira pagina, e quem não pagina recebe a
        # primeira fatia sem aviso nenhum. O fake corta igual (issue #419).
        casadas = casadas[:TETO_POSTGREST]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _TabelaComIdUuid(_TabelaFake):
    """A coluna `id` de `ouvidoria_setor_responsaveis` é UUID (migration 068).
    Filtrar por texto que não é UUID faz o PostgREST recusar com 22P02, e não
    devolver zero linhas: o fake precisa recusar o mesmo que ele recusa
    (issue #375)."""

    def eq(self, col, value):
        if col == "id" and not re.fullmatch(r"[0-9a-fA-F-]{36}", str(value)):
            self._id_invalido = True
        return super().eq(col, value)

    def execute(self):
        if getattr(self, "_id_invalido", False):
            from postgrest.exceptions import APIError

            raise APIError({"code": "22P02", "message": "invalid input syntax for type uuid"})
        return super().execute()


class _TabelaQueFalha(_TabelaFake):
    """Leitura, escrita ou remoção que estoura como o PostgREST fora do ar.
    Existe para exercitar os `except` de verdade: monkeypatch da função que lê
    pula o bloco que a guarda protege (issue #375, item 3)."""

    def execute(self):
        from postgrest.exceptions import APIError

        raise APIError({"message": 'relation "ouvidoria_setor_responsaveis" does not exist', "code": "42P01"})


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, responsaveis: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_setor_responsaveis": responsaveis if responsaveis is not None else [_responsavel()],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            # `ativo` espelha a tabela real (DEFAULT true desde a
            # `001_create_participantes.sql`): quem é desligado do hospital vira
            # `ativo: False` e para de ser lido como Diretoria (issue #403).
            "participantes": [
                {"id": "P11", "nome_completo": "Dr. Diretor", "email": "diretor@hsm.br", "ativo": True},
                {"id": "P03", "nome_completo": "Pedro Admin", "email": "admin@hsm.br", "ativo": True},
            ],
        }
        # Tabelas cuja operação estoura, para exercitar os `except` de verdade.
        self.indisponiveis: set[str] = set()
        # A coluna `id` do cadastro de responsáveis é UUID no banco real.
        self.id_e_uuid = False

    def table(self, nome: str):
        if nome in self.indisponiveis:
            return _TabelaQueFalha(nome, self.tabelas.setdefault(nome, []))
        if self.id_e_uuid and nome == "ouvidoria_setor_responsaveis":
            return _TabelaComIdUuid(nome, self.tabelas.setdefault(nome, []))
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar` (migration 064): estado e
        movimento na mesma transação."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        alvo["status"] = params["p_estado_novo"]
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_id": params["p_autor_id"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


def _client(
    monkeypatch,
    participante: dict | None,
    supabase: _SupabaseFake | None = None,
    agora: dt.datetime = DENTRO_DO_EXPEDIENTE,
):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestValidarEAcionar:
    """O ouvidor confere tipo, área e gravidade, e a área é acionada na hora."""

    def test_validacao_leva_para_aguardando_area_e_dispara_o_email_ao_titular(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Primeiro critério de aceite: a manifestação em classificação vira
        aguardando área, grava T1 e quem validou, e o titular vigente do setor
        recebe o email de acionamento."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["categoria"] == "Demora no atendimento"
        assert caso["setor"] == "Recepcao"
        assert caso["gravidade"] == "medio"
        assert caso["validada_em"], "T1 é o marco da validação: sem ele não há como medir a triagem"
        assert caso["validada_por"] == "P10"
        assert caso["prazo_area_em"], "O vencimento é persistido no acionamento, nunca derivado depois"
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

    def test_validacao_nao_sobrescreve_a_classificacao_sugerida_pela_ana(self, monkeypatch):
        """ADR 0034, decisão 10: a sugestão da IA fica guardada à parte e a
        decisão humana é a que vale. Uma não apaga a outra."""
        caso = _manifestacao(classificacao_ia={"gravidade_sugerida": "baixo", "confianca": 0.4})
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "alto"})

        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["gravidade"] == "alto"
        assert gravado["classificacao_ia"] == {"gravidade_sugerida": "baixo", "confianca": 0.4}

    def test_transicao_recusada_nao_carimba_o_marco_t1_nem_o_prazo(self, monkeypatch):
        """T1 é o marco de uma transição que aconteceu. Se a corrida com outra
        transição recusar o passo, o caso não pode ficar com hora de validação
        e prazo da área de um acionamento que nunca existiu."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        def _rpc_recusa(_nome, _params):
            raise APIError({"code": "23514", "message": "Transicao invalida"})

        monkeypatch.setattr(supabase, "rpc", _rpc_recusa)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 409
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["validada_em"] is None
        assert caso["validada_por"] is None
        assert caso["prazo_area_em"] is None
        assert caso["prazo_conclusivo_em"] is None, "O prazo conclusivo nasce do mesmo despacho que nunca existiu"
        assert supabase.tabelas["ouvidoria_notificacoes"] == [], "Setor não é acionado por transição recusada"

    def test_caso_ja_acionado_nao_e_acionado_de_novo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A porta do despacho é única: repetir a validação de um caso que já
        está com a área acordaria o setor duas vezes pelo mesmo motivo."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(status="aguardando_area")]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 409
        assert _nunca_envia_email_de_verdade == []


class TestPrazoConclusivoCongelado:
    """Issue #479 (PRD #468, D-10, RN-55): a validação também congela o prazo
    de dar o desfecho ao manifestante, contado do T0.

    Os números abaixo são literais de propósito. Recalculá-los no teste com o
    mesmo motor que o código usa deixaria passar o erro que mais importa aqui:
    contar o prazo do instante da validação em vez do T0, ou ler a célula
    errada da tabela. Com o T0 em 14/08 e a validação em 25/08, marco trocado
    ou origem trocada muda a data, e o teste acusa.
    """

    # T0 do caso: 14/08/2026, sexta, 16h50 de Brasília (`contato_em`).
    # Conclusiva do médio: 7 dias úteis, vencendo no fechamento do sétimo.
    CONCLUSIVO_MEDIO = "2026-08-25T20:00:00+00:00"
    # Prazo da área do médio: 4 dias úteis contados da validação (25/08). Fica
    # bem longe do conclusivo, então trocar um pelo outro no código aparece.
    AREA_MEDIO = "2026-08-31T20:00:00+00:00"

    def _valor(self, supabase, campo: str):
        bruto = supabase.tabelas["ouvidoria_protocolos"][0][campo]
        return dt.datetime.fromisoformat(str(bruto)) if bruto else None

    def test_validacao_congela_o_prazo_conclusivo_contado_do_t0(self, monkeypatch):
        """O vencimento conclusivo é gravado no caso, contado da ENTRADA da
        manifestação e não do instante da validação."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200, r.text
        assert self._valor(supabase, "prazo_conclusivo_em") == dt.datetime.fromisoformat(self.CONCLUSIVO_MEDIO)
        assert self._valor(supabase, "prazo_area_em") == dt.datetime.fromisoformat(self.AREA_MEDIO)

    def test_o_t0_e_a_hora_real_do_contato_e_nao_a_data_de_abertura(self, monkeypatch):
        """`contato_em` é o instante que o ouvidor digita no registro manual, e
        ele pode ser dias antes ou depois da abertura do protocolo. É ele o T0
        do caso, como já é para o teto de prorrogação e para as métricas.

        O caso abaixo tem as duas datas separadas de propósito: contar da
        abertura daria 25/08, e contar do contato dá 27/08."""
        caso = _manifestacao(contato_em="2026-08-18T13:00:00+00:00", data_abertura="2026-08-14")
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200, r.text
        assert self._valor(supabase, "prazo_conclusivo_em") == dt.datetime.fromisoformat("2026-08-27T20:00:00+00:00")

    def test_gravidade_sem_conclusiva_na_tabela_deixa_a_coluna_nula(self, monkeypatch):
        """Crítico não tem prazo conclusivo fixo na tabela da Diretoria (valor
        nulo na migration 065): o sistema não inventa data.

        O prazo da área do crítico existe (4 horas úteis) e é conferido junto:
        sem essa segunda asserção, o teste passaria verde também se a validação
        tivesse parado de gravar prazo nenhum."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "critico"})

        assert r.status_code == 200, r.text
        assert self._valor(supabase, "prazo_conclusivo_em") is None
        assert self._valor(supabase, "prazo_area_em") is not None, "Crítico tem prazo de área: 4 horas úteis"

    def test_gravidade_sem_prazo_de_area_ainda_tem_prazo_conclusivo(self, monkeypatch):
        """O avesso do caso acima: baixo não passa pela área (valor nulo), mas
        tem 2 dias úteis de conclusiva. As duas colunas são independentes, e é
        essa gravidade que prova."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "baixo"})

        assert r.status_code == 200, r.text
        assert self._valor(supabase, "prazo_area_em") is None
        assert self._valor(supabase, "prazo_conclusivo_em") == dt.datetime.fromisoformat("2026-08-18T20:00:00+00:00")

    def test_editar_a_tabela_de_prazos_depois_nao_recalcula_caso_ja_validado(self, monkeypatch):
        """RN-21: o vencimento do caso despachado está congelado. A Diretoria
        pode dobrar a célula conclusiva amanhã que o caso de ontem não anda."""
        client, supabase = _client(monkeypatch, OUVIDOR)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        congelado = self._valor(supabase, "prazo_conclusivo_em")

        diretoria, _ = _client(monkeypatch, DIRETORIA, supabase)
        r = diretoria.put("/api/ouvidoria/prazos/medio/conclusiva", json={"valor": 20, "unidade": "dias_uteis"})

        assert r.status_code == 200, r.text
        celula = next(
            p for p in supabase.tabelas["ouvidoria_prazos"] if (p["gravidade"], p["marco"]) == ("medio", "conclusiva")
        )
        assert celula["valor"] == 20, "A edição precisa ter valido de verdade"
        assert self._valor(supabase, "prazo_conclusivo_em") == congelado

        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-7")
        assert dossie.status_code == 200, dossie.text
        assert dt.datetime.fromisoformat(dossie.json()["prazo_conclusivo_em"]) == congelado

    def test_o_dossie_devolve_o_prazo_conclusivo(self, monkeypatch):
        """A API que alimenta a página do caso entrega o campo novo. Sem ele na
        resposta, a fatia dos quatro marcos não teria o que exibir."""
        client, _ = _client(monkeypatch, OUVIDOR)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert r.status_code == 200, r.text
        assert "prazo_conclusivo_em" in r.json()
        assert dt.datetime.fromisoformat(r.json()["prazo_conclusivo_em"]) == dt.datetime.fromisoformat(
            self.CONCLUSIVO_MEDIO
        )


class TestGateDaValidacao:
    """Nenhum setor é acionado por quem não é da Ouvidoria (ADR 0034, decisão 3)."""

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_quem_nao_e_da_ouvidoria_nao_valida_nem_pela_api(
        self, monkeypatch, participante, _nunca_envia_email_de_verdade
    ):
        """Segundo critério de aceite: o gate é do backend, não da tela. Nem o
        super admin técnico despacha manifestação."""
        client, supabase = _client(monkeypatch, participante)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"
        assert _nunca_envia_email_de_verdade == []

    def test_diretoria_executiva_tambem_valida(self, monkeypatch):
        """O perfil de supervisão da Ouvidoria despacha quando o ouvidor falta."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200
        assert supabase.tabelas["ouvidoria_protocolos"][0]["validada_por"] == "P11"


class TestSetorSemTitular:
    """Setor sem titular vigente não é acionável: a demanda sobe ao gestor da
    área, com alerta à Diretoria (ADR 0034, decisão 5)."""

    def test_sem_titular_vigente_a_demanda_sobe_ao_gestor(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Terceiro critério de aceite: o titular saiu do papel em julho, então
        quem recebe o acionamento é o gestor da área."""
        responsaveis = [
            _responsavel("titular", vigencia_fim="2026-07-31"),
            _responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br"),
        ]
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake(responsaveis=responsaveis))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200
        acionamento = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "nova_demanda"]
        assert [n["destinatario_email"] for n in acionamento] == ["regina@hsm.br"]
        assert acionamento[0]["papel_destinatario"] == "gestor"
        assert "regina@hsm.br" in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_sem_titular_vigente_a_diretoria_recebe_o_alerta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O buraco no cadastro não pode virar rotina silenciosa: quem pode
        mandar cadastrar o titular precisa saber que ele não existe."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        alertas = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "alerta_sem_titular"]
        assert [n["destinatario_email"] for n in alertas] == ["diretor@hsm.br"]
        assert "diretor@hsm.br" in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_diretora_desligada_nao_recebe_o_alerta_de_setor_sem_titular(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Issue #403: o desligamento é soft delete (`ativo: False`) e não limpa
        `perfil_ouvidoria`, então sem filtro quem saiu do hospital continua
        recebendo o alerta, com o protocolo no assunto e o setor no corpo.

        A porta da diretora ATIVA fica aberta no mesmo cenário: o teste falha se
        a correção matar o alerta em vez de filtrar quem foi desligado."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        supabase.tabelas["participantes"][0]["ativo"] = False
        supabase.tabelas["participantes"].append(
            {
                "id": "P12",
                "nome_completo": "Dra. Diretora",
                "email": "diretora@hsm.br",
                "perfil_ouvidoria": "diretoria_executiva",
                "ativo": True,
            }
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        alertas = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "alerta_sem_titular"]
        assert [n["destinatario_email"] for n in alertas] == ["diretora@hsm.br"]
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade if "diretor" in e["destinatario"]] == [
            "diretora@hsm.br"
        ]

    def test_sem_diretoria_ativa_o_alerta_cai_no_admin_tecnico(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Issue #415: o ramo vazio degradava para uma linha de `logger.warning`,
        e o alerta de setor sem titular sumia por inteiro. Ele ficou alcançável
        justamente pelo filtro de `ativo` da #403: num hospital cuja única
        diretora foi desligada, ninguém mais era avisado.

        O admin técnico é o segundo destinatário porque o buraco aqui é de
        cadastro, e cadastro é ele quem conserta."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        # Ninguém com `perfil_ouvidoria`: a Diretoria vem vazia.
        supabase.tabelas["participantes"][1]["access_profile"] = "super_admin"
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        para_o_admin = [e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "admin@hsm.br"]
        assert para_o_admin, "sem Diretoria, o alerta de setor sem titular tem que achar outro dono"
        assert "uuid-7" in para_o_admin[0]["texto"]

    def test_com_diretoria_ativa_o_admin_tecnico_nao_e_incomodado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Controle do teste acima: o admin é o plano B, não um cc permanente.
        Sem isto, um alerta que fosse SEMPRE ao admin passaria verde e vazio."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        supabase.tabelas["participantes"][1]["access_profile"] = "super_admin"
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        destinos = [e["destinatario"] for e in _nunca_envia_email_de_verdade]
        assert "diretor@hsm.br" in destinos
        assert "admin@hsm.br" not in destinos

    def test_titular_vigente_nao_gera_alerta_a_diretoria(self, monkeypatch):
        """Alerta que sai sempre não é alerta: com titular no lugar, a Diretoria
        não é incomodada."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        gatilhos = {n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]}
        assert gatilhos == {"nova_demanda"}

    def test_setor_sem_ninguem_cadastrado_recusa_o_acionamento(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Sem titular e sem gestor não há para quem despachar: acionar mandaria
        a demanda para o vazio e o prazo correria contra ninguém."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake(responsaveis=[]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 409
        assert "titular" in r.json()["detail"].lower()
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"
        assert _nunca_envia_email_de_verdade == []


class TestEmailDeAcionamento:
    """O que o responsável do setor lê. Quarto critério de aceite."""

    def test_email_traz_protocolo_setor_prazo_em_data_e_hora_e_contagem_regressiva(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Médio dá 4 dias úteis à área (seed da migration 065). Validado na
        terça 25/08 às 14h, o dia 1 é quarta 26 e o quarto dia útil é segunda
        31/08, que fecha às 17h."""
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        email = _nunca_envia_email_de_verdade[0]
        assert "2026-0007" in email["assunto"]
        assert "Recepcao" in email["assunto"]
        for esperado in ("2026-0007", "Recepcao", "31/08/2026 às 17h00", "vence em 4 dias úteis"):
            assert esperado in email["html"], f"Faltou no email do setor: {esperado}"
            assert esperado in email["texto"], f"Faltou no texto de fallback: {esperado}"

    def test_email_leva_o_extrato_escrito_pelo_ouvidor(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O setor precisa saber o que aconteceu para responder, e o que ele lê
        é o extrato da Ouvidoria: nem o resumo nem o relato saem daqui."""
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert EXTRATO in _nunca_envia_email_de_verdade[0]["html"]

    def test_caso_sigiloso_sai_sem_a_identificacao_do_manifestante(self, monkeypatch, _nunca_envia_email_de_verdade):
        """RN-40: o setor recebe o extrato necessário para resolver, e nada
        além. Denúncia não chega ao setor com o nome de quem denunciou."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(sigilo_reforcado=True)]))

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        email = _nunca_envia_email_de_verdade[0]
        assert "Joana da Silva" not in email["html"]
        assert "Joana da Silva" not in email["texto"]
        assert "sigilo reforçado" in email["html"].lower()

    def test_caso_comum_identifica_quem_manifestou(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Fora do sigilo o setor precisa saber com quem falar para resolver."""
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert "Joana da Silva" in _nunca_envia_email_de_verdade[0]["html"]

    def test_manifestacao_anonima_sai_sem_identificacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Anônimo é escolha de quem manifestou e vale até no email do setor."""
        caso = _manifestacao(anonimo=True, manifestante_nome=None)
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert "Quem manifestou" not in _nunca_envia_email_de_verdade[0]["html"]

    def test_gravidade_sem_prazo_na_tabela_nao_inventa_vencimento(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Baixo não passa pela área na tabela da Diretoria (valor nulo na
        migration 065): o email diz que não há prazo em vez de fabricar um."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "baixo"})

        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] is None
        assert "sem prazo definido" in _nunca_envia_email_de_verdade[0]["texto"]


class TestRegistroEReenvio:
    """Quinto critério de aceite: toda notificação fica no caso e o ouvidor
    pode insistir."""

    def _acionar(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        return client, supabase

    def test_notificacao_enviada_fica_registrada_no_caso(self, monkeypatch):
        """É o que prova a cobrança: data, destinatário e gatilho."""
        client, _ = self._acionar(monkeypatch)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7/notificacoes")

        assert r.status_code == 200, r.text
        registro = r.json()["notificacoes"][0]
        assert registro["gatilho"] == "nova_demanda"
        assert registro["destinatario_email"] == "carlos@hsm.br"
        assert registro["status"] == "enviada"
        assert registro["enviada_em"]

    def test_reenvio_manual_dispara_o_email_de_novo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O ouvidor insiste quando o setor diz que não recebeu."""
        client, supabase = self._acionar(monkeypatch)
        notificacao_id = supabase.tabelas["ouvidoria_notificacoes"][0]["id"]
        _nunca_envia_email_de_verdade.clear()

        r = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{notificacao_id}/reenviar")

        assert r.status_code == 201, r.text
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

    def test_reenvio_deixa_rastro_proprio_sem_apagar_o_envio_original(self, monkeypatch):
        """A trilha é append-only no espírito: o reenvio não reescreve o
        registro do primeiro envio, que é o que prova a data da cobrança."""
        client, supabase = self._acionar(monkeypatch)
        original = dict(supabase.tabelas["ouvidoria_notificacoes"][0])

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{original['id']}/reenviar")

        registros = supabase.tabelas["ouvidoria_notificacoes"]
        assert len(registros) == 2
        assert registros[0]["enviada_em"] == original["enviada_em"]

    def test_reenvio_de_notificacao_de_outro_caso_e_recusado(self, monkeypatch):
        """Id de notificação não pode virar caminho lateral para reenviar a
        cobrança de outra manifestação."""
        client, supabase = self._acionar(monkeypatch)
        supabase.tabelas["ouvidoria_protocolos"].append(_manifestacao(8))
        notificacao_id = supabase.tabelas["ouvidoria_notificacoes"][0]["id"]

        r = client.post(f"/api/ouvidoria/manifestacoes/uuid-8/notificacoes/{notificacao_id}/reenviar")

        assert r.status_code == 404

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_da_ouvidoria_nao_le_nem_reenvia(self, monkeypatch, participante):
        """A lista de notificações diz quem manifestou para quem, e o reenvio é
        ato de cobrança: os dois são da Ouvidoria."""
        client, supabase = self._acionar(monkeypatch)
        notificacao_id = supabase.tabelas["ouvidoria_notificacoes"][0]["id"]
        de_fora, _ = _client(monkeypatch, participante, supabase)

        assert de_fora.get("/api/ouvidoria/manifestacoes/uuid-7/notificacoes").status_code == 403
        assert (
            de_fora.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{notificacao_id}/reenviar").status_code
            == 403
        )


class TestJanelaComercial:
    """Sétimo critério de aceite: notificação não crítica respeita o expediente,
    crítica sai na hora."""

    def test_acionamento_nao_critico_fora_do_expediente_espera_a_abertura(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Validado às 22h30 de terça, o email do setor só sai às 8h de quarta:
        cobrança de madrugada não faz ninguém responder mais cedo."""
        client, supabase = _client(monkeypatch, OUVIDOR, agora=FORA_DO_EXPEDIENTE)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200
        assert _nunca_envia_email_de_verdade == []
        agendada = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert agendada["status"] == "agendada"
        assert agendada["enviar_a_partir_de"].startswith("2026-08-26T08:00")

    def test_alerta_a_diretoria_tambem_espera_a_janela_comercial(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A regra da janela vale para toda notificação da leva, não só para o
        acionamento: o setor estar sem titular não é urgência que justifique
        acordar a Diretoria às 22h30."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        client, _ = _client(monkeypatch, OUVIDOR, supabase, agora=FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        alerta = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "alerta_sem_titular"][0]
        assert _nunca_envia_email_de_verdade == []
        assert alerta["status"] == "agendada"
        assert alerta["enviar_a_partir_de"].startswith("2026-08-26T08:00")

    def test_alerta_de_caso_critico_a_diretoria_sai_na_hora(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Setor sem titular num caso crítico é exatamente o que a Diretoria
        precisa saber antes do expediente abrir."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        client, _ = _client(monkeypatch, OUVIDOR, supabase, agora=FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "critico"})

        assert "diretor@hsm.br" in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_diretora_desligada_nao_recebe_o_aviso_de_caso_critico(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Issue #403: o aviso de caso CRÍTICO sai na hora e leva o protocolo no
        assunto. É o pior email para chegar na caixa de quem já não trabalha no
        hospital, e a diretora ATIVA recebe no mesmo cenário."""
        responsaveis = [_responsavel("gestor", nome="Regina Gestora", email="regina@hsm.br")]
        supabase = _SupabaseFake(responsaveis=responsaveis)
        supabase.tabelas["participantes"][0]["perfil_ouvidoria"] = "diretoria_executiva"
        supabase.tabelas["participantes"][0]["ativo"] = False
        supabase.tabelas["participantes"].append(
            {
                "id": "P12",
                "nome_completo": "Dra. Diretora",
                "email": "diretora@hsm.br",
                "perfil_ouvidoria": "diretoria_executiva",
                "ativo": True,
            }
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase, agora=FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "critico"})

        criticos = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "critico_imediato"]
        assert [n["destinatario_email"] for n in criticos] == ["diretora@hsm.br"]
        assert "diretor@hsm.br" not in [e["destinatario"] for e in _nunca_envia_email_de_verdade]
        assert "diretora@hsm.br" in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_caso_critico_sai_imediatamente_fora_do_expediente(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O caso crítico é justamente o que não pode esperar o expediente
        abrir."""
        client, supabase = _client(monkeypatch, OUVIDOR, agora=FORA_DO_EXPEDIENTE)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**VALIDACAO, "gravidade": "critico"})

        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]
        assert supabase.tabelas["ouvidoria_notificacoes"][0]["status"] == "enviada"

    def test_o_job_entrega_a_notificacao_quando_o_expediente_abre(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quem tira a notificação da fila é o job periódico, e ele só leva o
        que já pode sair."""
        client, supabase = _client(monkeypatch, OUVIDOR, agora=FORA_DO_EXPEDIENTE)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        abertura = dt.datetime(2026, 8, 26, 11, 0, tzinfo=dt.UTC)  # 8h de quarta em Brasília

        entregues = ouvidoria_notificacoes.despachar_pendentes(supabase, abertura, frozenset())

        assert entregues == 1
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

    def test_o_job_nao_entrega_duas_vezes_a_mesma_notificacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Idempotência: rodar o job de novo não acorda o setor outra vez pelo
        mesmo caso."""
        client, supabase = _client(monkeypatch, OUVIDOR, agora=FORA_DO_EXPEDIENTE)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        abertura = dt.datetime(2026, 8, 26, 11, 0, tzinfo=dt.UTC)

        ouvidoria_notificacoes.despachar_pendentes(supabase, abertura, frozenset())
        ouvidoria_notificacoes.despachar_pendentes(supabase, abertura, frozenset())

        assert len(_nunca_envia_email_de_verdade) == 1


class TestRetentativa:
    """Sexto critério de aceite: falha do Resend não perde a notificação, e a
    terceira falha vira alerta ao admin técnico."""

    def _com_provedor_fora(self, monkeypatch):
        tentativas: list[str] = []

        def _recusa(destinatario, _assunto, _html, _texto):
            tentativas.append(destinatario)
            return False

        monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _recusa)
        return tentativas

    def test_falha_devolve_a_notificacao_para_a_fila_com_espera(self, monkeypatch):
        """Instabilidade do provedor não pode sumir com a cobrança: ela volta
        para a fila, com espera, e o job tenta de novo."""
        self._com_provedor_fora(monkeypatch)
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        pendente = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert pendente["status"] == "agendada"
        assert pendente["tentativas"] == 1
        assert pendente["enviar_a_partir_de"] > DENTRO_DO_EXPEDIENTE.isoformat()
        assert pendente["ultimo_erro"]

    def test_a_espera_cresce_a_cada_falha(self, monkeypatch):
        """Backoff: insistir no mesmo minuto contra um provedor fora do ar só
        gasta tentativa."""
        primeira = ouvidoria_notificacoes.proxima_tentativa(DENTRO_DO_EXPEDIENTE, 1)
        segunda = ouvidoria_notificacoes.proxima_tentativa(DENTRO_DO_EXPEDIENTE, 2)

        assert primeira is not None and segunda is not None
        assert segunda > primeira

    def test_tres_falhas_marcam_a_notificacao_e_alertam_o_admin_tecnico(self, monkeypatch):
        """Depois de três tentativas o problema é de infraestrutura, e quem
        conserta é o admin técnico do app."""
        tentativas = self._com_provedor_fora(monkeypatch)
        client, supabase = _client(monkeypatch, OUVIDOR)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        pendente = supabase.tabelas["ouvidoria_notificacoes"][0]
        supabase.tabelas["participantes"][1]["access_profile"] = "super_admin"

        for minuto in (10, 40):
            depois = DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=minuto)
            ouvidoria_notificacoes.despachar(supabase, dict(pendente), depois, frozenset())
            pendente = supabase.tabelas["ouvidoria_notificacoes"][0]

        assert pendente["status"] == "falha"
        assert pendente["tentativas"] == 3
        assert "admin@hsm.br" in tentativas, "O admin técnico precisa saber que a cobrança não saiu"

    def test_antes_da_terceira_falha_o_admin_tecnico_nao_e_incomodado(self, monkeypatch):
        """Alerta que sai na primeira instabilidade vira ruído e deixa de ser
        lido justo quando importa."""
        tentativas = self._com_provedor_fora(monkeypatch)
        client, supabase = _client(monkeypatch, OUVIDOR)
        supabase.tabelas["participantes"][1]["access_profile"] = "super_admin"

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert "admin@hsm.br" not in tentativas


NOVO_RESPONSAVEL = {
    "setor": "Recepcao",
    "papel": "titular",
    "nome": "Carlos Titular",
    "email": "carlos@hsm.br",
    "vigencia_inicio": "2026-08-01",
}


class TestCadastroDeResponsaveis:
    """História 22 do PRD: titular e substituto de cada setor, com vigência,
    para o despacho sempre achar um destinatário válido."""

    def test_diretoria_cadastra_titular_e_substituto_do_setor(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA, _SupabaseFake(responsaveis=[]))

        titular = client.post("/api/ouvidoria/responsaveis", json=NOVO_RESPONSAVEL)
        substituto = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_RESPONSAVEL, "papel": "substituto", "nome": "Bia Substituta", "email": "bia@hsm.br"},
        )

        assert titular.status_code == 201, titular.text
        assert substituto.status_code == 201, substituto.text
        cadastrados = {(r["papel"], r["email"]) for r in supabase.tabelas["ouvidoria_setor_responsaveis"]}
        assert cadastrados == {("titular", "carlos@hsm.br"), ("substituto", "bia@hsm.br")}

    def test_ouvidor_le_o_cadastro_mas_nao_edita(self, monkeypatch):
        """O ouvidor trabalha com o cadastro e precisa enxergar quem responde
        por cada setor; quem define os responsáveis é a Diretoria, como já
        acontece com a tabela de prazos."""
        client, _ = _client(monkeypatch, OUVIDOR)

        leitura = client.get("/api/ouvidoria/responsaveis")
        escrita = client.post("/api/ouvidoria/responsaveis", json=NOVO_RESPONSAVEL)

        assert leitura.status_code == 200
        assert [r["email"] for r in leitura.json()["responsaveis"]] == ["carlos@hsm.br"]
        assert escrita.status_code == 403

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN])
    def test_quem_esta_fora_da_ouvidoria_nao_ve_o_cadastro(self, monkeypatch, participante):
        client, _ = _client(monkeypatch, participante)

        assert client.get("/api/ouvidoria/responsaveis").status_code == 403

    def test_setor_fora_da_taxonomia_e_recusado(self, monkeypatch):
        """Sem cadastro paralelo de setor (ADR 0034, decisão 5): responsável só
        entra em setor que existe na taxonomia da casa, senão o acionamento
        nunca casaria com o setor da manifestação."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.post("/api/ouvidoria/responsaveis", json={**NOVO_RESPONSAVEL, "setor": "Setor Inventado"})

        assert r.status_code == 422
        assert len(supabase.tabelas["ouvidoria_setor_responsaveis"]) == 1

    def test_vigencia_que_termina_antes_de_comecar_e_recusada(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA)

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_RESPONSAVEL, "vigencia_inicio": "2026-08-10", "vigencia_fim": "2026-08-01"},
        )

        assert r.status_code == 422

    def test_encerrar_a_vigencia_do_titular_faz_a_proxima_demanda_subir_ao_gestor(self, monkeypatch):
        """O cadastro serve para isso: mudar quem responde muda para onde a
        demanda vai, sem programador no meio."""
        supabase = _SupabaseFake(
            responsaveis=[_responsavel("titular"), _responsavel("gestor", nome="Regina", email="regina@hsm.br")]
        )
        diretoria, _ = _client(monkeypatch, DIRETORIA, supabase)

        encerrada = diretoria.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-07-31"},
        )

        assert encerrada.status_code == 200, encerrada.text
        ouvidor, _ = _client(monkeypatch, OUVIDOR, supabase)
        ouvidor.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        acionamento = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "nova_demanda"]
        assert [n["destinatario_email"] for n in acionamento] == ["regina@hsm.br"]

    def test_responsavel_removido_sai_do_cadastro(self, monkeypatch):
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.delete("/api/ouvidoria/responsaveis/resp-titular")

        assert r.status_code == 204
        assert supabase.tabelas["ouvidoria_setor_responsaveis"] == []

    def test_remover_responsavel_que_nao_existe_devolve_404(self, monkeypatch):
        """Issue #375, item 5: o resultado do delete era ignorado, então
        apagar um id inexistente respondia 204. Quem chamou lê "removido" para
        uma remoção que não aconteceu, e o cadastro que a pessoa queria
        desfazer continua lá."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.delete("/api/ouvidoria/responsaveis/resp-que-nao-existe")

        assert r.status_code == 404
        # E o cadastro real não foi tocado.
        assert [x["id"] for x in supabase.tabelas["ouvidoria_setor_responsaveis"]] == ["resp-titular"]

    def test_leitura_do_cadastro_fora_do_ar_nao_vaza_a_mensagem_do_banco(self, monkeypatch):
        """Issue #375, item 3: as rotas de responsável deixavam o `APIError`
        subir até o handler global, que respondia com o texto da exceção. A
        mensagem do PostgREST carrega nome de tabela e de coluna."""
        supabase = _SupabaseFake()
        supabase.indisponiveis.add("ouvidoria_setor_responsaveis")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.get("/api/ouvidoria/responsaveis")

        assert r.status_code == 503
        assert "ouvidoria_setor_responsaveis" not in r.text
        assert "42P01" not in r.text

    def test_remocao_com_o_banco_fora_do_ar_nao_vaza_a_mensagem(self, monkeypatch):
        supabase = _SupabaseFake()
        supabase.indisponiveis.add("ouvidoria_setor_responsaveis")
        client, _ = _client(monkeypatch, DIRETORIA, supabase)

        r = client.delete("/api/ouvidoria/responsaveis/resp-titular")

        assert r.status_code == 500
        assert "ouvidoria_setor_responsaveis" not in r.text

    def test_com_dois_titulares_vigentes_o_destinatario_e_sempre_o_mesmo(self, monkeypatch):
        """Issue #375, item 4: sem ordem explícita, `escolher_destinatario`
        pegava o primeiro que o banco devolvesse, e quem recebe a demanda
        passava a depender da ordem física das linhas. Com ordem, o titular
        mais recente ganha, sempre."""
        antigo = _responsavel("titular", id="resp-a", nome="Ana Antiga", email="ana@hsm.br")
        novo = _responsavel(
            "titular", id="resp-b", nome="Bruno Novo", email="bruno@hsm.br", vigencia_inicio="2026-06-01"
        )

        # As duas ordens físicas possíveis dão o mesmo destinatário.
        for linhas in ([antigo, novo], [novo, antigo]):
            supabase = _SupabaseFake(responsaveis=[dict(r) for r in linhas])
            client, _ = _client(monkeypatch, OUVIDOR, supabase)

            client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

            acionamento = [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "nova_demanda"]
            assert [n["destinatario_email"] for n in acionamento] == ["bruno@hsm.br"]

    def test_segundo_titular_vigente_no_mesmo_setor_e_recusado(self, monkeypatch):
        """A outra metade do item 4: em vez de só desempatar, o cadastro para
        de aceitar o empate. Dois titulares vigentes no mesmo setor é erro de
        cadastro, e a Diretoria precisa ver isso na hora de cadastrar, não
        descobrir pelo email que foi para a pessoa errada."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_RESPONSAVEL, "nome": "Bruno Novo", "email": "bruno@hsm.br"},
        )

        assert r.status_code == 409
        assert [x["email"] for x in supabase.tabelas["ouvidoria_setor_responsaveis"]] == ["carlos@hsm.br"]

    def test_titular_novo_entra_depois_de_encerrada_a_vigencia_do_anterior(self, monkeypatch):
        """A porta certa continua aberta: trocar de titular é o caso comum, e
        a recusa não pode travar a troca."""
        encerrado = _responsavel("titular", vigencia_fim="2026-07-31")
        client, supabase = _client(monkeypatch, DIRETORIA, _SupabaseFake(responsaveis=[encerrado]))

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_RESPONSAVEL, "nome": "Bruno Novo", "email": "bruno@hsm.br"},
        )

        assert r.status_code == 201, r.text
        assert len(supabase.tabelas["ouvidoria_setor_responsaveis"]) == 2

    def test_titular_que_comeca_no_futuro_tambem_e_recusado(self, monkeypatch):
        """A guarda é de SOBREPOSIÇÃO, não de "vigente hoje". Titular novo com
        início marcado para daqui a um mês, sobre um titular sem data de saída,
        cria os dois vigentes a partir daquela data: o empate acontece depois,
        e é o mesmo empate."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={
                **NOVO_RESPONSAVEL,
                "nome": "Bruno Novo",
                "email": "bruno@hsm.br",
                "vigencia_inicio": "2026-12-01",
            },
        )

        assert r.status_code == 409, r.text
        assert [x["email"] for x in supabase.tabelas["ouvidoria_setor_responsaveis"]] == ["carlos@hsm.br"]

    def test_titular_que_entra_depois_da_saida_do_anterior_passa(self, monkeypatch):
        """A sucessão planejada é o caso comum e não pode travar: o anterior
        sai no dia 30, o novo entra no dia 1. Não há dia com dois."""
        sai_em_novembro = _responsavel("titular", vigencia_fim="2026-11-30")
        client, supabase = _client(monkeypatch, DIRETORIA, _SupabaseFake(responsaveis=[sai_em_novembro]))

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={
                **NOVO_RESPONSAVEL,
                "nome": "Bruno Novo",
                "email": "bruno@hsm.br",
                "vigencia_inicio": "2026-12-01",
            },
        )

        assert r.status_code == 201, r.text
        assert len(supabase.tabelas["ouvidoria_setor_responsaveis"]) == 2

    def test_reabrir_a_vigencia_pela_edicao_nao_cria_dois_titulares(self, monkeypatch):
        """A outra porta da mesma regra. `editar_responsavel` monta a mudança
        com `vigencia_fim: None` quando o payload não traz a data, então um PUT
        só para corrigir o NOME de um titular encerrado reabria a vigência
        dele, por cima do titular vigente de hoje. O 409 do POST não alcançava
        essa porta."""
        encerrado = _responsavel(
            "titular", id="resp-a", nome="Ana Antiga", email="ana@hsm.br", vigencia_fim="2026-07-31"
        )
        atual = _responsavel("titular", id="resp-b", nome="Bruno", email="bruno@hsm.br", vigencia_inicio="2026-08-01")
        supabase = _SupabaseFake(responsaveis=[encerrado, atual])
        client, _ = _client(monkeypatch, DIRETORIA, supabase)

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-a",
            json={"nome": "Ana Antiga Corrigida", "email": "ana@hsm.br"},
        )

        assert r.status_code == 409, r.text
        # E a vigência encerrada continua encerrada.
        assert supabase.tabelas["ouvidoria_setor_responsaveis"][0]["vigencia_fim"] == "2026-07-31"

    def test_editar_o_titular_vigente_sem_mexer_em_data_continua_passando(self, monkeypatch):
        """A porta certa fica aberta: corrigir o nome de quem responde hoje é o
        uso comum da edição, e a pessoa não conflita consigo mesma."""
        supabase = _SupabaseFake()
        client, _ = _client(monkeypatch, DIRETORIA, supabase)

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular Corrigido", "email": "carlos@hsm.br"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_setor_responsaveis"][0]["nome"] == "Carlos Titular Corrigido"

    def test_substituto_entra_com_titular_vigente(self, monkeypatch):
        """A recusa é por PAPEL: ter titular não impede cadastrar substituto
        nem gestor, que é como o setor fica completo."""
        client, _ = _client(monkeypatch, DIRETORIA)

        r = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_RESPONSAVEL, "papel": "substituto", "nome": "Bia", "email": "bia@hsm.br"},
        )

        assert r.status_code == 201, r.text

    def test_encerrar_a_vigencia_antes_do_inicio_ja_gravado_fala_de_data(self, monkeypatch):
        """Issue #375, item 2: o `model_validator` só compara as datas quando
        as duas vêm no payload. Mandando só `vigencia_fim`, a comparação com o
        `vigencia_inicio` que já está gravado nunca acontecia, o CHECK do banco
        recusava, e a Diretoria lia "Responsável não encontrado" para um erro
        de data num responsável que existe."""
        client, _ = _client(monkeypatch, DIRETORIA)

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2025-12-31"},
        )

        assert r.status_code == 422
        assert "não encontrado" not in r.text
        assert "vigência" in r.json()["detail"].lower()

    def test_encerrar_a_vigencia_numa_data_valida_continua_passando(self, monkeypatch):
        """A porta certa fica aberta: encerrar vigência é o caminho documentado
        de tirar alguém do papel."""
        client, supabase = _client(monkeypatch, DIRETORIA)

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-07-31"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_setor_responsaveis"][0]["vigencia_fim"] == "2026-07-31"


class TestIdQueNaoEUuid:
    """Issue #375: `ouvidoria_setor_responsaveis.id` é UUID (migration 068).
    Id malformado faz o PostgREST recusar com 22P02, e o `except APIError` da
    fatia traduzia isso em 500. Id que não existe e id que não é id são a mesma
    coisa para quem chamou: o cadastro não está lá."""

    @staticmethod
    def _client_com_id_uuid(monkeypatch, participante):
        supabase = _SupabaseFake()
        supabase.id_e_uuid = True
        return _client(monkeypatch, participante, supabase)

    def test_remover_com_id_malformado_devolve_404(self, monkeypatch):
        client, _ = self._client_com_id_uuid(monkeypatch, DIRETORIA)

        r = client.delete("/api/ouvidoria/responsaveis/nao-e-uuid")

        assert r.status_code == 404
        assert "uuid" not in r.text.lower()

    def test_editar_com_id_malformado_devolve_404(self, monkeypatch):
        """Antes desta fatia a rota devolvia 404 aqui; o `except APIError` novo
        não pode ter piorado esse caminho para 500."""
        client, _ = self._client_com_id_uuid(monkeypatch, DIRETORIA)

        r = client.put(
            "/api/ouvidoria/responsaveis/nao-e-uuid",
            json={"nome": "Carlos", "email": "carlos@hsm.br"},
        )

        assert r.status_code == 404


class TestTrilhaDeAcessoDasNotificacoes:
    """Issue #375, item 6, e decisão 8 do ADR 0034: quem abre dado do caso
    deixa rastro."""

    def test_listar_as_notificacoes_do_caso_registra_acesso(self, monkeypatch):
        """A lista mostra nome e email de cada destinatário do caso, sigiloso
        inclusive, e era a única leitura de dado do caso sem trilha: `validar`
        e `reenviar` já registravam."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7/notificacoes")

        assert r.status_code == 200, r.text
        acessos = supabase.tabelas["ouvidoria_acessos"]
        assert [(a["manifestacao_id"], a["ator_id"], a["acao"]) for a in acessos] == [
            ("uuid-7", "P10", "listar_notificacoes")
        ]


class TestVigencia:
    """A regra de quem responde hoje, como função pura (o único seam novo desta
    fatia fora do HTTP)."""

    @pytest.mark.parametrize(
        "inicio,fim,dia,esperado",
        [
            ("2026-01-01", None, "2026-08-25", True),
            ("2026-09-01", None, "2026-08-25", False),
            ("2026-01-01", "2026-08-25", "2026-08-25", True),
            ("2026-01-01", "2026-08-24", "2026-08-25", False),
        ],
    )
    def test_vigencia_cobre_o_dia_inteiro_das_pontas(self, inicio, fim, dia, esperado):
        """O fim é inclusivo: quem sai no dia 31 ainda responde no dia 31."""
        from app.services.ouvidoria_responsaveis import esta_vigente

        responsavel = {"vigencia_inicio": inicio, "vigencia_fim": fim}

        assert esta_vigente(responsavel, dt.date.fromisoformat(dia)) is esperado

    def test_responsavel_sem_email_nao_e_destinatario(self):
        """Cadastro pela metade não vira acionamento silencioso para o vazio."""
        from app.services.ouvidoria_responsaveis import escolher_destinatario

        escolhido = escolher_destinatario([_responsavel("titular", email="  ")], dt.date(2026, 8, 25))

        assert escolhido is None


class TestNomeDeQuemResponde:
    """Quem só EXIBE o nome pergunta diferente de quem vai MANDAR email
    (issue #429). O painel de pendências das métricas lê o cadastro sem o
    email, e por isso não pode herdar as duas regras que o acionamento tem
    justamente por causa do email."""

    def test_titular_sem_email_continua_sendo_quem_responde_pela_area(self):
        # No acionamento ele cai fora e a demanda sobe ao gestor, porque não há
        # para onde escrever. No painel não há nada a escrever: quem responde
        # pela área é ele, e trocá-lo pelo gestor diria à Diretoria que o setor
        # está sem titular quando o que falta é uma linha do cadastro.
        from app.services.ouvidoria_responsaveis import nome_de_quem_responde

        cadastro = [
            _responsavel("titular", nome="Carlos Titular", email=None),
            _responsavel("gestor", nome="Helena Gestora"),
        ]

        assert nome_de_quem_responde(cadastro, dt.date(2026, 8, 25)) == "Carlos Titular"

    def test_responsavel_sem_nome_nao_vira_o_email_na_tela(self):
        # `escolher_destinatario` usa o email como nome de reserva, porque ali
        # ele já vai no cabeçalho da mensagem de qualquer jeito. Aqui não: o
        # painel diz quem responde, não para onde escrever, e um email impresso
        # na tela seria dado pessoal aparecendo onde ninguém pediu.
        from app.services.ouvidoria_responsaveis import nome_de_quem_responde

        cadastro = [_responsavel("titular", nome=None, email="carlos@hsm.br")]

        assert nome_de_quem_responde(cadastro, dt.date(2026, 8, 25)) is None


class TestExtratoParaOSetor:
    """O extrato que o setor recebe é escrito pelo ouvidor, não copiado do
    relato (decisão de 25/08), e continua obrigatório em todo acionamento.

    Desde o diagnóstico da Diretoria (RN-78, ADR 0041) o caso comum leva o
    resumo e o relato integral junto do extrato: quem lê só a interpretação da
    Ouvidoria responde à interpretação, não ao paciente. O caso protegido segue
    como antes, e é o que estes testes guardam: sigiloso ou anônimo, o email sai
    só com o extrato, porque a palavra crua de quem manifestou carrega nome e
    leito embaixo de um selo que promete o contrário (RN-79)."""

    def _sigiloso(self) -> _SupabaseFake:
        return _SupabaseFake([_manifestacao(sigilo_reforcado=True, resumo=RELATO_CRU)])

    def _anonimo(self) -> _SupabaseFake:
        return _SupabaseFake([_manifestacao(anonimo=True, manifestante_nome=None, resumo=RELATO_CRU)])

    def test_caso_sigiloso_sem_extrato_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _client(monkeypatch, OUVIDOR, self._sigiloso())

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=SEM_EXTRATO)

        assert r.status_code == 422, r.text
        assert "extrato" in r.json()["detail"].lower()
        assert _nunca_envia_email_de_verdade == [], "Recusa não pode sair mandando email"
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"

    def test_caso_anonimo_sem_extrato_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _client(monkeypatch, OUVIDOR, self._anonimo())

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=SEM_EXTRATO)

        assert r.status_code == 422, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"

    @pytest.mark.parametrize("caso", ["sigiloso", "anonimo"])
    def test_email_de_caso_protegido_nunca_leva_o_relato_cru(self, monkeypatch, caso, _nunca_envia_email_de_verdade):
        """O que o setor lê é o extrato do ouvidor, e só ele."""
        supabase = self._sigiloso() if caso == "sigiloso" else self._anonimo()
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200, r.text
        email = _nunca_envia_email_de_verdade[0]
        assert EXTRATO in email["html"]
        for corpo in (email["html"], email["texto"]):
            assert "Maria Silva" not in corpo
            assert "leito 302" not in corpo

    @pytest.mark.parametrize("caso", ["sigiloso", "anonimo"])
    def test_reenvio_de_caso_protegido_tambem_sai_sem_o_relato_cru(
        self, monkeypatch, caso, _nunca_envia_email_de_verdade
    ):
        """O reenvio monta o email do zero: o vazamento não pode entrar por
        esse caminho."""
        supabase = self._sigiloso() if caso == "sigiloso" else self._anonimo()
        client, _ = _client(monkeypatch, OUVIDOR, supabase)
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        notificacao_id = supabase.tabelas["ouvidoria_notificacoes"][0]["id"]
        _nunca_envia_email_de_verdade.clear()

        r = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{notificacao_id}/reenviar")

        assert r.status_code == 201, r.text
        email = _nunca_envia_email_de_verdade[0]
        assert EXTRATO in email["html"]
        for corpo in (email["html"], email["texto"]):
            assert "Maria Silva" not in corpo
            assert "leito 302" not in corpo

    def test_extrato_fica_gravado_no_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Rastro do que o setor recebeu, e a garantia de que o reenvio manda a
        mesma coisa."""
        client, supabase = _client(monkeypatch, OUVIDOR, self._sigiloso())

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["extrato_para_o_setor"] == EXTRATO

    def test_caso_comum_sem_extrato_tambem_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Regra única, sem exceção (decisão de 25/08): não existe acionamento
        que caia no resumo. O resumo do canal da Ana é texto gerado da conversa
        com o cidadão e pode carregar identificação sem ninguém perceber, e a
        trava não pode morar só na tela."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=SEM_EXTRATO)

        assert r.status_code == 422, r.text
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"

    def test_extrato_do_ouvidor_acompanha_o_caso_comum_no_email(self, monkeypatch, _nunca_envia_email_de_verdade):
        """No caso comum a nota da Ouvidoria não é mais o único conteúdo: ela
        fecha os três blocos do ADR 0041, junto do resumo e do relato."""
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        email = _nunca_envia_email_de_verdade[0]
        assert EXTRATO in email["html"]
        assert "espera acima de duas horas" in email["html"], "o resumo passou a viajar com o extrato (RN-78)"


class TestSigiloPeloTipoNaValidacao:
    """A validação é onde o tipo é decidido, então é onde a regra de sigilo
    vale de novo (ADR 0034, decisão 1; issue #372).

    Caso que chegou pela Ana nasce sem tipo. Se o ouvidor o classifica como
    denúncia, o setor denunciado não pode receber o nome de quem denunciou."""

    def test_denuncia_classificada_na_validacao_eleva_o_sigilo(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "denuncia"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True

    def test_email_da_denuncia_sai_sem_o_nome_e_com_o_selo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O furo que isso fecha: sem reavaliar a categoria, o email da denúncia
        chegava ao setor denunciado com 'Quem manifestou' e sem o selo."""
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "relato_de_conduta"},
        )

        email = _nunca_envia_email_de_verdade[0]
        assert "Joana da Silva" not in email["html"]
        assert "Joana da Silva" not in email["texto"]
        assert "sigilo reforçado" in email["html"].lower()

    def test_tipo_comum_nao_eleva_sigilo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Elevar o sigilo esconde o caso de todo mundo fora da Ouvidoria: só o
        tipo que pede isso o faz."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False

    def test_caso_ja_sigiloso_continua_sigiloso_sem_pedido_explicito(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Descer o sigilo é ato consciente: reclassificar sozinho não devolve
        ao índice de todos um caso que já está protegido."""
        supabase = _SupabaseFake([_manifestacao(sigilo_reforcado=True)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "elogio"},
        )

        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True


class TestFalhaDoAcionamentoNaoPassaEmSilencio:
    """Erro de infraestrutura no acionamento não pode virar 200 na tela do
    ouvidor: o prazo corre contra um setor que ninguém avisou."""

    def test_notificacao_nao_registrada_devolve_erro_ao_ouvidor(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch, OUVIDOR)
        monkeypatch.setattr(ouvidoria_notificacoes, "registrar", lambda *a, **k: None)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 500, r.text
        assert "não foi notificado" in r.json()["detail"].lower()

    def test_validacao_nao_apaga_a_marca_de_dados_incompletos(self, monkeypatch, _nunca_envia_email_de_verdade):
        """`dados_incompletos` é identificação pela metade (migration 064), não
        falta de classificação. Validar não completa nome nem contato de
        ninguém, então a marca continua de pé."""
        caso = _manifestacao(dados_incompletos=True, manifestante_contato=None)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["dados_incompletos"] is True


class _SupabaseComMarcacaoQuebrada(_SupabaseFake):
    """PostgREST instável: aceita a leitura e o claim, e recusa o UPDATE que
    marca a notificação como enviada."""

    def table(self, nome: str):
        tabela = super().table(nome)
        if nome != "ouvidoria_notificacoes":
            return tabela
        update_original = tabela.update

        def _update(payload: dict):
            if payload.get("status") == ouvidoria_notificacoes.ENVIADA:
                raise APIError({"message": "canceling statement due to statement timeout", "code": "57014"})
            return update_original(payload)

        tabela.update = _update
        return tabela


class TestNotificacaoEmVoo:
    """A mesma cobrança não pode sair duas vezes. O job roda de 10 em 10
    minutos e não sabe que um request está no meio de uma chamada ao Resend."""

    def _registrar(self, supabase) -> dict:
        registro = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id="uuid-7",
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            destinatario_nome="Carlos Titular",
            destinatario_email="carlos@hsm.br",
            papel_destinatario="titular",
            enviar_a_partir_de=DENTRO_DO_EXPEDIENTE,
        )
        assert registro is not None
        return registro

    def test_job_nao_pega_notificacao_que_ja_esta_em_envio(self, monkeypatch):
        """Durante a chamada ao provedor a linha está reivindicada, e a
        varredura da fila passa por ela sem tocar."""
        supabase = _SupabaseFake()
        registro = self._registrar(supabase)
        enviados: list[str] = []

        def _envia_enquanto_o_cron_varre(destinatario, _assunto, _html, _texto):
            enviados.append(destinatario)
            if len(enviados) == 1:
                ouvidoria_notificacoes.despachar_pendentes(supabase, DENTRO_DO_EXPEDIENTE, frozenset())
            return True

        monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _envia_enquanto_o_cron_varre)

        ouvidoria_notificacoes.despachar(supabase, registro, DENTRO_DO_EXPEDIENTE, frozenset())

        assert enviados == ["carlos@hsm.br"], "O setor recebeu a mesma cobrança duas vezes"
        assert supabase.tabelas["ouvidoria_notificacoes"][0]["status"] == "enviada"

    def test_falha_ao_marcar_enviada_nao_devolve_a_linha_para_a_fila(self, monkeypatch):
        """Resend aceitou e o UPDATE caiu: a linha fica em envio, não volta a
        `agendada`. Reenviar vira decisão do ouvidor, não do job."""
        supabase = _SupabaseComMarcacaoQuebrada()
        registro = self._registrar(supabase)
        enviados: list[str] = []

        def _envia(destinatario, _assunto, _html, _texto):
            enviados.append(destinatario)
            return True

        monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _envia)

        ouvidoria_notificacoes.despachar(supabase, registro, DENTRO_DO_EXPEDIENTE, frozenset())
        linha = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert linha["status"] == ouvidoria_notificacoes.ENVIANDO

        depois = DENTRO_DO_EXPEDIENTE + dt.timedelta(minutes=10)
        ouvidoria_notificacoes.despachar_pendentes(supabase, depois, frozenset())

        assert enviados == ["carlos@hsm.br"], "A linha travada virou reenvio automático"


class TestMigration:
    """Tabela nova nasce com RLS default-deny (padrão da casa: 009/041/051/063
    a 066) e a migration é reaplicável sem quebrar."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "068_ouvidoria_responsaveis_notificacoes.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    @pytest.mark.parametrize("tabela", ["ouvidoria_setor_responsaveis", "ouvidoria_notificacoes"])
    def test_tabela_nova_tem_rls_habilitado(self, tabela):
        assert f"alter table {tabela} enable row level security" in self._ddl(), (
            f"Sem RLS, a anon_key do bundle do frontend leria {tabela} direto."
        )

    def test_migration_e_idempotente(self):
        ddl = self._ddl()
        assert ddl.count("create table if not exists") == 2
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl
        # CREATE TRIGGER não tem IF NOT EXISTS no Postgres.
        assert "drop trigger if exists" in ddl

    def test_notificacao_referencia_a_manifestacao_sem_permitir_apagar(self):
        """A notificação é prova de cobrança: apagar a manifestação por baixo
        dela deixaria o registro órfão."""
        assert "references ouvidoria_protocolos(id) on delete restrict" in self._ddl()

    def test_caso_guarda_o_extrato_que_foi_para_o_setor(self):
        assert "extrato_para_o_setor" in self._ddl()

    def test_status_da_notificacao_aceita_o_claim_de_envio(self):
        """`enviando` é a linha em voo: sem esse estado no CHECK o claim não
        grava e o job manda a mesma cobrança de novo."""
        ddl = self._ddl()
        assert "'enviando'" in ddl
        # O CHECK antigo já existe no banco de quem aplicou a versão anterior
        # desta migration, e CHECK não tem IF NOT EXISTS.
        assert "drop constraint if exists ouvidoria_notificacoes_status_check" in ddl


class TestSigiloNaValidacaoDepoisDaListaFechada:
    """A validação classifica, e classificar é a porta do sigilo (issue #372):
    a mesma regra da rota de classificação vale aqui, subindo e descendo."""

    def test_caso_do_canal_aberto_validado_como_elogio_volta_ao_indice_geral(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O QR nasce fail-closed. Se a única porta que desce o sigilo fosse a
        rota de classificação, todo caso do canal aberto teria que passar por
        duas telas para voltar à fila de todos."""
        preso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        supabase = _SupabaseFake([preso])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "elogio", "sigilo_reforcado": False},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False

    def test_validacao_nao_tira_o_sigilo_de_uma_denuncia(self, monkeypatch, _nunca_envia_email_de_verdade):
        preso = _manifestacao(tipo_manifestacao="denuncia", sigilo_reforcado=True)
        supabase = _SupabaseFake([preso])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "denuncia", "sigilo_reforcado": False},
        )

        assert r.status_code == 409
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True


class TestTipoInformacaoPelaPortaDaValidacao:
    """O sexto tipo chegando pela porta da validação e acionamento (issue
    #490, ADR 0040 decisão 1). É a porta da fila: classificar e acordar a área
    no mesmo ato."""

    def test_ouvidor_valida_e_aciona_um_caso_de_informacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Antes desta fatia o pedido morria no schema, com 422, e o ouvidor
        tinha de carimbar o caso de reclamação para conseguir acionar a área."""
        caso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "informacao", "sigilo_reforcado": False},
        )

        assert r.status_code == 200, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["tipo_manifestacao"] == "informacao"
        assert gravado["status"] == "aguardando_area"
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

    def test_caso_de_informacao_nao_fica_preso_no_sigilo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Informação não é sigilosa por natureza: o caso que chegou pelo canal
        aberto e nasceu fail-closed volta ao índice de quem está fora da
        Ouvidoria na mesma validação, sem precisar de uma segunda tela."""
        caso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**VALIDACAO, "tipo_manifestacao": "informacao", "sigilo_reforcado": False},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False


class TestCobrancaDoSetorPelaFila:
    """A cobrança de um clique vai ao responsável VIGENTE (issue #536).

    O botão COBRAR da fila nasceu na #495 reenviando o acionamento original, o
    que mandava o relato integral e um token novo do portal para o titular que
    já tinha saído do setor. O PR #534 fechou o vazamento travando a cobrança
    quando o destinatário do acionamento não era o responsável de hoje, e a
    trava deixou o botão inutilizado em todo caso aberto de um setor que trocou
    de titular.

    Aqui a decisão de PARA QUEM ENVIAR passa a ser do servidor, na cadeia do
    acionamento (titular, senão gestor). Setor sem ninguém continua recusando:
    inventar destinatário seria pior que não cobrar.
    """

    def _acionado(self, monkeypatch, responsaveis: list[dict] | None = None):
        """Um caso já com a área, acionado quando Carlos era o titular."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake(responsaveis=responsaveis))
        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
        return client, supabase

    @staticmethod
    def _tokens_de(supabase: _SupabaseFake, email: str) -> list[dict]:
        return [t for t in supabase.tabelas["ouvidoria_setor_tokens"] if t["destinatario_email"] == email]

    @staticmethod
    def _cadastro_apos_a_troca() -> list[dict]:
        """Carlos saiu em junho, Regina entrou em julho. O caso foi acionado
        quando Carlos ainda respondia pela área."""
        return [
            _responsavel(id="resp-antigo", nome="Carlos Titular", email="carlos@hsm.br", vigencia_fim="2026-06-30"),
            _responsavel(id="resp-nova", nome="Regina Nova", email="regina@hsm.br", vigencia_inicio="2026-07-01"),
        ]

    def test_titular_que_trocou_nao_inutiliza_a_cobranca(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O critério de aceite da issue: o ouvidor cobra um setor cujo titular
        trocou, sem passar pelo Dossiê, e quem recebe é quem responde hoje."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = self._cadastro_apos_a_troca()
        _nunca_envia_email_de_verdade.clear()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 201, r.text
        assert r.json()["destinatario"] == "Regina Nova"
        assert r.json()["entregue"] is True
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["regina@hsm.br"]

    def test_a_resposta_nao_devolve_o_email_de_quem_recebeu(self, monkeypatch):
        """A fila mostra o NOME do responsável, e não para onde escrever: o
        endereço não seria exibido nem usado pela tela, e dado pessoal que não é
        usado não tem por que atravessar a rede (mesma regra de
        `nome_de_quem_responde`)."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = self._cadastro_apos_a_troca()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        # O 201 primeiro: sem ele, uma recusa qualquer também não traria o
        # email, e o teste ficaria verde sobre uma cobrança que não saiu.
        assert r.status_code == 201, r.text
        assert "regina@hsm.br" not in r.text

    def test_o_titular_antigo_nao_recebe_email_nem_token_novo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Cada cobrança emite token do portal, e token é acesso ao caso: o que
        não pode sair é acesso NOVO para quem deixou o setor. O token do
        acionamento de junho continua de pé (é por ele que a área responderia),
        mas a cobrança de hoje não acrescenta outro."""
        client, supabase = self._acionado(monkeypatch)
        tokens_do_acionamento = self._tokens_de(supabase, "carlos@hsm.br")
        assert len(tokens_do_acionamento) == 1, "o acionamento original emitiu o token do Carlos"
        supabase.tabelas["ouvidoria_setor_responsaveis"] = self._cadastro_apos_a_troca()
        _nunca_envia_email_de_verdade.clear()

        client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert self._tokens_de(supabase, "carlos@hsm.br") == tokens_do_acionamento
        assert len(self._tokens_de(supabase, "regina@hsm.br")) == 1
        assert "carlos@hsm.br" not in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_sem_titular_a_cobranca_sobe_ao_gestor(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A cadeia da cobrança é a do acionamento (ADR 0034, decisão 5):
        titular, senão gestor. O substituto não entra aqui, senão o setor sem
        titular pararia de aparecer para a Diretoria."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [
            _responsavel(papel="substituto", id="resp-sub", nome="Sara Substituta", email="sara@hsm.br"),
            _responsavel(papel="gestor", id="resp-gestor", nome="Gina Gestora", email="gina@hsm.br"),
        ]
        _nunca_envia_email_de_verdade.clear()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 201, r.text
        assert r.json()["destinatario"] == "Gina Gestora"
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["gina@hsm.br"]

    def test_setor_sem_responsavel_vigente_continua_recusando(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Setor sem titular e sem gestor não ganha fallback nenhum: sem
        destinatário, cobrar seria mandar o caso para o vazio."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [_responsavel(id="resp-antigo", vigencia_fim="2026-06-30")]
        _nunca_envia_email_de_verdade.clear()
        notificacoes_antes = len(supabase.tabelas["ouvidoria_notificacoes"])
        tokens_antes = len(supabase.tabelas["ouvidoria_setor_tokens"])

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 409, r.text
        detalhe = r.json()["detail"]
        assert "titular nem gestor vigente" in detalhe
        # O cadastro de responsáveis é da Diretoria Executiva: o ouvidor que lê
        # a recusa não tem a tela para consertar, e a frase precisa dizer de
        # quem é o conserto em vez de mandá-lo cadastrar.
        assert "Diretoria Executiva" in detalhe
        assert _nunca_envia_email_de_verdade == []
        assert len(supabase.tabelas["ouvidoria_notificacoes"]) == notificacoes_antes
        assert len(supabase.tabelas["ouvidoria_setor_tokens"]) == tokens_antes

    def test_responsavel_vigente_sem_email_nao_e_acusado_de_ter_saido(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O achado da mesma revisão: a recusa acusava "não responde mais pelo
        setor" quando o responsável vigente é a MESMA pessoa, só que sem email
        no cadastro. A recusa está certa; a explicação mandava o ouvidor caçar
        o problema no lugar errado."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [_responsavel(nome="Carlos Titular", email=None)]
        _nunca_envia_email_de_verdade.clear()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 409, r.text
        detalhe = r.json()["detail"]
        assert "Carlos Titular" in detalhe
        assert "sem email" in detalhe
        assert "Diretoria Executiva" in detalhe
        assert "não responde mais" not in detalhe
        assert "titular nem gestor vigente" not in detalhe
        assert _nunca_envia_email_de_verdade == []

    def test_email_em_branco_nao_conta_como_email(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Espaço em branco é cadastro incompleto, e não endereço: sem esta
        guarda a cobrança sairia para o vazio com a tela dizendo que cobrou."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [_responsavel(nome="Carlos Titular", email="   ")]
        _nunca_envia_email_de_verdade.clear()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 409, r.text
        assert "sem email" in r.json()["detail"]
        assert _nunca_envia_email_de_verdade == []

    def test_a_trilha_registra_quem_recebeu_a_cobranca(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério de aceite: a cobrança emite acesso novo ao caso, então quem
        recebeu tem de ficar na linha do tempo, e não só na lista de
        notificações do Dossiê."""
        client, supabase = self._acionado(monkeypatch)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [
            _responsavel(id="resp-nova", nome="Regina Nova", email="regina@hsm.br")
        ]

        client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        movimentos = [m for m in supabase.tabelas["ouvidoria_movimentos"] if "Regina Nova" in (m["observacao"] or "")]
        assert len(movimentos) == 1, "a cobrança deixa um movimento nomeando quem recebeu"
        assert movimentos[0]["estado_anterior"] == movimentos[0]["estado_novo"] == "aguardando_area"
        assert movimentos[0]["autor_nome"] == "Marta Ouvidora"

    def test_a_trilha_nao_afirma_entrega_que_o_provedor_recusou(self, monkeypatch):
        """Provedor que recusou na hora não virou cobrança recebida: a linha do
        tempo diz que a cobrança ficou na fila, e a resposta diz `entregue`
        falso para a tela não prometer o que não saiu."""
        client, supabase = self._acionado(monkeypatch)
        monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", lambda *_a, **_kw: False)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 201, r.text
        assert r.json()["entregue"] is False
        observacoes = [m["observacao"] or "" for m in supabase.tabelas["ouvidoria_movimentos"]]
        assert any("Carlos Titular" in o and "fila de envio" in o for o in observacoes)
        assert not any("Setor cobrado por email" in o for o in observacoes)

    def test_caso_que_nao_esta_com_a_area_nao_emite_token(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Cobrar é insistir com quem está devendo resposta. A fila só oferece o
        botão em `aguardando_area`, mas o gate é do servidor: pela rota, um caso
        em classificação ganharia email de acionamento e token do portal sem
        nunca ter sido validado.

        O caso nasce com o setor JÁ preenchido e com titular vigente no
        cadastro: com o setor "A definir" do padrão, a recusa viria da falta de
        responsável, e o teste ficaria verde sem gate de estado nenhum."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(setor="Recepcao")]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 409, r.text
        assert "não está aguardando a área" in r.json()["detail"]
        assert _nunca_envia_email_de_verdade == []
        assert supabase.tabelas.get("ouvidoria_setor_tokens", []) == []
        assert supabase.tabelas["ouvidoria_notificacoes"] == []

    def test_cadastro_que_nao_pode_ser_lido_nao_vira_setor_sem_ninguem(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Leitura que falha não é "setor sem responsável": a recusa tem de
        dizer que o cadastro não foi lido, senão um timeout manda o ouvidor
        cadastrar quem já está cadastrado."""
        client, supabase = self._acionado(monkeypatch)
        _nunca_envia_email_de_verdade.clear()
        supabase.indisponiveis.add("ouvidoria_setor_responsaveis")

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 503, r.text
        assert "cadastro de responsáveis" in r.json()["detail"]
        assert _nunca_envia_email_de_verdade == []

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN])
    def test_quem_nao_e_da_ouvidoria_nao_cobra(self, monkeypatch, participante):
        """A cobrança manda o relato do manifestante e um token do portal: é
        ato da Ouvidoria, com o mesmo gate do reenvio pelo Dossiê."""
        _, supabase = self._acionado(monkeypatch)
        de_fora, _ = _client(monkeypatch, participante, supabase)

        assert de_fora.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor").status_code == 403
