"""Aguardando manifestante, sem retorno e reincidência (issue #335, PRD #318).

Quando falta dado de quem reclamou, o relógio da área para: o caso vai para
`aguardando_manifestante` e o tempo parado é devolvido ao prazo na retomada,
sem sumir do registro. Se o manifestante some de vez, o ouvidor encerra por
"sem retorno" depois de tentar contato de verdade, e esse desfecho fica neutro
no indicador. Se ele volta em até 30 dias, o caso original reabre marcado como
reincidência, em vez de virar caso novo (histórias 8 a 13 e 22 do PRD #318).

Cobre os critérios de aceite da #335 pelo seam HTTP, o mesmo das fatias
anteriores. O Resend nunca é chamado de verdade: o envio é mockado no ponto
único por onde todo email do app passa.
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

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

EXTRATO = "Demora na recepcao do plantao noturno. Apurar e responder a Ouvidoria."

VALIDACAO = {
    # Lista fechada desde a issue #372: é o tipo, e não o rótulo, que decide o
    # sigilo do caso.
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "gravidade": "medio",
    "extrato_para_o_setor": EXTRATO,
}

# Terça-feira, 14h de Brasília, dentro do expediente. Com prazo médio de 4 dias
# úteis, a manifestação validada aqui vence segunda 31/08 às 17h.
VALIDACAO_EM = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
PRAZO_ORIGINAL = "2026-08-31T20:00:00+00:00"

# Quarta 14h: falta o telefone do manifestante e o ouvidor pausa o caso.
PAUSA_EM = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)
# Sexta 14h: o manifestante respondeu e o caso volta para a área.
RETOMADA_EM = dt.datetime(2026, 8, 28, 17, 0, tzinfo=dt.UTC)
# O expediente parado entre as duas: quarta das 14h às 17h (3h), quinta inteira
# (9h) e sexta das 8h às 14h (6h). Dezoito horas úteis, dois dias de 9h.
MINUTOS_PAUSADOS = 18 * 60
# O vencimento original (segunda 17h) empurrado por esses dois dias úteis cai
# na quarta 02/09 às 17h. A área recebe de volta o mesmo tempo que perdeu, nem
# um minuto a mais.
PRAZO_APOS_RETOMADA = "2026-09-02T20:00:00+00:00"

MOTIVO_DA_PAUSA = "Falta o telefone do manifestante para confirmar a data do atendimento."


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
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
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
        "tipo_manifestacao": None,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "gravidade": None,
        "prazo_area_em": None,
        "prazo_rompido_em": None,
        "vespera_avisada_em": None,
        "escalonado_gestor_em": None,
        "escalonado_diretoria_em": None,
        "critico_avisado_em": None,
        "validada_em": None,
        "validada_por": None,
        "respondida_em": None,
        "resposta_da_area": None,
        "respondida_por_nome": None,
        "encerrada_em": None,
        # Desta fatia (issue #335).
        "pausada_em": None,
        "minutos_pausados": 0,
        "reincidencia": False,
        "reaberta_em": None,
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


PRAZOS = [
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
]


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, o insert devolve a linha com id, e os filtros filtram como lá."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._in: dict = {}
        self._ate: dict = {}
        self._de: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
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

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        self._filters[col] = None if value in ("null", None) else value
        return self

    def in_(self, col, values):
        self._in[col] = list(values)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def gte(self, col, value):
        self._de[col] = value
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

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
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
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
            and all(str(r.get(c) or "") >= v for c, v in self._de.items())
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


# O grafo que a RPC `ouvidoria_transicionar` aplica no banco (migrations 064,
# 074 e a 075 desta fatia). O fake recusa o que o banco recusaria, para o teste
# de transição proibida não passar só porque o Python foi generoso.
TRANSICOES_DO_BANCO = {
    "novo": {"em_classificacao"},
    "em_classificacao": {"aguardando_area", "encerrado"},
    "aguardando_area": {"respondido", "encerrado", "aguardando_area", "aguardando_manifestante"},
    "aguardando_manifestante": {"aguardando_area", "encerrado"},
    "respondido": {"encerrado", "aguardando_area"},
    "encerrado": {"aguardando_area"},
}

DESFECHOS_DO_BANCO = {
    "procedente",
    "improcedente",
    "parcialmente_procedente",
    "sem_condicoes_de_apuracao",
    "sem_retorno_do_manifestante",
}


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_tentativas_contato": [],
            "ouvidoria_setor_responsaveis": [_responsavel()],
            "ouvidoria_setor_tokens": [],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            "participantes": [
                {
                    "id": "P10",
                    "nome_completo": "Marta Ouvidora",
                    "email": "marta@hsm.br",
                    "perfil_ouvidoria": "ouvidor",
                },
            ],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar`: estado e movimento na
        mesma transação, com a regra do grafo aplicada antes."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        if params["p_estado_novo"] not in TRANSICOES_DO_BANCO.get(anterior, set()):
            raise APIError(
                {"message": f"Transicao invalida: {anterior} para {params['p_estado_novo']}", "code": "23514"}
            )
        if params["p_estado_novo"] == "encerrado" and (
            params.get("p_desfecho") not in DESFECHOS_DO_BANCO or not (params.get("p_desfecho_descricao") or "").strip()
        ):
            raise APIError({"message": "Encerrar exige desfecho e descricao", "code": "23514"})
        alvo["status"] = params["p_estado_novo"]
        if params.get("p_desfecho"):
            alvo["desfecho"] = params["p_desfecho"]
            alvo["desfecho_descricao"] = params.get("p_desfecho_descricao")
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
    supabase: _SupabaseFake | None = None,
    agora: dt.datetime = VALIDACAO_EM,
    participante: dict | None = None,
    relogio: dict | None = None,
):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante if participante is not None else OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    # Relógio compartilhado: pausa e retomada acontecem em instantes diferentes,
    # e o tempo devolvido ao prazo depende dos dois.
    relogio = relogio if relogio is not None else {"agora": agora}
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: relogio["agora"])
    monkeypatch.setattr(settings, "frontend_url", "http://app.test")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _acionado(monkeypatch, relogio: dict | None = None) -> tuple[TestClient, _SupabaseFake]:
    """Caso validado e com a área acionada, que é onde a pausa começa."""
    client, sb = _client(monkeypatch, relogio=relogio)
    assert client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO).status_code == 200
    assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL
    return client, sb


def _transicionar(client, estado: str, manifestacao_id: str = "uuid-7", **corpo):
    return client.post(
        f"/api/ouvidoria/manifestacoes/{manifestacao_id}/transicoes",
        json={"estado": estado, **corpo},
    )


class TestPausaERetomada:
    """Critério 1: as transições aguardando área ↔ aguardando manifestante
    funcionam, e o relógio da área pausa e retoma (histórias 8 e 9)."""

    def test_pausa_leva_o_caso_para_aguardando_manifestante(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        resposta = _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA)

        assert resposta.status_code == 200, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"

    def test_retomada_devolve_ao_prazo_o_tempo_util_que_o_caso_ficou_parado(self, monkeypatch):
        """O relógio não some nem recomeça: o vencimento anda para frente
        exatamente o expediente que o caso passou esperando o manifestante."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200

        relogio["agora"] = RETOMADA_EM
        resposta = _transicionar(client, "aguardando_area")

        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["prazo_area_em"] == PRAZO_APOS_RETOMADA


