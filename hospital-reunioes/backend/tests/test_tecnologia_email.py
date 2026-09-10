"""Os tres avisos por e-mail da aba Tecnologia (issue #642, PRD #634, ADR 0050).

Tres seams, na ordem em que a regra existe:

* **Quem recebe**, funcao pura, testada direto e sem HTTP. E aqui que moram as
  duas regras que a issue cobra: quem fez a acao nunca recebe, e a mesma pessoa
  nao leva dois avisos da mesma acao.
* **O envio**, com o transporte dublado. O que se prova e a peneira (quem
  perdeu o acesso a aba nao recebe, quem nao tem endereco nao recebe) e o que o
  envio devolve quando alguma parte falha.
* **Os gatilhos**, pela ROTA de verdade com o Supabase dublado, no molde dos
  arquivos das fatias anteriores: sao os tres, e SO os tres.

**Nenhum e-mail de verdade sai daqui.** Sao duas travas em serie, e as duas
importam:

1. o `_enviar_email` do `tecnologia_email` e trocado por um gravador em TODO
   teste deste arquivo (`autouse`), entao o codigo do repo nunca chega ao
   `resend` nem ao `smtplib`;
2. por baixo, a trava de rede do `conftest.py` sobe em `pytest_configure` e
   derruba a sessao inteira se alguem tentar abrir socket para fora. O pytest
   carrega o `.env` REAL, com usuario e senha de SMTP do Gmail: um teste que
   esquecesse a primeira trava nao ficaria verde em silencio, ele estouraria.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import tecnologia_email  # noqa: E402
from app.services.tecnologia import (  # noqa: E402
    AVISO_EMAIL_NAO_SAIU,
    CONTINUA_NA_DEMANDA,
    LIMITE_TRECHO,
    SEM_TRECHO,
    avisos_da_resposta,
    destinatario_da_atribuicao,
    mencoes_acrescentadas,
    trecho_do_aviso,
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda a contagem num storage de PROCESSO (issue #642).

    As tres rotas de gatilho ganharam `@limiter.limit`, e o `TestClient` sempre
    chega do mesmo endereco: sem este reset, o 61o request do ARQUIVO leva 429 e
    o teste que quebra e o proximo da fila, nao o que estourou o teto.
    """
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ─── 1. Quem recebe: a regra pura ────────────────────────────────────────────


class TestDestinatarioDaAtribuicao:
    def test_o_novo_responsavel_recebe(self):
        assert destinatario_da_atribuicao(responsavel_id="P2", quem_fez="P1") == "P2"

    def test_quem_atribuiu_a_si_mesmo_nao_recebe(self):
        """Ninguem quer receber aviso do que acabou de fazer (PRD #634,
        historia 46)."""
        assert destinatario_da_atribuicao(responsavel_id="P1", quem_fez="P1") is None

    def test_sem_responsavel_nao_ha_a_quem_avisar(self):
        assert destinatario_da_atribuicao(responsavel_id=None, quem_fez="P1") is None

    def test_responsavel_vazio_nao_e_pessoa(self):
        """`""` nao e NULL e nao e ninguem: mandado adiante, viraria uma busca
        por participante de id vazio."""
        assert destinatario_da_atribuicao(responsavel_id="", quem_fez="P1") is None


class TestAvisosDaResposta:
    def test_os_mencionados_recebem_o_aviso_de_mencao(self):
        avisos = avisos_da_resposta(responsavel_id="P9", mencoes=["P2", "P3"], quem_fez="P1")
        assert avisos.mencionados == ["P2", "P3"]

    def test_quem_respondeu_nao_recebe_nem_mencionando_a_si_mesmo(self):
        avisos = avisos_da_resposta(responsavel_id="P9", mencoes=["P1", "P2"], quem_fez="P1")
        assert avisos.mencionados == ["P2"]

    def test_o_responsavel_recebe_o_aviso_de_resposta(self):
        avisos = avisos_da_resposta(responsavel_id="P9", mencoes=[], quem_fez="P1")
        assert avisos.responsavel == "P9"

    def test_o_responsavel_que_respondeu_nao_recebe(self):
        """A bola nao voltou para ele: foi ele que bateu."""
        avisos = avisos_da_resposta(responsavel_id="P1", mencoes=[], quem_fez="P1")
        assert avisos.responsavel is None

    def test_sem_duplicata_quando_o_responsavel_tambem_foi_mencionado(self):
        """O criterio da issue #642. A mencao ganha porque e o aviso MAIS
        especifico: ela carrega o trecho em que a pessoa foi chamada pelo nome.

        As duas asseveracoes juntas sao a prova: dizer so que `responsavel` e
        `None` passaria numa implementacao que tambem perdesse a mencao, e a
        pessoa nao receberia aviso nenhum."""
        avisos = avisos_da_resposta(responsavel_id="P9", mencoes=["P9"], quem_fez="P1")
        assert avisos.mencionados == ["P9"]
        assert avisos.responsavel is None

    def test_mencao_repetida_no_payload_vira_um_destinatario_so(self):
        avisos = avisos_da_resposta(responsavel_id=None, mencoes=["P2", "P2", " P2 "], quem_fez="P1")
        assert avisos.mencionados == ["P2"]

    def test_a_demanda_sem_responsavel_ainda_avisa_os_mencionados(self):
        avisos = avisos_da_resposta(responsavel_id=None, mencoes=["P2"], quem_fez="P1")
        assert avisos.mencionados == ["P2"]
        assert avisos.responsavel is None


class TestMencoesAcrescentadas:
    """Quem ENTROU na menção pela correção (issue #670).

    A correção reescreve a linha inteira, e a lista que chega no PATCH é a
    lista FINAL: sem comparar com o que já estava gravado, avisar "os
    mencionados" chamaria de novo quem já tinha sido chamado pela mesma fala.
    """

    def test_quem_entrou_na_correcao_recebe(self):
        assert mencoes_acrescentadas(antes=[], depois=["P3"], quem_fez="P1") == ["P3"]

    def test_quem_ja_estava_mencionado_nao_entra_de_novo(self):
        assert mencoes_acrescentadas(antes=["P3"], depois=["P3"], quem_fez="P1") == []

    def test_so_o_que_entrou_e_avisado_quando_a_linha_ja_tinha_mencao(self):
        """A prova que separa "a diferença" de "a lista toda": um código que
        mandasse `depois` inteiro passaria no teste de cima quando a linha não
        tinha menção nenhuma."""
        assert mencoes_acrescentadas(antes=["P3"], depois=["P3", "P2"], quem_fez="P1") == ["P2"]

    def test_quem_corrige_nao_avisa_a_si_mesmo(self):
        """Mesma regra do envio: escrever "@Pedro" na própria correção é
        citar-se, não chamar."""
        assert mencoes_acrescentadas(antes=[], depois=["P1", "P2"], quem_fez="P1") == ["P2"]

    def test_tirar_uma_mencao_nao_avisa_ninguem(self):
        assert mencoes_acrescentadas(antes=["P2", "P3"], depois=["P3"], quem_fez="P1") == []

    def test_a_comparacao_e_sobre_os_ids_limpos(self):
        """As duas listas passam pelo `normalizar_mencoes`: sem isso, o mesmo id
        com um espaço a mais viraria "menção nova" e mandaria o e-mail de novo."""
        assert mencoes_acrescentadas(antes=[" P3 "], depois=["P3", "P3"], quem_fez="P1") == []

    def test_linha_sem_mencao_nenhuma_no_banco(self):
        """Coluna NULL: o PostgREST devolve `None`, e `None` não é iterável."""
        assert mencoes_acrescentadas(antes=None, depois=["P3"], quem_fez="P1") == ["P3"]


