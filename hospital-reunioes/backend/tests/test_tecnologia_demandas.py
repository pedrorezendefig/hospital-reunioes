"""A Demanda nasce e anda no Quadro (issue #637, PRD #634, ADR 0050).

Dois seams, na ordem em que a regra existe:

* **A maquina de estados**, funcao pura, testada direto e sem HTTP. A tabela de
  transicoes permitidas e escrita AQUI, a mao, a partir da PRD; a lista de
  proibidas e o complemento dela sobre o produto cartesiano dos cinco estados.
  Assim nenhuma transicao fica sem teste: quem acrescentar um estado quebra o
  piso de sanidade, e quem afrouxar a regra cai numa proibida.
* **Os endpoints**, pela ROTA de verdade com o Supabase dublado, no molde do
  `test_admin_tecnologia.py` da fatia anterior. E o unico jeito de provar que o
  movimento grava a linha do fio logo em seguida, e o que acontece quando essa
  segunda escrita falha (o PostgREST nao tem transacao).

O gate de papel nao se repete aqui: a matriz de `test_admin_tecnologia.py`
varre o schema OpenAPI e ja engole toda rota nova deste arquivo.
"""

from __future__ import annotations

import itertools
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.models.tecnologia_schemas import (  # noqa: E402
    EstadoDemanda,
    PrioridadeDemanda,
    TipoDemanda,
)
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services.tecnologia import (  # noqa: E402
    ESTADO_ROTULO,
    ESTADOS,
    JANELA_DE_EDICAO,
    LIMITE_RESPOSTA,
    MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO,
    MOTIVO_JANELA_ENCERRADA,
    MOTIVO_MENCAO_SEM_ACESSO,
    MOTIVO_MOVIMENTO_NAO_SE_EDITA,
    MOTIVO_PRODUTO_INATIVO,
    MOTIVO_PRODUTO_SEM_DONO,
    MOTIVO_RESPONSAVEL_SEM_ACESSO,
    MOTIVO_RESPOSTA_COM_CARACTERE_INVALIDO,
    MOTIVO_RESPOSTA_VAZIA,
    MOTIVO_SO_O_AUTOR_EDITA,
    PRIORIDADES,
    TIPOS,
    carimbos_da_transicao,
    dentro_da_janela_de_edicao,
    instante_do_banco,
    limite_da_janela_de_edicao,
    mencoes_sem_acesso,
    motivo_edicao_recusada,
    motivo_mencoes_demais,
    motivo_resposta_invalida,
    motivo_transicao_invalida,
    normalizar_mencoes,
    texto_movimento_estado,
    texto_movimento_responsavel,
    transicao_permitida,
)

# ─── 1. A maquina de estados ─────────────────────────────────────────────────

# Escrita a mao a partir da PRD #634: de `nova` para qualquer OUTRO;
# `em_andamento` e `aguardando` nos dois sentidos; das duas para `concluida` ou
# `cancelada`; de `concluida` e `cancelada` de volta para `em_andamento`.
PERMITIDAS = [
    ("nova", "em_andamento"),
    ("nova", "aguardando"),
    ("nova", "concluida"),
    ("nova", "cancelada"),
    ("em_andamento", "aguardando"),
    ("aguardando", "em_andamento"),
    ("em_andamento", "concluida"),
    ("em_andamento", "cancelada"),
    ("aguardando", "concluida"),
    ("aguardando", "cancelada"),
    ("concluida", "em_andamento"),
    ("cancelada", "em_andamento"),
]

# Tudo o mais entre os cinco estados: voltar para `nova`, ficar parado no
# mesmo estado, e pular direto de `concluida` para `cancelada` (ou o contrario)
# sem reabrir.
PROIBIDAS = [par for par in itertools.product(ESTADOS, ESTADOS) if par not in PERMITIDAS]


class TestMaquinaDeEstados:
    def test_o_piso_da_tabela(self):
        """Controle das duas listas abaixo: uma lista vazia satisfaz
        `parametrize` sem rodar caso nenhum, e as duas ficariam verdes sobre
        nada. Cinco estados dao 25 pares, 12 permitidos e 13 proibidos."""
        assert len(ESTADOS) == 5
        assert len(PERMITIDAS) == 12
        assert len(PROIBIDAS) == 13

    @pytest.mark.parametrize("de,para", PERMITIDAS)
    def test_cada_transicao_permitida(self, de, para):
        assert transicao_permitida(de, para) is True

    @pytest.mark.parametrize("de,para", PROIBIDAS)
    def test_cada_transicao_proibida(self, de, para):
        assert transicao_permitida(de, para) is False

    def test_nenhum_estado_volta_para_nova(self):
        """`nova` e so o comeco: a Demanda que voltou atras vai para
        `em_andamento`, e nao para a coluna de quem ainda nao foi olhada."""
        assert all(not transicao_permitida(de, "nova") for de in ESTADOS)

    def test_reabrir_cai_em_em_andamento_e_so(self):
        for fechado in ("concluida", "cancelada"):
            destinos = [para for para in ESTADOS if transicao_permitida(fechado, para)]
            assert destinos == ["em_andamento"]

    def test_o_motivo_da_recusa_diz_os_destinos_possiveis(self):
        motivo = motivo_transicao_invalida("concluida", "cancelada")
        assert "Concluída" in motivo
        assert "Cancelada" in motivo
        assert "Em andamento" in motivo

    def test_o_motivo_de_estado_desconhecido_nao_sai_quebrado(self):
        """Linha antiga, ou valor que entrou por fora do app: sem esta saida a
        frase terminaria em "os destinos sao: .", mandando a pessoa procurar
        uma lista que nao existe."""
        motivo = motivo_transicao_invalida("arquivada", "em_andamento")

        assert "arquivada" in motivo
        assert "não conhece" in motivo
        assert "destinos são: ." not in motivo

    def test_o_motivo_de_ficar_no_mesmo_estado_nao_culpa_a_transicao(self):
        """Causa que o codigo distingue: quem manda `aguardando` para uma
        Demanda ja em `aguardando` clicou duas vezes, nao pediu um caminho
        proibido. Dizer "de Aguardando para Aguardando nao existe" mandaria a
        pessoa procurar defeito onde nao ha."""
        motivo = motivo_transicao_invalida("aguardando", "aguardando")
        assert "já está" in motivo
        assert "Aguardando" in motivo


class TestAsListasFechadas:
    """As tres listas vivem em dois lugares: a tupla do servico (quem decide) e
    o `Literal` do payload (quem recusa com 422 antes do banco). Elas TEM que
    dizer a mesma coisa: um tipo novo so na tupla nasceria recusado pela API, e
    um so no `Literal` chegaria ao banco para bater no CHECK da migration 102,
    que vira 500."""

    @pytest.mark.parametrize(
        "literal,tupla",
        (
            (TipoDemanda, TIPOS),
            (EstadoDemanda, ESTADOS),
            (PrioridadeDemanda, PRIORIDADES),
        ),
    )
    def test_o_payload_e_o_servico_falam_a_mesma_lista(self, literal, tupla):
        assert set(get_args(literal)) == set(tupla)


class TestCarimbos:
    def test_concluir_carimba_data_e_pessoa(self):
        carimbos = carimbos_da_transicao(para="concluida", ator_id="P1", agora="2026-09-09T10:00:00Z")
        assert carimbos["concluida_em"] == "2026-09-09T10:00:00Z"
        assert carimbos["concluida_por"] == "P1"
        assert carimbos["cancelada_em"] is None
        assert carimbos["cancelada_por"] is None

    def test_cancelar_carimba_data_e_pessoa(self):
        carimbos = carimbos_da_transicao(para="cancelada", ator_id="P2", agora="2026-09-09T10:00:00Z")
        assert carimbos["cancelada_em"] == "2026-09-09T10:00:00Z"
        assert carimbos["cancelada_por"] == "P2"
        assert carimbos["concluida_em"] is None
        assert carimbos["concluida_por"] is None

    @pytest.mark.parametrize("destino", ("em_andamento", "aguardando"))
    def test_reabrir_limpa_os_quatro_carimbos(self, destino):
        carimbos = carimbos_da_transicao(para=destino, ator_id="P1", agora="2026-09-09T10:00:00Z")
        assert carimbos == {
            "concluida_em": None,
            "concluida_por": None,
            "cancelada_em": None,
            "cancelada_por": None,
        }


