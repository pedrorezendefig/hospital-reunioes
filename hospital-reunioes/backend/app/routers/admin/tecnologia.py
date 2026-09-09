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
- GET   /admin/tecnologia/demandas/{id}/conversa o fio inteiro.

Mover e atribuir sao portas separadas do PATCH de proposito: sao as duas
mudancas que gravam linha automatica na Conversa, e um PATCH que tambem as
aceitasse moveria a Demanda sem deixar rastro no fio.

Escrita no fio (issue #638):

- POST  /admin/tecnologia/demandas/{id}/conversa        responde no card.
- PATCH /admin/tecnologia/demandas/{id}/conversa/{lid}  corrige a PROPRIA
                                                        resposta, por 10
                                                        minutos.

Nao existe DELETE: desativar (Produto) e cancelar (Demanda) sao as saidas
(ADR 0050, decisao 11), e resposta nao se apaga nunca (PRD #634, historia 29).
A linha continua no banco.
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
    RespostaPayload,
)
from app.services.tecnologia import (
    MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO,
    MOTIVO_DONO_SEM_ACESSO,
    MOTIVO_MENCAO_SEM_ACESSO,
    MOTIVO_PRODUTO_ATIVO_SEM_DONO,
    MOTIVO_PRODUTO_INATIVO,
    MOTIVO_PRODUTO_SEM_DONO,
    MOTIVO_RESPONSAVEL_SEM_ACESSO,
    carimbos_da_transicao,
    e_pessoa_da_aba,
    edicao_deixa_produto_ativo_sem_dono,
    instante_do_banco,
    limite_da_janela_de_edicao,
    mencoes_sem_acesso,
    motivo_edicao_recusada,
    motivo_resposta_invalida,
    motivo_transicao_invalida,
    normalizar_mencoes,
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


LIMITE_TITULO = 200


def _titulo_valido(bruto: str) -> str:
    """O titulo limpo, ou 422 com frase de gente nos DOIS limites.

    Vazio e "grande demais" saem daqui, e nao do pydantic, pelo mesmo motivo:
    o `detail` do pydantic vem em LISTA, e a tela mostra o JSON cru no alerta
    vermelho. Colar um texto no campo Título passa de 200 caracteres com
    facilidade, entao esse caso e tao comum quanto apagar o campo.
    """
    titulo = bruto.strip()
    if not titulo:
        _recusar("Título da Demanda não pode ser vazio.")
    if len(titulo) > LIMITE_TITULO:
        _recusar(f"Título da Demanda pode ter no máximo {LIMITE_TITULO} caracteres.")
    return titulo


def _fio_incompleto() -> NoReturn:
    """500 honesto: o movimento foi, a linha do fio nao."""
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            "A Demanda mudou, mas a linha do movimento não entrou na Conversa: "
            "o fio desta Demanda ficou incompleto. Recarregue o Quadro para ver o estado atual."
        ),
    )


