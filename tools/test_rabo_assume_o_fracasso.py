"""O rabo assume o próprio fracasso antes de soltar o semáforo (issue #999).

ADR 0064, decisão 6a, emenda de 06/10/2026: a onda seguinte não lê nada da
anterior. Quem ordena os deploys é o semáforo, e quem diz o que está bloqueado
é o GitHub. Por isso o `fechar_onda.py`, ainda com a trava:
- nas saídas 3 e 4 marca a trava como parada, e o rabo seguinte sai na hora com
  8, sem pegar a trava e sem mandar ninguém forçar;
- na saída 6 reabre as issues do lote e mergeia o revert dos squashes;
- confere de novo o `blocked_by` da issue de cada PR (a bloqueadora pode ter
  sido reaberta por um rollback).

Os testes do rabo usam o repositório de verdade e os dublês de
`test_fechar_onda_pr_avulso.py`; os da trava rodam o `semaforo.sh` de verdade,
numa trava própria em /tmp.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from test_fechar_onda_pr_avulso import carregar_fechar_onda, codigo_na_docstring, onda_de_dois, pr_de_codigo, preparar

RAIZ = Path(__file__).resolve().parent.parent
SEMAFORO = RAIZ / ".claude" / "skills" / "deploy" / "scripts" / "semaforo.sh"
DUAS_HORAS = 2 * 60 * 60


@pytest.fixture
def trava(monkeypatch):
    """Uma trava só deste teste. O passo de espera é longo de propósito: quem
    espera em vez de sair na hora estoura o limite de tempo dos testes."""
    slug = f"teste-999-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("SEMAFORO_SLUG", slug)
    monkeypatch.setenv("SEMAFORO_PASSO", "5")
    monkeypatch.setenv("SEMAFORO_ESPERA", "5")
    pasta = Path(f"/tmp/deploy-semaforo-{slug}.lock")
    yield pasta
    shutil.rmtree(pasta, ignore_errors=True)


def semaforo_sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SEMAFORO), *args], capture_output=True, text=True,
                          timeout=120, env=dict(os.environ), check=False)


# ------------------------------------------------------- semaforo.sh parado


def test_trava_parada_recusa_quem_chega_na_hora_sem_pegar_e_sem_mandar_forcar(trava):
    assert semaforo_sh("pegar", "onda-a-onda1", "PRs #7").returncode == 0
    linha = "build: backend: failed. Semaforo preso na chave onda-a-onda1: rode `/deploy rollback` com ela."
    assert semaforo_sh("parar", "onda-a-onda1", linha).returncode == 0
    # a marca mora dentro da pasta da trava, com a chave e a linha do erro
    assert (trava / "parada").read_text(encoding="utf-8").splitlines() == ["onda-a-onda1", linha]

    for chave in ("onda-a-onda2", "onda-a-onda1"):  # nem o dono entra de novo
        t = time.monotonic()
        proc = semaforo_sh("pegar", chave, "PRs #8")
        assert proc.returncode == 4, (chave, proc)
        assert time.monotonic() - t < 3, "esperou a trava em vez de sair na hora"
        assert "parada" in proc.stderr and "onda-a-onda1" in proc.stderr, proc.stderr
        assert "--forcar" not in proc.stdout + proc.stderr, proc
    # quem chegou não pegou: a trava segue com o dono, parada
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-a-onda1"
    assert "parada" in semaforo_sh("status").stdout


def test_trava_velha_recusa_sem_mandar_forcar(trava):
    assert semaforo_sh("pegar", "onda-a-onda1", "PRs #7").returncode == 0
    (trava / "desde").write_text(str(int(time.time()) - DUAS_HORAS), encoding="utf-8")

    proc = semaforo_sh("pegar", "onda-b-onda1", "PRs #8")

    assert proc.returncode == 2, proc
    assert "--forcar" not in proc.stdout + proc.stderr, proc
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-a-onda1"


# ------------------------------------------------- o rabo e a trava parada

def com_semaforo_de_verdade(monkeypatch, c):
    """Carrega o rabo, prepara os dublês e põe o `semaforo.sh` de verdade no
    lugar do dublê, copiado para o clone em que o rabo roda. Quem espera a
    trava em vez de sair na hora cai num `3` e para o teste ali, em vez de
    esperar para sempre."""
    fo = carregar_fechar_onda()
    semaforo_real = fo.semaforo
    preparar(fo, monkeypatch, c)
    destino = c.clone / ".claude" / "skills" / "deploy" / "scripts" / "semaforo.sh"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SEMAFORO, destino)

    def semaforo(raiz, acao, chave, descricao=""):
        rc = semaforo_real(raiz, acao, chave, descricao)
        assert not (acao == "pegar" and rc == 3), "o rabo esperou a trava em vez de sair na hora"
        return rc

    monkeypatch.setattr(fo, "semaforo", semaforo)
    return fo


def rodar(fo, monkeypatch, c, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["fechar_onda.py", *argv, "--raiz", str(c.clone)])
    try:
        return fo.main()
    except SystemExit as e:
        return e.code


def test_saida_3_deixa_a_trava_parada_e_o_rabo_seguinte_sai_com_8_na_hora(tmp_path, monkeypatch, capsys, trava):
    c = onda_de_dois(tmp_path)
    fo = com_semaforo_de_verdade(monkeypatch, c)
    monkeypatch.setattr(fo, "esperar_build", lambda service, desde, sha, ignorar=(): ("failed", 30))

    assert rodar(fo, monkeypatch, c, "--prs", "7", "--sessao", "onda-a-onda1") == fo.EXIT_BUILD == 3

    # a trava fica presa com quem quebrou, marcada com a linha do erro
    build = next(li for li in capsys.readouterr().out.splitlines() if li.startswith("build:"))
    assert (trava / "parada").read_text(encoding="utf-8").splitlines() == ["onda-a-onda1", build]
    merges = list(c.merges)

    # outra onda chega: sai na hora com 8, sem pegar a trava e sem mexer na main
    t = time.monotonic()
    assert rodar(fo, monkeypatch, c, "--prs", "8", "--sessao", "onda-a-onda2") == fo.EXIT_PARADA == 8
    assert time.monotonic() - t < 4, "esperou a trava em vez de sair na hora"

    saida = capsys.readouterr().out
    parada = saida.strip().splitlines()[-1]
    assert parada.startswith("parada: prod espera rollback humano, chave onda-a-onda1"), parada
    assert "--forcar" not in saida, saida
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-a-onda1"
    assert c.merges == merges and c.prs[8]["state"] == "OPEN"


def test_trava_velha_o_rabo_sai_com_8_na_hora_sem_pegar_e_sem_mandar_forcar(tmp_path, monkeypatch, capsys, trava):
    c = pr_de_codigo(tmp_path)
    fo = com_semaforo_de_verdade(monkeypatch, c)
    assert semaforo_sh("pegar", "onda-b-onda3", "PRs #5").returncode == 0
    (trava / "desde").write_text(str(int(time.time()) - DUAS_HORAS), encoding="utf-8")

    assert rodar(fo, monkeypatch, c, "--prs", "7") == fo.EXIT_PARADA

    saida = capsys.readouterr().out
    parada = saida.strip().splitlines()[-1]
    assert parada.startswith("parada: prod espera rollback humano, chave onda-b-onda3"), parada
    assert "--forcar" not in saida, saida
    assert (trava / "chave").read_text(encoding="utf-8").strip() == "onda-b-onda3"
    assert c.merges == [] and c.coolify() == []


# ------------------------------------- bloqueio conferido de novo com a trava


def test_pr_cuja_issue_ganhou_bloqueio_aberto_fica_de_fora_e_nao_entra(tmp_path, monkeypatch, capsys):
    """A #6 (do PR #8) depende da #4, que um rollback reabriu depois que a
    sessão montou a onda: com a trava pega, o rabo pergunta ao GitHub de novo e
    deixa o #8 de fora. O #7, cuja bloqueadora já fechou, sobe sozinho."""
    fo = carregar_fechar_onda()
    c = onda_de_dois(tmp_path)
    c.bloqueadoras[5] = [{"number": 3, "state": "closed"}]
    c.bloqueadoras[6] = [{"number": 4, "state": "open"}]
    preparar(fo, monkeypatch, c)
    eventos: list[str] = []
    semaforo, gh_json = fo.semaforo, fo.gh_json

    def semaforo_anotando(raiz, acao, chave, descricao=""):
        eventos.append(acao)
        return semaforo(raiz, acao, chave, descricao)

    def gh_json_anotando(args, cwd=None):
        if args[-1].endswith("/dependencies/blocked_by"):
            eventos.append("blocked_by " + args[-1].split("/")[4])
        return gh_json(args, cwd)

    monkeypatch.setattr(fo, "semaforo", semaforo_anotando)
    monkeypatch.setattr(fo, "gh_json", gh_json_anotando)

    assert rodar(fo, monkeypatch, c, "--prs", "7", "8", "--sessao", "onda-x") == fo.EXIT_MERGE

    # perguntado com a trava na mão, não antes
    assert eventos[:3] == ["pegar", "blocked_by 5", "blocked_by 6"], eventos
    assert c.merges[0]["pr"] == 7 and 8 not in [m["pr"] for m in c.merges], c.merges
    assert c.prs[8]["state"] == "OPEN" and c._tip("feature-8") == c.prs[8]["headRefOid"]
    saida = capsys.readouterr().out
    fora = [li for li in saida.splitlines() if li.startswith("de fora:")]
    assert len(fora) == 1 and fora[0].startswith("de fora: #8 bloqueada por #4"), fora
    assert saida.strip().splitlines()[-1].startswith("onda onda-x fechada sem #8"), saida