class TestTextoDoMovimento:
    def test_o_texto_do_movimento_de_estado(self):
        assert texto_movimento_estado(autor_nome="Pedro", para="aguardando") == "Pedro moveu para Aguardando"

    @pytest.mark.parametrize(
        "estado,rotulo",
        (
            ("nova", "Nova"),
            ("em_andamento", "Em andamento"),
            ("aguardando", "Aguardando"),
            ("concluida", "Concluída"),
            ("cancelada", "Cancelada"),
        ),
    )
    def test_cada_estado_tem_o_seu_rotulo_de_gente(self, estado, rotulo):
        assert ESTADO_ROTULO[estado] == rotulo

    def test_o_texto_do_movimento_de_responsavel(self):
        texto = texto_movimento_responsavel(autor_nome="Pedro", para_nome="Sócia Vitta")
        assert texto == "Pedro atribuiu a Sócia Vitta"


# ─── Supabase dublê ──────────────────────────────────────────────────────────


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


class _SupabaseComFalhaNoFio(_SupabaseMock):
    """O insert da Conversa falha, do jeito que o PostgREST falha de verdade.

    `vazio`: a escrita volta sem linha nenhuma. `excecao`: a chamada estoura
    (timeout, PostgREST fora do ar). Os dois caminhos precisam do mesmo
    desfeixo: a Demanda ja mudou, e o fio ficou sem a linha.
    """

    def __init__(self, tabelas: dict[str, list[dict]], modo: str):
        super().__init__(tabelas)
        self._modo = modo

    def table(self, nome: str):
        consulta = super().table(nome)
        if nome != "tecnologia_conversas":
            return consulta
        original = consulta.execute

        def execute():
            # `_insert` privado de proposito: so a ESCRITA falha; a leitura do
            # fio continua funcionando, senao o teste provaria outra coisa.
            if consulta._insert is None:
                return original()
            if self._modo == "excecao":
                raise RuntimeError("PostgREST fora do ar")
            return _Result(data=[])

        consulta.execute = execute
        return consulta


class _SupabaseComCorrida(_SupabaseMock):
    """Outra pessoa move a mesma Demanda entre a leitura e a escrita.

    Na PRIMEIRA leitura da tabela de Demandas a linha volta como estava; logo
    depois, o estado no banco muda por fora. E o que acontece quando duas
    pessoas clicam em Mover no mesmo card ao mesmo tempo.
    """

    def __init__(self, tabelas: dict[str, list[dict]], estado_de_fora: str):
        super().__init__(tabelas)
        self._estado = estado_de_fora
        self._ja_leu = False

    def table(self, nome: str):
        consulta = super().table(nome)
        if nome != "tecnologia_demandas":
            return consulta
        original = consulta.execute

        def execute():
            resultado = original()
            if not self._ja_leu and consulta._insert is None and consulta._update is None and resultado.data:
                self._ja_leu = True
                for linha in self.tabelas["tecnologia_demandas"]:
                    linha["estado"] = self._estado
            return resultado

        consulta.execute = execute
        return consulta


# ─── Cenario ─────────────────────────────────────────────────────────────────


def _pessoa(pid: str, nome: str, *, access_profile: str | None = "super_admin", ativo: bool = True) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid}@hsm.com",
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


def _produto(pid: str, nome: str, *, dono_id: str | None = "P1", ativo: bool = True) -> dict:
    return {"id": pid, "nome": nome, "ativo": ativo, "ordem": 1, "dono_id": dono_id}


