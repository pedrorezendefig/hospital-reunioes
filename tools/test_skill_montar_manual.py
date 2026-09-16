"""A `/montar-manual` combina com a `/manual` que existe de verdade.

A `/montar-manual` não produz nada: ela escreve prompts que outro terminal cola.
Prompt que chama um modo inexistente ou um conferidor com outro nome só falha
lá na frente, no terminal do Pedro. Estes testes leem as duas skills e provam,
aqui, que o que o prompt manda rodar existe (issue #737).
"""

from __future__ import annotations

import re
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
        sem_acento(m.group(1))
        for m in re.finditer(r"`/manual ([^`]+)`", TEXTO_MONTAR)
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


def test_todo_caminho_do_repo_que_o_plano_cita_existe():
    """Pasta e script citados no prompt são os do repositório, não de memória."""
    citados = {
        m.group(1)
        for m in re.finditer(
            r"`?((?:tools|docs/manual|docs/spec)/[\w./<>-]+)", TEXTO_MONTAR
        )
    }
    faltando = []
    for caminho in sorted(citados):
        if "<" in caminho:  # molde por módulo ou por slug, conferido pelo teste acima
            continue
        if not (RAIZ / caminho.rstrip("/.")).exists():
            faltando.append(caminho)
    assert faltando == []


def test_os_cinco_modulos_do_plano_sao_os_da_manual():
    import inventario_manual

    for modulo in inventario_manual.MODULOS:
        assert f"`{modulo}`" in TEXTO_MANUAL or modulo in TEXTO_MANUAL
        assert modulo in TEXTO_MONTAR
