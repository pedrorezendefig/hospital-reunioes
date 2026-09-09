"""A Demanda nasce e anda no Quadro (issue #637, PRD #634, ADR 0050).

Dois seams, na ordem em que a regra existe:

* **A maquina de estados**, funcao pura, testada direto e sem HTTP. A tabela de
  transicoes permitidas e escrita AQUI, a mao, a partir da PRD; a lista de
  proibidas e o complemento dela sobre o produto cartesiano dos cinco estados.
  Assim nenhuma transicao fica sem teste: quem acrescentar um estado quebra o
  piso de sanidade, e quem afrouxar a regra cai numa proibida.
* **Os endpoints**, pela ROTA de verdade com o Supabase dublado, no molde do
  `test_admin_tecnologia.py` da fatia anterior. E o unico jeito de provar que a
  linha de movimento sai na MESMA operacao do movimento.

O gate de papel nao se repete aqui: a matriz de `test_admin_tecnologia.py`
varre o schema OpenAPI e ja engole toda rota nova deste arquivo.
"""

from __future__ import annotations

import itertools
import os
import sys
from dataclasses import dataclass
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
    MOTIVO_PRODUTO_INATIVO,
    MOTIVO_PRODUTO_SEM_DONO,
    MOTIVO_RESPONSAVEL_SEM_ACESSO,
    PRIORIDADES,
    TIPOS,
    carimbos_da_transicao,
    motivo_transicao_invalida,
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
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(tecnologia_router.router, prefix="/api")

    pessoas = [dict(p) for p in (participantes if participantes is not None else [PEDRO, SOCIA, FACILITADOR])]
    if all(p["id"] != logado["id"] for p in pessoas):
        pessoas.append(dict(logado))

    sb = _SupabaseMock(
        tabelas={
            "participantes": pessoas,
            "tecnologia_produtos": [
                dict(p) for p in (produtos if produtos is not None else [_produto("prod-1", "Ana")])
            ],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        }
    )

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
