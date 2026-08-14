"""Router /admin/dados-atendimento — módulo Dados do Atendimento (ADR 0031).

CRUD das quatro tabelas de valores que alimentam a Ana (consultas
particulares, exames, estimativas de cirurgias, convênios por especialidade).

Autorização por papel (padrão do backend, regras em Python):
- Leitura: qualquer papel do contexto Reuniões (facilitador consulta).
- Escrita: super admin ou secretária.

A edição reflete imediatamente nos endpoints da API da Ana: leitura direta
do banco, sem cache. Não há DELETE: desativar (PATCH ativo=false) preserva o
histórico e tira a linha da resposta da Ana.

As quatro tabelas têm o mesmo contrato (listar, criar, editar/desativar), com
colunas próprias; os endpoints são construídos por uma factory dirigida pela
spec de campos de cada tabela (espelho das migrations 061/062).
"""

# Sem `from __future__ import annotations`: os endpoints são closures cujas
# annotations (CreateModel/UpdateModel) o FastAPI precisa resolver em runtime;
# como strings elas não existem no namespace do módulo e virariam query params.
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, create_model
from supabase import Client

from app.dependencies import (
    get_supabase_client,
    require_participante_reunioes,
    require_super_admin_ou_secretaria,
)
from app.services import audit
from app.utils.text_sanitizer import sanitizar_travessao

router = APIRouter(prefix="/admin/dados-atendimento", tags=["admin", "dados-atendimento"])

_OBRIGATORIO = ...


class _TabelaValores:
    """Spec de uma tabela de valores: slug HTTP (mesmo da API da Ana), tabela
    Postgres, ordenação da listagem e campos editáveis (espelho da migration).

    `campos` mapeia nome -> (tipo, default); default `...` marca campo
    obrigatório na criação (NOT NULL sem default no banco).
    """

    def __init__(self, slug: str, table: str, order: list[str], campos: dict[str, tuple]):
        self.slug = slug
        self.table = table
        self.order = order
        self.campos = campos
        self.obrigatorios = {nome for nome, (_, default) in campos.items() if default is _OBRIGATORIO}
        self.create_model = create_model(
            f"Create_{table}",
            **{nome: (tipo, default) for nome, (tipo, default) in campos.items()},
        )
        update_fields: dict = {nome: (tipo | None, None) for nome, (tipo, _) in campos.items()}
        update_fields["ativo"] = (bool | None, None)
        self.update_model = create_model(f"Update_{table}", **update_fields)


_TABELAS = [
    _TabelaValores(
        slug="consultas-particulares",
        table="consultas_particulares",
        order=["especialidade"],
        campos={
            "especialidade": (str, _OBRIGATORIO),
            "valor_rs": (float, _OBRIGATORIO),
            "descricao_servico": (str, _OBRIGATORIO),
            "diferencial_1": (str, ""),
            "diferencial_2": (str, ""),
            "diferencial_3": (str, ""),
            "alta_demanda": (bool, False),
            "observacoes_ana": (str, ""),
        },
    ),
    _TabelaValores(
        slug="exames",
        table="exames",
        order=["nome_exame"],
        campos={
            "nome_exame": (str, _OBRIGATORIO),
            "tipo_exame": (str, _OBRIGATORIO),
            "convenio_aceito": (bool, False),
            "valor_particular_rs": (float, _OBRIGATORIO),
            "requer_pedido_medico": (bool, False),
            "preparo_necessario": (bool, False),
            "instrucoes_preparo_completas": (str, ""),
            "tempo_resultado": (str, ""),
            "local_realizacao": (str, ""),
            "diferencial_1": (str, ""),
            "diferencial_2": (str, ""),
            "observacoes_ana": (str, ""),
        },
    ),
    _TabelaValores(
        slug="cirurgias-estimativas",
        table="cirurgias_estimativas",
        order=["procedimento"],
        campos={
            "procedimento": (str, _OBRIGATORIO),
            "descricao_procedimento": (str, _OBRIGATORIO),
            "honorarios_equipe_rs": (float, _OBRIGATORIO),
            "valor_internacao_rs": (float, _OBRIGATORIO),
            "estimativa_total_rs": (float, _OBRIGATORIO),
            "o_que_inclui_honorarios": (str, ""),
            "o_que_inclui_internacao": (str, ""),
            "diferencial_1": (str, ""),
            "diferencial_2": (str, ""),
            "caveat_obrigatorio_ana": (str, _OBRIGATORIO),
            "observacoes_ana": (str, ""),
        },
    ),
    _TabelaValores(
        slug="convenios-especialidade",
        table="convenios_especialidade",
        order=["convenio", "especialidade"],
        campos={
            "convenio": (str, _OBRIGATORIO),
            "especialidade": (str, _OBRIGATORIO),
            "cobre": (bool, _OBRIGATORIO),
            "observacao": (str, ""),
        },
    ),
]


