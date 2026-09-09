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

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import tecnologia_email  # noqa: E402
from app.services.tecnologia import (  # noqa: E402
    AVISO_EMAIL_NAO_SAIU,
    CONTINUA_NA_DEMANDA,
    LIMITE_TRECHO,
    SEM_TRECHO,
    avisos_da_resposta,
    destinatario_da_atribuicao,
    trecho_do_aviso,
)

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
    """PostgREST minimo: select/eq/in_/order/insert/update."""

    def __init__(self, rows: list[dict], nome: str):
        self._rows = rows
        self._nome = nome
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._order: str | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order = coluna
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

        if self._order:
            casadas.sort(key=lambda linha: (linha.get(self._order) is None, linha.get(self._order)))
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []), nome)


@dataclass
class _Enviado:
    destinatario: str
    assunto: str
    html: str
    texto: str


@dataclass
class _Transporte:
    """O dublê do `_enviar_email`: guarda o que sairia e responde o que se pede.

    `falhar` liga o caminho do transporte configurado que RECUSOU (o
    `_enviar_email` de verdade devolve `False` ali), que e o unico caso em que
    a tela precisa ser avisada.
    """

    falhar: bool = False
    enviados: list[_Enviado] = field(default_factory=list)

    def __call__(self, destinatario, assunto, html_content, texto_fallback, *_a, **_kw) -> bool:
        self.enviados.append(_Enviado(destinatario, assunto, html_content, texto_fallback))
        return not self.falhar

    @property
    def destinatarios(self) -> list[str]:
        return [e.destinatario for e in self.enviados]


@pytest.fixture(autouse=True)
def transporte(monkeypatch) -> _Transporte:
    """A trava de e-mail de verdade deste arquivo. Ver o docstring do topo."""
    dublê = _Transporte()
    monkeypatch.setattr(tecnologia_email, "_enviar_email", dublê)
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
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
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
        }
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
        """O criterio de conteudo da issue #642, no HTML e no texto simples."""
        client, _ = _montar(
            logado=PEDRO,
            produtos=[_produto(dono_id="P2")],
            demandas=[_demanda(responsavel_id="P1", titulo="Prazo da Ana", descricao="Decidir até sexta.")],
        )

        client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        enviado = transporte.enviados[0]
        for corpo in (enviado.html, enviado.texto):
            assert "Prazo da Ana" in corpo
            assert "Decisão" in corpo
            assert "Ana" in corpo
            assert "Decidir até sexta." in corpo
            assert "/admin/tecnologia?demanda=d1" in corpo


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

    def test_corrigir_a_propria_resposta_nao_manda_aviso_de_novo(self, transporte):
        """A janela de 10 minutos e para corrigir digitacao (issue #638). Um
        aviso por edicao chamaria a mesma pessoa duas vezes pela mesma fala, e
        deixaria a mencao acrescentada numa correcao avisar de novo quem ja
        tinha sido avisado.

        A linha ja nasce no fio, com `criado_em` de agora: passar pelo POST
        primeiro misturaria o gatilho da resposta com o da edicao, que e
        justamente o que se quer separar aqui.
        """
        agora = datetime.now(UTC).isoformat()
        client, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda(responsavel_id="P2")],
            conversas=[
                {
                    "id": "c1",
                    "demanda_id": "d1",
                    "autor_id": "P1",
                    "linha": "resposta",
                    "texto": "Decidido: sexta.",
                    "mencoes": [],
                    "movimento_campo": None,
                    "movimento_de": None,
                    "movimento_para": None,
                    "criado_em": agora,
                    "editado_em": None,
                }
            ],
        )

        editada = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Diretor do Hospital, decidido: sexta-feira.", "mencoes": ["P3"]},
        )

        assert editada.status_code == 200
        assert transporte.enviados == []


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
    def test_mencionado_que_perdeu_o_acesso_a_aba_nao_recebe(self, transporte):
        """A #638 recusa a mencao a quem nao tem acesso, entao a lista GRAVADA
        ja e limpa. Mas quem tinha acesso na hora da mencao pode ter perdido
        antes do e-mail sair: aqui a menção esta na linha antiga do fio e a
        pessoa saiu do Super admin. O e-mail nao pode ir.
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
