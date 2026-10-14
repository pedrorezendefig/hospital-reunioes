"""Trava de dono morto não congela a fila por 60 min.

A subida do PR #1238 morreu por sinal 11 s depois do merge (a sessão foi para o
background) e a trava ficou com um dono que não existia mais: as outras subidas
esperaram até a trava ficar velha e sairiam com 8 pedindo o humano. Agora a
trava guarda o pid da subida (`SEMAFORO_PID`) e a fase dela, e quem chega
confere se o dono está vivo:
- morto sem código do app na main: a trava é órfã, sai do caminho e quem chega pega;
- morto com código do app na main (fase `app-na-main`): a trava fica parada na
  hora, e prod espera o humano, como na saída 3 ou 4 da subida;
- vivo, ou trava sem pid (o `/ship` manual): espera na fila, como antes.
"""

from __future__ import annotations

import os
import subprocess
import time

from test_fechar_onda_pr_avulso import carregar_fechar_onda, preparar, pr_de_codigo, pr_de_ferramenta, rodar_main
from test_subida_assume_o_fracasso import semaforo_sh, trava  # noqa: F401 (fixture)


def pid_morto() -> int:
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def pegar_como(monkeypatch, pid: int, chave: str = "onda-a-onda1") -> None:
    monkeypatch.setenv("SEMAFORO_PID", str(pid))
    assert semaforo_sh("pegar", chave, "PRs #7").returncode == 0
    monkeypatch.delenv("SEMAFORO_PID")


def test_dono_morto_sem_app_na_main_a_trava_sai_do_caminho_e_quem_chega_pega(trava, monkeypatch):
    pegar_como(monkeypatch, pid_morto())

    t = time.monotonic()
    proc = semaforo_sh("pegar", "onda-b-onda1", "PRs #8")

    assert proc.returncode == 0, proc
    assert time.monotonic() - t < 3, "esperou o dono morto em vez de soltar a trava"
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-b-onda1"
    assert "órfã" in proc.stdout and "onda-a-onda1" in proc.stdout, proc.stdout


def test_dono_morto_com_app_na_main_deixa_a_trava_parada_e_sai_com_4_na_hora(trava, monkeypatch):
    pegar_como(monkeypatch, pid_morto())
    assert semaforo_sh("fase", "onda-a-onda1", "app-na-main").returncode == 0

    t = time.monotonic()
    proc = semaforo_sh("pegar", "onda-b-onda1", "PRs #8")

    assert proc.returncode == 4, proc
    assert time.monotonic() - t < 3, "esperou a trava em vez de sair na hora"
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-a-onda1"
    dono, linha = (trava / "parada").read_text(encoding="utf-8").splitlines()
    assert dono == "onda-a-onda1" and "morreu" in linha and "app" in linha, linha


def test_dono_vivo_segue_na_fila(trava, monkeypatch):
    pegar_como(monkeypatch, os.getpid())

    assert semaforo_sh("pegar", "onda-b-onda1", "PRs #8").returncode == 3
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-a-onda1"


def test_trava_sem_pid_segue_na_fila_como_antes(trava):
    assert semaforo_sh("pegar", "onda-a-onda1", "PRs #7").returncode == 0

    assert semaforo_sh("pegar", "onda-b-onda1", "PRs #8").returncode == 3
    assert not (trava / "pid").exists()


def test_so_o_dono_muda_a_fase(trava):
    assert semaforo_sh("pegar", "onda-a-onda1", "PRs #7").returncode == 0

    assert semaforo_sh("fase", "onda-b-onda1", "app-na-main").returncode == 1
    assert not (trava / "fase").exists()


# ------------------------------------------------------ a subida e a trava


def fases_e_pid(fo, monkeypatch, c, semaforo_real) -> list[tuple]:
    """Cada chamada do semáforo, com o pid que a subida passou e quantos merges
    já tinham entrado na main naquela hora. O `semaforo` é o de verdade (o dublê
    de `preparar` sai), e o `semaforo.sh` responde 0 sem rodar."""
    chamadas: list[tuple] = []
    run = fo.run

    def anotando(cmd, *a, **kw):
        if str(cmd[1]).endswith("semaforo.sh"):
            chamadas.append((cmd[2], cmd[4:], (kw.get("env") or {}).get("SEMAFORO_PID"), len(c.merges)))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return run(cmd, *a, **kw)

    monkeypatch.setattr(fo, "run", anotando)
    monkeypatch.setattr(fo, "semaforo", semaforo_real)
    return chamadas


def test_subida_de_app_passa_o_pid_e_marca_app_na_main_antes_do_primeiro_merge(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_codigo(tmp_path)
    semaforo_real = fo.semaforo
    preparar(fo, monkeypatch, c)
    chamadas = fases_e_pid(fo, monkeypatch, c, semaforo_real)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert [ch[0] for ch in chamadas] == ["pegar", "fase", "soltar"], chamadas
    _, args, pid, merges = chamadas[1]
    assert args == ["app-na-main"] and merges == 0, chamadas[1]
    assert {ch[2] for ch in chamadas} == {str(os.getpid())}, chamadas


def test_subida_de_ferramenta_nao_marca_fase(tmp_path, monkeypatch):
    fo = carregar_fechar_onda()
    c = pr_de_ferramenta(tmp_path)
    semaforo_real = fo.semaforo
    preparar(fo, monkeypatch, c)
    chamadas = fases_e_pid(fo, monkeypatch, c, semaforo_real)

    assert rodar_main(fo, monkeypatch, c) == 0

    assert [ch[0] for ch in chamadas] == ["pegar", "soltar"], chamadas
