"""Contas médicas (PRD #1113, ADR 0070): confere a conta de internação antes
do envio à operadora.

Esta é a fundação (issue #1114): o eixo de permissão e a rota que diz à pessoa
o que ela pode fazer no módulo. As rotas de envio, fila, Guia e operadoras
chegam nas fatias seguintes, cada uma atrás de `require_permissao_cm`.
"""

from fastapi import APIRouter, Depends, Request

from app.dependencies import require_permissao_cm
from app.limiter import limiter

router = APIRouter(prefix="/contas-medicas", tags=["contas-medicas"])


@router.get("/me")
@limiter.limit("60/minute")
async def minhas_permissoes(request: Request, me: dict = Depends(require_permissao_cm())) -> dict:
    """O perfil de Contas médicas da pessoa e as permissões ligadas para ela.

    É o que a tela usa para decidir o que mostrar; quem decide o acesso de
    verdade é o gate de cada rota. Quem não tem o eixo recebe 403 aqui.
    """
    return {"perfil": me.get("perfil_contas_medicas"), "permissoes": me["permissoes_cm"]}
