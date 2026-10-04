"""A /onda-enxuta exige Claude Code 2.1.280 ou mais (issue #921).

O `lancar_sessao.sh` usa `--bg`, `--strict-mcp-config` e `--effort`, flags que
um Claude Code antigo não conhece. O Nível 2 do `/setup-maquina` promete cobrir
a enxuta, então precisa conferir a versão, não só que o binário existe. Roda a
conferência isolada, com um `claude` de mentira que responde a versão pedida.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from test_setup_maquina_esteira import RAIZ, SAIDAS, TEXTO, falso, funcao, linha


ENXUTA = (RAIZ / ".claude" / "skills" / "onda-enxuta" / "SKILL.md").read_text(encoding="utf-8")


def piso() -> str:
    achado = re.search(r'^CLAUDE_MIN="([0-9.]+)"', TEXTO, re.M)
    assert achado, "o piso vive numa variável CLAUDE_MIN no topo do script"
    return achado.group(1)


def roda_claude(tmp_path: Path, versao: str | None, corpo: str | None = None) -> str:
    """`corpo` substitui o claude de mentira inteiro; sem ele, responde `versao`."""
    falso(tmp_path, "claude", corpo or (f'echo "{versao} (Claude Code)"' if versao else "exit 1"))
    script = (
        SAIDAS
        + f'CLAUDE_MIN="{piso()}"\nPATH_SHELL="$PATH"\n'
        + funcao("versao_min")
        + "\n"
        + funcao("checa_claude_versao")
        + "\n"
        + "checa_claude_versao\n"
    )
    r = subprocess.run(
        ["bash", "-c", script],
        env={"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    return r.stdout + r.stderr


def test_o_piso_e_o_da_onda_enxuta():
    # O número vem da seção "Em máquina nova" da /onda-enxuta, que é quem exige.
    exigido = re.search(r"`claude --version` \((\d+\.\d+\.\d+) ou mais", ENXUTA)
    assert exigido, "a /onda-enxuta não diz mais qual versão exige"
    assert piso() == exigido.group(1)
    assert re.search(r"^CLAUDE_MIN=.*onda-enxuta", TEXTO, re.M), "o comentário cita quem exige o piso"


def test_versao_acima_do_piso_passa(tmp_path):
    li = linha(roda_claude(tmp_path, "2.1.288"), f"claude >= {piso()}")
    assert li.startswith("OK")
    assert "2.1.288" in li


def test_versao_abaixo_do_piso_acusa_e_diz_como_atualizar(tmp_path):
    li = linha(roda_claude(tmp_path, "2.1.279"), f"claude >= {piso()}")
    assert li.startswith("FALTA")
    assert "2.1.279" in li
    assert "install.sh" in li


def test_versao_igual_ao_piso_passa(tmp_path):
    # Fronteira: "2.1.280 ou mais" inclui o próprio piso; um "maior estrito" reprovaria.
    assert linha(roda_claude(tmp_path, piso()), f"claude >= {piso()}").startswith("OK")


def test_comparacao_e_por_numero_nao_por_texto(tmp_path):
    # 2.1.1000 > 2.1.280 por número; no alfabeto "1000" vem antes de "280".
    assert linha(roda_claude(tmp_path, "2.1.1000"), f"claude >= {piso()}").startswith("OK")


def test_claude_que_nao_responde_acusa(tmp_path):
    # Binário presente que não responde é instalação quebrada: a enxuta não lança.
    li = linha(roda_claude(tmp_path, None), f"claude >= {piso()}")
    assert li.startswith("FALTA")
    assert "install.sh" in li


def test_saida_sem_numero_nao_passa(tmp_path):
    # "Update available" ou "Claude Code 2.1.288" na primeira linha: nada de OK por texto.
    saida = roda_claude(tmp_path, None, corpo='echo "Update available"')
    assert linha(saida, f"claude >= {piso()}").startswith("FALTA")


def test_retorno_de_carro_do_windows_nao_suja_a_versao(tmp_path):
    li = linha(roda_claude(tmp_path, None, corpo="printf '2.1.288 (Claude Code)\\r\\n'"), f"claude >= {piso()}")
    assert li.startswith("OK")
    assert "\r" not in li


def test_o_nivel_2_chama_a_conferencia():
    nivel2 = TEXTO.split("Nível 2:")[1].split("Nível 3:")[0]
    assert "checa_claude_versao" in nivel2