def _demanda(did: str, **campos) -> dict:
    base = {
        "id": did,
        "titulo": "Encerrar conversas da Ana",
        "descricao": None,
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
FACILITADOR = _pessoa("P3", "Facilitador", access_profile="regular")

BASE = "/api/admin/tecnologia"


def _montar(
    *,
    logado: dict = PEDRO,
    participantes: list[dict] | None = None,
    produtos: list[dict] | None = None,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    fio_falha: str | None = None,
    corrida_para: str | None = None,
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(tecnologia_router.router, prefix="/api")

    pessoas = [dict(p) for p in (participantes if participantes is not None else [PEDRO, SOCIA, FACILITADOR])]
    if all(p["id"] != logado["id"] for p in pessoas):
        pessoas.append(dict(logado))

    tabelas = {
        "participantes": pessoas,
        "tecnologia_produtos": [dict(p) for p in (produtos if produtos is not None else [_produto("prod-1", "Ana")])],
        "tecnologia_demandas": [dict(d) for d in (demandas or [])],
        "tecnologia_conversas": [dict(c) for c in (conversas or [])],
    }
    if fio_falha:
        sb: _SupabaseMock = _SupabaseComFalhaNoFio(tabelas, fio_falha)
    elif corrida_para:
        sb = _SupabaseComCorrida(tabelas, corrida_para)
    else:
        sb = _SupabaseMock(tabelas)

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


# ─── 2. A Demanda nasce ──────────────────────────────────────────────────────


class TestCriarDemanda:
    def test_nasce_em_nova_com_o_dono_do_produto_e_prioridade_normal(self):
        client, sb = _montar(produtos=[_produto("prod-1", "Ana", dono_id="P2")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Encerrar conversas", "tipo": "decisao", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["estado"] == "nova"
        assert corpo["responsavel_id"] == "P2"
        assert corpo["responsavel_nome"] == "Sócia Vitta"
        assert corpo["prioridade"] == "normal"
        assert corpo["produto_nome"] == "Ana"
        # O autor e quem esta logado, e nao o dono do Produto: e por ele que se
        # sabe de que lado veio o pedido (ADR 0050, decisao 2).
        assert corpo["autor_id"] == "P1"
        assert sb.tabelas["tecnologia_demandas"][0]["titulo"] == "Encerrar conversas"

    def test_produto_sem_dono_e_recusado(self):
        client, sb = _montar(produtos=[_produto("prod-1", "Ana", dono_id=None)])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_PRODUTO_SEM_DONO
        assert sb.tabelas["tecnologia_demandas"] == []

    def test_produto_inativo_e_recusado(self):
        client, sb = _montar(produtos=[_produto("prod-1", "Ana", ativo=False)])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_PRODUTO_INATIVO
        assert sb.tabelas["tecnologia_demandas"] == []

    def test_produto_ativo_com_dono_e_aceito(self):
        """O par de presenca das duas recusas acima: um 422 cravado no POST
        passaria pelos dois sem olhar Produto nenhum."""
        client, _ = _montar(produtos=[_produto("prod-1", "Ana", dono_id="P1")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201

    def test_tipo_fora_da_lista_de_sete_e_recusado(self):
        client, _ = _montar()

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "duvida", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422

    def test_prazo_vazio_nao_vira_texto_no_banco(self):
        """`""` nao e NULL: gravado como texto numa coluna DATE, e 500."""
        client, sb = _montar()

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1", "prazo": ""},
        )

        assert resposta.status_code == 201
        assert sb.tabelas["tecnologia_demandas"][0]["prazo"] is None

    def test_produto_inexistente_e_recusado_sem_estourar(self):
        client, _ = _montar()

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-9"},
        )

        assert resposta.status_code == 404

    def test_dono_que_perdeu_o_acesso_a_aba_e_recusado(self):
        """A criacao recusa o mesmo estado que a porta de atribuir recusa.

        P3 virou dono do Produto quando ainda era Super admin; depois o
        diretor tirou o papel dele. Sem esta guarda, a Demanda nasceria com
        `responsavel_id: "P3"` (201) enquanto `POST /atribuir` com o MESMO P3
        responde 422: o app criaria por uma porta o estado que recusa pela
        outra, e o card ficaria com um responsavel que nao abre a aba.
        """
        client, sb = _montar(produtos=[_produto("prod-1", "Ana", dono_id="P3")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO
        assert sb.tabelas["tecnologia_demandas"] == []

    def test_a_recusa_do_dono_sem_acesso_diz_onde_consertar(self):
        """Guarda-corpo que so diz "nao pode" vira indisponibilidade.

        Quem TEM onde carimbar e o proprio Super admin, na mesma tela: a lista
        de Produtos fica logo abaixo do Quadro, e dentro da aba todos podem
        tudo (ADR 0050, decisao 11). A frase tem que apontar para la.
        """
        assert "dono" in MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO
        assert "lista de Produtos" in MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO

    def test_dono_desativado_tambem_e_recusado(self):
        """Perder o acesso nao e so perder o Super admin: participante
        desativado tambem sai da lista da aba."""
        saiu = _pessoa("P4", "Saiu da Vitta", ativo=False)
        client, _ = _montar(
            participantes=[PEDRO, saiu],
            produtos=[_produto("prod-1", "Ana", dono_id="P4")],
        )

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO

    def test_dono_com_acesso_segue_criando(self):
        """O par de presenca das duas recusas acima: a guarda nova nao pode
        travar o caminho normal, que e o unico que existe hoje em producao."""
        client, sb = _montar(produtos=[_produto("prod-1", "Ana", dono_id="P2")])

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "Pedido", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 201
        assert sb.tabelas["tecnologia_demandas"][0]["responsavel_id"] == "P2"

    def test_titulo_vazio_volta_frase_de_gente_e_nao_json_do_pydantic(self):
        """`min_length=1` responderia ANTES do router e devolveria `detail` em
        LISTA, que a tela mostra como JSON cru no alerta vermelho."""
        client, _ = _montar()

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "", "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Título da Demanda não pode ser vazio."

    def test_titulo_grande_demais_na_criacao_tambem_volta_frase_de_gente(self):
        client, sb = _montar()

        resposta = client.post(
            f"{BASE}/demandas",
            json={"titulo": "x" * 201, "tipo": "ajuste", "produto_id": "prod-1"},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Título da Demanda pode ter no máximo 200 caracteres."
        assert sb.tabelas["tecnologia_demandas"] == []


# ─── 3. A Demanda anda ───────────────────────────────────────────────────────


class TestMoverPelaRota:
    @pytest.mark.parametrize("de,para", PERMITIDAS)
    def test_cada_transicao_permitida_pelo_endpoint(self, de, para):
        client, sb = _montar(demandas=[_demanda("d1", estado=de)])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": para})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == para
        assert sb.tabelas["tecnologia_demandas"][0]["estado"] == para

    @pytest.mark.parametrize("de,para", PROIBIDAS)
    def test_cada_transicao_proibida_pelo_endpoint(self, de, para):
        client, sb = _montar(demandas=[_demanda("d1", estado=de)])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": para})

        assert resposta.status_code == 422
        assert sb.tabelas["tecnologia_demandas"][0]["estado"] == de
        # A recusa nao grava linha de movimento: o fio conta o que aconteceu.
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_estado_fora_dos_cinco_e_recusado(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "arquivada"})

        assert resposta.status_code == 422

    def test_concluir_carimba_data_e_pessoa_no_banco(self):
        client, sb = _montar(logado=SOCIA, demandas=[_demanda("d1", estado="em_andamento")])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "concluida"})

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["concluida_por"] == "P2"
        assert linha["concluida_em"]

    def test_cancelar_carimba_data_e_pessoa_no_banco(self):
        client, sb = _montar(logado=SOCIA, demandas=[_demanda("d1", estado="aguardando")])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "cancelada"})

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["cancelada_por"] == "P2"
        assert linha["cancelada_em"]

    def test_reabrir_limpa_o_carimbo_de_concluida(self):
        client, sb = _montar(
            demandas=[_demanda("d1", estado="concluida", concluida_em="2026-09-05T10:00:00Z", concluida_por="P2")]
        )

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "em_andamento"})

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["concluida_em"] is None
        assert linha["concluida_por"] is None

    def test_reabrir_limpa_o_carimbo_de_cancelada(self):
        client, sb = _montar(
            demandas=[_demanda("d1", estado="cancelada", cancelada_em="2026-09-05T10:00:00Z", cancelada_por="P2")]
        )

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "em_andamento"})

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["cancelada_em"] is None
        assert linha["cancelada_por"] is None

    def test_quem_perde_a_corrida_leva_409_e_nao_move_de_novo(self):
        """TOCTOU: duas pessoas movem o mesmo card ao mesmo tempo.

        As duas leem `nova`, as duas passam pela maquina de estados. Sem
        amarrar o estado lido no update, as duas gravariam e o fio ganharia
        duas linhas contando historias diferentes. Aqui a segunda nao casa
        linha nenhuma e leva 409, com o fio intacto.
        """
        client, sb = _montar(demandas=[_demanda("d1", estado="nova")], corrida_para="aguardando")

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "concluida"})

        assert resposta.status_code == 409
        motivo = resposta.json()["detail"]
        # A frase fala do DESFECHO. O codigo so sabe que o update nao casou
        # linha nenhuma: quem mexeu, e onde a Demanda foi parar, ele nao viu.
        assert "O Quadro está desatualizado" in motivo
        assert "não foi feito" in motivo
        assert "Recarregue o Quadro" in motivo
        assert "alguém" not in motivo
        # A escrita nao passou: o estado e o que a outra pessoa deixou.
        assert sb.tabelas["tecnologia_demandas"][0]["estado"] == "aguardando"
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_sem_corrida_o_movimento_passa(self):
        """O par de presenca do 409: uma amarra que nunca casasse devolveria
        409 em todo movimento, e o teste acima passaria sozinho."""
        client, sb = _montar(demandas=[_demanda("d1", estado="nova")])

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "concluida"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["estado"] == "concluida"

    @pytest.mark.parametrize("modo", ("vazio", "excecao"))
    def test_falha_ao_gravar_o_fio_nao_passa_calada(self, modo):
        """O movimento e a linha do fio sao duas chamadas ao PostgREST, que nao
        tem transacao (e RPC esta fora do escopo desta fatia). O minimo honesto
        e nao engolir a falha: a resposta diz que a Demanda MUDOU e que o fio
        ficou incompleto. "Nao deu certo" seria mentira.
        """
        client, sb = _montar(demandas=[_demanda("d1", estado="nova")], fio_falha=modo)

        resposta = client.post(f"{BASE}/demandas/d1/mover", json={"estado": "aguardando"})

        assert resposta.status_code == 500
        motivo = resposta.json()["detail"]
        assert "A Demanda mudou" in motivo
        assert "fio desta Demanda ficou incompleto" in motivo
        # E a resposta nao mente: o movimento esta gravado.
        assert sb.tabelas["tecnologia_demandas"][0]["estado"] == "aguardando"

    def test_o_log_da_falha_nao_leva_nome_de_gente(self, caplog):
        """O padrao da casa e logar identificador, nao payload.

        O `texto` da linha carrega o nome de quem moveu ("Pedro Vitta moveu
        para Aguardando"). O log diz a mesma coisa com `demanda_id`, `campo`,
        `de` e `para`, sem nome de pessoa. A ausencia so significa algo porque
        os marcadores positivos estao no mesmo registro: sem eles, um log vazio
        passaria.
        """
        client, _ = _montar(demandas=[_demanda("d1", estado="nova")], fio_falha="vazio")

        with caplog.at_level(logging.ERROR, logger="app.routers.admin.tecnologia"):
            client.post(f"{BASE}/demandas/d1/mover", json={"estado": "aguardando"})

        assert "d1" in caplog.text
        assert "campo=estado" in caplog.text
        assert "para=aguardando" in caplog.text
        assert "Pedro Vitta" not in caplog.text

    def test_o_movimento_grava_a_linha_na_conversa(self):
        client, sb = _montar(demandas=[_demanda("d1", estado="nova")])

        client.post(f"{BASE}/demandas/d1/mover", json={"estado": "aguardando"})

        linhas = sb.tabelas["tecnologia_conversas"]
        assert len(linhas) == 1
        assert linhas[0]["demanda_id"] == "d1"
        assert linhas[0]["linha"] == "movimento"
        assert linhas[0]["movimento_campo"] == "estado"
        assert linhas[0]["movimento_de"] == "nova"
        assert linhas[0]["movimento_para"] == "aguardando"
        assert linhas[0]["texto"] == "Pedro Vitta moveu para Aguardando"
        # Linha automatica nao tem autor: quem fez a acao esta no texto.
        assert linhas[0]["autor_id"] is None