class TestTrechoDoAviso:
    def test_texto_curto_vai_inteiro(self):
        assert trecho_do_aviso("Precisa da sua decisão sobre a Ana.") == "Precisa da sua decisão sobre a Ana."

    def test_texto_sem_nada_diz_que_nao_ha_trecho(self):
        assert trecho_do_aviso("   ") == SEM_TRECHO
        assert trecho_do_aviso(None) == SEM_TRECHO

    def test_texto_longo_e_cortado_e_diz_que_continua(self):
        """O limite e escrito A MAO aqui (400), e nao lido da constante: um
        teste que medisse o corte contra o proprio `LIMITE_TRECHO` continuaria
        verde com o limite trocado para 4 ou para 40 mil."""
        assert LIMITE_TRECHO == 400
        longo = "a" * 900

        cortado = trecho_do_aviso(longo)

        assert cortado.startswith("a" * 400)
        assert "a" * 401 not in cortado
        assert cortado.endswith(CONTINUA_NA_DEMANDA)

    def test_o_texto_no_limite_exato_nao_ganha_a_marca(self):
        """Borda: 400 caracteres cabem inteiros, e dizer "continua" sobre um
        texto que nao continua seria mandar a pessoa procurar o que nao ha."""
        assert trecho_do_aviso("b" * 400) == "b" * 400


