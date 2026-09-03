"""A ação do próprio ouvidor carimba o visto (issue #521, RN-66).

A régua do visto passa a ter DOIS lugares que carimbam, e é decisão do humano
na triagem da #521:

* a LEITURA: abrir o Dossiê, que é o carimbo original da issue #484 e continua
  valendo sem nenhuma mudança;
* a AÇÃO: encerrar e validar. São as duas ações que o ouvidor dispara pelo
  botão da própria lista, sem abrir o caso.

Sem o segundo carimbo, encerrar ou validar pela lista gravava um movimento
novo na trilha, e a régua da novidade (`ultimo_movimento_em > vista`) acendia o
ponto e subia o contador logo depois de o ouvidor ter trabalhado no caso. O
sinal existe para dizer "tem coisa nova aqui que você não viu", e não pode
dizer isso sobre o que ele mesmo acabou de fazer.

Nada mais carimba. Pausar, retomar, devolver, responder e reabrir seguem
acendendo o ponto: nenhuma delas é o ouvidor dizendo "vi este caso e resolvi".

Duas armadilhas moram aqui, e os testes são montados contra elas:

* provar que um caminho NÃO carimba é fácil de fazer errado: o teste fica verde
  e vazio se a requisição morreu antes por outra razão (403, 409, 422). Por
  isso os testes do que não carimba abrem TODAS as outras portas e conferem o
  200 antes de olhar o efeito;
* o detector também pode ser cego: um helper que lesse a coluna errada ficaria
  verde em cima de um carimbo indevido. Por isso o mesmo detector é usado nos
  dois sentidos, e cada teste do ponto aceso tem irmão do ponto apagado.

O relógio destes testes ANDA. Um relógio congelado esconderia o erro mais
provável desta fatia: ler o instante do carimbo ANTES da transição (que é onde
a validação lê o relógio dela, para o prazo do setor) deixa o visto mais velho
que o próprio movimento, e o ponto continua aceso.
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
from app.services import ouvidoria_escalonamento, ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

# Terça-feira, 14h de Brasília: dentro do expediente e longe de feriado, como
# no teste da validação. O prazo do setor e a janela de envio do email dependem
# desta hora.
INICIO = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)

ENCERRAMENTO = {
    "estado": "encerrado",
    "desfecho": "procedente",
    "desfecho_descricao": "Recepcao ajustou a escala; manifestante avisado por telefone.",
}
VALIDACAO = {
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "gravidade": "medio",
    "extrato_para_o_setor": "Conduta da equipe na recepcao. Apurar e responder a Ouvidoria.",
}

# As doze células da migration 065, como no teste da validação: a rota lê duas
# colunas (o prazo da área e o conclusivo), e uma tabela pela metade aqui
# esconderia a troca de marco no código.
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
        enviados.append({"destinatario": destinatario, "assunto": assunto})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


class _Relogio:
    """O relógio do servidor e o do banco, que são o mesmo e ANDAM.

    Cada leitura avança um segundo. É o que dá sentido ao teste da ordem: com
    todo instante igual, carimbar o visto antes ou depois da transição daria o
    mesmo resultado, e o erro que esta fatia mais arrisca ficaria invisível."""

    def __init__(self, inicio: dt.datetime):
        self._agora = inicio

    def agora(self) -> dt.datetime:
        self._agora += dt.timedelta(seconds=1)
        return self._agora


def _caso(numero: int = 7, **overrides) -> dict:
    """Uma linha de `ouvidoria_protocolos` com as colunas que as três rotas
    envolvidas leem: a fila, a transição e a validação."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "respondido",
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-1",
        "gravidade": "medio",
        "prazo_area_em": None,
        "prazo_conclusivo_em": None,
        "respondida_em": None,
        "minutos_pausados": 0,
        "desfecho": None,
        "desfecho_descricao": None,
        "pausada_em": None,
        "area_estourou_em": None,
        "relato_integral": "Cheguei as 8h e so fui atendida as 10h30.",
        # Telefone, e não email: o aviso de encerramento não tem para onde ir e
        # o teste não depende do provedor.
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "natureza_informada": None,
        "canal": "ana",
        "canal_setor": None,
        "canal_ponto": None,
        "contato_em": "2026-08-14T19:50:00+00:00",
        "prazo_rompido_em": None,
        "validada_em": None,
        "validada_por": None,
        "resposta_da_area": None,
        "respondida_por_nome": None,
        "encerrada_em": None,
        "reincidencia": 0,
        "reaberta_em": None,
        # A vez única do aviso de caso crítico: nulo é caso ainda não avisado.
        "critico_avisado_em": None,
        "acuse_recebimento_em": None,
        "acuse_sem_contato_em": None,
        "encerramento_avisado_em": None,
        "encerramento_sem_contato_em": None,
        # O carimbo do visto: nulo é o normal do caso que ninguém abriu, e é o
        # estado em que o ponto está aceso.
        "vista_pela_ouvidoria_em": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só as colunas
    pedidas, o filtro casa por igualdade e o `range` recorta de verdade, para o
    laço da paginação ter fim."""

    def __init__(self, nome: str, rows: list[dict], relogio: _Relogio, falha_do_visto: Exception | None = None):
        self.nome = nome
        self.rows = rows
        self.relogio = relogio
        self.falha_do_visto = falha_do_visto
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
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        self._filters[col] = None if value in ("null", None) else value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, _quantas):
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
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
                # `ocorrido_em` é DEFAULT now() na trilha (migration 064), e o
                # insert de quem grava movimento FORA da RPC não manda a coluna
                # (o alerta de caso crítico e o de prazo rompido são assim). Sem
                # o default aqui, esse movimento nasceria sem instante e sumiria
                # do agregado da novidade: o fake esconderia justamente a ordem
                # que os testes existem para segurar.
                if self.nome == "ouvidoria_movimentos":
                    linha.setdefault("ocorrido_em", self.relogio.agora().isoformat())
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            # A falha é do carimbo do visto, e SÓ dele: derrubar todo update de
            # `ouvidoria_protocolos` levaria junto o T3 e o prazo, e o teste
            # provaria outra coisa.
            if self.falha_do_visto is not None and "vista_pela_ouvidoria_em" in self._update:
                raise self.falha_do_visto
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _AgregadoFake:
    """A função `ouvidoria_ultimo_movimento` (migration 092) servida como o
    PostgREST serve: em páginas e com ordem estável."""

    def __init__(self, linhas: list[dict]):
        self._linhas = sorted(linhas, key=lambda linha: linha["manifestacao_id"])

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        return _AgregadoFake(self._linhas[inicio : fim + 1])

    def execute(self):
        return type("R", (), {"data": [dict(linha) for linha in self._linhas]})()


class _SupabaseFake:
    def __init__(self, casos: list[dict], relogio: _Relogio):
        self.relogio = relogio
        # A exceção que o update do visto levanta, quando o teste quer o
        # fail-open. `None` significa banco de pé.
        self.falha_do_visto: Exception | None = None
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos,
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "ouvidoria_setor_responsaveis": [
                {
                    "id": "3f8a1c2e-1111-4a2b-9c3d-000000000001",
                    "setor": "Recepcao",
                    "papel": "titular",
                    "nome": "Carlos Titular",
                    "email": "carlos@hsm.br",
                    "vigencia_inicio": "2026-01-01",
                    "vigencia_fim": None,
                }
            ],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            # A Diretoria Executiva de verdade, com perfil e email: é ela que faz
            # o ramo do caso crítico rodar em vez de desistir por falta de
            # destinatário (`_diretoria` devolvendo vazio).
            "participantes": [
                {
                    "id": "P11",
                    "nome_completo": "Dr. Diretor",
                    "email": "diretor@hsm.br",
                    "ativo": True,
                    "perfil_ouvidoria": "diretoria_executiva",
                }
            ],
        }

    def table(self, nome: str):
        falha = self.falha_do_visto if nome == "ouvidoria_protocolos" else None
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.relogio, falha)

    def rpc(self, nome: str, params: dict | None = None):
        if nome == "ouvidoria_ultimo_movimento":
            ultimo: dict[str, str] = {}
            for mov in self.tabelas["ouvidoria_movimentos"]:
                caso = str(mov["manifestacao_id"])
                ultimo[caso] = max(str(mov["ocorrido_em"]), ultimo.get(caso, ""))
            return _AgregadoFake([{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()])
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(c for c in self.tabelas["ouvidoria_protocolos"] if c["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        alvo["status"] = params["p_estado_novo"]
        if params.get("p_desfecho") is not None:
            alvo["desfecho"] = params["p_desfecho"]
        if params.get("p_desfecho_descricao") is not None:
            alvo["desfecho_descricao"] = params["p_desfecho_descricao"]
        # `ocorrido_em` é DEFAULT now() no banco (migration 064): o instante do
        # movimento nasce do relógio do servidor de banco, no meio da chamada, e
        # não do relógio que a rota leu antes de chamar.
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_id": params["p_autor_id"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
                "ocorrido_em": self.relogio.agora().isoformat(),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


def _client(monkeypatch, casos: list[dict] | None = None, participante: dict | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    relogio = _Relogio(INICIO)
    supabase = _SupabaseFake(casos if casos is not None else [_caso()], relogio)
    quem = participante if participante is not None else OUVIDOR

    async def _fake_participante(_user, _sb, fields=None):
        return quem

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", relogio.agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


# ---------------------------------------------------------------------------
# Os detectores. São dois, e cada um é exercitado NOS DOIS SENTIDOS ao longo do
# arquivo: se um deles olhasse a coluna errada, ficaria preso num só valor e o
# par de testes que o cerca reprovaria.
# ---------------------------------------------------------------------------


def _ponto_aceso(client, numero: int = 7) -> bool:
    """O ponto da linha, como a tela da fila o recebe."""
    r = client.get("/api/ouvidoria/protocolos")
    assert r.status_code == 200, r.text
    linha = next(p for p in r.json()["protocolos"] if p["id"] == f"uuid-{numero}")
    return linha["tem_novidade"]


def _contador(client) -> int | None:
    """O número do distintivo do menu."""
    r = client.get("/api/ouvidoria/novidades")
    assert r.status_code == 200, r.text
    return r.json()["total"]


def _visto(supabase, numero: int = 7):
    caso = next(c for c in supabase.tabelas["ouvidoria_protocolos"] if c["id"] == f"uuid-{numero}")
    return caso["vista_pela_ouvidoria_em"]


def _ultimo_movimento(supabase, numero: int = 7) -> str:
    movimentos = [m for m in supabase.tabelas["ouvidoria_movimentos"] if m["manifestacao_id"] == f"uuid-{numero}"]
    return max(m["ocorrido_em"] for m in movimentos)


def _encerrar(client, numero: int = 7):
    return client.post(f"/api/ouvidoria/manifestacoes/uuid-{numero}/transicoes", json=ENCERRAMENTO)


def _movimentos(supabase, numero: int = 7) -> list[dict]:
    return [m for m in supabase.tabelas["ouvidoria_movimentos"] if m["manifestacao_id"] == f"uuid-{numero}"]


def _validar(client, numero: int = 7, **campos):
    return client.post(f"/api/ouvidoria/manifestacoes/uuid-{numero}/validar", json=VALIDACAO | campos)


class TestOPontoAntesDaAcao:
    """A contraprova do arquivo inteiro: sem ela, todo teste daqui para baixo
    poderia estar provando que o ponto já estava apagado antes da ação."""

    def test_o_caso_nunca_visto_com_movimento_na_trilha_esta_com_o_ponto_aceso(self, monkeypatch):
        client, supabase = _client(monkeypatch, [_caso(status="aguardando_area")])
        client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "aguardando_manifestante", "observacao": "Falta o numero do leito."},
        )

        assert _ponto_aceso(client) is True
        assert _contador(client) == 1
        assert _visto(supabase) is None


class TestEncerrarCarimba:
    """Encerrar pela lista é ação do ouvidor, e ação dele carimba o visto."""

    def test_encerrar_apaga_o_ponto_da_linha(self, monkeypatch):
        client, supabase = _client(monkeypatch, [_caso(status="respondido")])

        assert _encerrar(client).status_code == 200

        assert _visto(supabase) is not None
        assert _ponto_aceso(client) is False

    def test_encerrar_nao_sobe_o_contador(self, monkeypatch):
        """O sintoma que o diretor veria: o número do menu subindo logo depois
        de o ouvidor ter encerrado o caso."""
        client, _ = _client(monkeypatch, [_caso(status="respondido")])

        assert _contador(client) == 1
        assert _encerrar(client).status_code == 200

        assert _contador(client) == 0

    def test_o_carimbo_e_mais_novo_que_o_movimento_do_proprio_encerramento(self, monkeypatch):
        """A régua compara `ultimo_movimento_em > vista`: um carimbo lido antes
        da transição fica mais VELHO que o movimento que ela grava, e o ponto
        continua aceso mesmo com a escrita acontecendo."""
        client, supabase = _client(monkeypatch, [_caso(status="respondido")])

        _encerrar(client)

        assert _visto(supabase) > _ultimo_movimento(supabase)

    def test_o_carimbo_e_so_do_caso_encerrado(self, monkeypatch):
        """Carimbo é do caso agido, e nunca da fila toda: apagar o ponto do
        vizinho esconderia trabalho que ninguém viu."""
        client, supabase = _client(monkeypatch, [_caso(numero=7, status="respondido"), _caso(numero=8)])

        assert _contador(client) == 2
        _encerrar(client, 7)

        assert _visto(supabase, 7) is not None
        assert _visto(supabase, 8) is None
        assert _ponto_aceso(client, 8) is True
        assert _contador(client) == 1

    @pytest.mark.parametrize(
        "falha",
        [
            # Timeout do PostgREST sobe cru, sem virar `APIError` (precedente do
            # módulo: `APIError` só nasce depois que a resposta HTTP chega).
            httpx.ReadTimeout("o PostgREST nao respondeu ao carimbo do visto"),
            # O socket embaixo do transporte. Antes desta issue o carimbo só
            # rodava em GET; agora ele roda depois de uma transição JÁ
            # COMMITADA, e uma exceção que escapasse daqui viraria 500 num ato
            # que já valeu: o ouvidor tentaria encerrar de novo o caso encerrado.
            ConnectionResetError("conexao com o PostgREST caiu no meio do carimbo"),
        ],
        ids=["timeout_httpx", "socket_oserror"],
    )
    def test_falha_ao_carimbar_nao_derruba_o_encerramento(self, monkeypatch, falha):
        """Mesma escolha do carimbo da leitura: o ato já está na trilha
        imutável, e perder o visto custa um ponto aceso a mais na fila."""
        client, supabase = _client(monkeypatch, [_caso(status="respondido")])
        supabase.falha_do_visto = falha

        r = _encerrar(client)

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "encerrado"
        assert caso["encerrada_em"], "o T3 é de outra escrita e não pode cair junto"
        assert _visto(supabase) is None


class TestValidarCarimba:
    """Validar pela lista despacha o caso sem abrir o Dossiê: a mesma régua."""

    def test_validar_apaga_o_ponto_da_linha(self, monkeypatch):
        client, supabase = _client(monkeypatch, [_caso(status="em_classificacao")])

        assert _validar(client).status_code == 200

        assert _visto(supabase) is not None
        assert _ponto_aceso(client) is False

    def test_validar_nao_sobe_o_contador(self, monkeypatch):
        client, _ = _client(monkeypatch, [_caso(status="em_classificacao")])

        assert _contador(client) == 1
        assert _validar(client).status_code == 200

        assert _contador(client) == 0

    def test_o_carimbo_e_mais_novo_que_o_movimento_da_propria_validacao(self, monkeypatch):
        """O ponto exato onde esta rota erraria: ela lê o relógio ANTES da RPC,
        porque é dele que saem o prazo do setor e a hora do email. Reaproveitar
        aquele instante para o visto deixaria o carimbo mais velho que o
        movimento, e o ponto acenderia com a escrita feita."""
        client, supabase = _client(monkeypatch, [_caso(status="em_classificacao")])

        _validar(client)

        assert _visto(supabase) > _ultimo_movimento(supabase)

    def test_validar_caso_critico_apaga_o_ponto(self, monkeypatch):
        """O caso crítico avisa a Diretoria na hora (PRD #318, história 18), e
        esse aviso grava um movimento na trilha FORA da RPC da transição.

        É a ordem mais frágil da fatia: o carimbo tem que vir depois desse
        movimento também, senão TODO caso crítico validado volta com o ponto
        aceso, e ninguém repara, porque a validação em si funcionou.

        O teste só vale porque o fake sabe representar movimento gravado fora
        da RPC: `ocorrido_em` é DEFAULT now() no banco, o insert do alerta não
        manda a coluna, e sem o default do fake esse movimento sumiria do
        agregado da novidade."""
        client, supabase = _client(monkeypatch, [_caso(status="em_classificacao")])

        assert _validar(client, gravidade="critico").status_code == 200

        # A contraprova do próprio teste: sem o movimento do alerta, o cenário
        # seria o mesmo do caso médio e o teste não provaria ordem nenhuma.
        observacoes = [m.get("observacao") for m in _movimentos(supabase)]
        assert ouvidoria_escalonamento.OBSERVACAO_CRITICO in observacoes, (
            "o alerta de caso crítico não gravou movimento: o teste ficaria vazio"
        )
        assert _visto(supabase) > _ultimo_movimento(supabase)
        assert _ponto_aceso(client) is False
        assert _contador(client) == 0

    def test_transicao_recusada_na_validacao_nao_carimba(self, monkeypatch):
        """Caso que já está com a área não é validado de novo (é devolução, que
        tem porta própria). Sem transição não há ação do ouvidor, e sem ação
        não há visto: carimbar aqui apagaria o ponto de um caso intocado."""
        client, supabase = _client(monkeypatch, [_caso(status="aguardando_area")])

        assert _validar(client).status_code == 409
        assert _visto(supabase) is None


class TestOQueNaoCarimba:
    """A outra metade da régua. Cada teste aqui abre TODAS as outras portas (o
    perfil certo, a transição válida, o corpo completo) e confere o 200 antes
    de olhar o efeito: sem isso o verde provaria só que a requisição morreu
    antes de chegar ao carimbo."""

    def test_parar_o_caso_esperando_o_manifestante_nao_carimba(self, monkeypatch):
        client, supabase = _client(monkeypatch, [_caso(status="aguardando_area", prazo_area_em=None)])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "aguardando_manifestante", "observacao": "Falta o numero do leito."},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_manifestante"
        assert _visto(supabase) is None
        assert _ponto_aceso(client) is True
        assert _contador(client) == 1

    def test_encaminhar_a_area_pela_transicao_generica_nao_carimba(self, monkeypatch):
        """A porta genérica leva de `em_classificacao` para `aguardando_area`
        sem nada do que a validação faz (sem prazo, sem email ao setor). Não é
        a ação que a régua nomeia, e não carimba."""
        client, supabase = _client(monkeypatch, [_caso(status="em_classificacao")])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "aguardando_area", "observacao": "Encaminhado a Recepcao."},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"
        assert _visto(supabase) is None
        assert _ponto_aceso(client) is True
        assert _contador(client) == 1

    def test_a_transicao_recusada_nao_carimba(self, monkeypatch):
        """Encerrar sem desfecho é recusado, e o caso segue como estava. O
        carimbo não pode acontecer antes da regra valer."""
        client, supabase = _client(monkeypatch, [_caso(status="respondido")])

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/transicoes", json={"estado": "encerrado"})

        assert r.status_code == 422
        assert _visto(supabase) is None
        assert _ponto_aceso(client) is True