class TestAtribuir:
    def test_troca_o_responsavel_e_grava_a_linha(self):
        client, sb = _montar(demandas=[_demanda("d1", responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P2"})

        assert resposta.status_code == 200
        assert resposta.json()["responsavel_id"] == "P2"
        assert sb.tabelas["tecnologia_demandas"][0]["responsavel_id"] == "P2"

        linhas = sb.tabelas["tecnologia_conversas"]
        assert len(linhas) == 1
        assert linhas[0]["movimento_campo"] == "responsavel"
        assert linhas[0]["movimento_de"] == "P1"
        assert linhas[0]["movimento_para"] == "P2"
        assert linhas[0]["texto"] == "Pedro Vitta atribuiu a Sócia Vitta"

    def test_so_aceita_quem_tem_acesso_a_aba(self):
        client, sb = _montar(demandas=[_demanda("d1", responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P3"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_RESPONSAVEL_SEM_ACESSO
        assert sb.tabelas["tecnologia_demandas"][0]["responsavel_id"] == "P1"
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_atribuir_a_quem_ja_e_responsavel_nao_duplica_linha(self):
        client, sb = _montar(demandas=[_demanda("d1", responsavel_id="P1")])

        resposta = client.post(f"{BASE}/demandas/d1/atribuir", json={"responsavel_id": "P1"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_conversas"] == []


# ─── 4. Editar ───────────────────────────────────────────────────────────────


class TestEditar:
    def test_edita_os_campos_do_modal(self):
        client, sb = _montar(
            produtos=[_produto("prod-1", "Ana"), _produto("prod-2", "POPs")],
            demandas=[_demanda("d1")],
        )

        resposta = client.patch(
            f"{BASE}/demandas/d1",
            json={
                "titulo": "Título novo",
                "descricao": "Contexto",
                "tipo": "defeito",
                "produto_id": "prod-2",
                "prioridade": "alta",
                "prazo": "2026-10-01",
            },
        )

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["titulo"] == "Título novo"
        assert linha["descricao"] == "Contexto"
        assert linha["tipo"] == "defeito"
        assert linha["produto_id"] == "prod-2"
        assert linha["prioridade"] == "alta"
        assert linha["prazo"] == "2026-10-01"

    def test_limpar_o_prazo(self):
        client, sb = _montar(demandas=[_demanda("d1", prazo="2026-10-01")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"prazo": None})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["prazo"] is None

    def test_prazo_vazio_tambem_limpa(self):
        """A tela manda `""` quando o campo de data e apagado."""
        client, sb = _montar(demandas=[_demanda("d1", prazo="2026-10-01")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"prazo": ""})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["prazo"] is None

    def test_campo_ausente_fica_como_esta(self):
        """O par de presenca do teste do prazo: se `None` fosse tratado como
        "nao informado", limpar o prazo nao funcionaria; se todo campo ausente
        virasse NULL, editar o titulo apagaria o prazo."""
        client, sb = _montar(demandas=[_demanda("d1", prazo="2026-10-01", descricao="Antiga")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "Só o título"})

        assert resposta.status_code == 200
        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["titulo"] == "Só o título"
        assert linha["prazo"] == "2026-10-01"
        assert linha["descricao"] == "Antiga"

    def test_titulo_apagado_no_modal_volta_frase_de_gente(self):
        """Apagar o Título no modal e salvar mandava `""` e, com `min_length=1`
        no payload, a tela mostrava o JSON do pydantic no alerta vermelho.
        Quem recusa e o router, com frase de gente e `detail` em TEXTO."""
        client, sb = _montar(demandas=[_demanda("d1", titulo="Tinha título")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": ""})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Título da Demanda não pode ser vazio."
        assert sb.tabelas["tecnologia_demandas"][0]["titulo"] == "Tinha título"

    def test_titulo_so_de_espacos_cai_na_mesma_frase(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "   "})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Título da Demanda não pode ser vazio."

    def test_titulo_grande_demais_tambem_volta_frase_de_gente(self):
        """O outro extremo do titulo, pelo mesmo motivo do vazio.

        Afirmar so o status seria cego ao FORMATO, que e onde estava o defeito:
        com `max_length` no payload, o `detail` vinha em LISTA e a tela mostrava
        o JSON do pydantic. Colar um texto no campo passa de 200 caracteres com
        facilidade.
        """
        client, sb = _montar(demandas=[_demanda("d1", titulo="Tinha título")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "x" * 201})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Título da Demanda pode ter no máximo 200 caracteres."
        assert sb.tabelas["tecnologia_demandas"][0]["titulo"] == "Tinha título"

    def test_titulo_no_limite_passa(self):
        """O par de presenca do teste acima: um limite errado por um caractere
        recusaria o titulo de 200, que e valido."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "x" * 200})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["titulo"] == "x" * 200

    def test_prazo_com_formato_invalido_e_recusado(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"prazo": "01/10/2026"})

        assert resposta.status_code == 422

    def test_editar_nao_troca_o_estado_nem_o_responsavel(self):
        """A porta de estado e `mover`, a de responsavel e `atribuir`: as duas
        gravam linha de movimento, e um PATCH que aceitasse os dois campos
        moveria a Demanda sem deixar rastro no fio."""
        client, sb = _montar(demandas=[_demanda("d1", estado="nova", responsavel_id="P1")])

        client.patch(f"{BASE}/demandas/d1", json={"estado": "concluida", "responsavel_id": "P2"})

        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["estado"] == "nova"
        assert linha["responsavel_id"] == "P1"
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_produto_inexistente_e_recusado(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.patch(f"{BASE}/demandas/d1", json={"produto_id": "prod-9"})

        assert resposta.status_code == 404

    def test_o_produto_desativado_depois_nao_trava_a_edicao(self):
        """Guarda-corpo que virasse indisponibilidade: a regra "Produto inativo
        nao recebe Demanda" e da CRIACAO. A Demanda que ja mora num Produto
        desativado depois continua editavel, senao desativar um Produto
        congelaria o historico dele, que e o contrario do ADR 0050."""
        client, sb = _montar(
            produtos=[_produto("prod-1", "Ana", ativo=False)],
            demandas=[_demanda("d1", produto_id="prod-1")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1", json={"titulo": "Ainda editável"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["titulo"] == "Ainda editável"


# ─── 5. Listar ───────────────────────────────────────────────────────────────


class TestListar:
    def _cenario(self):
        return _montar(
            produtos=[_produto("prod-1", "Ana"), _produto("prod-2", "POPs")],
            demandas=[
                _demanda("d1", estado="nova", tipo="decisao", produto_id="prod-1", responsavel_id="P1"),
                _demanda("d2", estado="aguardando", tipo="defeito", produto_id="prod-2", responsavel_id="P2"),
                _demanda("d3", estado="concluida", tipo="decisao", produto_id="prod-2", responsavel_id="P1"),
            ],
        )

    def test_sem_filtro_traz_as_cinco_colunas_inteiras(self):
        client, _ = self._cenario()

        corpo = client.get(f"{BASE}/demandas").json()

        assert {d["id"] for d in corpo} == {"d1", "d2", "d3"}

    def test_traz_o_nome_do_produto_e_do_responsavel(self):
        """A tela nao cruza tabela: o card mostra Produto e responsavel pelo
        nome, e quem resolve e o backend."""
        client, _ = self._cenario()

        por_id = {d["id"]: d for d in client.get(f"{BASE}/demandas").json()}

        assert por_id["d1"]["produto_nome"] == "Ana"
        assert por_id["d1"]["responsavel_nome"] == "Pedro Vitta"
        assert por_id["d2"]["produto_nome"] == "POPs"
        assert por_id["d2"]["responsavel_nome"] == "Sócia Vitta"

    @pytest.mark.parametrize(
        "filtro,esperado",
        (
            ({"estado": "nova"}, {"d1"}),
            ({"tipo": "decisao"}, {"d1", "d3"}),
            ({"produto_id": "prod-2"}, {"d2", "d3"}),
            ({"responsavel_id": "P1"}, {"d1", "d3"}),
            ({"tipo": "decisao", "produto_id": "prod-2"}, {"d3"}),
        ),
    )
    def test_cada_filtro_reduz_a_lista(self, filtro, esperado):
        client, _ = self._cenario()

        corpo = client.get(f"{BASE}/demandas", params=filtro).json()

        assert {d["id"] for d in corpo} == esperado


class TestConversa:
    def test_lista_as_linhas_em_ordem_cronologica_com_autor(self):
        client, _ = _montar(
            demandas=[_demanda("d1")],
            conversas=[
                {
                    "id": "c2",
                    "demanda_id": "d1",
                    "autor_id": None,
                    "linha": "movimento",
                    "texto": "Pedro Vitta moveu para Aguardando",
                    "mencoes": [],
                    "movimento_campo": "estado",
                    "movimento_de": "nova",
                    "movimento_para": "aguardando",
                    "criado_em": "2026-09-02T10:00:00Z",
                    "editado_em": None,
                },
                {
                    "id": "c1",
                    "demanda_id": "d1",
                    "autor_id": "P2",
                    "linha": "resposta",
                    "texto": "Vou olhar hoje",
                    "mencoes": [],
                    "movimento_campo": None,
                    "movimento_de": None,
                    "movimento_para": None,
                    "criado_em": "2026-09-01T10:00:00Z",
                    "editado_em": None,
                },
            ],
        )

        corpo = client.get(f"{BASE}/demandas/d1/conversa").json()

        assert [linha["id"] for linha in corpo] == ["c1", "c2"]
        assert corpo[0]["autor_nome"] == "Sócia Vitta"
        # Linha automatica nao tem autor no banco; a tela mostra o texto, que ja
        # traz o nome de quem moveu.
        assert corpo[1]["autor_nome"] is None
        assert corpo[1]["linha"] == "movimento"

    def test_a_conversa_de_uma_demanda_nao_traz_a_da_outra(self):
        client, _ = _montar(
            demandas=[_demanda("d1"), _demanda("d2")],
            conversas=[
                {
                    "id": "c1",
                    "demanda_id": "d2",
                    "autor_id": "P1",
                    "linha": "resposta",
                    "texto": "Da outra Demanda",
                    "mencoes": [],
                    "movimento_campo": None,
                    "movimento_de": None,
                    "movimento_para": None,
                    "criado_em": "2026-09-01T10:00:00Z",
                    "editado_em": None,
                }
            ],
        )

        assert client.get(f"{BASE}/demandas/d1/conversa").json() == []
        assert [linha["id"] for linha in client.get(f"{BASE}/demandas/d2/conversa").json()] == ["c1"]

    def test_demanda_inexistente_da_404(self):
        client, _ = _montar()

        assert client.get(f"{BASE}/demandas/d9/conversa").status_code == 404


# ─── 6. Responder e editar no fio (issue #638) ───────────────────────────────

# A janela de 10 minutos e uma regra de TEMPO, e por isso ela e testada como
# funcao pura com o instante injetado: ler o relogio dentro da regra deixaria
# as bordas sem teste possivel. As duas bordas estao aqui; a rota, mais abaixo,
# usa minutos folgados (1 e 30) porque o que ela prova e o desfecho, nao o
# limite.

ENVIO = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)


class TestJanelaDeEdicao:
    def test_a_janela_e_de_dez_minutos(self):
        """O numero da PRD, escrito uma vez so. Os casos abaixo sao lidos a
        partir dele; se a constante mudar sem a PRD mudar, este teste cai."""
        assert JANELA_DE_EDICAO == timedelta(minutes=10)

    @pytest.mark.parametrize(
        "passou,dentro",
        (
            (timedelta(seconds=0), True),
            (timedelta(minutes=9, seconds=59), True),
            # A borda exata AINDA vale ("por ate 10 minutos"). E o caso que
            # mata o mutante que troca `<=` por `<`.
            (timedelta(minutes=10), True),
            # E o primeiro instante depois dela nao vale: e o caso que mata o
            # mutante que afrouxa a comparacao para um limite maior, e o que a
            # apaga de vez.
            (timedelta(minutes=10, microseconds=1), False),
            (timedelta(minutes=10, seconds=1), False),
            (timedelta(hours=3), False),
        ),
    )
    def test_cada_lado_da_borda(self, passou, dentro):
        assert dentro_da_janela_de_edicao(criado_em=ENVIO, agora=ENVIO + passou) is dentro

    def test_o_limite_e_o_envio_mais_a_janela(self):
        """O instante que a tela recebe para sumir com o botao sozinha."""
        assert limite_da_janela_de_edicao(ENVIO) == datetime(2026, 9, 9, 12, 10, 0, tzinfo=UTC)

    def test_instante_ilegivel_nao_vira_data_de_hoje(self):
        """`criado_em` que nao da para ler nao pode virar "acabou de chegar":
        seria uma janela aberta para sempre em cima de dado quebrado."""
        assert instante_do_banco(None) is None
        assert instante_do_banco("ontem de manha") is None

    @pytest.mark.parametrize(
        "texto",
        ("2026-09-09T12:00:00Z", "2026-09-09T12:00:00+00:00", "2026-09-09T12:00:00.123456+00:00"),
    )
    def test_le_os_formatos_que_o_postgrest_devolve(self, texto):
        lido = instante_do_banco(texto)
        assert lido is not None
        assert lido.tzinfo is not None
        assert lido.replace(microsecond=0) == ENVIO

    def test_instante_sem_fuso_conta_como_utc(self):
        """Comparar um `datetime` ingenuo com um consciente estoura TypeError,
        e a janela viraria 500 em vez de recusa."""
        lido = instante_do_banco("2026-09-09T12:00:00")
        assert lido == ENVIO


class TestQuemPodeEditar:
    def _resposta(self, **campos):
        base = {"linha": "resposta", "autor_id": "P1", "criado_em": ENVIO.isoformat()}
        base.update(campos)
        return base

    def test_o_autor_dentro_da_janela_pode(self):
        """O par de presenca de todas as recusas abaixo: um motivo cravado
        recusaria tambem quem tem direito."""
        assert motivo_edicao_recusada(linha=self._resposta(), ator_id="P1", agora=ENVIO) is None

    def test_outra_pessoa_nao_edita_resposta_alheia(self):
        motivo = motivo_edicao_recusada(linha=self._resposta(), ator_id="P2", agora=ENVIO)
        assert motivo == MOTIVO_SO_O_AUTOR_EDITA

    def test_fora_da_janela_nem_o_autor_edita(self):
        motivo = motivo_edicao_recusada(linha=self._resposta(), ator_id="P1", agora=ENVIO + timedelta(minutes=11))
        assert motivo == MOTIVO_JANELA_ENCERRADA

    def test_linha_de_movimento_nunca_e_editavel(self):
        """Nem para quem moveu: a linha automatica e a trilha, e trilha que se
        reescreve nao e trilha. Ela vem com `autor_id` NULL no banco, entao a
        recusa por autor diria "nao e sua" a quem acabou de mover."""
        linha = {"linha": "movimento", "autor_id": None, "criado_em": ENVIO.isoformat()}
        assert motivo_edicao_recusada(linha=linha, ator_id="P1", agora=ENVIO) == MOTIVO_MOVIMENTO_NAO_SE_EDITA

    def test_a_ordem_das_recusas_nao_culpa_a_causa_errada(self):
        """Movimento fora da janela e de outra pessoa: a frase tem que ser a do
        movimento, que e a razao de fundo. Dizer "acabou o prazo" sugeriria que
        dentro do prazo daria, e nao da nunca."""
        linha = {"linha": "movimento", "autor_id": "P2", "criado_em": ENVIO.isoformat()}
        motivo = motivo_edicao_recusada(linha=linha, ator_id="P1", agora=ENVIO + timedelta(hours=1))
        assert motivo == MOTIVO_MOVIMENTO_NAO_SE_EDITA

    def test_resposta_com_data_ilegivel_e_recusada_sem_estourar(self):
        linha = self._resposta(criado_em=None)
        assert motivo_edicao_recusada(linha=linha, ator_id="P1", agora=ENVIO) == MOTIVO_JANELA_ENCERRADA


class TestMencoesPuras:
    def test_normalizar_tira_vazio_espaco_e_repetido(self):
        """`""` nao e id de ninguem: passar adiante sujaria a coluna e faria a
        guarda de acesso recusar uma resposta por causa de um item vazio."""
        assert normalizar_mencoes([" P1 ", "", "P1", "  ", "P2"]) == ["P1", "P2"]

    def test_sem_mencao_a_lista_e_vazia(self):
        assert normalizar_mencoes(None) == []
        assert normalizar_mencoes([]) == []

    def test_quem_nao_esta_na_lista_da_aba_e_apontado(self):
        assert mencoes_sem_acesso(["P1", "P9"], {"P1", "P2"}) == ["P9"]

    def test_todo_mundo_com_acesso_passa(self):
        """Par de presenca: uma funcao que sempre apontasse alguem recusaria
        toda mencao."""
        assert mencoes_sem_acesso(["P1", "P2"], {"P1", "P2"}) == []

    def test_a_recusa_do_teto_diz_os_dois_numeros(self):
        """Guarda-corpo que so diz "nao pode" vira indisponibilidade: a frase
        tem de dizer quantas mencoes vieram e quanta gente existe, para quem
        escreveu saber o que sobra tirar."""
        motivo = motivo_mencoes_demais(quantas=7, com_acesso=3)

        assert "7" in motivo
        assert "3" in motivo
        assert "pessoas têm" in motivo

    def test_a_recusa_do_teto_fala_no_singular_quando_e_uma_pessoa_so(self):
        assert "1 pessoa tem" in motivo_mencoes_demais(quantas=2, com_acesso=1)

    def test_a_dedupe_nao_depende_da_ordem_de_chegada(self):
        """O controle de repetido virou `set` (a varredura linear era
        quadratica). O resultado tem de continuar sendo o mesmo: sem repetido, e
        na ordem em que cada um apareceu pela primeira vez."""
        assert normalizar_mencoes(["P2", "P1", "P2", "P3", "P1"]) == ["P2", "P1", "P3"]

    def test_a_dedupe_aguenta_lista_grande_sem_virar_conta_quadratica(self):
        """Nao e teste de relogio, e de ORDEM DE GRANDEZA: com a varredura
        linear de antes, 20 mil ids levavam mais de meio segundo dentro do event
        loop de um uvicorn com um worker so, e o app inteiro parava junto."""
        import time

        muitos = [f"P{i}" for i in range(20_000)]

        comeco = time.monotonic()
        limpos = normalizar_mencoes(muitos)

        assert len(limpos) == 20_000
        assert time.monotonic() - comeco < 0.2

    def test_o_teto_da_resposta_e_de_cinco_mil_caracteres(self):
        """A trava do valor, no molde da `test_a_janela_e_de_dez_minutos`: o
        numero vem da PRD e nao muda sem alguem decidir."""
        assert LIMITE_RESPOSTA == 5000

    def test_o_byte_nulo_e_recusado_antes_de_chegar_ao_banco(self):
        """O Postgres nao aceita NUL em coluna TEXT (22P05). Sem esta guarda o
        texto passava e morria no insert, e quem escreveu levava um 500 no lugar
        de uma frase que diz o que houve."""
        assert motivo_resposta_invalida("Oi\x00tudo bem") == MOTIVO_RESPOSTA_COM_CARACTERE_INVALIDO

    def test_texto_normal_nao_e_confundido_com_caractere_invalido(self):
        """Par de presenca: uma guarda que recusasse texto comum seria pior do
        que o 500 que ela veio evitar."""
        assert motivo_resposta_invalida("Oi, tudo bem? Acento é acento.") is None


# ─── 7. As duas portas de escrita do fio ─────────────────────────────────────


def _resposta_no_banco(cid: str, **campos) -> dict:
    base = {
        "id": cid,
        "demanda_id": "d1",
        "autor_id": "P1",
        "linha": "resposta",
        "texto": "Vou olhar hoje",
        "mencoes": [],
        "movimento_campo": None,
        "movimento_de": None,
        "movimento_para": None,
        "criado_em": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "editado_em": None,
    }
    base.update(campos)
    return base


class TestResponder:
    def test_grava_a_resposta_com_autor_e_texto(self):
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Já pedi à Global Health"})

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["texto"] == "Já pedi à Global Health"
        assert corpo["autor_id"] == "P1"
        assert corpo["autor_nome"] == "Pedro Vitta"
        assert corpo["linha"] == "resposta"
        gravada = sb.tabelas["tecnologia_conversas"][0]
        assert gravada["demanda_id"] == "d1"
        assert gravada["linha"] == "resposta"
        assert gravada["editado_em"] is None

    def test_a_resposta_aparece_no_fio_da_demanda(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Respondido"})
        fio = client.get(f"{BASE}/demandas/d1/conversa").json()

        assert [linha["texto"] for linha in fio] == ["Respondido"]

    def test_texto_vazio_e_recusado_com_frase_de_gente(self):
        """`""` e `"   "` nao sao resposta. A recusa sai do router, e nao do
        `min_length` do pydantic, cujo `detail` vem em LISTA e chega a tela como
        JSON cru."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "   "})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_RESPOSTA_VAZIA
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_texto_grande_demais_e_recusado_com_o_limite_a_vista(self):
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "x" * (LIMITE_RESPOSTA + 1)})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == f"A resposta pode ter no máximo {LIMITE_RESPOSTA} caracteres."
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_texto_no_limite_passa(self):
        """Par de presenca do teste acima: um limite errado por um caractere
        recusaria a resposta de tamanho valido."""
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "x" * LIMITE_RESPOSTA})

        assert resposta.status_code == 201

    def test_cinco_mil_caracteres_cravados_passam(self):
        """O NUMERO combinado, e nao a mecanica em volta dele.

        Os dois casos acima medem o teto contra ele mesmo (`LIMITE_RESPOSTA`),
        entao trocar a constante por 200 os deixaria verdes sobre outro limite.
        Aqui e este par o valor esta escrito a mao: 5000 passa, 5001 nao.
        """
        client, _ = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "x" * 5000})

        assert resposta.status_code == 201

    def test_cinco_mil_e_um_caracteres_sao_recusados_com_o_numero_na_frase(self):
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "x" * 5001})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "A resposta pode ter no máximo 5000 caracteres."
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_a_mencao_escolhida_fica_na_linha(self):
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Sócia Vitta consegue olhar?", "mencoes": ["P2"]},
        )

        assert resposta.status_code == 201
        assert resposta.json()["mencoes"] == ["P2"]
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == ["P2"]

    def test_mencao_a_quem_nao_tem_acesso_a_aba_e_recusada(self):
        """A mesma regra da porta de atribuir: quem nao ve a aba nao vira
        responsavel, e tambem nao vira mencao, senao o app criaria por uma porta
        o estado que a outra recusa (e o e-mail da fatia seguinte chamaria quem
        nao consegue abrir o link)."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Facilitador olha isso", "mencoes": ["P3"]},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_MENCAO_SEM_ACESSO
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_mencao_vazia_nao_derruba_a_resposta(self):
        """Item vazio na lista e sujeira do payload, nao mencao a ninguem:
        recusar a resposta por causa dele seria cobrar da pessoa uma correcao
        que ela nao tem onde fazer."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Sem menção", "mencoes": [""]})

        assert resposta.status_code == 201
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == []

    def test_id_fora_da_lista_leva_a_frase_do_id_fora_da_lista(self):
        """As duas recusas de mencao sao DUAS CAUSAS, e cada uma tem a sua
        frase.

        Aqui vem tudo junto: tres ids para duas pessoas com acesso, e um deles
        de fora. A causa que a pessoa precisa ler e o id de fora, que e a
        especifica; cobrar a QUANTIDADE mandaria cortar mencoes quando o
        problema e outro. Este caso e o que mata a inversao da ordem.
        """
        client, sb = _montar(demandas=[_demanda("d1")])

        # Duas pessoas tem acesso a aba no cenario padrao (o facilitador nao).
        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "Chamando quem não tem acesso", "mencoes": ["P1", "P2", "P9"]},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_MENCAO_SEM_ACESSO
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_lista_de_mencoes_maior_que_a_aba_e_recusada_pelo_teto(self):
        """A outra causa, sozinha: todos os ids valem, e ainda assim vieram
        mais menções do que existe gente com acesso.

        O teto mede o que VEIO no payload, e nao a lista ja limpa: depois da
        limpeza os ids sao distintos, e a conta nunca passaria do numero de
        pessoas. Medido no bruto, o numero da frase e o numero que a pessoa
        mandou, e o guarda-corpo continua fechando o payload de milhares de ids.
        """
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Pedro Vitta olha", "mencoes": ["P1", "P1", "P1"]},
        )

        assert resposta.status_code == 422
        motivo = resposta.json()["detail"]
        assert motivo == motivo_mencoes_demais(quantas=3, com_acesso=2)
        # A frase fala do que veio (3), e nao do que sobrou depois da limpeza (1).
        assert "3 menções" in motivo
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_mencao_repetida_dentro_do_teto_continua_valendo(self):
        """Par de presenca do teto: repetir nao e crime enquanto couber no
        numero de gente da aba. A lista gravada sai sem repetido."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Pedro Vitta olha", "mencoes": ["P1", "P1"]},
        )

        assert resposta.status_code == 201
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == ["P1"]

    def test_mencionar_todo_mundo_da_aba_continua_valendo(self):
        """Par de presenca do teto: ele nao pode morder o caso normal, senao o
        guarda-corpo vira indisponibilidade. Chamar as duas pessoas que existem
        e legitimo."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(
            f"{BASE}/demandas/d1/conversa",
            json={"texto": "@Pedro Vitta e @Sócia Vitta, olhem", "mencoes": ["P1", "P2"]},
        )

        assert resposta.status_code == 201
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == ["P1", "P2"]

    def test_texto_com_byte_nulo_e_recusado_com_frase_de_gente(self):
        """Pela rota: o que o Postgres recusaria com 22P05 sai daqui como 422
        com frase, e nao como o 500 "a sua resposta nao entrou"."""
        client, sb = _montar(demandas=[_demanda("d1")])

        resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Colado\x00de outro lugar"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_RESPOSTA_COM_CARACTERE_INVALIDO
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_demanda_inexistente_da_404_e_nao_grava(self):
        client, sb = _montar()

        resposta = client.post(f"{BASE}/demandas/d9/conversa", json={"texto": "Oi"})

        assert resposta.status_code == 404
        assert sb.tabelas["tecnologia_conversas"] == []

    def test_responder_nao_move_a_demanda_nem_troca_o_responsavel(self):
        """Responder e falar, nao mexer no quadro."""
        client, sb = _montar(demandas=[_demanda("d1", estado="aguardando", responsavel_id="P2")])

        client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Falando"})

        linha = sb.tabelas["tecnologia_demandas"][0]
        assert linha["estado"] == "aguardando"
        assert linha["responsavel_id"] == "P2"

    @pytest.mark.parametrize("modo", ("vazio", "excecao"))
    def test_falha_na_escrita_do_fio_nao_passa_calada(self, modo, caplog):
        """O PostgREST pode recusar ou cair. Devolver 201 com a resposta que
        nao entrou faria a pessoa achar que falou, e o outro lado nunca leria."""
        client, sb = _montar(demandas=[_demanda("d1")], fio_falha=modo)

        with caplog.at_level(logging.ERROR):
            resposta = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Some no caminho"})

        assert resposta.status_code == 500
        assert "não entrou" in resposta.json()["detail"]
        assert "d1" in caplog.text
        assert sb.tabelas["tecnologia_conversas"] == []


