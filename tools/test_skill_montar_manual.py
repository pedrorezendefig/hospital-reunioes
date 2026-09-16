"""A `/montar-manual` combina com a `/manual` que existe de verdade.

A `/montar-manual` não produz nada: ela escreve prompts que outro terminal cola.
Prompt que chama um modo inexistente ou um conferidor com outro nome só falha
lá na frente, no terminal do Pedro. Estes testes leem as duas skills e provam,
aqui, que o que o prompt manda rodar existe (issue #737).
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MONTAR = RAIZ / ".claude" / "skills" / "montar-manual" / "SKILL.md"
MANUAL = RAIZ / ".claude" / "skills" / "manual" / "SKILL.md"

TEXTO_MONTAR = MONTAR.read_text(encoding="utf-8")
TEXTO_MANUAL = MANUAL.read_text(encoding="utf-8")

# Teto da descrição de skill: acima disso o carregador corta e o roteamento
# passa a decidir por meia frase (critério de aceite da #737).
TETO_DA_DESCRICAO = 200


def sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def descricao(texto: str) -> str:
    return re.search(r"^description: (.+)$", texto, re.M).group(1)


def modos_declarados() -> set[str]:
    """Os modos da tabela "Três modos" da `/manual`."""
    return {
        sem_acento(m.group(1))
        for m in re.finditer(r"^\| `/manual ([^`]+)` \|", TEXTO_MANUAL, re.M)
    }


def test_descricao_cabe_no_teto():
    assert len(descricao(TEXTO_MONTAR)) <= TETO_DA_DESCRICAO


def test_todo_modo_da_manual_que_o_plano_chama_existe():
    citados = {
        sem_acento(m.group(1)) for m in re.finditer(r"`/manual ([^`]+)`", TEXTO_MONTAR)
    }
    assert citados, "o plano precisa dizer que modo da /manual cada terminal roda"
    assert citados <= modos_declarados()


def test_o_checklist_que_o_prompt_manda_rodar_e_o_da_manual():
    """Conferidor renomeado na `/manual` não pode sobreviver aqui colado."""
    bloco = re.search(
        r"## Antes de entregar\n+```bash\n(.*?)```", TEXTO_MANUAL, re.S
    ).group(1)
    comandos = [linha.strip() for linha in bloco.splitlines() if linha.strip()]
    assert len(comandos) == 4
    for comando in comandos:
        assert comando in TEXTO_MONTAR, comando


def ignorados(caminhos: list[str]) -> set[str]:
    """Caminho que o repositório ignora de propósito (MP4 renderizado, dist)."""
    if not caminhos:
        return set()
    saida = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(caminhos),
        capture_output=True,
        text=True,
        cwd=RAIZ,
    ).stdout
    return {linha.strip() for linha in saida.splitlines() if linha.strip()}


def test_todo_caminho_do_repo_que_as_skills_citam_existe():
    """Pasta e script citados são os do repositório, não de memória.

    Vale para as duas skills, references incluídas: é lá que a receita da
    `/manual` chama os conferidores pelo nome, e renomear um sem mexer no texto
    deixaria a receita mandando rodar script que não existe.
    """
    citados: set[str] = set()
    for skill in ("manual", "montar-manual"):
        for md in sorted((RAIZ / ".claude" / "skills" / skill).rglob("*.md")):
            citados |= {
                m.group(1)
                for m in re.finditer(
                    r"`?((?:tools|docs/manual|docs/spec)/[\w./<>-]+)",
                    md.read_text(encoding="utf-8"),
                )
            }
    # Molde por módulo ou por slug: quem confere esses é o teste dos modos.
    # A barra final vai para o `check-ignore` como está citada: `public/video/`
    # só casa o padrão do .gitignore com ela, porque a pasta nem existe no clone.
    concretos = sorted(c.rstrip(".") for c in citados if "<" not in c)
    fora_do_git = ignorados(concretos)
    conferidos = [c.rstrip("/") for c in concretos if c not in fora_do_git]
    # Piso de sanidade: sem ele, reescrever o texto de um jeito que a regex não
    # reconhece deixaria este teste verde sobre lista vazia.
    assert len(conferidos) >= 5
    assert [c for c in conferidos if not (RAIZ / c).exists()] == []


def prompt_gerado() -> str:
    """O template do prompt que a skill manda o Pedro colar no terminal."""
    blocos = re.findall(r"^```[a-z]*\n(.*?)^```", TEXTO_MONTAR, re.S | re.M)
    prompts = [b for b in blocos if "/manual <modulo>" in b]
    assert len(prompts) == 1, "o plano tem um template de prompt de terminal"
    return prompts[0]


def test_o_prompt_abre_o_worktree_antes_de_criar_branch():
    """Branch criada na árvore principal é a colisão que esta skill evita."""
    prompt = prompt_gerado()
    assert prompt.index("worktree") < prompt.index("/pegar-issue")


def test_o_prompt_manda_carimbar_o_prd_no_frontmatter_de_novidades():
    """Sem o `prd:` no novidades.md, o inventário acusa a entrada que já existe."""
    prompt = prompt_gerado()
    linha = next(li for li in prompt.splitlines() if "Novidades" in li)
    assert "prd:" in linha


def test_os_cinco_modulos_do_plano_sao_os_da_manual():
    import inventario_manual

    for modulo in inventario_manual.MODULOS:
        assert f"`{modulo}`" in TEXTO_MANUAL or modulo in TEXTO_MANUAL
        assert modulo in TEXTO_MONTAR