# --------------------------------------------- saída 6 inteira dentro da trava

IMAGEM_ANTERIOR = "cab8930958d1f89545d688418f37745936cc576f"


def onda_que_quebra_o_health(tmp_path: Path):
    """Os PRs #7 e #8 entram, o backend da v0.10.1 responde 500 e a imagem
    anterior volta com o health verde (o rollback de imagem da issue #968)."""
    c = onda_de_dois(tmp_path)
    c.imagens_no_coolify("uuid-backend", IMAGEM_ANTERIOR)
    c.health_ruim_em.add("0.10.1")
    return c


def anotar_o_semaforo(fo, monkeypatch, c) -> list[dict]:
    """O que já tinha acontecido a cada chamada do semáforo: os merges na main e
    as issues reabertas."""
    momentos: list[dict] = []
    semaforo = fo.semaforo

    def anotando(raiz, acao, chave, descricao=""):
        momentos.append({"acao": acao, "descricao": descricao, "merges": [m["branch"] for m in c.merges],
                         "reabertas": [a[2] for a in c.gh_chamadas if a[:2] == ["issue", "reopen"]]})
        return semaforo(raiz, acao, chave, descricao)

    monkeypatch.setattr(fo, "semaforo", anotando)
    return momentos


def arvore(c, ref: str) -> str:
    return subprocess.run(["git", "rev-parse", f"{ref}^{{tree}}"], cwd=c.remoto, capture_output=True,
                          text=True, check=True).stdout.strip()


