"""A trilha da Demonstração no modo rápido do `/divulgar`: a faixa menos usada.

O `escolher_trilha.py` lê o campo "musica" dos `meta.json` das demonstrações anteriores e
devolve a faixa da biblioteca que menos entrou. Os testes rodam o script como a sessão roda,
com uma biblioteca e um repositório falsos em pastas temporárias.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "divulgar" / "scripts" / "escolher_trilha.py"


def _biblioteca(tmp: Path, faixas: dict[str, list[str]]) -> Path:
    musica = tmp / "musica"
    for clima, nomes in faixas.items():
        (musica / clima).mkdir(parents=True)
        for nome in nomes:
            (musica / clima / nome).write_bytes(b"")
    return musica


def _demonstracao(raiz: Path, pasta: str, musica: str, quando: str) -> None:
    video = raiz / "docs" / "comunicacao" / "tecnologia" / pasta / "video"
    video.mkdir(parents=True)
    (video / "meta.json").write_text(json.dumps({"musica": musica, "gerado_em": quando}), encoding="utf-8")


def _rodar(musica: Path, raiz: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--musica", str(musica), "--raiz", str(raiz), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_nunca_usada_vem_antes_da_usada(tmp_path):
    musica = _biblioteca(tmp_path, {"tecnologia": ["a.mp3", "b.mp3"]})
    raiz = tmp_path / "repo"
    _demonstracao(raiz, "1-x", "tecnologia/a.mp3", "2026-11-01T10:00:00-03:00")
    saida = _rodar(musica, raiz)
    assert saida.returncode == 0
    assert saida.stdout.strip() == str(musica / "tecnologia" / "b.mp3")


def test_no_empate_de_usos_vence_a_usada_ha_mais_tempo(tmp_path):
    musica = _biblioteca(tmp_path, {"tecnologia": ["a.mp3", "b.mp3"]})
    raiz = tmp_path / "repo"
    _demonstracao(raiz, "1-x", "tecnologia/a.mp3", "2026-11-10T10:00:00-03:00")
    _demonstracao(raiz, "2-y", "tecnologia/b.mp3", "2026-11-02T10:00:00-03:00")
    assert _rodar(musica, raiz).stdout.strip() == str(musica / "tecnologia" / "b.mp3")


def test_conta_os_usos_e_so_olha_os_climas_pedidos(tmp_path):
    musica = _biblioteca(tmp_path, {"tecnologia": ["a.mp3"], "animada": ["c.mp3"], "calma": ["piano.mp3"]})
    raiz = tmp_path / "repo"
    _demonstracao(raiz, "1-x", "tecnologia/a.mp3", "2026-11-01T10:00:00-03:00")
    _demonstracao(raiz, "2-y", "tecnologia/a.mp3", "2026-11-02T10:00:00-03:00")
    _demonstracao(raiz, "3-z", "animada/c.mp3", "2026-11-03T10:00:00-03:00")
    # c foi usada 1 vez e a 2 vezes; a calma nunca usada fica de fora porque não foi pedida.
    assert _rodar(musica, raiz).stdout.strip() == str(musica / "animada" / "c.mp3")
    assert _rodar(musica, raiz, "--climas", "calma").stdout.strip() == str(musica / "calma" / "piano.mp3")


def test_sem_faixa_nos_climas_sai_com_erro(tmp_path):
    musica = _biblioteca(tmp_path, {"calma": ["piano.mp3"]})
    saida = _rodar(musica, tmp_path / "repo")
    assert saida.returncode == 1
    assert "nenhuma faixa" in saida.stderr