def _gravar_movimento(
    supabase: Client,
    *,
    demanda_id: str,
    campo: str,
    de: str | None,
    para: str,
    texto: str,
) -> None:
    """A linha automatica do fio, logo depois do movimento.

    Sem autor: quem moveu esta no `texto`, que o backend monta (o de/para
    estruturado fica nas colunas ao lado, para quem for ler por programa).

    NAO e atomico com o movimento, e nao da para fingir que e: sao duas
    chamadas ao PostgREST, que nao tem transacao, e RPC nova esta fora do
    escopo desta fatia. O que da para garantir e que a falha nao passe calada.
    Se o insert nao voltar a linha (recusa do banco, timeout, PostgREST fora),
    o log guarda o identificador e o de/para, e quem clicou recebe 500 com a
    frase honesta: a Demanda MUDOU e o fio ficou incompleto. Dizer "nao deu
    certo" seria mentira, porque o movimento ja esta gravado.

    O log NAO leva o `texto`: ele carrega o nome de quem moveu ("Pedro moveu
    para Aguardando"), e o padrao da casa e logar identificador, nao payload
    (o `ouvidoria_setor.py` loga so o `manifestacao_id`). `demanda_id`, `campo`,
    `de` e `para` dizem a mesma coisa para quem for reconstruir a linha.
    """
    linha = {
        "demanda_id": demanda_id,
        "autor_id": None,
        "linha": "movimento",
        "texto": texto,
        "mencoes": [],
        "movimento_campo": campo,
        "movimento_de": de,
        "movimento_para": para,
    }
    try:
        result = supabase.table(TABELA_CONVERSAS).insert(linha).execute()
    except Exception:
        # `except APIError` nao pegaria o `httpx.HTTPError` que o timeout do
        # PostgREST sobe cru, e aqui qualquer falha tem o mesmo desfecho: a
        # linha nao entrou.
        logger.exception(
            "Falha ao gravar a linha de movimento da Demanda %s (campo=%s, de=%s, para=%s)",
            demanda_id,
            campo,
            de,
            para,
        )
        _fio_incompleto()
    if not result.data:
        logger.error(
            "Linha de movimento nao gravada para a Demanda %s (campo=%s, de=%s, para=%s)",
            demanda_id,
            campo,
            de,
            para,
        )
        _fio_incompleto()


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
    Produto e que diz quem responde por ele, e por isso Produto sem dono,
    inativo, ou com dono que perdeu o acesso a aba e recusado aqui, e nao
    depois, com a Demanda ja orfa no quadro.

    A terceira guarda existe porque `atribuir` recusa exatamente esse estado: o
    dono do Produto pode ter perdido o Super admin DEPOIS de virar dono, e sem
    ela o app criaria por uma porta o que recusa pela outra, deixando o card
    com um responsavel que nao consegue abrir a aba.
    """
    produto = _buscar_produto(supabase, payload.produto_id)
    if not produto.get("ativo"):
        _recusar(MOTIVO_PRODUTO_INATIVO)
    dono_id = produto.get("dono_id")
    if not dono_id:
        _recusar(MOTIVO_PRODUTO_SEM_DONO)
    if dono_id not in {p["id"] for p in _pessoas_da_aba(supabase)}:
        _recusar(MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO)

    titulo = _titulo_valido(payload.titulo)
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
        mudancas["titulo"] = _titulo_valido(payload.titulo)
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
    linha de movimento e gravada logo em seguida: sem ela, o quadro mudaria sem
    ninguem saber quem mexeu.

    O update amarra o estado LIDO (`.eq("estado", de)`), e nao so o id: sem
    isso, duas pessoas movendo o mesmo card ao mesmo tempo passariam as duas
    pela validacao, as duas gravariam, e o fio ganharia duas linhas contando
    historias diferentes. Com a amarra, a segunda nao casa nenhuma linha e leva
    409.
    """
    atual = _buscar_demanda(supabase, demanda_id)
    de = str(atual.get("estado") or "")
    para = payload.estado
    if not transicao_permitida(de, para):
        _recusar(motivo_transicao_invalida(de, para))

    mudancas: dict = {"estado": para}
    mudancas.update(carimbos_da_transicao(para=para, ator_id=ator["id"], agora=_agora()))

    result = supabase.table(TABELA_DEMANDAS).update(mudancas).eq("id", demanda_id).eq("estado", de).execute()
    if not result.data:
        # A frase fala do DESFECHO, e nao da causa nem de onde a Demanda esta.
        # O que o codigo sabe e so isto: o update nao casou linha nenhuma, e
        # portanto o movimento nao aconteceu. Quem moveu, e para onde a Demanda
        # foi parar, o codigo nao viu.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("O Quadro está desatualizado e este movimento não foi feito. Recarregue o Quadro e tente de novo."),
        )

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


# ─── Conversa: helpers ───────────────────────────────────────────────────────


def _com_janela(linha: dict, *, ator_id: str, autor_nome: str | None) -> dict:
    """A linha do fio como a tela a le, com o limite da janela de edicao.

    `editavel_ate` so vem preenchido na PROPRIA resposta de quem esta pedindo:
    e o que permite ao modal desenhar o botao de corrigir sem saber qual
    participante e o usuario logado (o `useAuth` carrega o id do Supabase Auth,
    nao o `participantes.id`).

    O que vai e o INSTANTE em que a janela fecha, e nao um "pode: sim": o modal
    fica aberto enquanto os 10 minutos correm, e um booleano congelado no
    carregamento continuaria oferecendo o botao depois. Quem recusa de verdade
    continua sendo o PATCH.
    """
    editavel_ate = None
    if linha.get("linha") == "resposta" and linha.get("autor_id") == ator_id:
        criado_em = instante_do_banco(linha.get("criado_em"))
        if criado_em is not None:
            editavel_ate = limite_da_janela_de_edicao(criado_em).isoformat()
    return {**linha, "autor_nome": autor_nome, "editavel_ate": editavel_ate}


def _texto_e_mencoes(supabase: Client, payload: RespostaPayload) -> tuple[str, list[str]]:
    """O que vai para a coluna, ja validado, nas DUAS portas de escrita.

    Responder e corrigir passam pelo mesmo funil de proposito: um criterio que
    valesse so no envio deixaria a edicao criar a mencao que o envio recusa.

    A lista de pessoas so e consultada quando ha mencao: sem isso, toda
    resposta pagaria uma leitura da tabela de participantes para nada.
    """
    motivo = motivo_resposta_invalida(payload.texto)
    if motivo:
        _recusar(motivo)
    mencoes = normalizar_mencoes(payload.mencoes)
    if mencoes and mencoes_sem_acesso(mencoes, {p["id"] for p in _pessoas_da_aba(supabase)}):
        _recusar(MOTIVO_MENCAO_SEM_ACESSO)
    return payload.texto.strip(), mencoes


