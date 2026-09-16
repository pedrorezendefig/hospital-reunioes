"""A máquina que vai publicar o Manual é conferida antes, não no erro de build.

O site do manual é Starlight 0.42, que exige Node >= 22.12; o vídeo de tarefa
precisa de `ffmpeg` e o Roteiro de prints, de Playwright. Estes testes provam
que o diagnóstico do `/setup-maquina` acusa isso (issue #735), e que ele compara
versão por número: `22.9` é menor que `22.12`, embora venha depois no alfabeto.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tirar_draft_manual  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "setup-maquina" / "scripts" / "diagnostico.sh"
SKILL = RAIZ / ".claude" / "skills" / "setup-maquina" / "SKILL.md"

TEXTO = SCRIPT.read_text(encoding="utf-8")
NODE_MIN = "22.12"  # Starlight 0.42 (ADR 0057); a fonte é o CI do Manual


def funcao(nome: str) -> str:
    """O corpo da função tal como está no script, para rodar isolada."""
    achado = re.search(rf"^{nome}\(\) \{{.*?^\}}", TEXTO, re.S | re.M)
    assert achado, f"o script não tem mais a função {nome}()"
    return achado.group(0)


def compara(atual: str, minima: str) -> int:
    return subprocess.run(
        ["bash", "-c", f'{funcao("versao_min")}\nversao_min "{atual}" "{minima}"'],
    ).returncode


def test_versao_e_comparada_por_numero_nao_por_texto():
    assert compara("22.12.0", NODE_MIN) == 0
    assert compara("24.1.0", NODE_MIN) == 0
    assert compara(NODE_MIN, NODE_MIN) == 0
    # O mutante clássico: `sort` sem -V põe 22.9 depois de 22.12 e aprova.
    assert compara("22.9.0", NODE_MIN) != 0
    assert compara("20.11.1", NODE_MIN) != 0


def diagnostico(tmp_path: Path, versao_do_node: str, nivel: str = "4") -> str:
    """Roda o diagnóstico inteiro com um `node` de mentira no PATH."""
    falso = tmp_path / "bin"
    falso.mkdir(exist_ok=True)
    node = falso / "node"
    node.write_text(f'#!/bin/sh\necho "v{versao_do_node}"\n', encoding="utf-8")
    node.chmod(0o755)
    ambiente = dict(os.environ, PATH=f"{falso}:{os.environ['PATH']}")
    return subprocess.run(
        ["bash", str(SCRIPT), "--nivel", nivel],
        capture_output=True,
        text=True,
        env=ambiente,
        timeout=300,
    ).stdout


def linha_do_node(saida: str) -> str:
    """A linha do Node do manual, que o nível 3 (app local) não confunde."""
    linhas = [li for li in saida.splitlines() if "(manual)" in li]
    assert len(linhas) == 1, f"esperava uma linha do node do manual: {linhas}"
    return linhas[0]


@pytest.fixture(scope="module")
def com_node_novo(tmp_path_factory) -> str:
    """O diagnóstico roda o script inteiro: vale uma vez para o módulo."""
    return diagnostico(tmp_path_factory.mktemp("node-novo"), NODE_MIN + ".0")


def test_diagnostico_acusa_node_abaixo_do_minimo(tmp_path):
    linha = linha_do_node(diagnostico(tmp_path, "20.11.1"))

    assert "FALTA" in linha
    assert "20.11.1" in linha, "a mensagem diz qual versão a máquina tem"
    assert NODE_MIN in linha, "a mensagem diz qual versão o manual exige"


def test_diagnostico_aceita_o_node_minimo(com_node_novo):
    assert "OK" in linha_do_node(com_node_novo)


def test_o_nivel_4_acrescenta_o_playwright_do_roteiro_de_prints(com_node_novo):
    assert "playwright" in com_node_novo.lower()


def test_o_nivel_do_deploy_ja_exige_o_que_publica_o_manual(tmp_path):
    """O `/deploy ship` publica o Manual: Node, corepack e ffmpeg são nível 2.

    Deixá-los no nível 4 ("opcional") faria quem segue a skill deployar, tirar
    o draft e travar no build, com a página fora do ar e fora do draft.
    """
    saida = diagnostico(tmp_path, "20.11.1", nivel="2")

    assert "FALTA" in linha_do_node(saida)
    assert "corepack" in saida
    assert "ffmpeg" in saida


def test_a_skill_e_o_script_falam_do_mesmo_node():
    """Número na prosa que o script não confere é promessa sem detector."""
    texto = SKILL.read_text(encoding="utf-8")
    assert NODE_MIN in texto
    assert NODE_MIN in TEXTO
    assert re.search(r"Playwright", texto)
    # O script e o conferidor do deploy comparam com o mesmo número: se um
    # subir de versão sozinho, a máquina passa aqui e trava lá.
    assert ".".join(str(n) for n in tirar_draft_manual.NODE_MIN) == NODE_MIN