def test_saida_6_reabre_as_issues_e_mergeia_o_revert_antes_de_soltar_a_trava(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = onda_que_quebra_o_health(tmp_path)
    preparar(fo, monkeypatch, c)
    momentos = anotar_o_semaforo(fo, monkeypatch, c)

    assert rodar(fo, monkeypatch, c, "--prs", "7", "8", "--sessao", "onda-x") == fo.EXIT_ROLLBACK == 6

    # o semáforo só solta depois das issues reabertas e do revert na main
    assert [m["acao"] for m in momentos] == ["pegar", "soltar"], momentos
    soltar = momentos[-1]
    assert soltar["reabertas"] == ["5", "6"], soltar
    assert soltar["merges"] == ["feature", "feature-8", "revert/onda-x"], soltar
    # o revert desfaz os dois squashes: a main volta à árvore de antes da onda
    revert = c.merges[-1]
    assert arvore(c, revert["main"]) == arvore(c, c.base)
    assert c.prs[revert["pr"]]["state"] == "MERGED"
    # o build que o merge do revert disparou é cancelado: a imagem no ar já é a anterior
    assert c.cancelamentos[-1] == revert["main"], c.cancelamentos
    assert c.esperados == [c.merges[1]["main"]], "nenhum build além do da onda"
    # cada issue volta para a fila, com o que o health respondeu
    for issue in ("5", "6"):
        assert ["issue", "edit", issue, "--remove-label", "in-progress", "--add-label", "ready-for-agent"] \
            in c.gh_chamadas, c.gh_chamadas
        [corpo] = [a[a.index("--body") + 1] for a in c.gh_chamadas if a[:3] == ["issue", "comment", issue]]
        assert corpo.startswith("<!-- automacao -->\n") and "health: backend: http 500" in corpo, corpo
    rollback = capsys.readouterr().out.strip().splitlines()[-1]
    assert rollback.startswith("rollback:"), rollback
    for trecho in (f"PR #{revert['pr']}", "issue #5", "issue #6", "v0.10.0", "semaforo solto"):
        assert trecho in rollback, (trecho, rollback)


def test_revert_recusado_sai_com_4_e_a_trava_fica_presa_e_parada(tmp_path, monkeypatch, capsys):
    fo = carregar_fechar_onda()
    c = onda_que_quebra_o_health(tmp_path)
    mergear = c.mergear_pela_api

    def recusar_o_revert(n, campos):
        if c.prs[n]["headRefName"].startswith("revert/"):
            raise RuntimeError("gh api -> 405: Required status check is failing.")
        return mergear(n, campos)

    c.mergear_pela_api = recusar_o_revert
    preparar(fo, monkeypatch, c)
    momentos = anotar_o_semaforo(fo, monkeypatch, c)

    assert rodar(fo, monkeypatch, c, "--prs", "7", "8", "--sessao", "onda-x") == fo.EXIT_HEALTH == 4

    # sem soltar: presa e marcada parada, com a linha do revert que não entrou
    assert [m["acao"] for m in momentos] == ["pegar", "parar"], momentos
    linha = capsys.readouterr().out.strip().splitlines()[-1]
    assert momentos[-1]["descricao"] == linha, (momentos[-1], linha)
    assert "revert" in linha and "405" in linha and "Semaforo preso na chave onda-x" in linha, linha
    assert [m["branch"] for m in c.merges] == ["feature", "feature-8"]


# ------------------------------------------------------------------ docstring


def test_docstring_documenta_a_parada_e_o_revert_feito_pelo_rabo():
    fo = carregar_fechar_onda()
    assert "--forcar" not in fo.__doc__

    parada = codigo_na_docstring(fo, 8)
    for termo in ("parada", "velha", "rollback humano", "sem pegar o semaforo", "nada entrou na main"):
        assert termo in parada, (termo, parada)
    rollback = codigo_na_docstring(fo, 6).lower()
    for termo in ("reabre", "ready-for-agent", "revert/<chave>", "antes de soltar o semaforo"):
        assert termo in rollback, (termo, rollback)
    for codigo in (3, 4):
        assert "marcado parado" in codigo_na_docstring(fo, codigo), codigo
    assert "bloqueada por" in codigo_na_docstring(fo, 2)
    assert "trava velha" not in codigo_na_docstring(fo, 1)