def _resposta_nao_entrou() -> NoReturn:
    """500 honesto: a pessoa falou e o fio nao guardou.

    Devolver 201 com a linha que nao entrou faria quem escreveu achar que
    respondeu, e o outro lado nunca leria.
    """
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            "A sua resposta não entrou na Conversa desta Demanda. Copie o texto, recarregue o Quadro e envie de novo."
        ),
    )


# ─── Conversa: endpoints ─────────────────────────────────────────────────────


@router.get("/demandas/{demanda_id}/conversa", response_model=list[ConversaLinhaResponse])
async def listar_conversa(
    demanda_id: str,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """O fio da Demanda em ordem cronologica, respostas e movimentos juntos."""
    _buscar_demanda(supabase, demanda_id)
    result = supabase.table(TABELA_CONVERSAS).select("*").eq("demanda_id", demanda_id).order("criado_em").execute()
    linhas = list(result.data or [])
    nomes = _nomes_de_participantes(supabase, {linha["autor_id"] for linha in linhas if linha.get("autor_id")})
    return [_com_janela(linha, ator_id=ator["id"], autor_nome=nomes.get(linha.get("autor_id"))) for linha in linhas]


@router.post(
    "/demandas/{demanda_id}/conversa",
    response_model=ConversaLinhaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def responder_na_conversa(
    demanda_id: str,
    payload: RespostaPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Responde dentro do card: uma linha `resposta`, assinada por quem escreve.

    Responder nao move a Demanda nem troca o responsavel: falar e falar, e as
    portas de `mover` e `atribuir` continuam sendo as unicas que mexem no
    quadro.
    """
    _buscar_demanda(supabase, demanda_id)
    texto, mencoes = _texto_e_mencoes(supabase, payload)

    nova = {
        "demanda_id": demanda_id,
        "autor_id": ator["id"],
        "linha": "resposta",
        "texto": texto,
        "mencoes": mencoes,
        "movimento_campo": None,
        "movimento_de": None,
        "movimento_para": None,
        "editado_em": None,
    }
    try:
        result = supabase.table(TABELA_CONVERSAS).insert(nova).execute()
    except Exception:
        # `except APIError` nao pegaria o `httpx.HTTPError` que o timeout do
        # PostgREST sobe cru, e aqui qualquer falha tem o mesmo desfecho: a
        # resposta nao entrou. O log leva o identificador, nao o texto.
        logger.exception("Falha ao gravar a resposta na Conversa da Demanda %s", demanda_id)
        _resposta_nao_entrou()
    if not result.data:
        logger.error("Resposta nao gravada na Conversa da Demanda %s", demanda_id)
        _resposta_nao_entrou()

    return _com_janela(result.data[0], ator_id=ator["id"], autor_nome=ator.get("nome_completo"))


@router.patch("/demandas/{demanda_id}/conversa/{linha_id}", response_model=ConversaLinhaResponse)
async def editar_resposta(
    demanda_id: str,
    linha_id: str,
    payload: RespostaPayload,
    ator: dict = Depends(require_super_admin),
    supabase: Client = Depends(get_supabase_client),
):
    """Corrige a PROPRIA resposta, dentro da janela de 10 minutos.

    Tres recusas, cada uma com a sua frase (`motivo_edicao_recusada`): linha de
    movimento nao se edita, resposta de outra pessoa nao e sua, e passados os
    10 minutos ela fica como esta. Nao existe porta de apagar: a correcao
    reescreve o texto e carimba `editado_em`, que a tela mostra.

    A busca amarra as DUAS chaves. Procurar so pelo id da linha deixaria quem
    soubesse esse id editar por qualquer card.
    """
    _buscar_demanda(supabase, demanda_id)
    achadas = supabase.table(TABELA_CONVERSAS).select("*").eq("id", linha_id).eq("demanda_id", demanda_id).execute()
    if not achadas.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linha da Conversa nao encontrada")
    linha = achadas.data[0]

    motivo = motivo_edicao_recusada(linha=linha, ator_id=ator["id"], agora=datetime.now(UTC))
    if motivo:
        _recusar(motivo)

    texto, mencoes = _texto_e_mencoes(supabase, payload)
    mudancas = {"texto": texto, "mencoes": mencoes, "editado_em": _agora()}
    try:
        result = (
            supabase.table(TABELA_CONVERSAS).update(mudancas).eq("id", linha_id).eq("demanda_id", demanda_id).execute()
        )
    except Exception:
        logger.exception("Falha ao corrigir a linha %s da Conversa da Demanda %s", linha_id, demanda_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar a correção. Copie o texto, recarregue o Quadro e tente de novo.",
        ) from None
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linha da Conversa nao encontrada")

    return _com_janela(result.data[0], ator_id=ator["id"], autor_nome=ator.get("nome_completo"))
