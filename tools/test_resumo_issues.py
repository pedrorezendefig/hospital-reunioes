"""Resumo das issues por pessoa e PRD, o `/resumo-issues`.

Cobre o miolo puro `montar(issues)` com dados de mentira; o GitHub não entra.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "resumo-issues" / "scripts" / "resumo_issues.py"

_spec = importlib.util.spec_from_file_location("resumo_issues", SCRIPT)
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)


def issue(n, titulo="t", donos=(), parent=None, corpo=""):
    return {"number": n, "title": titulo, "body": corpo, "assignees": list(donos), "parent": parent}


def bloco(saida: str, pessoa: str) -> str:
    """O trecho de uma pessoa, do cabeçalho até a linha em branco."""
    inicio = saida.index(f"\n{pessoa} (")
    fim = saida.find("\n\n", inicio + 1)
    return saida[inicio:] if fim == -1 else saida[inicio:fim]


def test_conta_por_pessoa_com_apelido_e_sem_responsavel():
    saida = ri.montar([
        issue(1, donos=["pedroribbe"]),
        issue(2, donos=["pedroribbe"]),
        issue(3, donos=["lucassampaioc1"]),
        issue(4),
    ])
    assert saida.startswith("Hospital: 4 abertas\n")
    assert "\nRib (2)\n" in saida
    assert "\nLucas (1)\n" in saida
    assert "\nSem responsável (1)\n" in saida
    assert saida.index("Rib (2)") < saida.index("Lucas (1)") < saida.index("Sem responsável (1)")


def test_login_fora_dos_apelidos_aparece_como_esta():
    assert "\nfulano (1)\n" in ri.montar([issue(1, donos=["fulano"])])


def test_card_vai_para_baixo_do_prd_pai_e_avulsa_fica_em_avulsas():
    pai = {"number": 809, "title": "PRD: Central de Comando migra"}
    saida = ri.montar([
        issue(862, "Conferir no celular", donos=["pedroribbe"], parent=pai),
        issue(1324, "Ativar o 2FA", donos=["pedroribbe"]),
    ])
    rib = bloco(saida, "Rib")
    assert "  PRD #809 Central de Comando migra\n    #862 Conferir no celular" in rib
    assert "  Avulsas\n    #1324 Ativar o 2FA" in rib


def test_prd_com_a_pessoa_vira_grupo_proprio_marcado():
    saida = ri.montar([issue(1415, "PRD: Contas médicas", donos=["pedrorezendefig"])])
    assert "  PRD #1415 Contas médicas\n    #1415 (o PRD)" in saida
    assert "Avulsas" not in saida


def test_pai_sem_titulo_de_prd_nao_aparece_duas_vezes():
    pai = {"number": 810, "title": "Wayfinder: Blog"}
    saida = ri.montar([issue(810, "Wayfinder: Blog"), issue(811, "Acesso do Felipe", parent=pai)])
    assert saida.count("#810 ") == 2  # o cabeçalho e a linha "(o PRD)"
    assert "    #810 (o PRD)" in saida
    assert "Avulsas" not in saida


def test_linha_muda_vem_do_bloco_para_o_diretor():
    corpo = "## 👔 Para o diretor\n**O que muda:** a Central antiga sai do ar.\n"
    saida = ri.montar([issue(828, "Corte da Central", corpo=corpo)])
    assert "    #828 Corte da Central\n      muda: a Central antiga sai do ar.\n" in saida


def test_muda_longo_e_cortado_e_ausente_nao_gera_linha():
    corpo = "**O que muda:** " + "x" * 300
    saida = ri.montar([issue(1, "Com corpo longo", corpo=corpo), issue(2, "Sem corpo")])
    linha = next(l for l in saida.splitlines() if l.startswith("      muda: "))
    assert len(linha) == len("      muda: ") + ri.LARGURA
    assert linha.endswith("...")
    assert saida.count("muda:") == 1


def test_card_com_dois_responsaveis_conta_para_os_dois():
    saida = ri.montar([issue(5, donos=["pedroribbe", "lucassampaioc1"])])
    assert "\nRib (1)\n" in saida and "\nLucas (1)\n" in saida


def test_caractere_de_controle_no_titulo_e_no_muda_vira_espaco():
    corpo = "**O que muda:** linha\x1b[31m vermelha"
    saida = ri.montar([issue(7, "Título\x07 com sino", corpo=corpo)])
    assert "\x1b" not in saida and "\x07" not in saida
    assert "    #7 Título  com sino\n      muda: linha [31m vermelha" in saida