# ─── 2. Supabase dublê e transporte dublado ──────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    """PostgREST minimo: select/eq/in_/order/range/insert/update.

    `order` ACUMULA as colunas, e `range` existe, pelos mesmos motivos dos
    dubles irmaos depois da issue #641: o `_fio_ordenado` ordena por
    `criado_em` e desempata por `id`, e as leituras de lista sao paginadas.
    Um duble que guardasse so a ultima chamada de `order` deixaria a ordem
    cronologica do fio verde por outro motivo."""

    def __init__(self, rows: list[dict], nome: str, falhar_ao_ler: str | None = None):
        self._rows = rows
        self._nome = nome
        self._falhar_ao_ler = falhar_ao_ler
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._order: list[str] = []
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order.append(coluna)
        return self

    def range(self, inicio, fim):
        self._range = (inicio, fim)
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def insert(self, payload):
        linhas = payload if isinstance(payload, list) else [payload]
        self._insert = [dict(linha) for linha in linhas]
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        # A LEITURA que estoura o timeout do PostgREST (issue #670). O erro e
        # `httpx.ReadTimeout` de proposito: ele NAO e `APIError`, sobe cru, e o
        # projeto ja foi mordido por um `except APIError` que nao o pegava.
        if self._falhar_ao_ler == self._nome and self._insert is None and self._update is None:
            raise httpx.ReadTimeout("o PostgREST nao respondeu a tempo")

        if self._insert is not None:
            for i, linha in enumerate(self._insert):
                linha.setdefault("id", f"{self._nome}-{len(self._rows) + i + 1}")
                linha.setdefault("criado_em", f"2026-09-09T12:00:{len(self._rows) + i:02d}Z")
            self._rows.extend(self._insert)
            return _Result(data=[dict(linha) for linha in self._insert])

        casadas = [linha for linha in self._rows if self._casa(linha)]

        if self._update is not None:
            for linha in casadas:
                linha.update(self._update)
            return _Result(data=[dict(linha) for linha in casadas])

        for coluna in reversed(self._order):
            casadas.sort(key=lambda linha, c=coluna: (linha.get(c) is None, linha.get(c)))
        if self._range is not None:
            inicio, fim = self._range
            casadas = casadas[inicio : fim + 1]
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]], falhar_ao_ler: str | None = None):
        self.tabelas = tabelas
        # A tabela cuja LEITURA estoura. So a leitura: a escrita que ja
        # aconteceu antes dela continua acontecendo, que e o cenario inteiro.
        self.falhar_ao_ler = falhar_ao_ler
        # A thread da PRIMEIRA consulta de cada requisicao e a da rota, que roda
        # no event loop. A da ULTIMA e a do `_pessoas_por_id`, que acontece
        # DENTRO do envio. As duas juntas medem se o envio saiu do loop: a
        # primeira diz de onde ele saiu, a segunda diz onde ele foi parar.
        self.thread_da_primeira_consulta: int | None = None
        self.thread_da_ultima_consulta: int | None = None

    def table(self, nome: str):
        agora = threading.get_ident()
        if self.thread_da_primeira_consulta is None:
            self.thread_da_primeira_consulta = agora
        self.thread_da_ultima_consulta = agora
        return _TableQuery(self.tabelas.setdefault(nome, []), nome, self.falhar_ao_ler)


@dataclass
class _Enviado:
    destinatario: str
    assunto: str
    html: str
    texto: str
    # A thread em que o envio rodou. E o que prova que ele NAO segurou o event
    # loop (ver `TestOEnvioNaoSeguraOEventLoop`).
    thread: int = 0
    # O que o `email_service` escreveria no log no lugar do assunto de verdade.
    assunto_no_log: str | None = None
    endereco_fora_do_log: bool = False


@dataclass
class _Transporte:
    """O dublê do `_enviar_email`: guarda o que sairia e responde o que se pede.

    `falhar` liga o caminho do transporte configurado que RECUSOU (o
    `_enviar_email` de verdade devolve `False` ali), que e o unico caso em que
    a tela precisa ser avisada.
    """

    falhar: bool = False
    enviados: list[_Enviado] = field(default_factory=list)

    def __call__(self, destinatario, assunto, html_content, texto_fallback, *_a, **kw) -> bool:
        self.enviados.append(
            _Enviado(
                destinatario,
                assunto,
                html_content,
                texto_fallback,
                thread=threading.get_ident(),
                assunto_no_log=kw.get("assunto_no_log"),
                endereco_fora_do_log=bool(kw.get("endereco_fora_do_log")),
            )
        )
        return not self.falhar

    @property
    def destinatarios(self) -> list[str]:
        return [e.destinatario for e in self.enviados]


@pytest.fixture(autouse=True)
def transporte(monkeypatch) -> _Transporte:
    """A trava de e-mail de verdade deste arquivo. Ver o docstring do topo.

    O `transporte_configurado` vai junto, cravado em `True`, porque o dublê É um
    transporte que funciona. Sem isso o resultado dos testes passaria a depender
    do `.env` da máquina: no CI não há `RESEND_API_KEY` nem `SMTP_USER`, e a
    guarda do modo mock recusaria todo envio. Quem exercita a guarda é a classe
    `TestSemTransporteConfigurado`, que a desliga na mão.
    """
    dublê = _Transporte()
    monkeypatch.setattr(tecnologia_email, "_enviar_email", dublê)
    monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: True)
    return dublê


# ─── 3. Cenario ──────────────────────────────────────────────────────────────


def _pessoa(pid: str, nome: str, *, access_profile: str | None = "super_admin", ativo: bool = True, email=...) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid}@hsm.com" if email is ... else email,
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": ativo,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "data_cadastro": "2026-01-01",
    }


def _produto(pid: str = "prod-1", nome: str = "Ana", *, dono_id: str | None = "P1", ativo: bool = True) -> dict:
    return {"id": pid, "nome": nome, "ativo": ativo, "ordem": 1, "dono_id": dono_id}


def _demanda(did: str = "d1", **campos) -> dict:
    base = {
        "id": did,
        "titulo": "Encerrar conversas da Ana",
        "descricao": "O diretor precisa decidir o prazo.",
        "tipo": "decisao",
        "produto_id": "prod-1",
        "estado": "nova",
        "responsavel_id": "P1",
        "autor_id": "P1",
        "prioridade": "normal",
        "prazo": None,
        "criado_em": "2026-09-01T09:00:00Z",
        "atualizado_em": "2026-09-01T09:00:00Z",
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
    }
    base.update(campos)
    return base


def _conversa(cid: str = "c1", **campos) -> dict:
    """Uma linha `resposta` ja no fio, com `criado_em` de agora.

    A janela de 10 minutos conta a partir do `criado_em`: uma data fixa deixaria
    a correcao recusada com o passar do tempo, e o teste que quebraria seria o
    do gatilho, sem falar nada sobre a janela.
    """
    base = {
        "id": cid,
        "demanda_id": "d1",
        "autor_id": "P1",
        "linha": "resposta",
        "texto": "Decidido: sexta.",
        "mencoes": [],
        "movimento_campo": None,
        "movimento_de": None,
        "movimento_para": None,
        "criado_em": datetime.now(UTC).isoformat(),
        "editado_em": None,
    }
    base.update(campos)
    return base


PEDRO = _pessoa("P1", "Pedro Vitta")
SOCIA = _pessoa("P2", "Sócia Vitta")
DIRETOR = _pessoa("P3", "Diretor do Hospital")

BASE = "/api/admin/tecnologia"


def _montar(
    *,
    logado: dict = PEDRO,
    participantes: list[dict] | None = None,
    produtos: list[dict] | None = None,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    falhar_ao_ler: str | None = None,
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    # O limitador das rotas de gatilho precisa do `app.state` (o `main.py` faz o
    # mesmo): sem ele, `@limiter.limit` estoura em vez de limitar.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(tecnologia_router.router, prefix="/api")

    pessoas = [dict(p) for p in (participantes if participantes is not None else [PEDRO, SOCIA, DIRETOR])]
    if all(p["id"] != logado["id"] for p in pessoas):
        pessoas.append(dict(logado))

    sb = _SupabaseMock(
        tabelas={
            "participantes": pessoas,
            "tecnologia_produtos": [dict(p) for p in (produtos if produtos is not None else [_produto()])],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        },
        falhar_ao_ler=falhar_ao_ler,
    )

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


# ─── 4. Gatilho 1: a atribuicao (inclusive na criacao) ───────────────────────


class TestGatilhoAtribuicao:
    def test_a_criacao_avisa_o_dono_do_produto(self, transporte):
        """PRD #634, historia 41: "inclusive na criacao"."""
        client, _ = _montar(logado=PEDRO, produtos=[_produto(dono_id="P2")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201
        assert transporte.destinatarios == ["P2@hsm.com"]

    def test_quem_abre_a_demanda_no_proprio_produto_nao_recebe(self, transporte):
        """O Pedro e o dono do Produto e foi ele quem abriu: o aviso seria de si
        mesmo. A irma de presenca e o teste acima, com o mesmo endpoint."""
        client, _ = _montar(logado=PEDRO, produtos=[_produto(dono_id="P1")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201
        assert transporte.enviados == []

    def test_trocar_o_responsavel_avisa_quem_recebeu_a_demanda(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        assert resposta.status_code == 200
        assert transporte.destinatarios == ["P2@hsm.com"]

    def test_atribuir_a_si_mesmo_nao_manda_aviso(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P1"})

        assert resposta.status_code == 200
        assert transporte.enviados == []

    def test_o_aviso_traz_titulo_tipo_produto_trecho_e_link(self, transporte):
        """O criterio de conteudo da issue #642, no HTML e no texto simples.

        Cada um dos cinco campos e cobrado com um valor que NAO aparece em
        nenhum outro campo do cenario. E o que faz a assercao distinguir de
        verdade: com o Produto chamado "Ana" e o titulo "Prazo da Ana", um
        `assert "Ana" in corpo` casava com o TITULO, e trocar `produto_nome` por
        `produto_id` (o e-mail mostrando "prod-1") passava batido.
        """
        client, _ = _montar(
            logado=PEDRO,
            produtos=[_produto(nome="Portal do RH", dono_id="P2")],
            demandas=[
                _demanda(
                    responsavel_id="P1",
                    titulo="Rever o fluxo de férias",
                    descricao="Decidir até sexta.",
                )
            ],
        )

        client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        enviado = transporte.enviados[0]
        for corpo in (enviado.html, enviado.texto):
            assert "Rever o fluxo de férias" in corpo
            assert "Decisão" in corpo
            assert "Portal do RH" in corpo
            assert "Decidir até sexta." in corpo
            assert "/admin/tecnologia?demanda=d1" in corpo

    def test_o_aviso_nao_leva_id_nem_endereco_de_ninguem(self, transporte):
        """O par de AUSENCIA do teste acima, no molde do `texto_para_ia`.

        O e-mail sai do app e chega numa caixa de entrada, e o `_contexto` e o
        lugar onde alguem acrescenta um campo "so para depurar". Sem esta
        assercao, id de participante e endereco de terceiro entrariam no corpo
        sem nenhuma resistencia. O que a leitura precisa e o NOME de quem falou;
        a chave do nosso banco, nao.

        A irma de presenca e o teste acima, no mesmo cenario: o corpo NAO esta
        vazio, ele tem os cinco campos.

        Os ids do cenario levam hifen de proposito. O HTML carrega a logo em
        base64, e o alfabeto do base64 NAO tem hifen: um id como "P1" apareceria
        por acaso dentro da logo e a assercao acusaria vazamento que nao houve.
        """
        quem_escreve = _pessoa("part-aa1", "Pedro Vitta")
        chamada = _pessoa("part-bb2", "Sócia Vitta")
        responsavel = _pessoa("part-cc3", "Diretor do Hospital")
        client, _ = _montar(
            logado=quem_escreve,
            participantes=[quem_escreve, chamada, responsavel],
            demandas=[_demanda(responsavel_id=responsavel["id"])],
        )

        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Sócia Vitta, veja isto.", "mencoes": [chamada["id"]]},
        )

        assert len(transporte.enviados) == 2, "sem e-mail nenhum, a ausência abaixo passa de graça"
        for enviado in transporte.enviados:
            for corpo in (enviado.html, enviado.texto, enviado.assunto):
                assert "@hsm.com" not in corpo
                for pid in ("part-aa1", "part-bb2", "part-cc3"):
                    assert pid not in corpo


# ─── 5. Gatilho 2 e 3: a mencao e a resposta ─────────────────────────────────


class TestGatilhoResposta:
    def test_responder_avisa_o_responsavel(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.status_code == 201
        assert transporte.destinatarios == ["P2@hsm.com"]

    def test_o_responsavel_que_responde_nao_recebe_aviso_de_si(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Vou olhar."})

        assert resposta.status_code == 201
        assert transporte.enviados == []

    def test_a_mencao_avisa_quem_foi_chamado(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Diretor do Hospital, o que você acha?", "mencoes": ["P3"]},
        )

        assert resposta.status_code == 201
        assert transporte.destinatarios == ["P3@hsm.com"]

    def test_o_aviso_de_mencao_leva_o_trecho_da_resposta(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Diretor do Hospital, precisamos do aval do jurídico.", "mencoes": ["P3"]},
        )

        enviado = transporte.enviados[0]
        assert "precisamos do aval do jurídico." in enviado.texto
        assert "precisamos do aval do jurídico." in enviado.html

    def test_o_responsavel_mencionado_recebe_um_aviso_so(self, transporte):
        """O criterio "sem duplicata" visto pela rota: uma resposta, um e-mail
        para a Sócia, mesmo ela sendo responsavel E mencionada."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Sócia Vitta pode assumir?", "mencoes": ["P2"]},
        )

        assert transporte.destinatarios == ["P2@hsm.com"]

    def test_mencionado_e_responsavel_diferentes_recebem_os_dois_avisos(self, transporte):
        """A irma de presenca do teste acima: sem ela, um codigo que so mandasse
        UM e-mail por resposta passaria pelos dois."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Diretor do Hospital, veja isto.", "mencoes": ["P3"]},
        )

        assert sorted(transporte.destinatarios) == ["P2@hsm.com", "P3@hsm.com"]


# ─── 5.1 O gatilho da CORRECAO (issue #670) ──────────────────────────────────


class TestGatilhoDaCorrecao:
    """A mencao ACRESCENTADA na janela de 10 minutos tambem chama (issue #670).

    Aqui morava o teste que travava o comportamento errado: ele montava uma
    linha sem mencao, acrescentava uma na correcao e afirmava que nada saia. O
    docstring dele protegia o caso certo (nao chamar duas vezes quem ja foi
    chamado), e o cenario provava o oposto. Sao dois casos, e agora sao dois
    testes.

    A linha ja nasce no fio, com `criado_em` de agora: passar pelo POST primeiro
    misturaria o gatilho da resposta com o da correcao, que e justamente o que
    se quer separar aqui.
    """

    def test_a_mencao_que_entrou_na_correcao_chama_quem_entrou(self, transporte):
        """PRD #634, historia 42, pela porta da correcao. O responsavel e a
        Sócia, e ela NAO aparece: a correcao nao repete o "chegou resposta" que
        o envio ja mandou."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")], conversas=[_conversa()])

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert editada.status_code == 200
        assert transporte.destinatarios == ["P3@hsm.com"]

    def test_o_aviso_leva_o_texto_corrigido_e_o_produto(self, transporte):
        """Duas coisas que so a correcao resolve, e cada uma mata um erro:

        - o trecho sai da CORRECAO, e nao do que estava gravado: um e-mail com o
          texto velho chamaria a pessoa mostrando a frase em que ela ainda nao
          tinha sido citada;
        - o nome do PRODUTO aparece, o que so acontece com a Demanda passando
          pelo `_com_nomes`. Ele tem um valor que nao existe em nenhum outro
          campo do cenario, senao a assercao casaria com o titulo."""
        client, _ = _montar(
            logado=PEDRO,
            produtos=[_produto(nome="Radiologia")],
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[_conversa()],
        )

        client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, precisamos do aval do jurídico.", "mencoes": ["P3"]},
        )

        enviado = transporte.enviados[0]
        assert "precisamos do aval do jurídico." in enviado.texto
        assert "Decidido: sexta." not in enviado.texto
        assert "Radiologia" in enviado.html

    def test_quem_ja_estava_mencionado_nao_e_chamado_de_novo(self, transporte):
        """O caso que o teste antigo dizia proteger, agora com o cenario certo:
        a janela de 10 minutos e para corrigir digitacao, e um aviso por edicao
        chamaria a mesma pessoa duas vezes pela mesma fala."""
        client, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[_conversa(texto="@Diretor do Hospital, decidido: sexta.", mencoes=["P3"])],
        )

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert editada.status_code == 200
        assert transporte.enviados == []

    def test_a_correcao_chama_so_quem_entrou(self, transporte):
        """A prova de que o envio olha a DIFERENCA, e nao a lista final: um
        codigo que mandasse `mencoes` inteira passaria no primeiro teste desta
        classe e chamaria o Diretor duas vezes aqui."""
        client, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P1")],
            conversas=[_conversa(texto="@Diretor do Hospital, e agora?", mencoes=["P3"])],
        )

        client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, @Sócia Vitta, e agora?", "mencoes": ["P3", "P2"]},
        )

        assert transporte.destinatarios == ["P2@hsm.com"]

    def test_corrigir_sem_mexer_nas_mencoes_nao_manda_aviso(self, transporte):
        """A correcao de virgula continua muda, inclusive para o responsavel.

        A assercao do campo nao e enfeite: "nao havia o que avisar" tem que
        chegar na tela como `None`, e nao como o aviso de falha. Sem ela, um
        codigo que devolvesse `AVISO_EMAIL_NAO_SAIU` quando nao ha ninguem a
        chamar pintaria o alerta em TODA correcao de virgula."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")], conversas=[_conversa()])

        editada = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Decidido: sexta-feira."})

        assert editada.status_code == 200
        assert transporte.enviados == []
        assert editada.json()["aviso_por_email"] is None

    def test_quem_corrige_nao_chama_a_si_mesmo(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")], conversas=[_conversa()])

        client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "Eu, @Pedro Vitta, fico com isso.", "mencoes": ["P1"]},
        )

        assert transporte.enviados == []

    def test_a_correcao_diz_na_tela_que_o_aviso_nao_saiu(self, transporte):
        """O mesmo campo do envio (issue #642): quem corrigiu e quem ainda pode
        dar o recado por outro caminho, e e a unica pessoa com a tela aberta."""
        transporte.falhar = True
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")], conversas=[_conversa()])

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert editada.status_code == 200
        assert editada.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU

    def test_a_leitura_que_estoura_depois_da_escrita_nao_vira_500(self, transporte):
        """O aviso da correcao le o Produto DEPOIS de a correcao estar gravada.

        Se essa leitura derrubar a rota, a tela diz "nao foi possivel salvar", a
        pessoa salva de novo, e na segunda vez a mencao JA esta na linha: a
        diferenca volta vazia e o e-mail nao sai nunca, que e o defeito que esta
        issue veio consertar. Por isso a falha vira aviso, e nao 500.

        O erro e `httpx.ReadTimeout`, e nao `APIError`: e o que o timeout do
        PostgREST sobe cru, e um `except APIError` nao o pegaria.
        """
        client, sb = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[_conversa()],
            falhar_ao_ler="tecnologia_produtos",
        )

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert editada.status_code == 200
        assert editada.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU
        # A correcao ENTROU: e por isso que a falha nao pode virar 500.
        gravada = sb.tabelas["tecnologia_conversas"][0]
        assert gravada["texto"] == "@Diretor do Hospital, decidido: sexta-feira."
        assert gravada["mencoes"] == ["P3"]
        assert gravada["editado_em"]
        # E o e-mail nao saiu, porque nem chegou ao transporte.
        assert transporte.enviados == []

    def test_o_duble_so_derruba_a_leitura_daquela_tabela(self, transporte):
        """O controle do teste acima: sem ele, um dublê que estourasse em
        qualquer consulta deixaria o 200 provado por acaso (a rota nem teria
        gravado), e um dublê que nao estourasse em nada deixaria o teste verde
        sobre falha nenhuma."""
        client, sb = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[_conversa()],
            falhar_ao_ler="tecnologia_produtos",
        )

        with pytest.raises(httpx.ReadTimeout):
            sb.table("tecnologia_produtos").select("*").execute()
        # As outras tabelas seguem lendo, e por isso a correcao chega a ser
        # gravada la em cima.
        assert sb.table("tecnologia_conversas").select("*").execute().data
        # E sem a injecao, nem essa tabela estoura.
        limpo = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])[1]
        assert limpo.table("tecnologia_produtos").select("*").execute().data is not None

    def test_a_correcao_que_avisou_nao_inventa_alarme(self, transporte):
        """A irma de presenca da de cima: um campo cravado no aviso pintaria o
        alerta em toda correcao."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")], conversas=[_conversa()])

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert transporte.destinatarios == ["P3@hsm.com"]
        assert editada.json()["aviso_por_email"] is None


# ─── 6. O que NAO manda e-mail ───────────────────────────────────────────────


class TestOQueNaoAvisa:
    @pytest.mark.parametrize("destino", ("em_andamento", "aguardando", "concluida", "cancelada"))
    def test_mover_de_coluna_nunca_manda_email(self, transporte, destino):
        """PRD #634, historia 44. Sao os quatro destinos que saem de `nova`, e
        nao um so: um `if` no destino errado deixaria tres passando."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2", estado="nova")])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": destino})

        assert resposta.status_code == 200
        assert transporte.enviados == []

    def test_editar_os_campos_da_demanda_nao_manda_email(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "Outro título"})

        assert resposta.status_code == 200
        assert transporte.enviados == []

    def test_atribuir_a_mesma_pessoa_de_novo_nao_manda_email(self, transporte):
        """A porta ja sai antes de gravar quando nada muda (issue #637), e e o
        que faz o duplo clique em "atribuir" NAO virar dois e-mails."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        primeira = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        assert primeira.status_code == 200
        assert transporte.enviados == []


# ─── 7. A allowlist do e-mail ────────────────────────────────────────────────


class TestQuemNaoRecebe:
    def test_o_responsavel_que_saiu_do_super_admin_nao_recebe(self, transporte):
        """O caminho REAL de um destinatario fora da lista: o responsavel.

        Ele foi gravado na Demanda quando tinha acesso, e perdeu o Super admin
        depois. E por isso que o envio recheca a allowlist, e nao por causa da
        mencao: as mencoes sao validadas e enviadas na MESMA requisicao (ver
        `test_a_mencao_a_quem_perdeu_o_acesso_nem_chega_ao_envio`), entao pela
        rota elas nunca chegam ao envio fora da lista.
        """
        saiu = _pessoa("P4", "Saiu do Super admin", access_profile="regular")
        client, _ = _montar(
            logado=PEDRO,
            participantes=[PEDRO, SOCIA, saiu],
            demandas=[_demanda(responsavel_id="P4")],
        )

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Alguém aí?"})

        assert resposta.status_code == 201
        assert transporte.enviados == []

    def test_a_mencao_a_quem_perdeu_o_acesso_nem_chega_ao_envio(self, transporte):
        """A rota fecha antes: 422 do `_texto_e_mencoes` (issue #638).

        Este teste existe para a prosa nao mentir. A "janela entre a mencao e o
        envio" tem o tamanho de UM request, porque as duas coisas acontecem na
        mesma chamada: a resposta nem e gravada.
        """
        saiu = _pessoa("P4", "Saiu do Super admin", access_profile="regular")
        client, sb = _montar(
            logado=PEDRO,
            participantes=[PEDRO, SOCIA, saiu],
            demandas=[_demanda(responsavel_id="P1")],
        )

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Saiu do Super admin, e aí?", "mencoes": ["P4"]},
        )

        assert resposta.status_code == 422
        assert sb.tabelas["tecnologia_conversas"] == []
        assert transporte.enviados == []

    def test_a_peneira_do_envio_vale_tambem_para_a_mencao(self, transporte):
        """A allowlist do ENVIO, cobrada no seam do proprio envio.

        Pela rota este caminho e inalcancavel hoje (o teste acima mostra por
        que), mas a regra e uma so, e quem escrever o proximo gatilho nao deve
        precisar saber qual dos dois caminhos e o real de hoje. Aqui a funcao e
        chamada direto, com um mencionado que nao tem acesso.
        """
        saiu = _pessoa("P4", "Saiu do Super admin", access_profile="regular")
        sb = _SupabaseMock(tabelas={"participantes": [dict(PEDRO), dict(SOCIA), dict(saiu)]})

        tudo_saiu = tecnologia_email.avisar_mencao(
            sb,
            demanda=_demanda(responsavel_id="P1"),
            destinatarios=["P4", "P2"],
            texto="@Saiu do Super admin e @Sócia Vitta, vejam.",
            quem_fez_nome="Pedro Vitta",
        )

        # A Sócia recebe, quem saiu não. E não é falha: o aviso de quem saiu
        # NÃO devia sair.
        assert transporte.destinatarios == ["P2@hsm.com"]
        assert tudo_saiu is True

    def test_o_responsavel_desativado_nao_recebe(self, transporte):
        desativado = _pessoa("P4", "Desativado", ativo=False)
        client, _ = _montar(
            logado=PEDRO,
            participantes=[PEDRO, SOCIA, desativado],
            demandas=[_demanda(responsavel_id="P4")],
        )

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Alguém aí?"})

        assert transporte.enviados == []

    def test_quem_tem_acesso_recebe_no_mesmo_cenario(self, transporte):
        """A irma de presenca das duas de cima: sem ela, um codigo que nunca
        mandasse e-mail nenhum passaria nas tres."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Alguém aí?"})

        assert transporte.destinatarios == ["P2@hsm.com"]


