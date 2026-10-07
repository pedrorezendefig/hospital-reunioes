"""A ponte com o desenvolvimento (issue #1063, ADR 0069, decisão 2).

Quem desenvolve a Demanda busca os prints pelo app, por uma boca só: o script
`.claude/skills/pegar-issue/scripts/anexos.py` lê o id da Demanda no marcador da
issue e chama esta rota. Os anexos nunca vão para o GitHub (o repositório é
público); daqui sai só a URL assinada de vida curta de cada um.

Autenticação por chave de serviço própria (`X-API-Key` contra
`TECNOLOGIA_AUTOMACAO_API_KEY`), fora do fluxo JWT, no molde da API da Ana.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_supabase_client, require_tecnologia_automacao_api_key
from app.services import tecnologia_anexos

router = APIRouter(
    prefix="/automacao/tecnologia",
    tags=["automacao"],
    dependencies=[Depends(require_tecnologia_automacao_api_key)],
)


@router.get("/demandas/{demanda_id}/anexos")
def anexos_da_demanda(demanda_id: UUID, supabase=Depends(get_supabase_client)) -> dict:
    """Nome, tipo e URL assinada de cada anexo não apagado da Demanda.

    O id é UUID na assinatura: lixo no caminho vira 422 aqui, e não 500 no
    PostgREST. Demanda sem anexo, ou que não existe, devolve a lista vazia.
    """
    return {"anexos": tecnologia_anexos.para_quem_desenvolve(supabase, str(demanda_id))}