class TestOsMarcosVoltamComOCaso:
    """A página do caso TROCA o caso da tela pelo corpo que estas rotas
    devolvem (issue #480). Dossiê pela metade aqui não dá erro nenhum: o bloco
    dos quatro marcos, o prazo da área e a data de validação simplesmente somem
    da tela no primeiro clique do ouvidor, e só voltam se ele recarregar a
    página."""

    def test_a_pausa_devolve_o_dossie_com_os_marcos_e_os_prazos(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        corpo = _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).json()

        assert [m["chave"] for m in corpo["marcos"]] == ["T0", "T1", "T2", "T3"]
        assert [p["chave"] for p in corpo["prazos"]] == ["area", "conclusivo"]
        # O calendário foi lido pela porta nomeada: sem isso a tela afirmaria
        # dias úteis que ninguém confirmou (issue #449).
        assert corpo["degradado"] == []

    def test_a_reabertura_devolve_os_marcos_do_ciclo_novo(self, monkeypatch):
        """O número volta recalculado do caso JÁ gravado, e não do que estava
        na tela: a reabertura tira a conclusão do ciclo corrente, e é isso que
        o ouvidor precisa ver na hora."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        corpo = _reabrir(client).json()

        conclusao = corpo["marcos"][3]
        assert conclusao["pendente"] is True
        assert conclusao["tramitacao_anterior_em"] is not None


class TestRelatoSeparadoDoTempoPausado:
    """Critério 2: o tempo pausado é descontado do prazo E reportado à parte.

    Só descontar esconderia lentidão real: um caso que demorou um mês com duas
    semanas de espera pelo manifestante mostraria duas semanas de trabalho. A
    Diretoria precisa dos dois números (história 10)."""

    def test_dossie_reporta_o_expediente_que_o_caso_ficou_esperando(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
        relogio["agora"] = RETOMADA_EM
        assert _transicionar(client, "aguardando_area").status_code == 200

        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert dossie.status_code == 200, dossie.text
        assert dossie.json()["minutos_pausados"] == MINUTOS_PAUSADOS

    def test_indice_do_painel_traz_o_tempo_pausado_ao_lado_do_prazo(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
        relogio["agora"] = RETOMADA_EM
        assert _transicionar(client, "aguardando_area").status_code == 200

        indice = client.get("/api/ouvidoria/protocolos")

        assert indice.status_code == 200, indice.text
        caso = next(p for p in indice.json()["protocolos"] if p["id"] == "uuid-7")
        assert caso["minutos_pausados"] == MINUTOS_PAUSADOS
        # O desconto e o relato não se confundem: o prazo já veio empurrado, e
        # o número da espera continua visível ao lado dele.
        assert caso["prazo_area_em"] == PRAZO_APOS_RETOMADA

    def test_duas_pausas_somam_no_mesmo_acumulado(self, monkeypatch):
        """O relato é do caso, não da última espera."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
        relogio["agora"] = RETOMADA_EM
        assert _transicionar(client, "aguardando_area").status_code == 200

        # Segunda espera: segunda 31/08 das 9h às 12h de Brasília, três horas
        # inteiras dentro do expediente.
        relogio["agora"] = dt.datetime(2026, 8, 31, 12, 0, tzinfo=dt.UTC)
        assert _transicionar(client, "aguardando_manifestante", observacao="Falta a data exata.").status_code == 200
        relogio["agora"] = dt.datetime(2026, 8, 31, 15, 0, tzinfo=dt.UTC)
        assert _transicionar(client, "aguardando_area").status_code == 200

        assert sb.tabelas["ouvidoria_protocolos"][0]["minutos_pausados"] == MINUTOS_PAUSADOS + 3 * 60


