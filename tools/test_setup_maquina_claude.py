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

from test_setup_maquina_esteira import SAIDAS, TEXTO, falso, funcao, linha


def piso() -> str:
    achado = re.search(r'^CLAUDE_MIN="([0-9.]+)"', TEXTO, re.M)
    assert achado, "o piso vive numa variável CLAUDE_MIN no topo do script"
    return achado.group(1)


def roda_claude(tmp_path: Path, versao: str | None) -> str:
    falso(tmp_path, "claude", f'echo "{versao} (Claude Code)"' if versao else "exit 1")
    script = (
        SAIDAS
        + f'CLAUDE_MIN="{piso()}"\n'
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
    assert piso() == "2.1.280"
    assert re.search(r"^CLAUDE_MIN=.*onda-enxuta", TEXTO, re.M), "o comentário cita quem exige o piso"


def test_versao_acima_do_piso_passa(tmp_path):
    li = linha(roda_claude(tmp_path, "2.1.288"), "claude >= 2.1.280")
    assert li.startswith("OK")
    assert "2.1.288" in li


def test_versao_abaixo_do_piso_acusa_e_diz_como_atualizar(tmp_path):
    li = linha(roda_claude(tmp_path, "2.1.279"), "claude >= 2.1.280")
    assert li.startswith("FALTA")
    assert "2.1.279" in li
    assert "install.sh" in li


def test_versao_igual_ao_piso_passa(tmp_path):
    # Fronteira: "2.1.280 ou mais" inclui o próprio piso; um "maior estrito" reprovaria.
    assert linha(roda_claude(tmp_path, "2.1.280"), "claude >= 2.1.280").startswith("OK")


def test_comparacao_e_por_numero_nao_por_texto(tmp_path):
    # 2.1.1000 > 2.1.280 por número; no alfabeto "1000" vem antes de "280".
    assert linha(roda_claude(tmp_path, "2.1.1000"), "claude >= 2.1.280").startswith("OK")


def test_claude_que_nao_responde_so_avisa(tmp_path):
    li = linha(roda_claude(tmp_path, None), "claude >= 2.1.280")
    assert li.startswith("AVISO")


def test_o_nivel_2_chama_a_conferencia():
    nivel2 = TEXTO.split("Nível 2:")[1].split("Nível 3:")[0]
    assert "checa_claude_versao" in nivel2