# ─── 8. Quando o e-mail nao sai ──────────────────────────────────────────────


class TestFalhaNoEnvio:
    def test_a_resposta_fica_gravada_mesmo_com_o_transporte_recusando(self, transporte):
        """O criterio da issue: falha no transporte NAO desfaz a acao."""
        transporte.falhar = True
        client, sb = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.status_code == 201
        assert [linha["texto"] for linha in sb.tabelas["tecnologia_conversas"]] == ["Decidido: sexta."]

    def test_a_falha_volta_para_a_tela_em_vez_de_passar_calada(self, transporte):
        transporte.falhar = True
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU

    def test_o_envio_que_deu_certo_nao_avisa_nada(self, transporte):
        """A irma de presenca: sem ela, um `aviso_por_email` cravado passaria."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] is None

    def test_a_demanda_nasce_mesmo_com_o_transporte_recusando(self, transporte):
        transporte.falhar = True
        client, sb = _montar(logado=PEDRO, produtos=[_produto(dono_id="P2")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201
        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU
        assert len(sb.tabelas["tecnologia_demandas"]) == 1

    def test_a_atribuicao_vale_mesmo_com_o_transporte_recusando(self, transporte):
        transporte.falhar = True
        client, sb = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        assert resposta.status_code == 200
        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU
        assert sb.tabelas["tecnologia_demandas"][0]["responsavel_id"] == "P2"

    def test_a_mencao_que_falha_nao_cancela_o_aviso_ao_responsavel(self, transporte):
        """Os dois gatilhos da mesma resposta sao tentados, mesmo com o
        primeiro falhando: uma falha nao pode virar duas por conta de um
        curto-circuito no `and` que junta os dois resultados."""
        transporte.falhar = True
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Diretor do Hospital, veja isto.", "mencoes": ["P3"]},
        )

        assert sorted(transporte.destinatarios) == ["P2@hsm.com", "P3@hsm.com"]

    def test_o_destinatario_sem_endereco_conta_como_aviso_que_nao_saiu(self, transporte):
        """Quem TEM acesso a aba devia receber. Sem endereco, o aviso nao chega
        a ninguem, e isso e falha, nao peneira: por isso a tela e avisada."""
        sem_email = _pessoa("P4", "Sem endereço", email=None)
        client, _ = _montar(
            logado=PEDRO,
            participantes=[PEDRO, SOCIA, sem_email],
            demandas=[_demanda(responsavel_id="P4")],
        )

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Alguém aí?"})

        assert transporte.enviados == []
        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU

    def test_quem_perdeu_o_acesso_a_aba_nao_e_falha(self, transporte):
        """Peneira, e nao falha: esse aviso NAO devia sair. Avisar a tela aqui
        cobraria de quem respondeu um conserto que nao existe, sobre um e-mail
        que o app decidiu nao mandar."""
        saiu = _pessoa("P4", "Saiu do Super admin", access_profile="regular")
        client, _ = _montar(
            logado=PEDRO,
            participantes=[PEDRO, SOCIA, saiu],
            demandas=[_demanda(responsavel_id="P4")],
        )

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Alguém aí?"})

        assert resposta.json()["aviso_por_email"] is None

    def test_o_erro_dentro_do_envio_nao_derruba_a_acao(self, transporte, monkeypatch):
        """Template quebrado, logo fora do ar, o que for: a resposta ja esta
        gravada, e um 500 aqui faria quem escreveu enviar de novo e duplicar a
        propria fala no fio."""

        def _explode(*_a, **_kw):
            raise RuntimeError("template sumiu")

        monkeypatch.setattr(tecnologia_email.jinja_env, "get_template", _explode)
        client, sb = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.status_code == 201
        assert len(sb.tabelas["tecnologia_conversas"]) == 1
        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU


# ─── 9. Os templates ─────────────────────────────────────────────────────────


class TestTemplates:
    """O CI faz grep de travessao nos templates HTML do backend. Aqui a prova e
    do texto RENDERIZADO, que e o que a pessoa le: um travessao que entrasse por
    variavel (o titulo da Demanda, por exemplo) nao apareceria no grep do
    arquivo."""

    @pytest.mark.parametrize("template", sorted(tecnologia_email.TEMPLATES.values()))
    def test_o_arquivo_do_template_nao_tem_travessao(self, template):
        caminho = os.path.join(os.path.dirname(__file__), "..", "app", "templates", template)
        with open(caminho, encoding="utf-8") as arquivo:
            fonte = arquivo.read()
        assert "—" not in fonte
        assert "–" not in fonte

    def test_sao_tres_templates_distintos(self):
        """Piso de sanidade: um dicionario com um template so satisfaria o teste
        acima e mandaria o mesmo e-mail nos tres gatilhos."""
        assert len(set(tecnologia_email.TEMPLATES.values())) == 3

    def test_cada_gatilho_manda_o_seu_template(self, transporte):
        """Os tres avisos nao podem ser o mesmo e-mail: o assunto e a frase de
        abertura dizem o que aconteceu, e e isso que a pessoa le na caixa de
        entrada antes de abrir."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])
        client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})
        client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Diretor do Hospital, veja.", "mencoes": ["P3"]},
        )

        assuntos = [e.assunto for e in transporte.enviados]

        assert len(assuntos) == 3
        assert len(set(assuntos)) == 3