# Cinco dias úteis contados da primeira tentativa (quarta 26/08 às 14h) terminam
# na quarta 02/09 às 14h de Brasília: 3h na quarta de partida e 9h em cada um
# dos quatro dias úteis seguintes.
ENCERRAMENTO_EM = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
# Um dia útil antes disso a espera ainda não fechou.
ENCERRAMENTO_CEDO = dt.datetime(2026, 9, 1, 17, 0, tzinfo=dt.UTC)

SEM_RETORNO = {
    "estado": "encerrado",
    "desfecho": "sem_retorno_do_manifestante",
    "desfecho_descricao": "Duas tentativas de contato sem resposta em cinco dias uteis.",
}


def _tentativa(client, canal: str = "telefone", manifestacao_id: str = "uuid-7", **corpo):
    return client.post(
        f"/api/ouvidoria/manifestacoes/{manifestacao_id}/tentativas-contato",
        json={"canal": canal, **corpo},
    )


def _pausado(monkeypatch, relogio: dict) -> tuple[TestClient, _SupabaseFake]:
    """Caso acionado e já parado esperando o manifestante, que é de onde o
    encerramento por abandono sai."""
    client, sb = _acionado(monkeypatch, relogio=relogio)
    relogio["agora"] = PAUSA_EM
    assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
    return client, sb


