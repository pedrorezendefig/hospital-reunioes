"""Router /admin/tecnologia, a aba Tecnologia (issues #636 e #637, PRD #634).

Todos os endpoints exigem `require_super_admin`. Esse e o gate de verdade: a
sidebar apenas esconde o item, e esconder nao e proteger (ADR 0050, decisao 2).

Produto (issue #636):

- GET   /admin/tecnologia/pessoas               quem tem acesso a aba.
- GET   /admin/tecnologia/produtos              lista os Produtos.
- POST  /admin/tecnologia/produtos              cria Produto.
- PATCH /admin/tecnologia/produtos/{id}         renomeia, ativa, desativa,
                                                troca o dono e a ordem.

Demanda e Conversa (issue #637):

- GET   /admin/tecnologia/demandas              o Quadro, com filtros por
                                                estado, tipo, Produto e
                                                responsavel.
- POST  /admin/tecnologia/demandas              abre a Demanda (nasce em
                                                `nova`, com o dono do Produto).
- PATCH /admin/tecnologia/demandas/{id}         edita os campos do modal.
- POST  /admin/tecnologia/demandas/{id}/mover   anda pela maquina de estados.
- POST  /admin/tecnologia/demandas/{id}/atribuir troca o responsavel.
- GET   /admin/tecnologia/demandas/{id}/conversa o fio, so leitura nesta fatia.

Mover e atribuir sao portas separadas do PATCH de proposito: sao as duas
mudancas que gravam linha automatica na Conversa, e um PATCH que tambem as
aceitasse moveria a Demanda sem deixar rastro no fio.

Nao existe DELETE: desativar (Produto) e cancelar (Demanda) sao as saidas
(ADR 0050, decisao 11). A linha continua no banco.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.dependencies import get_supabase_client, require_super_admin
from app.models.tecnologia_schemas import (
    AtribuirPayload,
    ConversaLinhaResponse,
    DemandaCreatePayload,
    DemandaResponse,
    DemandaUpdatePayload,
    MoverPayload,
    PessoaDaAba,
    ProdutoCreatePayload,
    ProdutoResponse,
    ProdutoUpdatePayload,
)
from app.services.tecnologia import (
    MOTIVO_DONO_SEM_ACESSO,
    MOTIVO_PRODUTO_ATIVO_SEM_DONO,
    MOTIVO_PRODUTO_INATIVO,
    MOTIVO_PRODUTO_SEM_DONO,
    MOTIVO_RESPONSAVEL_SEM_ACESSO,
    carimbos_da_transicao,
    e_pessoa_da_aba,
    edicao_deixa_produto_ativo_sem_dono,
    motivo_transicao_invalida,
    produto_ativo_sem_dono,
    texto_movimento_estado,
    texto_movimento_responsavel,
    transicao_permitida,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tecnologia", tags=["admin", "tecnologia"])

TABELA_PRODUTOS = "tecnologia_produtos"
TABELA_DEMANDAS = "tecnologia_demandas"
TABELA_CONVERSAS = "tecnologia_conversas"

# O que a lista de pessoas precisa ler do participante. `ativo` e
# `access_profile`/`is_super_admin` entram porque o filtro roda em Python: um
# `.eq("ativo", True)` no PostgREST descartaria as linhas com `ativo` NULL.
_CAMPOS_PESSOA = "id, nome_completo, email, ativo, is_super_admin, access_profile"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _pessoas_da_aba(supabase: Client) -> list[dict]:
    """Participantes ativos com Super admin, em ordem de nome."""
    result = supabase.table("participantes").select(_CAMPOS_PESSOA).order("nome_completo").execute()
    return [linha for linha in (result.data or []) if e_pessoa_da_aba(linha)]


def _recusar(motivo: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=motivo)


def _normalizar_nome(nome: str) -> str:
    return " ".join(nome.strip().split())


def _normalizar_dono(dono_id: str | None) -> str | None:
    """String vazia vira NULL.

    `""` passa pelas duas guardas do dono (e falsy, entao nao e "sem dono
    escolhido" nem "dono a conferir") e chegaria ao banco como texto vazio, que
    nao existe em `participantes(id)`: violacao de chave estrangeira, 500. Quem
    manda `dono_id` vazio esta dizendo "sem dono", e e isso que se grava.
    """
    if dono_id is None:
        return None
    limpo = dono_id.strip()
    return limpo or None


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
        _recusar(MOTIVO_DONO_SEM_ACESSO)


def _exigir_dono_no_produto_novo(dono_id: str | None) -> None:
    """Produto nasce ativo, e ativo exige dono."""
    if produto_ativo_sem_dono(ativo=True, dono_id=dono_id):
        _recusar(MOTIVO_PRODUTO_ATIVO_SEM_DONO)


def _proxima_ordem(supabase: Client) -> int:
    """O Produto novo entra no fim da lista.

    Sem isto o novo nasceria com ordem 0 e apareceria na frente dos sete do
    seed (ordem 1 a 7), que e o contrario do que quem acabou de criar espera.
    """
    result = supabase.table(TABELA_PRODUTOS).select("ordem").execute()
    ordens = [linha.get("ordem") or 0 for linha in (result.data or [])]
    return (max(ordens) + 1) if ordens else 1


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
        _recusar("Nome do Produto nao pode ser vazio.")
    dono_id = _normalizar_dono(payload.dono_id)
    _exigir_dono_no_produto_novo(dono_id)
    if dono_id:
        _exigir_dono_com_acesso(supabase, dono_id)
    _exigir_nome_livre(supabase, nome)

    novo = {
        "nome": nome,
        "ativo": True,
        "dono_id": dono_id,
        "ordem": payload.ordem if payload.ordem is not None else _proxima_ordem(supabase),
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

    A regra do dono olha o antes e o depois: recusa a edicao que DEIXA o
    Produto ativo sem dono, e nao a que apenas o encontra assim. Os sete
    Produtos do seed nascem ativos e sem dono, e renomear um deles nao e o
    ato que os deixou sem ninguem.
    """
    atual = _buscar_produto(supabase, produto_id)
    informados = payload.model_fields_set
    mudancas: dict = {}

    if "nome" in informados and payload.nome is not None:
        nome = _normalizar_nome(payload.nome)
        if not nome:
            _recusar("Nome do Produto nao pode ser vazio.")
        if nome.lower() != str(atual.get("nome", "")).strip().lower():
            _exigir_nome_livre(supabase, nome, exceto_id=produto_id)
        mudancas["nome"] = nome

    ativo = payload.ativo if ("ativo" in informados and payload.ativo is not None) else bool(atual.get("ativo"))
    dono_id = _normalizar_dono(payload.dono_id) if "dono_id" in informados else atual.get("dono_id")

    if edicao_deixa_produto_ativo_sem_dono(
        antes_ativo=bool(atual.get("ativo")),
        antes_dono=atual.get("dono_id"),
        depois_ativo=ativo,
        depois_dono=dono_id,
    ):
        _recusar(MOTIVO_PRODUTO_ATIVO_SEM_DONO)
    if "dono_id" in informados and dono_id:
        _exigir_dono_com_acesso(supabase, dono_id)

    if "ativo" in informados and payload.ativo is not None:
        mudancas["ativo"] = payload.ativo
    if "dono_id" in informados:
        mudancas["dono_id"] = dono_id
    if "ordem" in informados and payload.ordem is not None:
        mudancas["ordem"] = payload.ordem

    if not mudancas:
        return _com_nome_do_dono(supabase, [atual])[0]

    result = supabase.table(TABELA_PRODUTOS).update(mudancas).eq("id", produto_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto nao encontrado")
    return _com_nome_do_dono(supabase, [result.data[0]])[0]


# ─── Demanda: helpers ────────────────────────────────────────────────────────


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _buscar_demanda(supabase: Client, demanda_id: str) -> dict:
    result = supabase.table(TABELA_DEMANDAS).select("*").eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")
    return result.data[0]


def _nomes_de_participantes(supabase: Client, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    result = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute()
    return {linha["id"]: linha.get("nome_completo") for linha in (result.data or [])}


def _com_nomes(supabase: Client, demandas: list[dict]) -> list[dict]:
    """Resolve `produto_nome` e `responsavel_nome` em duas consultas, para toda
    a lista de uma vez: o card mostra os dois, e a tela nao cruza tabela."""
    produtos_ids = {d["produto_id"] for d in demandas if d.get("produto_id")}
    nomes_produto: dict[str, str] = {}
    if produtos_ids:
        result = supabase.table(TABELA_PRODUTOS).select("id, nome").in_("id", sorted(produtos_ids)).execute()
        nomes_produto = {linha["id"]: linha.get("nome") for linha in (result.data or [])}

    nomes_pessoa = _nomes_de_participantes(supabase, {d["responsavel_id"] for d in demandas if d.get("responsavel_id")})

    return [
        {
            **d,
            "produto_nome": nomes_produto.get(d.get("produto_id")),
            "responsavel_nome": nomes_pessoa.get(d.get("responsavel_id")),
        }
        for d in demandas
    ]


def _normalizar_prazo(valor: str | None) -> str | None:
    """Texto vazio vira NULL; o resto tem que ser uma data ISO de verdade.

    `""` nao e NULL: numa coluna DATE ele vira erro de banco, ou seja 500 com
    cara de defeito nosso, quando o que houve foi a pessoa apagar o campo. E
    uma data escrita ao contrario ("01/10/2026") tem que voltar como 422 com o
    formato certo, e nao como erro do Postgres.
    """
    if valor is None:
        return None
    limpo = valor.strip()
    if not limpo:
        return None
    try:
        return date.fromisoformat(limpo).isoformat()
    except ValueError:
        _recusar("Prazo precisa estar no formato AAAA-MM-DD.")


def _gravar_movimento(
    supabase: Client,
    *,
    demanda_id: str,
    campo: str,
    de: str | None,
    para: str,
    texto: str,
) -> None:
    """A linha automatica do fio, na mesma operacao do movimento.

    Sem autor: quem moveu esta no `texto`, que o backend monta (o de/para
    estruturado fica nas colunas ao lado, para quem for ler por programa).
    """
    supabase.table(TABELA_CONVERSAS).insert(
        {
            "demanda_id": demanda_id,
            "autor_id": None,
            "linha": "movimento",
            "texto": texto,
            "mencoes": [],
            "movimento_campo": campo,
            "movimento_de": de,
            "movimento_para": para,
        }
    ).execute()


# ─── Demanda: endpoints ──────────────────────────────────────────────────────


@router.get("/demandas", response_model=list[DemandaResponse])
async def listar_demandas(
    estado: str | None = None,
    tipo: str | None = None,
    produto_id: str | None = None,
    responsavel_id: str | None = None,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """As Demandas do Quadro, com os filtros da PRD.

    Sem filtro vem tudo, as cinco colunas: quem monta o Quadro e a tela, numa
    chamada so. Os filtros existem desde ja porque a API e a mesma para a tela
    de filtros da fatia seguinte.

    Ordem por `criado_em` crescente: dentro da coluna, a mais velha aparece
    primeiro, que e a que o cartao de idade cobra.
    """
    consulta = supabase.table(TABELA_DEMANDAS).select("*")
    for coluna, valor in (
        ("estado", estado),
        ("tipo", tipo),
        ("produto_id", produto_id),
        ("responsavel_id", responsavel_id),
    ):
        if valor:
            consulta = consulta.eq(coluna, valor)
    result = consulta.order("criado_em").execute()
    return _com_nomes(supabase, list(result.data or []))


@router.post("/demandas", response_model=DemandaResponse, status_code=status.HTTP_201_CREATED)
async def criar_demanda(
    payload: DemandaCreatePayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Abre uma Demanda: ela nasce em `nova`, com o dono do Produto.

    O responsavel nao vem do payload de proposito (ADR 0050, decisao 4): o
    Produto e que diz quem responde por ele, e por isso Produto sem dono ou
    inativo e recusado aqui, e nao depois, com a Demanda ja orfa no quadro.
    """
    produto = _buscar_produto(supabase, payload.produto_id)
    if not produto.get("ativo"):
        _recusar(MOTIVO_PRODUTO_INATIVO)
    dono_id = produto.get("dono_id")
    if not dono_id:
        _recusar(MOTIVO_PRODUTO_SEM_DONO)

    titulo = payload.titulo.strip()
    if not titulo:
        _recusar("Título da Demanda não pode ser vazio.")
    descricao = (payload.descricao or "").strip() or None

    nova = {
        "titulo": titulo,
        "descricao": descricao,
        "tipo": payload.tipo,
        "produto_id": produto["id"],
        "estado": "nova",
        "responsavel_id": dono_id,
        "autor_id": ator["id"],
        "prioridade": payload.prioridade,
        "prazo": _normalizar_prazo(payload.prazo),
    }
    result = supabase.table(TABELA_DEMANDAS).insert(nova).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao criar a Demanda",
        )
    return _com_nomes(supabase, [result.data[0]])[0]


@router.patch("/demandas/{demanda_id}", response_model=DemandaResponse)
async def atualizar_demanda(
    demanda_id: str,
    payload: DemandaUpdatePayload,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Edita os campos do modal. Campo ausente fica como esta.

    O Produto novo so precisa existir. A regra "Produto inativo nao recebe
    Demanda" e da CRIACAO: cobra-la aqui congelaria toda Demanda que ja mora
    num Produto desativado depois, e desativar um Produto passaria a esconder
    o historico dele em vez de so tira-lo da escolha (ADR 0050, decisao 11).
    """
    atual = _buscar_demanda(supabase, demanda_id)
    informados = payload.model_fields_set
    mudancas: dict = {}

    if "titulo" in informados and payload.titulo is not None:
        titulo = payload.titulo.strip()
        if not titulo:
            _recusar("Título da Demanda não pode ser vazio.")
        mudancas["titulo"] = titulo
    if "descricao" in informados:
        mudancas["descricao"] = (payload.descricao or "").strip() or None
    if "tipo" in informados and payload.tipo is not None:
        mudancas["tipo"] = payload.tipo
    if "prioridade" in informados and payload.prioridade is not None:
        mudancas["prioridade"] = payload.prioridade
    if "prazo" in informados:
        mudancas["prazo"] = _normalizar_prazo(payload.prazo)
    if "produto_id" in informados and payload.produto_id:
        mudancas["produto_id"] = _buscar_produto(supabase, payload.produto_id)["id"]

    if not mudancas:
        return _com_nomes(supabase, [atual])[0]

    result = supabase.table(TABELA_DEMANDAS).update(mudancas).eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")
    return _com_nomes(supabase, [result.data[0]])[0]


@router.post("/demandas/{demanda_id}/mover", response_model=DemandaResponse)
async def mover_demanda(
    demanda_id: str,
    payload: MoverPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Move a Demanda de coluna, se a maquina de estados permitir.

    Concluir e cancelar carimbam data e pessoa; reabrir limpa os carimbos. A
    linha de movimento sai na mesma operacao: sem ela, o quadro mudaria sem
    ninguem saber quem mexeu.
    """
    atual = _buscar_demanda(supabase, demanda_id)
    de = str(atual.get("estado") or "")
    para = payload.estado
    if not transicao_permitida(de, para):
        _recusar(motivo_transicao_invalida(de, para))

    mudancas: dict = {"estado": para}
    mudancas.update(carimbos_da_transicao(para=para, ator_id=ator["id"], agora=_agora()))

    result = supabase.table(TABELA_DEMANDAS).update(mudancas).eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")

    _gravar_movimento(
        supabase,
        demanda_id=demanda_id,
        campo="estado",
        de=de,
        para=para,
        texto=texto_movimento_estado(autor_nome=ator.get("nome_completo") or "Alguém", para=para),
    )
    return _com_nomes(supabase, [result.data[0]])[0]


@router.post("/demandas/{demanda_id}/atribuir", response_model=DemandaResponse)
async def atribuir_demanda(
    demanda_id: str,
    payload: AtribuirPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Troca o responsavel, entre as pessoas com acesso a aba.

    Repassar para quem nao ve a aba entregaria a Demanda a alguem que nao pode
    abri-la, e ela ficaria parada sem ninguem saber por que.
    """
    atual = _buscar_demanda(supabase, demanda_id)
    novo_id = payload.responsavel_id.strip()

    pessoas = {p["id"]: p for p in _pessoas_da_aba(supabase)}
    if novo_id not in pessoas:
        _recusar(MOTIVO_RESPONSAVEL_SEM_ACESSO)

    de = atual.get("responsavel_id")
    if de == novo_id:
        # Nada mudou: gravar linha de movimento aqui encheria o fio de
        # "atribuiu a Fulano" sempre que alguem reabrisse o seletor.
        return _com_nomes(supabase, [atual])[0]

    result = supabase.table(TABELA_DEMANDAS).update({"responsavel_id": novo_id}).eq("id", demanda_id).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demanda nao encontrada")

    _gravar_movimento(
        supabase,
        demanda_id=demanda_id,
        campo="responsavel",
        de=de,
        para=novo_id,
        texto=texto_movimento_responsavel(
            autor_nome=ator.get("nome_completo") or "Alguém",
            para_nome=pessoas[novo_id].get("nome_completo") or novo_id,
        ),
    )
    return _com_nomes(supabase, [result.data[0]])[0]


@router.get("/demandas/{demanda_id}/conversa", response_model=list[ConversaLinhaResponse])
async def listar_conversa(
    demanda_id: str,
    _ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O fio da Demanda em ordem cronologica, respostas e movimentos juntos.

    So leitura nesta fatia: responder no card e da issue #638.
    """
    _buscar_demanda(supabase, demanda_id)
    result = supabase.table(TABELA_CONVERSAS).select("*").eq("demanda_id", demanda_id).order("criado_em").execute()
    linhas = list(result.data or [])
    nomes = _nomes_de_participantes(supabase, {linha["autor_id"] for linha in linhas if linha.get("autor_id")})
    return [{**linha, "autor_nome": nomes.get(linha.get("autor_id"))} for linha in linhas]
