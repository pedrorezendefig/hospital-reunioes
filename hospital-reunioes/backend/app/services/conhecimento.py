"""Kit de conhecimento do Assistente de Tecnologia (ADR 0056, decisao 2).

Uma pasta de `.md` dentro do app do backend, viajando no deploy junto com o
codigo. Nao e o glossario nem o manual: e uma terceira escrita do mesmo
conhecimento, para outro leitor (o diretor), sem numero de issue, label, nome
de tabela nem vocabulario do repositorio.

O kit inteiro entra no prompt a cada turno (sem RAG, ADR 0056): sao poucos
arquivos e eles cabem na janela do modelo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

CONHECIMENTO_DIR = Path(__file__).parent.parent / "conhecimento"


@lru_cache(maxsize=1)
def carregar_kit() -> str:
    """Todo o kit em um texto so, com o nome do arquivo como cabecalho.

    O cabecalho e o nome do arquivo, e nao o titulo de dentro dele, porque e
    por ele que o assistente cita de onde tirou a resposta e por ele que quem
    cuida do kit acha o arquivo a atualizar.

    Le uma vez por processo (`lru_cache`): os arquivos nao mudam entre um
    request e outro, so entre um deploy e outro.

    Cuidado ao mexer na pasta: TODO `.md` que estiver la dentro vai inteiro
    para o prompt. Ela nao e lugar de README nem de nota para quem programa,
    que o assistente leria como material de consulta e citaria ao diretor.
    """
    partes = [
        f"# {caminho.name}\n\n{caminho.read_text(encoding='utf-8').strip()}"
        for caminho in sorted(CONHECIMENTO_DIR.glob("*.md"))
    ]
    return "\n\n".join(partes)
