"""Router /admin/manual: a aba Ana do manual (issue #1720, ADR 0094, decisão 3).

A aba Ana é o Retrato da Ana, como ele é, lido do repositório privado da Ana
pela integração do GitHub (ADR 0093). Esta rota é um repasse estreito:

- Só Super admin logado (o Retrato mostra o prompt, as chamadas e as
  ferramentas).
- Só sai a página do Retrato: `retrato/index.html`, os arquivos de
  `retrato/assets/` e `retrato/dados/retrato.json`. Caminho com `..`, absoluto
  ou fora dessa lista é recusado antes de qualquer chamada ao GitHub.
- Nada é gravado: nem no repositório do Hospital, que é público, nem em disco.
  Cada pedido lê a branch principal da Ana de novo.

Sem `GITHUB_INTEGRACAO_REPO_ANA`, ou sem acesso ao repositório, a resposta é
503 com a frase que a tela mostra.
"""

from __future__ import annotations

import mimetypes

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies import require_super_admin
from app.services import github_client

router = APIRouter(prefix="/admin/manual", tags=["admin", "manual"])

NAO_LIGADO = "O Retrato da Ana ainda não está ligado"

# O que a página do Retrato carrega, a partir de `retrato/`.
_PAGINA = "index.html"
_DADOS = "dados/retrato.json"
_PASTA_DOS_ARQUIVOS = "assets/"


def caminho_no_retrato(caminho: str) -> str | None:
    """O caminho no repositório da Ana, ou `None` quando ele não é da página.

    Recusa barra no começo, contrabarra e qualquer parte vazia, `.` ou `..`:
    o caminho entra na URL do GitHub e quem o escreve é o navegador.
    """
    if not caminho or caminho.startswith("/") or "\\" in caminho:
        return None
    if any(parte in ("", ".", "..") for parte in caminho.split("/")):
        return None
    if caminho in (_PAGINA, _DADOS) or caminho.startswith(_PASTA_DOS_ARQUIVOS):
        return f"retrato/{caminho}"
    return None


@router.get("/ana/retrato/{caminho:path}")
async def arquivo_do_retrato(caminho: str, _me: dict = Depends(require_super_admin)) -> Response:
    no_repositorio = caminho_no_retrato(caminho)
    if no_repositorio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo fora do Retrato da Ana")
    try:
        conteudo = await anyio.to_thread.run_sync(
            lambda: github_client.ler_arquivo(no_repositorio, projeto=github_client.PROJETO_ANA)
        )
    except github_client.IssueNaoEncontradaError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado no Retrato") from exc
    except (github_client.GithubNaoConfiguradoError, github_client.GithubIndisponivelError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=NAO_LIGADO) from exc
    tipo = mimetypes.guess_type(no_repositorio)[0] or "application/octet-stream"
    return Response(
        content=conteudo,
        media_type=tipo,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