# ─── 10. O envio nao pode segurar o event loop ───────────────────────────────


class TestOEnvioNaoSeguraOEventLoop:
    """O envio e sincrono para quem clicou, e fora do loop para o resto do app.

    O `Dockerfile` sobe o uvicorn com UM worker: um processo, um event loop. O
    `resend` fala HTTP por `requests` e o SMTP por `smtplib`, os dois
    bloqueantes. Chamados de dentro da rota `async`, uma resposta com tres
    mencoes vira quatro envios em fila segurando o processo inteiro, e com ele a
    Ouvidoria, as Atas, as Reunioes e o portal publico.

    A prova aqui e por THREAD, e nao por leitura: a primeira consulta ao
    Supabase acontece na rota, no loop; o envio tem que acontecer em outra.
    """

    @pytest.mark.parametrize(
        "acao",
        (
            "criar",
            "atribuir",
            "responder",
        ),
    )
    def test_o_envio_roda_em_outra_thread(self, transporte, acao):
        client, sb = _montar(
            logado=PEDRO,
            produtos=[_produto(dono_id="P2")],
            demandas=[_demanda(responsavel_id="P2")],
        )

        if acao == "criar":
            client.post(
                f"{BASE}/demandas",
                json={"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"},
            )
        elif acao == "atribuir":
            client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P3"})
        else:
            client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert len(transporte.enviados) == 1
        assert sb.thread_da_primeira_consulta is not None
        # A ausência (não é a thread da rota) e a PRESENÇA (é a mesma thread em
        # que o próprio envio consultou os participantes). Só a ausência ficaria
        # verde com um dublê que gravasse zero no lugar da thread de verdade.
        assert transporte.enviados[0].thread == sb.thread_da_ultima_consulta
        assert transporte.enviados[0].thread != sb.thread_da_primeira_consulta

    def test_o_resultado_do_envio_ainda_volta_na_resposta(self, transporte):
        """A ida para a thread nao pode custar o que a fatia entrega: quem
        clicou continua sabendo se o aviso saiu ANTES de a resposta voltar."""
        transporte.falhar = True
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU


# ─── 11. Sem transporte configurado, o app nao diz que avisou ────────────────


class TestSemTransporteConfigurado:
    """O modo mock devolve `True` sem nada sair (a armadilha da issue #435).

    Em producao ele acontece com a `RESEND_API_KEY` rotacionada para vazio, que
    e o modo de falha MAIS provavel desta fatia. Deixa-lo contar como enviado
    seria o app dizer "avisei" em toda atribuicao e toda resposta sem ninguem
    receber nada, justamente na fatia que existe para a falha nao passar calada.
    """

    @pytest.fixture
    def sem_transporte(self, monkeypatch):
        monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: False)

    def test_em_producao_a_tela_e_avisada(self, transporte, sem_transporte, monkeypatch):
        monkeypatch.setattr(tecnologia_email.settings, "environment", "production")
        client, sb = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] == AVISO_EMAIL_NAO_SAIU
        # E a acao continua de pe: a resposta esta no fio.
        assert len(sb.tabelas["tecnologia_conversas"]) == 1
        # E nada foi entregue ao transporte: ele nem foi chamado.
        assert transporte.enviados == []

    def test_em_desenvolvimento_o_modo_mock_continua_valendo(self, transporte, sem_transporte, monkeypatch):
        """A irma do teste acima. Na maquina de quem desenvolve nao ha chave, e
        pintar o alerta em cima de toda acao tornaria a aba inusavel ali."""
        monkeypatch.setattr(tecnologia_email.settings, "environment", "development")
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] is None

    def test_com_transporte_configurado_o_aviso_sai(self, transporte, monkeypatch):
        """A outra irma: a guarda olha o TRANSPORTE, e nao o ambiente sozinho.

        Sem ela, uma guarda escrita so sobre `environment != "development"`
        recusaria todo envio em producao."""
        monkeypatch.setattr(tecnologia_email.settings, "environment", "production")
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Decidido: sexta."})

        assert resposta.json()["aviso_por_email"] is None
        assert transporte.destinatarios == ["P2@hsm.com"]


