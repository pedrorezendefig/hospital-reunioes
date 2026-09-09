"""Router /admin/tecnologia, a fundacao da aba Tecnologia (issue #636, PRD #634).

Todos os endpoints exigem `require_super_admin`. Esse e o gate de verdade: a
sidebar apenas esconde o item, e esconder nao e proteger (ADR 0050, decisao 2).

Nesta fatia:

- GET   /admin/tecnologia/pessoas               quem tem acesso a aba.
- GET   /admin/tecnologia/produtos              lista os Produtos.
- POST  /admin/tecnologia/produtos              cria Produto.
- PATCH /admin/tecnologia/produtos/{id}         renomeia, ativa, desativa,
                                                troca o dono e a ordem.

Nao existe DELETE: desativar e a saida (ADR 0050, decisao 11). A linha continua
no banco e volta na lista marcada como inativa.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.tecnologia_schemas import (
    PessoaDaAba,
    ProdutoCreatePayload,
    ProdutoResponse,
    ProdutoUpdatePayload,
)
from app.services.tecnologia import (
    MOTIVO_DONO_SEM_ACESSO,
    MOTIVO_PRODUTO_ATIVO_SEM_DONO,
    e_pessoa_da_aba,
    produto_ativo_sem_dono,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tecnologia", tags=["admin", "tecnologia"])

TABELA_PRODUTOS = "tecnologia_produtos"

# O que a lista de pessoas precisa ler do participante. `ativo` e
# `access_profile`/`is_super_admin` entram porque o filtro roda em Python: um
# `.eq("ativo", True)` no PostgREST descartaria as linhas com `ativo` NULL.
_CAMPOS_PESSOA = "id, nome_completo, email, ativo, is_super_admin, access_profile"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _pessoas_da_aba(supabase: Client) -> list[dict]:
    """Participantes ativos com Super admin, em ordem de nome."""
    result = supabase.table("participantes").select(_CAMPOS_PESSOA).order("nome_completo").execute()
    return [linha for linha in (result.data or []) if e_pessoa_da_aba(linha)]


def _normalizar_nome(nome: str) -> str:
    return " ".join(nome.strip().split())


def _buscar_produto(supabase: Client, produto_id: str) -> dict:
    result = supabase.table(TABELA_PRODUTOS).select("*").eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto nao encontrado")
    return result.data[0]


def _exigir_nome_livre(supabase: Client, nome: str, *, exceto_id: str | None = None) -> None:
    """409 se outro Produto ja usa este nome, sem distinguir maiusculas."""
    result = supabase.table(TABELA_PRODUTOS).select("id, nome").execute()
    alvo = nome.strip().lower()
    for linha in result.data or []:
        if linha.get("id") == exceto_id:
            continue
        if str(linha.get("nome", "")).strip().lower() == alvo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ja existe um Produto com esse nome.",
            )


def _exigir_dono_com_acesso(supabase: Client, dono_id: str) -> None:
    """422 se o dono escolhido nao esta na lista de pessoas da aba."""
    if dono_id not in {p["id"] for p in _pessoas_da_aba(supabase)}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=MOTIVO_DONO_SEM_ACESSO,
        )


def _exigir_dono_no_produto_ativo(*, ativo: bool, dono_id: str | None) -> None:
    if produto_ativo_sem_dono(ativo=ativo, dono_id=dono_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=MOTIVO_PRODUTO_ATIVO_SEM_DONO,
        )


def _com_nome_do_dono(supabase: Client, produtos: list[dict]) -> list[dict]:
    """Resolve `dono_nome` numa consulta so, para a tela nao precisar cruzar."""
    ids = {p["dono_id"] for p in produtos if p.get("dono_id")}
    nomes: dict[str, str] = {}
    if ids:
        donos = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute()
        nomes = {linha["id"]: linha.get("nome_completo") for linha in (donos.data or [])}
    return [{**p, "dono_nome": nomes.get(p.get("dono_id"))} for p in produtos]


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/pessoas", response_model=list[PessoaDaAba])
async def listar_pessoas(
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Quem tem acesso a aba: participante ativo com Super admin.

    Serve aos tres usos da PRD (dono de Produto, responsavel e @mencao), por
    isso a lista e uma so.
    """
    return _pessoas_da_aba(supabase)


@router.get("/produtos", response_model=list[ProdutoResponse])
async def listar_produtos(
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Todos os Produtos, ativos e inativos, na ordem de exibicao.

    O inativo continua aparecendo de proposito: desativar tira o Produto da
    escolha de Demanda nova, nao da vista.
    """
    result = supabase.table(TABELA_PRODUTOS).select("*").order("ordem").execute()
    produtos = sorted(result.data or [], key=lambda p: (p.get("ordem") or 0, str(p.get("nome", ""))))
    return _com_nome_do_dono(supabase, produtos)


@router.post("/produtos", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
async def criar_produto(
    payload: ProdutoCreatePayload,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Cria Produto. Nasce ativo, e ativo exige dono."""
    nome = _normalizar_nome(payload.nome)
    if not nome:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nome do Produto nao pode ser vazio.",
        )
    _exigir_dono_no_produto_ativo(ativo=True, dono_id=payload.dono_id)
    if payload.dono_id:
        _exigir_dono_com_acesso(supabase, payload.dono_id)
    _exigir_nome_livre(supabase, nome)

    novo = {
        "nome": nome,
        "ativo": True,
        "dono_id": payload.dono_id,
        "ordem": payload.ordem if payload.ordem is not None else 0,
    }
    result = supabase.table(TABELA_PRODUTOS).insert(novo).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao criar o Produto",
        )
    return _com_nome_do_dono(supabase, [result.data[0]])[0]


@router.patch("/produtos/{produto_id}", response_model=ProdutoResponse)
async def atualizar_produto(
    produto_id: str,
    payload: ProdutoUpdatePayload,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Renomeia, ativa, desativa, troca o dono e a ordem.

    A regra do dono vale sobre o RESULTADO da edicao, nao sobre o campo que
    veio no corpo: desativar o dono e manter o Produto ativo e a mesma recusa
    que criar ativo sem dono.
    """
    atual = _buscar_produto(supabase, produto_id)
    informados = payload.model_fields_set
    mudancas: dict = {}

    if "nome" in informados and payload.nome is not None:
        nome = _normalizar_nome(payload.nome)
        if not nome:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nome do Produto nao pode ser vazio.",
            )
        if nome.lower() != str(atual.get("nome", "")).strip().lower():
            _exigir_nome_livre(supabase, nome, exceto_id=produto_id)
        mudancas["nome"] = nome

    ativo = payload.ativo if ("ativo" in informados and payload.ativo is not None) else bool(atual.get("ativo"))
    dono_id = payload.dono_id if "dono_id" in informados else atual.get("dono_id")

    _exigir_dono_no_produto_ativo(ativo=ativo, dono_id=dono_id)
    if "dono_id" in informados and payload.dono_id:
        _exigir_dono_com_acesso(supabase, payload.dono_id)

    if "ativo" in informados and payload.ativo is not None:
        mudancas["ativo"] = payload.ativo
    if "dono_id" in informados:
        mudancas["dono_id"] = payload.dono_id
    if "ordem" in informados and payload.ordem is not None:
        mudancas["ordem"] = payload.ordem

    if not mudancas:
        return _com_nome_do_dono(supabase, [atual])[0]

    result = supabase.table(TABELA_PRODUTOS).update(mudancas).eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto nao encontrado")
    return _com_nome_do_dono(supabase, [result.data[0]])[0]