class TestEditarAPropriaResposta:
    def test_o_autor_corrige_dentro_da_janela_e_a_linha_fica_marcada(self):
        client, sb = _montar(demandas=[_demanda("d1")], conversas=[_resposta_no_banco("c1")])

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Vou olhar amanhã"})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["texto"] == "Vou olhar amanhã"
        assert corpo["editado_em"] is not None
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Vou olhar amanhã"
        assert sb.tabelas["tecnologia_conversas"][0]["editado_em"] is not None

    def test_a_edicao_troca_tambem_a_lista_de_mencoes(self):
        """Tirar o @Fulano do texto tem que tirar a mencao: senao a linha
        continuaria dizendo que chamou alguem que o texto nao chama mais."""
        client, sb = _montar(
            demandas=[_demanda("d1")],
            conversas=[_resposta_no_banco("c1", mencoes=["P2"], texto="@Sócia Vitta olha")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Deixa comigo", "mencoes": []})

        assert resposta.status_code == 200
        assert resposta.json()["mencoes"] == []
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == []

    def test_outra_pessoa_nao_edita_a_resposta_alheia(self):
        client, sb = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1")],
            conversas=[_resposta_no_banco("c1", autor_id="P1", texto="Do Pedro")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Reescrevendo o alheio"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_SO_O_AUTOR_EDITA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Do Pedro"

    def test_o_autor_da_linha_edita_a_dele_no_mesmo_cenario(self):
        """Par de presenca do teste acima: uma recusa cravada recusaria todo
        mundo, inclusive quem escreveu."""
        client, sb = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1")],
            conversas=[_resposta_no_banco("c1", autor_id="P2", texto="Da Sócia")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Da Sócia, corrigido"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Da Sócia, corrigido"

    def test_fora_da_janela_o_proprio_autor_e_recusado(self):
        antiga = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        client, sb = _montar(
            demandas=[_demanda("d1")],
            conversas=[_resposta_no_banco("c1", criado_em=antiga, texto="Antiga")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Tarde demais"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_JANELA_ENCERRADA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Antiga"

    def test_corrigir_de_novo_dentro_dos_dez_minutos_do_envio_e_aceito(self):
        """Enviada ha 9 minutos, ja corrigida ha 1: ainda da para corrigir.

        E o par de presenca do teste seguinte: sem ele, uma regra que recusasse
        toda linha ja corrigida passaria por aquele sem contar a verdade.
        """
        client, sb = _montar(
            demandas=[_demanda("d1")],
            conversas=[
                _resposta_no_banco(
                    "c1",
                    criado_em=(datetime.now(UTC) - timedelta(minutes=9)).isoformat(),
                    editado_em=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                    texto="Primeira correção",
                )
            ],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Segunda correção"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Segunda correção"

    def test_corrigir_nao_renova_o_prazo(self):
        """Enviada ha 30 minutos, corrigida ha 1: o prazo continua fechado.

        A janela conta do ENVIO. Se contasse da ultima edicao, corrigir de 9 em
        9 minutos deixaria a resposta editavel para sempre, e o fio deixaria de
        ser trilha. O caso so morde porque `editado_em` esta PREENCHIDO e
        RECENTE: e a unica forma de a guarda ter de escolher entre os dois
        campos.
        """
        client, sb = _montar(
            demandas=[_demanda("d1")],
            conversas=[
                _resposta_no_banco(
                    "c1",
                    criado_em=(datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
                    editado_em=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                    texto="Corrigida uma vez, ha muito tempo",
                )
            ],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Terceira tentativa"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_JANELA_ENCERRADA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Corrigida uma vez, ha muito tempo"

    def test_a_linha_ja_corrigida_nao_volta_editavel_no_fio(self):
        """O mesmo pela porta de LEITURA: o `editavel_ate` daquela linha antiga
        ja passou, entao a tela nao desenha o botao para ela."""
        client, _ = _montar(
            demandas=[_demanda("d1")],
            conversas=[
                _resposta_no_banco(
                    "c1",
                    criado_em=(datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
                    editado_em=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                ),
                _resposta_no_banco(
                    "c2",
                    criado_em=(datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
                    editado_em=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                ),
            ],
        )

        por_id = {linha["id"]: linha for linha in client.get(f"{BASE}/demandas/d1/conversa").json()}

        assert instante_do_banco(por_id["c1"]["editavel_ate"]) < datetime.now(UTC)
        # Par de presenca no MESMO fio: a linha corrigida ha pouco, mas enviada
        # ha 2 minutos, continua dentro do prazo.
        assert instante_do_banco(por_id["c2"]["editavel_ate"]) > datetime.now(UTC)

    def test_linha_de_movimento_e_recusada(self):
        movimento = _resposta_no_banco(
            "c1",
            autor_id=None,
            linha="movimento",
            texto="Pedro Vitta moveu para Aguardando",
            movimento_campo="estado",
            movimento_de="nova",
            movimento_para="aguardando",
        )
        client, sb = _montar(demandas=[_demanda("d1")], conversas=[movimento])

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Não moveu nada"})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_MOVIMENTO_NAO_SE_EDITA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Pedro Vitta moveu para Aguardando"

    def test_texto_vazio_na_edicao_e_recusado(self):
        """Apagar tudo nao e o jeito de apagar a resposta: nao existe apagar."""
        client, sb = _montar(demandas=[_demanda("d1")], conversas=[_resposta_no_banco("c1", texto="Tinha texto")])

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "  "})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_RESPOSTA_VAZIA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Tinha texto"

    def test_mencao_sem_acesso_tambem_e_recusada_na_edicao(self):
        """A porta de editar valida o mesmo que a de responder: senao daria
        para criar pela edicao a mencao que o envio recusa."""
        client, sb = _montar(demandas=[_demanda("d1")], conversas=[_resposta_no_banco("c1")])

        resposta = client.patch(
            f"{BASE}/demandas/d1/conversa/c1",
            json={"texto": "@Facilitador olha isso", "mencoes": ["P3"]},
        )

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_MENCAO_SEM_ACESSO
        assert sb.tabelas["tecnologia_conversas"][0]["mencoes"] == []

    def test_linha_de_outra_demanda_nao_e_alcancada_pelo_id(self):
        """O caminho carrega as duas chaves: sem a amarra da Demanda, quem
        soubesse o id da linha editaria por qualquer card."""
        client, sb = _montar(
            demandas=[_demanda("d1"), _demanda("d2")],
            conversas=[_resposta_no_banco("c1", demanda_id="d2", texto="Da outra")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Invadindo"})

        assert resposta.status_code == 404
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Da outra"

    def test_a_linha_de_outra_demanda_nem_chega_as_regras_de_edicao(self):
        """A BUSCA e que tem de amarrar as duas chaves, e nao so a escrita.

        Uma busca so pelo id da linha acharia a resposta da outra Demanda e
        rodaria as regras em cima dela: a recusa sairia como "so quem escreveu
        corrige" (422), contando a quem perguntou que aquela linha existe e e de
        outra pessoa. Pelo caminho certo, a linha simplesmente nao esta neste
        card, e a resposta e 404.
        """
        client, sb = _montar(
            demandas=[_demanda("d1"), _demanda("d2")],
            conversas=[_resposta_no_banco("c1", demanda_id="d2", autor_id="P2", texto="Da outra, de outra pessoa")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Invadindo"})

        assert resposta.status_code == 404
        assert resposta.json()["detail"] != MOTIVO_SO_O_AUTOR_EDITA
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Da outra, de outra pessoa"

    def test_a_linha_da_propria_demanda_e_alcancada(self):
        """Par de presenca dos dois acima: um 404 cravado no PATCH passaria
        pelos dois sem procurar linha nenhuma."""
        client, sb = _montar(
            demandas=[_demanda("d1"), _demanda("d2")],
            conversas=[_resposta_no_banco("c1", demanda_id="d1", texto="Desta Demanda")],
        )

        resposta = client.patch(f"{BASE}/demandas/d1/conversa/c1", json={"texto": "Corrigida"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_conversas"][0]["texto"] == "Corrigida"

    def test_linha_inexistente_da_404(self):
        client, _ = _montar(demandas=[_demanda("d1")])

        assert client.patch(f"{BASE}/demandas/d1/conversa/c9", json={"texto": "Oi"}).status_code == 404

    def test_nao_existe_porta_de_apagar_resposta(self):
        """Criterio de aceite da issue #638: nada se apaga no fio. A varredura
        e sobre o schema publicado, e nao sobre uma chamada so, para pegar
        tambem um DELETE que entrasse com outro caminho."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        do_fio = {c: ops for c, ops in caminhos.items() if "/admin/tecnologia/" in c and "conversa" in c}
        # Par de presenca: as duas portas de escrita ESTAO publicadas, entao a
        # ausencia do delete abaixo nao e varredura vazia.
        assert any("post" in ops for ops in do_fio.values())
        assert any("patch" in ops for ops in do_fio.values())
        assert all("delete" not in ops for ops in do_fio.values())


class TestOFioDizQuemPodeCorrigir:
    """`editavel_ate` e o carimbo que a tela usa para desenhar (ou nao) o botao
    de editar. A tela nao sabe qual participante e o usuario logado: o
    `useAuth` traz o id do Supabase Auth, e nao o `participantes.id`. Por isso
    quem diz "esta linha e sua e ainda da tempo" e o backend."""

    def test_a_propria_resposta_recente_vem_com_o_limite_da_janela(self):
        client, _ = _montar(demandas=[_demanda("d1")], conversas=[_resposta_no_banco("c1", autor_id="P1")])

        linha = client.get(f"{BASE}/demandas/d1/conversa").json()[0]

        assert linha["editavel_ate"] is not None

    def test_a_resposta_de_outra_pessoa_nao_vem_editavel(self):
        client, _ = _montar(demandas=[_demanda("d1")], conversas=[_resposta_no_banco("c1", autor_id="P2")])

        linha = client.get(f"{BASE}/demandas/d1/conversa").json()[0]

        assert linha["editavel_ate"] is None
        # Par de presenca no MESMO fio: a linha existe e traz o autor.
        assert linha["autor_nome"] == "Sócia Vitta"

    def test_a_linha_de_movimento_nunca_vem_editavel(self):
        movimento = _resposta_no_banco("c1", autor_id=None, linha="movimento", texto="Pedro Vitta moveu para Nova")
        client, _ = _montar(demandas=[_demanda("d1")], conversas=[movimento])

        linha = client.get(f"{BASE}/demandas/d1/conversa").json()[0]

        assert linha["editavel_ate"] is None

    def test_o_limite_e_dez_minutos_depois_do_envio(self):
        envio = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
        client, _ = _montar(
            demandas=[_demanda("d1")],
            conversas=[_resposta_no_banco("c1", criado_em=envio.isoformat())],
        )

        linha = client.get(f"{BASE}/demandas/d1/conversa").json()[0]

        # O instante e escrito a mao, e nao como `envio + JANELA_DE_EDICAO`:
        # repetir a expressao do codigo faria o teste acompanhar qualquer
        # mudanca da constante em vez de cobrar o valor combinado com a PRD.
        assert instante_do_banco(linha["editavel_ate"]) == datetime(2026, 9, 9, 12, 10, 0, tzinfo=UTC)

    def test_o_limite_conta_do_envio_mesmo_na_linha_ja_corrigida(self):
        """A linha corrigida as 12:09 continua fechando as 12:10.

        Se o `editavel_ate` contasse da ultima edicao, a resposta corrigida de 9
        em 9 minutos ficaria editavel para sempre, e a tela ofereceria o botao
        eternamente. O caso precisa de `editado_em` PREENCHIDO: sem ele o
        detector nunca ve a diferenca entre os dois campos.
        """
        envio = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
        client, _ = _montar(
            demandas=[_demanda("d1")],
            conversas=[
                _resposta_no_banco(
                    "c1",
                    criado_em=envio.isoformat(),
                    editado_em=datetime(2026, 9, 9, 12, 9, 0, tzinfo=UTC).isoformat(),
                )
            ],
        )

        linha = client.get(f"{BASE}/demandas/d1/conversa").json()[0]

        # 12:10, e nao 12:19.
        assert instante_do_banco(linha["editavel_ate"]) == datetime(2026, 9, 9, 12, 10, 0, tzinfo=UTC)
        # Par de presenca, no mesmo corpo: a linha realmente esta marcada como
        # corrigida, entao o `editado_em` chegou ao endpoint e foi ignorado de
        # proposito, e nao por estar ausente.
        assert linha["editado_em"] is not None

    def test_a_resposta_recem_enviada_ja_volta_editavel(self):
        """Quem acabou de enviar tem que ver o botao sem recarregar o modal."""
        client, _ = _montar(demandas=[_demanda("d1")])

        criada = client.post(f"{BASE}/demandas/d1/conversa", json={"texto": "Corrijo já já"}).json()

        assert criada["editavel_ate"] is not None
