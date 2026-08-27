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


# Seed da migration 065: o que a área tem para responder um caso médio.
PRAZOS = [
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
]


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
            return type("R", (), {"data": []})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


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

    def table(self, nome: str):
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
        assert supabase.tabelas["ouvidoria_notificacoes"] == [], "Setor não é acionado por transição recusada"

    def test_caso_ja_acionado_nao_e_acionado_de_novo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A porta do despacho é única: repetir a validação de um caso que já
        está com a área acordaria o setor duas vezes pelo mesmo motivo."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(status="aguardando_area")]))

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert r.status_code == 409
        assert _nunca_envia_email_de_verdade == []


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


class TestExtratoParaOSetor:
    """O extrato que o setor recebe é escrito pelo ouvidor, não copiado do
    relato (decisão de 25/08).

    O responsável do setor é gente de fora da Ouvidoria, sem login no app. O
    email dele não pode carregar a palavra crua de quem manifestou, ainda mais
    embaixo de um selo que promete o contrário."""

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

    def test_extrato_do_ouvidor_manda_no_email_do_caso_comum(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        email = _nunca_envia_email_de_verdade[0]
        assert EXTRATO in email["html"]
        assert "espera acima de duas horas" not in email["html"]


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
