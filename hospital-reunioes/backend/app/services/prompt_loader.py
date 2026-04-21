"""
Loader dinâmico de prompts.

Lê arquivos .md do diretório app/prompts/ e aplica substituição de variáveis
usando a sintaxe {{variavel}}.

Uso:
    from app.services.prompt_loader import load_prompt, render_prompt

    # Carregar prompt sem variáveis
    system_msg = load_prompt("extracao_ata")

    # Carregar e renderizar com variáveis
    user_msg = render_prompt("user_extracao", tipo_reuniao="DGH", hoje_str="01/04/2026", ...)
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Diretório base onde os arquivos .md de prompts residem
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(nome: str) -> str:
    """
    Carrega o conteúdo bruto de um arquivo de prompt.

    Args:
        nome: nome do arquivo sem extensão (ex: "extracao_ata")

    Returns:
        Conteúdo do arquivo .md como string.

    Raises:
        FileNotFoundError: se o arquivo não existir em app/prompts/.
    """
    caminho = PROMPTS_DIR / f"{nome}.md"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo de prompt não encontrado: {caminho}. "
            f"Crie o arquivo em backend/app/prompts/{nome}.md"
        )
    conteudo = caminho.read_text(encoding="utf-8")
    logger.debug(f"[PromptLoader] Carregado: {nome}.md ({len(conteudo)} chars)")
    return conteudo


def render_prompt(nome: str, **kwargs) -> str:
    """
    Carrega e renderiza um prompt substituindo variáveis {{chave}} pelos valores.

    Args:
        nome: nome do arquivo sem extensão (ex: "user_extracao")
        **kwargs: pares chave=valor para substituição de {{chave}} no template.

    Returns:
        Prompt renderizado com as variáveis substituídas.
    """
    template = load_prompt(nome)
    for chave, valor in kwargs.items():
        placeholder = "{{" + chave + "}}"
        template = template.replace(placeholder, str(valor))
    return template