class TestEncerramentoSemRetorno:
    """Critério 3: encerrar por "sem retorno" só passa com duas tentativas de
    contato registradas e cinco dias úteis de espera (história 11).

    A leitura de "duas tentativas registradas em cinco dias úteis": as duas
    tentativas existem E a primeira delas tem pelo menos cinco dias úteis de
    idade. Sem a espera a regra não protegeria ninguém, porque duas ligações
    no mesmo minuto já liberariam o encerramento.
    """

    def test_encerrar_sem_nenhuma_tentativa_e_recusado(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _pausado(monkeypatch, relogio)

        relogio["agora"] = ENCERRAMENTO_EM
        resposta = _transicionar(client, **SEM_RETORNO)

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"

    def test_encerrar_com_uma_tentativa_so_e_recusado(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _pausado(monkeypatch, relogio)

        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201

        relogio["agora"] = ENCERRAMENTO_EM
        resposta = _transicionar(client, **SEM_RETORNO)

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"

    def test_encerrar_antes_dos_cinco_dias_uteis_e_recusado(self, monkeypatch):
        """Duas tentativas existem, mas a espera ainda não fechou."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _pausado(monkeypatch, relogio)

        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201
        relogio["agora"] = RETOMADA_EM
        assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201

        relogio["agora"] = ENCERRAMENTO_CEDO
        resposta = _transicionar(client, **SEM_RETORNO)

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"

    def test_encerrar_com_duas_tentativas_e_cinco_dias_uteis_passa(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _pausado(monkeypatch, relogio)

        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201
        relogio["agora"] = RETOMADA_EM
        assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201

        relogio["agora"] = ENCERRAMENTO_EM
        resposta = _transicionar(client, **SEM_RETORNO)

        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "encerrado"
        assert caso["desfecho"] == "sem_retorno_do_manifestante"

    def test_outros_desfechos_nao_pedem_tentativa_de_contato(self, monkeypatch):
        """A guarda é do abandono, não do encerramento em geral: caso apurado e
        respondido fecha sem ninguém ter que ligar para o manifestante."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _pausado(monkeypatch, relogio)

        relogio["agora"] = ENCERRAMENTO_EM
        resposta = _transicionar(
            client,
            estado="encerrado",
            desfecho="procedente",
            desfecho_descricao="A demora foi confirmada e a escala do plantao foi refeita.",
        )

        assert resposta.status_code == 200, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"

    def test_tentativas_registradas_ficam_visiveis_no_caso(self, monkeypatch):
        """O ouvidor precisa ver o que já tentou antes de decidir encerrar."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _pausado(monkeypatch, relogio)

        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201
        relogio["agora"] = RETOMADA_EM
        assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201

        listagem = client.get("/api/ouvidoria/manifestacoes/uuid-7/tentativas-contato")

        assert listagem.status_code == 200, listagem.text
        tentativas = listagem.json()["tentativas"]
        assert [t["canal"] for t in tentativas] == ["telefone", "email"]
        assert tentativas[0]["autor_nome"] == "Marta Ouvidora"


def _do_indice(client, manifestacao_id: str = "uuid-7") -> dict:
    indice = client.get("/api/ouvidoria/protocolos")
    assert indice.status_code == 200, indice.text
    return next(p for p in indice.json()["protocolos"] if p["id"] == manifestacao_id)


class TestDesfechoNeutroNoIndicador:
    """Critério 4: "sem retorno" não conta nem como resolvido nem como não
    resolvido (história 12).

    Contar como resolvido inflaria o acerto da Ouvidoria com caso que ninguém
    apurou; contar como não resolvido a puniria por alguém ter sumido. O
    consumo do número é do PRD 3; aqui ele nasce certo."""

    def test_caso_encerrado_por_sem_retorno_fica_fora_da_conta(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _pausado(monkeypatch, relogio)
        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201
        relogio["agora"] = RETOMADA_EM
        assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201

        relogio["agora"] = ENCERRAMENTO_EM
        assert _transicionar(client, **SEM_RETORNO).status_code == 200

        assert _do_indice(client)["conta_no_indicador_de_resolucao"] is False

    def test_caso_apurado_conta_na_divisao_entre_resolvido_e_nao_resolvido(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _pausado(monkeypatch, relogio)

        relogio["agora"] = ENCERRAMENTO_EM
        assert (
            _transicionar(
                client,
                estado="encerrado",
                desfecho="improcedente",
                desfecho_descricao="A espera relatada nao foi confirmada pelo registro do plantao.",
            ).status_code
            == 200
        )

        assert _do_indice(client)["conta_no_indicador_de_resolucao"] is True

    def test_caso_ainda_aberto_nao_entra_na_conta(self, monkeypatch):
        """Sem desfecho não há o que classificar."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionado(monkeypatch, relogio=relogio)

        assert _do_indice(client)["conta_no_indicador_de_resolucao"] is False


# Segunda 21/09 às 14h de Brasília: dezenove dias corridos depois do
# encerramento, dentro da janela da reincidência.
REABERTURA_EM = dt.datetime(2026, 9, 21, 17, 0, tzinfo=dt.UTC)
# O prazo médio inteiro (4 dias úteis) contado dali vence sexta 25/09 às 17h: a
# área recebe o problema de volta com o relógio cheio, não com o resto do antigo.
PRAZO_APOS_REABERTURA = "2026-09-25T20:00:00+00:00"
# Trinta e três dias corridos depois do encerramento: fora da janela.
REABERTURA_TARDE = dt.datetime(2026, 10, 5, 17, 0, tzinfo=dt.UTC)

MOTIVO_DA_REABERTURA = "O manifestante retornou com o mesmo relato e trouxe a data exata do atendimento."


def _reabrir(client, motivo: str = MOTIVO_DA_REABERTURA, manifestacao_id: str = "uuid-7"):
    return client.post(f"/api/ouvidoria/manifestacoes/{manifestacao_id}/reaberturas", json={"motivo": motivo})


def _encerrado_sem_retorno(monkeypatch, relogio: dict) -> tuple[TestClient, _SupabaseFake]:
    """Caso abandonado e fechado, que é de onde a reabertura sai."""
    client, sb = _pausado(monkeypatch, relogio)
    assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201
    relogio["agora"] = RETOMADA_EM
    assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201
    relogio["agora"] = ENCERRAMENTO_EM
    assert _transicionar(client, **SEM_RETORNO).status_code == 200
    return client, sb


class TestReaberturaComReincidencia:
    """Critério 5: o manifestante que volta em até 30 dias corridos reabre o
    caso original marcado como reincidência, em vez de gerar caso novo
    (história 13)."""

    def test_reabertura_devolve_o_caso_a_area_marcado_como_reincidencia(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        resposta = _reabrir(client)

        assert resposta.status_code == 201, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["reincidencia"] is True
        assert caso["reaberta_em"] == REABERTURA_EM.isoformat()

    def test_reabertura_nao_gera_protocolo_novo(self, monkeypatch):
        """O caso original continua sendo um só: é isso que impede a
        reincidência de inflar o volume de casos novos."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)
        protocolo = sb.tabelas["ouvidoria_protocolos"][0]["protocolo"]

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        assert len(sb.tabelas["ouvidoria_protocolos"]) == 1
        assert sb.tabelas["ouvidoria_protocolos"][0]["protocolo"] == protocolo

    def test_area_recebe_o_prazo_inteiro_da_gravidade_e_e_avisada(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Sem prazo novo o caso voltaria à área sem relógio, e nenhum degrau
        da escada de cobrança o encontraria."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)
        _nunca_envia_email_de_verdade.clear()

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_APOS_REABERTURA
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

    def test_reabertura_sem_motivo_e_recusada(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        resposta = _reabrir(client, motivo="   ")

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"

    def test_reabertura_depois_de_trinta_dias_e_recusada(self, monkeypatch):
        """Fora da janela não é eco do mesmo problema: o caminho é registrar
        manifestação nova, e reabrir um caso velho embaralharia os marcos."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_TARDE
        resposta = _reabrir(client)

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"
        assert sb.tabelas["ouvidoria_protocolos"][0]["reincidencia"] is False

    def test_reabrir_caso_que_nao_esta_encerrado_e_recusado(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        resposta = _reabrir(client)

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"

    def test_transicao_generica_nao_reabre_o_caso_pela_porta_de_tras(self, monkeypatch):
        """Reabrir pelo painel sem passar pela reabertura devolveria o caso à
        área sem prazo, sem marca de reincidência e sem ninguém avisado."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        resposta = _transicionar(client, "aguardando_area")

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"


class TestTrilhaDoCaso:
    """Critério 6: pausa, retomada, encerramento e reabertura aparecem na
    trilha imutável do caso (história 22).

    A trilha é a fonte da verdade dos atos: os carimbos no caso guardam o
    estado de agora, e só ela guarda a história de como o caso chegou nele."""

    def test_os_quatro_atos_novos_ficam_registrados_em_ordem(self, monkeypatch):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
        assert _tentativa(client, observacao="Ligacao sem atendimento.").status_code == 201

        relogio["agora"] = RETOMADA_EM
        assert _transicionar(client, "aguardando_area", observacao="O manifestante ligou de volta.").status_code == 200
        assert _tentativa(client, canal="email", observacao="Email sem resposta.").status_code == 201

        # Segunda 31/08 às 14h: falta outro dado e o caso para de novo.
        relogio["agora"] = dt.datetime(2026, 8, 31, 17, 0, tzinfo=dt.UTC)
        assert _transicionar(client, "aguardando_manifestante", observacao="Falta a data exata.").status_code == 200

        relogio["agora"] = ENCERRAMENTO_EM
        assert _transicionar(client, **SEM_RETORNO).status_code == 200

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        caminho = [(m["estado_anterior"], m["estado_novo"]) for m in sb.tabelas["ouvidoria_movimentos"]]
        assert caminho == [
            ("em_classificacao", "aguardando_area"),
            ("aguardando_area", "aguardando_manifestante"),
            ("aguardando_manifestante", "aguardando_area"),
            ("aguardando_area", "aguardando_manifestante"),
            ("aguardando_manifestante", "encerrado"),
            ("encerrado", "aguardando_area"),
        ]

    def test_o_motivo_escrito_pelo_ouvidor_viaja_junto_do_movimento(self, monkeypatch):
        """Sem o motivo na trilha, quem lê o caso meses depois vê o caso parar
        e voltar sem saber por quê."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        observacoes = [m["observacao"] for m in sb.tabelas["ouvidoria_movimentos"]]
        assert MOTIVO_DA_PAUSA in observacoes
        assert any(m and MOTIVO_DA_REABERTURA in m for m in observacoes)
        assert all(m["autor_nome"] == "Marta Ouvidora" for m in sb.tabelas["ouvidoria_movimentos"])


class TestOsAchadosDaRevisaoIndependente:
    """Buracos que o revisor de spec x diff encontrou antes do merge. Cada um
    quebra um critério de aceite por uma porta que os testes acima não olhavam."""

    def test_durante_a_pausa_o_indicador_de_prazo_congela(self, monkeypatch):
        """Critério 1. A escada de cobrança para porque filtra o status, mas a
        projeção do prazo não olhava status nenhum: um caso parado atravessando
        o vencimento aparecia como estourado, e o indicador de cumprimento
        carimbava falha contra a área por uma espera que não é dela."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200

        # Duas semanas parado: o vencimento original (segunda 31/08) ficou
        # muito para trás no calendário.
        relogio["agora"] = dt.datetime(2026, 9, 11, 17, 0, tzinfo=dt.UTC)
        caso = _do_indice(client)

        assert caso["prazo_estourado"] is False
        assert caso["cumprimento"] == "em_prazo"
        # O que sobra do prazo é o que sobrava quando o relógio parou: da
        # quarta 14h até segunda 17h são 3h na quarta e 9h em cada um dos três
        # dias úteis seguintes (quinta, sexta e segunda).
        assert caso["minutos_uteis_restantes"] == (3 + 9 * 3) * 60

    def test_encerrar_com_a_pausa_aberta_liquida_o_tempo_parado(self, monkeypatch):
        """Critério 2. Encerrar por "sem retorno" sai de aguardando manifestante,
        que é justamente o caso com pausa aberta. Sem liquidar ali, o relato
        separado perde a espera mais longa do caso: a que levou ao abandono."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["pausada_em"] is None
        # Este caminho não tem retomada: o caso ficou parado da quarta 26/08 às
        # 14h até a quarta 02/09 às 14h. São 3h na quarta de partida, cinco
        # dias úteis inteiros (quinta, sexta, segunda e terça) e 6h na quarta
        # em que o ouvidor encerrou.
        assert caso["minutos_pausados"] == (3 + 9 * 4 + 6) * 60
        # E a área não fica com estouro na ficha por uma espera que não é dela:
        # o vencimento acompanha o tempo parado, como na retomada.
        assert caso["prazo_area_em"] > PRAZO_ORIGINAL

    def test_reabertura_nao_herda_as_tentativas_do_ciclo_anterior(self, monkeypatch):
        """Critério 3. As duas tentativas que fecharam o ciclo passado já
        satisfaziam a regra: dava para reabrir e fechar por "sem retorno" no
        minuto seguinte, sem tentar falar com ninguém."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        # O caso volta a esperar o manifestante e o ouvidor tenta encerrar sem
        # nenhuma tentativa nova.
        assert (
            _transicionar(client, "aguardando_manifestante", observacao="Falta o retorno de novo.").status_code == 200
        )
        relogio["agora"] = REABERTURA_EM + dt.timedelta(days=40)
        resposta = _transicionar(client, **SEM_RETORNO)

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"

    def test_a_listagem_mostra_so_as_tentativas_que_a_regra_conta(self, monkeypatch):
        """A tela conta tentativas para dizer ao ouvidor se ele já pode
        encerrar. Mostrar as do ciclo anterior faria a conta da tela divergir
        da conta da regra."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _encerrado_sem_retorno(monkeypatch, relogio)

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201
        assert _tentativa(client, canal="whatsapp", observacao="Mensagem sem resposta.").status_code == 201

        listagem = client.get("/api/ouvidoria/manifestacoes/uuid-7/tentativas-contato")

        assert [t["canal"] for t in listagem.json()["tentativas"]] == ["whatsapp"]

    def test_reabertura_preserva_o_marco_do_encerramento_anterior(self, monkeypatch):
        """Zerar `encerrada_em` apagava o T3 do ciclo que fechou, e os
        relatórios do PRD 3 leem T0 a T3 como o tempo de uma tramitação."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)
        encerrada_em = sb.tabelas["ouvidoria_protocolos"][0]["encerrada_em"]
        assert encerrada_em is not None

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["encerrada_em"] == encerrada_em

    def test_pausar_depois_do_estouro_nao_apaga_o_estouro_consumado(self, monkeypatch):
        """Achado do code review. Prazo rompido é fato consumado: a área já
        falhou, e a cobrança já saiu. Empurrar o vencimento na retomada e zerar
        `prazo_rompido_em` faria o estouro sumir do indicador, e pausar viraria
        um jeito de limpar a ficha. O tempo parado ainda entra no relato."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        # A cobrança do vencimento já rodou: o prazo estourou na segunda 17h.
        caso["prazo_rompido_em"] = "2026-08-31T20:00:00+00:00"

        # Terça 14h, com o prazo já rompido, o ouvidor pausa.
        relogio["agora"] = dt.datetime(2026, 9, 1, 17, 0, tzinfo=dt.UTC)
        assert _transicionar(client, "aguardando_manifestante", observacao=MOTIVO_DA_PAUSA).status_code == 200
        # Quarta 14h o manifestante responde: um dia útil parado.
        relogio["agora"] = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        assert _transicionar(client, "aguardando_area").status_code == 200

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["prazo_area_em"] == PRAZO_ORIGINAL
        assert caso["prazo_rompido_em"] == "2026-08-31T20:00:00+00:00"
        assert caso["minutos_pausados"] == 9 * 60

    def test_reabertura_limpa_o_desfecho_do_ciclo_que_fechou(self, monkeypatch):
        """Achado do code review. A RPC aplica COALESCE no desfecho sem olhar o
        estado, então o caso voltava para a área ainda carregando o desfecho
        antigo: o indicador de resolução contava como resolvido um caso que
        ninguém tinha resolvido, e a tela mostrava desfecho em caso aberto."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)
        assert sb.tabelas["ouvidoria_protocolos"][0]["desfecho"] == "sem_retorno_do_manifestante"

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["desfecho"] is None
        assert caso["desfecho_descricao"] is None
        assert _do_indice(client)["conta_no_indicador_de_resolucao"] is False

    def test_reabertura_comeca_o_relato_de_espera_do_zero(self, monkeypatch):
        """Achado do code review. O ciclo novo ganha prazo inteiro novo, então
        dizer 'este caso já esperou X, e esse tempo saiu do seu prazo' seria
        mentira sobre o prazo que está correndo. O tempo do ciclo anterior
        continua na trilha."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _encerrado_sem_retorno(monkeypatch, relogio)
        assert sb.tabelas["ouvidoria_protocolos"][0]["minutos_pausados"] > 0

        relogio["agora"] = REABERTURA_EM
        assert _reabrir(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["minutos_pausados"] == 0
        assert sb.tabelas["ouvidoria_protocolos"][0]["pausada_em"] is None

    @pytest.mark.parametrize("observacao", [None, "", "   "])
    def test_pausa_sem_motivo_e_recusada_pelo_servidor(self, monkeypatch, observacao):
        """Achado do code review. A exigência do motivo estava só no navegador.
        Um POST direto parava o relógio da área com movimento sem observação,
        que é a mesma porta de fundo que as guardas da devolução e da
        reabertura fecham."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionado(monkeypatch, relogio=relogio)

        relogio["agora"] = PAUSA_EM
        corpo = {} if observacao is None else {"observacao": observacao}
        resposta = _transicionar(client, "aguardando_manifestante", **corpo)

        assert resposta.status_code == 422, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["pausada_em"] is None


class TestReaberturaNaoVazaIdentificacao:
    """Achado da revisão de segurança. A reabertura virou uma SEGUNDA porta
    para o setor, ao lado do acionamento, e não repetia as guardas dele.

    O acionamento reaplica `nasce_sigilosa(categoria)` antes de despachar
    (ADR 0034, decisão 8): denúncia e relato de conduta sobem para sigiloso, e
    o portal do setor esconde o nome de quem manifestou. Sem isso, o email da
    reabertura leva token de portal e o responsável do setor lê o nome do
    manifestante de uma denúncia."""

    def test_reabrir_caso_que_nunca_foi_acionado_e_recusado(self, monkeypatch):
        """A raiz do vazamento: caso encerrado direto da classificação nunca
        passou pela validação, então não tem gravidade, prazo, extrato nem
        elevação de sigilo. Devolvê-lo à área despacharia um caso que o setor
        nunca viu, sem nada do que o acionamento garante."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="encerrado",
                    categoria="Denuncia de conduta",
                    setor="Recepcao",
                    encerrada_em=ENCERRAMENTO_EM.isoformat(),
                    desfecho="sem_condicoes_de_apuracao",
                    desfecho_descricao="Sem elementos para apurar.",
                    validada_em=None,
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=REABERTURA_EM)

        resposta = _reabrir(client)

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"
        assert sb.tabelas["ouvidoria_notificacoes"] == []

    def test_reabertura_eleva_o_sigilo_do_tipo_antes_de_despachar(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Defesa em profundidade: mesmo com o caso validado, a reabertura
        repete a elevação em vez de confiar que alguém já a aplicou. Toda porta
        que leva o caso ao setor carrega a mesma guarda."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="encerrado",
                    tipo_manifestacao="denuncia",
                    categoria="Denuncia de conduta",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    validada_em=VALIDACAO_EM.isoformat(),
                    encerrada_em=ENCERRAMENTO_EM.isoformat(),
                    desfecho="sem_condicoes_de_apuracao",
                    desfecho_descricao="Sem elementos para apurar.",
                    sigilo_reforcado=False,
                    manifestante_nome="Joana da Silva",
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=REABERTURA_EM)

        assert _reabrir(client).status_code == 201, "a reabertura de caso validado continua valendo"

        assert sb.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True
        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")
        assert "Joana" not in email["texto"] and "Joana" not in email["html"]

    def test_reabertura_de_caso_comum_nao_esconde_o_caso_de_todo_mundo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O contra-teste do de cima, e o que prova que a guarda olha o TIPO.
        Sem ele, uma reabertura que forçasse sigilo em todo caso passaria nos
        dois: reclamação reaberta sumiria do painel de facilitador, secretária
        e super admin, para sempre, sem ninguém ter pedido."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="encerrado",
                    tipo_manifestacao="reclamacao",
                    categoria="Demora no atendimento",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    validada_em=VALIDACAO_EM.isoformat(),
                    encerrada_em=ENCERRAMENTO_EM.isoformat(),
                    desfecho="sem_condicoes_de_apuracao",
                    desfecho_descricao="Sem elementos para apurar.",
                    sigilo_reforcado=False,
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=REABERTURA_EM)

        assert _reabrir(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False


class TestReaberturaPreservaAProvaDaResposta:
    """Segundo achado da revisão de segurança, e regressão introduzida pela
    correção anterior: `resposta_da_area` é a resposta corrente que o ouvidor
    relê. A devolução da #334 preserva o campo de propósito; a reabertura
    passou a apagá-lo, e numa Ouvidoria hospitalar esse texto é a prova do que
    a área respondeu. Desde a #374 o movimento da trilha guarda uma cópia
    imutável por ciclo, mas a coluna continua sendo o que a tela mostra."""

    def test_reabertura_nao_apaga_o_texto_que_o_setor_escreveu(self, monkeypatch):
        resposta_antiga = "Refizemos a escala do plantao noturno e orientamos a equipe da recepcao."
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="encerrado",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    validada_em=VALIDACAO_EM.isoformat(),
                    encerrada_em=ENCERRAMENTO_EM.isoformat(),
                    desfecho="procedente",
                    desfecho_descricao="A demora foi confirmada.",
                    respondida_em="2026-08-27T17:00:00+00:00",
                    resposta_da_area=resposta_antiga,
                    respondida_por_nome="Carlos Titular",
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=REABERTURA_EM)

        assert _reabrir(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["resposta_da_area"] == resposta_antiga
        # O marco T2 e o crédito saem, como na devolução: é o T2 que move o
        # indicador de cumprimento, e a resposta antiga não vale para o ciclo
        # novo. O texto fica, porque não existe outra cópia dele.
        assert caso["respondida_em"] is None
        assert caso["respondida_por_nome"] is None