def _normalizar_texto(config: _TabelaValores, valores: dict) -> dict:
    """Sanitiza tipografia (ADR 0013: o texto chega à conversa da Ana) e
    recusa campo obrigatório vazio."""
    normalizados: dict = {}
    for nome, valor in valores.items():
        if isinstance(valor, str):
            valor = sanitizar_travessao(valor).strip()
            if nome in config.obrigatorios and not valor:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Campo obrigatório não pode ser vazio: {nome}",
                )
        normalizados[nome] = valor
    return normalizados


def _fetch_by_id(supabase: Client, table: str, item_id: str) -> dict:
    result = supabase.table(table).select("*").eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado",
        )
    return result.data[0]


def _register_rotas(config: _TabelaValores) -> None:
    CreateModel: type[BaseModel] = config.create_model  # noqa: N806 — classe pydantic
    UpdateModel: type[BaseModel] = config.update_model  # noqa: N806 — classe pydantic
    table = config.table

    @router.get(f"/{config.slug}", name=f"list_{table}")
    async def _list(
        _me: dict = Depends(require_participante_reunioes),
        supabase: Client = Depends(get_supabase_client),
    ):
        """Lista todas as linhas (ativas e desativadas) e a data da última
        atualização da tabela."""
        query = supabase.table(table).select("*")
        for col in config.order:
            query = query.order(col)
        result = query.execute()
        rows = result.data or []
        datas = [r["ultima_atualizacao"] for r in rows if r.get("ultima_atualizacao")]
        return {
            "data": rows,
            "total": len(rows),
            "ultima_atualizacao": max(datas) if datas else None,
        }

    @router.post(f"/{config.slug}", status_code=status.HTTP_201_CREATED, name=f"create_{table}")
    async def _create(
        payload: CreateModel,
        request: Request,
        actor: dict = Depends(require_super_admin_ou_secretaria),
        supabase: Client = Depends(get_supabase_client),
    ):
        valores = _normalizar_texto(config, payload.model_dump())
        valores["ativo"] = True
        valores["ultima_atualizacao"] = date.today().isoformat()
        try:
            result = supabase.table(table).insert(valores).execute()
        except APIError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registro duplicado ou inválido",
            ) from exc
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao criar registro",
            )
        row = result.data[0]
        audit.log_action(
            supabase,
            actor=actor,
            action=f"{table}_create",
            target_type=table,
            target_id=str(row["id"]),
            metadata={"valores": valores},
            request=request,
        )
        return row

    @router.patch(f"/{config.slug}/{{item_id}}", name=f"update_{table}")
    async def _update(
        item_id: str,
        payload: UpdateModel,
        request: Request,
        actor: dict = Depends(require_super_admin_ou_secretaria),
        supabase: Client = Depends(get_supabase_client),
    ):
        existing = _fetch_by_id(supabase, table, item_id)
        updates = _normalizar_texto(config, payload.model_dump(exclude_unset=True, exclude_none=True))
        if not updates:
            return existing
        updates["ultima_atualizacao"] = date.today().isoformat()
        try:
            result = supabase.table(table).update(updates).eq("id", item_id).execute()
        except APIError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registro duplicado ou inválido",
            ) from exc
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registro não encontrado",
            )
        updated = result.data[0]
        audit.log_action(
            supabase,
            actor=actor,
            action=f"{table}_update",
            target_type=table,
            target_id=str(item_id),
            metadata={
                "antes": {k: existing.get(k) for k in updates},
                "depois": updates,
            },
            request=request,
        )
        return updated


for _config_tabela in _TABELAS:
    _register_rotas(_config_tabela)