# ─── 12. O que o e-mail deixa escrito no log ─────────────────────────────────


class TestOQueVaiParaOLog:
    """O log corre em INFO em producao, e o `email_service` escreve destinatario
    e assunto nos dois caminhos de sucesso e no `[MOCK EMAIL]`.

    O assunto que a pessoa RECEBE carrega o titulo da Demanda, que e texto
    digitado num campo livre ("Prontuario da paciente Maria nao abre"). Quem tem
    acesso ao log do Coolify e nenhum perfil na aba nao pode ler isso.
    """

    def test_o_assunto_que_vai_ao_log_nao_leva_o_titulo(self, transporte):
        client, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2", titulo="Prontuário da paciente Maria não abre")],
        )

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Vendo isso."})

        enviado = transporte.enviados[0]
        # A irmã de presença: quem RECEBE continua vendo o título, que é o que
        # faz o assunto servir na caixa de entrada.
        assert "Prontuário da paciente Maria não abre" in enviado.assunto
        # E o log leva exatamente isto, escrito à mão aqui: o gatilho e a
        # Demanda, nada mais. Cobrar só as ausências deixaria passar um dublê
        # que gravasse qualquer frase sem campo livre.
        assert enviado.assunto_no_log == "aviso de resposta da Demanda d1"

    def test_cada_gatilho_diz_qual_foi_na_linha_do_log(self, transporte):
        """O par do teste acima, com OUTRO gatilho e OUTRO texto esperado.

        Dois gatilhos com frases diferentes é o que impede um dublê que cravasse
        uma frase só de passar por detector: o que o log guarda tem que variar
        com o que aconteceu, senão ele não responde "o aviso desta Demanda
        saiu?", que é a única razão de ele existir.
        """
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P1")])

        client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        assert transporte.enviados[0].assunto_no_log == "aviso de atribuicao da Demanda d1"

    def test_o_nome_do_produto_tambem_fica_fora_do_log(self, transporte):
        """Nome de Produto e texto digitado por gente, como o titulo: a lista e
        curada, mas nada impede um nome que nao devia ficar escrito no log."""
        client, _ = _montar(
            logado=PEDRO,
            produtos=[_produto(nome="Portal do RH", dono_id="P1")],
            demandas=[_demanda(responsavel_id="P2")],
        )

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Vendo isso."})

        assert "Portal do RH" not in (transporte.enviados[0].assunto_no_log or "")

    def test_o_endereco_de_quem_recebe_fica_fora_do_log(self, transporte):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Vendo isso."})

        assert transporte.enviados[0].endereco_fora_do_log is True

    def test_o_assunto_nao_leva_quebra_de_linha(self, transporte):
        """Injecao de cabecalho: `_titulo_valido` so faz `strip()`, entao um
        `\\r\\n` no MEIO do titulo passa e chega ao assunto. Pelo SMTP o
        `EmailMessage` recusa; pelo Resend a string viaja como JSON e quem monta
        o MIME e o provedor."""
        client, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2", titulo="Oi\r\nBcc: fora@atacante.example\r\nX:")],
        )

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Vendo isso."})

        assunto = transporte.enviados[0].assunto
        assert "\r" not in assunto
        assert "\n" not in assunto
        # A irmã de presença: o assunto não virou vazio, o título ainda está lá.
        assert "Bcc: fora@atacante.example" in assunto


# ─── 13. O teto por minuto das rotas de gatilho ──────────────────────────────


