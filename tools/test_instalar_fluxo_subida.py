"""O kit `tools/instalar-fluxo/` leva a subida ao DESTINO (issue #924).

O `/ship` copiado termina rodando o `fechar_onda.py` da `onda-enxuta`; o kit
tem que levar essa skill e os agentes `hr-*`, descrever a subida do DESTINO na
Fase 4.4 e deixar o `/deploy` sem o modo `ship`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
KIT = RAIZ / "tools" / "instalar-fluxo"
AGENTES = sorted(p.name for p in (RAIZ / ".claude" / "agents").glob("hr-*.md"))


def ler(nome: str) -> str:
    return (KIT / nome).read_text(encoding="utf-8")


def textos_do_kit() -> dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(KIT.iterdir())
        if p.is_file()
    }


def secao(texto: str, titulo: str) -> str:
    inicio = texto.index(titulo)
    fim = texto.find("\n### ", inicio + len(titulo))
    return texto[inicio : fim if fim != -1 else len(texto)]


def linha_da_tabela(texto: str, chave: str) -> str:
    linhas = [li for li in texto.splitlines() if li.startswith(f"| {chave} |")]
    assert linhas, f"MANIFESTO sem linha para {chave}"
    return linhas[0]


def test_empacotar_dry_run_lista_onda_enxuta_e_agentes_sem_gerar_zip(tmp_path):
    proc = subprocess.run(
        ["bash", str(KIT / "empacotar.sh"), "--dry-run", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        cwd=RAIZ,
    )
    listados = set(proc.stdout.splitlines())
    assert ".claude/skills/onda-enxuta/" in listados
    assert AGENTES, "nenhum agente hr-* na ORIGEM"
    for agente in AGENTES:
        assert f".claude/agents/{agente}" in listados
    assert ".claude/skills/divulgar/" not in listados
    assert list(tmp_path.iterdir()) == []


def test_manifesto_lista_onda_enxuta_com_seus_arquivos():
    linha = linha_da_tabela(ler("MANIFESTO.md"), "`onda-enxuta`")
    assert "| adaptar |" in linha
    for arquivo in (
        "SKILL.md",
        "references/",
        "scripts/fechar_onda.py",
        "revisao-sensivel.txt",
        "onda-settings.json",
    ):
        assert arquivo in linha, arquivo
        assert (RAIZ / ".claude" / "skills" / "onda-enxuta" / arquivo).exists(), arquivo


def test_manifesto_lista_cada_agente_hr_com_sua_acao():
    manifesto = ler("MANIFESTO.md")
    for agente in AGENTES:
        linha = linha_da_tabela(manifesto, f"`.claude/agents/{agente}`")
        assert re.search(r"\| (copiar|adaptar) \|", linha), linha
    assert "hr-mapeador" not in manifesto


def test_roteiro_fase_4_4_descreve_a_subida_do_destino_e_o_deploy_sem_ship():
    fase = secao(ler("ROTEIRO.md"), "### 4.4")
    assert "subida" in fase
    assert "fechar_onda.py" in fase
    for ponto in ("plataforma", "versão", "migrations", "health", "pos-merge.yml"):
        assert ponto in fase, ponto
    for modo in ("`status`", "`rollback`", "`setup`"):
        assert modo in fase, modo
    assert not re.search(r"[Mm]odos? `ship`", fase)


AFIRMACOES_DO_PIPELINE_ANTIGO = [
    r"/deploy ship",
    r"[Mm]odos? `ship`",
    r"`/ship`[^.\n|]{0,40}\b(mergeia|deploya|faz (o )?deploy|faz bump)",
    r"OK humano citando o PR",
    r"\brabo\b",
]


def test_nenhuma_frase_do_kit_diz_que_o_ship_mergeia_ou_que_o_deploy_ship_faz_deploy():
    achados = [
        (nome, padrao)
        for nome, texto in textos_do_kit().items()
        for padrao in AFIRMACOES_DO_PIPELINE_ANTIGO
        if re.search(padrao, texto)
    ]
    assert achados == []


def test_kit_sem_travessao_nem_meia_risca():
    achados = [
        nome
        for nome, texto in textos_do_kit().items()
        if re.search("[\u2014\u2013]", texto)
    ]
    assert achados == []