class TestLimiteDeGatilho:
    """Cada escrita nestas QUATRO portas consome cota e reputacao de remetente
    do Resend, que e recurso COMPARTILHADO: uma chave, um `email_service`, um
    remetente. A Ouvidoria manda por esse mesmo canal os avisos de prazo, que
    tem obrigacao legal (ADR 0034). Um laco numa conta de Super admin desta aba
    sem teto derrubaria aqueles avisos.

    A quarta e a CORRECAO (issue #670): ela virou gatilho quando a mencao
    acrescentada nos 10 minutos passou a chamar quem entrou.
    """

    # Escrito a mao a partir do `@limiter.limit("60/minute")`: medir contra a
    # propria constante ficaria verde com o teto trocado para 60 mil.
    TETO_POR_MINUTO = 60

    def test_o_teto_existe_nas_portas_de_gatilho(self):
        assert tecnologia_router.LIMITE_DE_GATILHO == f"{self.TETO_POR_MINUTO}/minute"
        assert tecnologia_router.ESCOPO_DO_GATILHO

    def test_responder_demais_leva_429(self):
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        codigos = [
            client.post(f"{BASE}/demandas/d1/conversa", json={"texto": f"Resposta {i}"}).status_code
            for i in range(self.TETO_POR_MINUTO + 1)
        ]

        # As 60 primeiras entram, a 61 leva o teto.
        assert codigos[: self.TETO_POR_MINUTO] == [201] * self.TETO_POR_MINUTO
        assert codigos[self.TETO_POR_MINUTO] == 429

    def test_criar_demandas_demais_leva_429(self):
        client, _ = _montar(logado=PEDRO, produtos=[_produto(dono_id="P2")])
        corpo = {"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"}

        codigos = [client.post(f"{BASE}/demandas", json=corpo).status_code for _ in range(self.TETO_POR_MINUTO + 1)]

        assert codigos[self.TETO_POR_MINUTO] == 429

    def test_atribuir_demais_leva_429_mesmo_espalhando_pelas_demandas(self):
        """Cada requisicao vai para uma Demanda DIFERENTE de proposito.

        O `Limiter` da casa nasce com `key_style="url"`, entao um `@limiter.limit`
        comum daria 60 por minuto POR DEMANDA e o teto viraria enfeite: bastava
        rodar o laco trocando o id. E por isso que as portas de gatilho usam
        `shared_limit` com escopo proprio.
        """
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(did=f"d{i}", responsavel_id="P1") for i in range(70)])

        codigos = [
            client.post(f"{BASE}/demandas/d{i}/atribuir", json={"responsavel_id": "P2"}).status_code
            for i in range(self.TETO_POR_MINUTO + 1)
        ]

        assert codigos[: self.TETO_POR_MINUTO] == [200] * self.TETO_POR_MINUTO
        assert codigos[self.TETO_POR_MINUTO] == 429

    def test_corrigir_demais_leva_429(self):
        """A quarta porta (issue #670). Sem ela no balde, um laco de correcoes
        acrescentando e tirando mencao mandaria e-mail sem teto nenhum."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")], conversas=[_conversa()])

        codigos = [
            client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": f"Correção {i}"}).status_code
            for i in range(self.TETO_POR_MINUTO + 1)
        ]

        assert codigos[: self.TETO_POR_MINUTO] == [200] * self.TETO_POR_MINUTO
        assert codigos[self.TETO_POR_MINUTO] == 429

    def test_o_balde_e_um_so_para_as_quatro_portas(self):
        """O recurso escasso e a cota do Resend, que e uma so para o app: um
        balde por porta daria quatro vezes o teto a quem alternasse entre elas.

        As duas portas atropeladas sao de METODOS diferentes (POST e PATCH), e e
        a correcao que fecha o caso novo: com `limit` no lugar de `shared_limit`
        ela teria balde proprio e responderia 200 aqui."""
        client, _ = _montar(
            logado=PEDRO,
            produtos=[_produto(dono_id="P2")],
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[_conversa()],
        )
        corpo = {"titulo": "Fechar a conversa da Ana", "tipo": "decisao", "produto_id": "prod-1"}
        for _ in range(self.TETO_POR_MINUTO):
            assert client.post(f"{BASE}/demandas", json=corpo).status_code == 201

        # Portas diferentes, mesmo balde.
        atropelada = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "E aí?"})
        correcao = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Corrigindo"})

        assert atropelada.status_code == 429
        assert correcao.status_code == 429

    def test_ler_o_quadro_nao_tem_teto(self):
        """A irma de ausencia: o teto e das portas que MANDAM e-mail. Um teto na
        leitura brigaria com a atualizacao automatica de 30 em 30 segundos, que
        e a outra metade desta fatia."""
        client, _ = _montar(logado=PEDRO, demandas=[_demanda(responsavel_id="P2")])

        codigos = [client.get(f"{BASE}/demandas").status_code for _ in range(self.TETO_POR_MINUTO + 5)]

        assert set(codigos) == {200}


# ─── 14. O teto de tempo do transporte ───────────────────────────────────────


class TestTetoDeTempoDoTransporte:
    """O envio vai para uma thread (secao 10), e thread pendurada continua
    pendurada: quem fecha o pior caso e o teto de TEMPO do transporte.

    Mora neste arquivo, e nao num do `email_service`, porque foi esta fatia que
    o criou e e ela que depende dele: sem teto, uma resposta com tres mencoes
    pode segurar quatro threads para sempre.
    """

    def test_o_smtp_abre_a_conexao_com_teto(self, monkeypatch):
        from app.services import email_service

        abertas: list[dict] = []

        class _SMTPFalso:
            def __init__(self, host, port, timeout=None):
                abertas.append({"host": host, "port": port, "timeout": timeout})

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def starttls(self):
                pass

            def login(self, *_a):
                pass

            def send_message(self, *_a):
                pass

        # Sem rede: o `smtplib.SMTP` inteiro é trocado. A trava do `conftest.py`
        # continua por baixo se algum dia esta troca sumir.
        monkeypatch.setattr(email_service.smtplib, "SMTP", _SMTPFalso)
        monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
        monkeypatch.setattr(email_service, "_smtp_configurado", lambda: True)

        assert email_service._enviar_email("alguem@hsm.com", "Assunto", "<p>oi</p>", "oi") is True

        # 20 escrito à mão: medir contra a própria constante ficaria verde com
        # ela trocada para `None`, que é "espere para sempre".
        assert email_service.TIMEOUT_DO_TRANSPORTE == 20
        assert abertas == [{"host": settings.smtp_host, "port": settings.smtp_port, "timeout": 20}]

    def test_o_cliente_http_do_resend_tem_teto(self):
        """O SDK monta a requisicao num cliente proprio, e e ELE que tem o
        `timeout`. As versoes novas ja trazem um; o `pyproject.toml` pede
        `resend>=2.0.0`, entao o que o CI instala nao e o que a `uv.lock` fixa
        (issues #542 e #546) e o teto e escrito pelo app."""
        import resend

        from app.services import email_service

        assert getattr(resend.default_http_client, "_timeout", None) == email_service.TIMEOUT_DO_TRANSPORTE


# ─── 15. O `assunto_no_log` do proprio `email_service` ───────────────────────


class TestOAssuntoNoLogDoEmailService:
    """A ponta de baixo do MUST-FIX do log: quem de fato ESCREVE a linha.

    Os testes da secao 12 provam que a aba Tecnologia MANDA um assunto neutro
    para o log. Sem esta classe, o `email_service` podia ignorar o que recebe e
    escrever o assunto de verdade assim mesmo, e a secao 12 continuaria verde.
    """

    def _com_smtp_falso(self, monkeypatch) -> list[dict]:
        from app.services import email_service

        enviados: list[dict] = []

        class _SMTPFalso:
            def __init__(self, host, port, timeout=None):
                enviados.append({"host": host, "timeout": timeout})

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def starttls(self):
                pass

            def login(self, *_a):
                pass

            def send_message(self, *_a):
                pass

        monkeypatch.setattr(email_service.smtplib, "SMTP", _SMTPFalso)
        monkeypatch.setattr(email_service, "_resend_configurado", lambda: False)
        monkeypatch.setattr(email_service, "_smtp_configurado", lambda: True)
        return enviados

    def test_a_linha_do_log_leva_o_assunto_neutro_e_nao_o_de_verdade(self, monkeypatch, caplog):
        from app.services import email_service

        self._com_smtp_falso(monkeypatch)

        with caplog.at_level(logging.INFO, logger="app.services.email_service"):
            email_service._enviar_email(
                "diretor@hsm.com",
                "Demanda na sua mão: Prontuário da paciente Maria não abre",
                "<p>oi</p>",
                "oi",
                endereco_fora_do_log=True,
                assunto_no_log="aviso de atribuicao da Demanda d1",
            )

        escrito = caplog.text
        assert "aviso de atribuicao da Demanda d1" in escrito
        assert "Prontuário da paciente Maria não abre" not in escrito
        assert "diretor@hsm.com" not in escrito

    def test_sem_assunto_neutro_o_log_continua_como_sempre(self, monkeypatch, caplog):
        """A irmã de presença, e a garantia de que nada mudou para quem já
        usava o `email_service`: sem o parâmetro, o log é o de antes. Uma
        omissão que apagasse o assunto de todo mundo tiraria da Ouvidoria o
        rastro de "o email deste caso saiu?"."""
        from app.services import email_service

        self._com_smtp_falso(monkeypatch)

        with caplog.at_level(logging.INFO, logger="app.services.email_service"):
            email_service._enviar_email("setor@hsm.com", "Ouvidoria 2026-0042: caso validado", "<p>oi</p>", "oi")

        assert "Ouvidoria 2026-0042: caso validado" in caplog.text
        assert "setor@hsm.com" in caplog.text
