"""Testes do inventário do Manual (tools/inventario_manual.py).

Cada teste monta um manual mínimo num diretório temporário e cobra do
inventário o que a issue #737 pede: as lacunas de cada módulo achadas e cada
uma delas em exatamente um balde, para o `/montar-manual` conseguir dividir o
passivo em um terminal por módulo sem deixar nada de fora.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import inventario_manual  # noqa: E402

INVENTARIO = Path(__file__).resolve().parent / "inventario_manual.py"

VISAO_GERAL = """---
title: Ouvidoria
description: Visão geral do módulo da Ouvidoria.
prd: [731]
draft: false
---

Esta seção cobre o caminho de um caso, do registro ao encerramento.
"""

TAREFA = """---
title: Registrar uma manifestação pelo formulário
description: Como contar uma reclamação para a Ouvidoria.
prd: [731]
draft: false
papel: [Qualquer pessoa]
video: registrar-manifestacao-pelo-formulario
---

## Passo a passo

![A tela do formulário](../../../assets/ouvidoria/formulario-publico.png)

1. Clique em **Enviar manifestação**.
"""

NOVIDADES = """---
title: Novidades da Ouvidoria
description: O que mudou na Ouvidoria, da entrega mais nova para a mais antiga.
prd: [731]
draft: false
---

## 16/09/2026 · O formulário público entra no ar

Quem não tem conta passa a registrar a manifestação sozinho.
"""


def montar(raiz: Path) -> None:
    """Um manual sem lacuna: os cinco módulos, e a Ouvidoria escrita inteira."""
    conteudo = raiz / "src" / "content" / "docs"
    for modulo in inventario_manual.MODULOS:
        (conteudo / modulo).mkdir(parents=True)
        (conteudo / modulo / "index.md").write_text(VISAO_GERAL, encoding="utf-8")
        (conteudo / modulo / "novidades.md").write_text(NOVIDADES, encoding="utf-8")
    (conteudo / "ouvidoria" / "registrar-manifestacao-pelo-formulario.md").write_text(
        TAREFA, encoding="utf-8"
    )
    prints = raiz / "src" / "assets" / "ouvidoria"
    prints.mkdir(parents=True)
    (prints / "formulario-publico.png").write_bytes(b"png")


def tipos(inventario: inventario_manual.Inventario, modulo: str) -> list[str]:
    return [lacuna.tipo for lacuna in inventario.modulos[modulo]]


def test_manual_escrito_nao_tem_lacuna(tmp_path):
    montar(tmp_path)
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    assert sorted(inventario.modulos) == sorted(inventario_manual.MODULOS)
    assert inventario.lacunas == []
    assert inventario.fora_de_balde == []


def test_pagina_de_tarefa_sem_video_vira_lacuna_do_modulo(tmp_path):
    montar(tmp_path)
    tarefa = (
        tmp_path
        / "src"
        / "content"
        / "docs"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario.md"
    )
    tarefa.write_text(
        TAREFA.replace("video: registrar-manifestacao-pelo-formulario\n", ""),
        encoding="utf-8",
    )
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    assert tipos(inventario, "ouvidoria") == ["sem-video"]
    assert tipos(inventario, "pops") == []


def test_print_referenciado_que_nao_existe_vira_lacuna(tmp_path):
    """Print some do disco (ou nunca foi gerado) e a página fica com o alt."""
    montar(tmp_path)
    (tmp_path / "src" / "assets" / "ouvidoria" / "formulario-publico.png").unlink()
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    assert tipos(inventario, "ouvidoria") == ["print-faltando"]
    assert "formulario-publico.png" in inventario.lacunas[0].detalhe


def test_prd_entregue_sem_entrada_em_novidades_vira_lacuna(tmp_path):
    """O PRD #706 subiu e a página Novidades da Ouvidoria não conta isso."""
    montar(tmp_path)
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731, 706]})
    assert tipos(inventario, "ouvidoria") == ["prd-sem-novidades"]
    assert "#706" in inventario.lacunas[0].detalhe


def test_modulo_sem_pagina_de_novidades_acusa_cada_prd_entregue(tmp_path):
    montar(tmp_path)
    (tmp_path / "src" / "content" / "docs" / "pops" / "novidades.md").unlink()
    inventario = inventario_manual.inventariar(tmp_path, {"pops": [617]})
    assert tipos(inventario, "pops") == ["prd-sem-novidades"]


def test_pagina_em_draft_de_prd_ja_entregue_vira_lacuna(tmp_path):
    """Draft é o único mecanismo de invisibilidade: esquecido, some do site."""
    montar(tmp_path)
    tarefa = (
        tmp_path
        / "src"
        / "content"
        / "docs"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario.md"
    )
    tarefa.write_text(TAREFA.replace("draft: false", "draft: true"), encoding="utf-8")
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    assert tipos(inventario, "ouvidoria") == ["draft-entregue"]
    assert "#731" in inventario.lacunas[0].detalhe


def test_draft_de_prd_que_ainda_nao_subiu_nao_e_lacuna(tmp_path):
    """Página de funcionalidade não deployada nasce em draft, e está certo."""
    montar(tmp_path)
    tarefa = (
        tmp_path
        / "src"
        / "content"
        / "docs"
        / "ouvidoria"
        / "registrar-manifestacao-pelo-formulario.md"
    )
    tarefa.write_text(TAREFA.replace("draft: false", "draft: true"), encoding="utf-8")
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    inventario_sem = inventario_manual.inventariar(tmp_path, {"ouvidoria": []})
    assert tipos(inventario, "ouvidoria") == ["draft-entregue"]
    assert tipos(inventario_sem, "ouvidoria") == []


def test_pagina_fora_dos_cinco_modulos_nao_fecha_a_conta(tmp_path):
    """Sem módulo, não há terminal que feche a lacuna: a conta não fecha."""
    montar(tmp_path)
    solta = tmp_path / "src" / "content" / "docs" / "tecnologia"
    solta.mkdir()
    (solta / "index.md").write_text(VISAO_GERAL, encoding="utf-8")
    inventario = inventario_manual.inventariar(tmp_path, {"ouvidoria": [731]})
    assert inventario.fora_de_balde == ["tecnologia/index.md"]


def rodar(
    raiz: Path, entregues: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """O inventário como o CI e a skill chamam: o que trava é o código de saída."""
    comando = [sys.executable, str(INVENTARIO), "--dir", str(raiz)]
    if entregues:
        comando += ["--entregues", str(entregues)]
    return subprocess.run(comando, capture_output=True, text=True)


def test_manual_com_lacunas_sai_com_codigo_0(tmp_path):
    """Lacuna é o passivo que a skill divide, não erro: o relatório sai e passa."""
    montar(tmp_path)
    entregues = tmp_path / "entregues.json"
    entregues.write_text(json.dumps({"ouvidoria": [731, 706]}), encoding="utf-8")
    resultado = rodar(tmp_path, entregues)
    assert resultado.returncode == 0, resultado.stderr
    assert "prd-sem-novidades" in resultado.stdout
    assert "5 módulos" in resultado.stdout


def test_pagina_fora_dos_cinco_modulos_sai_com_codigo_1(tmp_path):
    montar(tmp_path)
    solta = tmp_path / "src" / "content" / "docs" / "tecnologia"
    solta.mkdir()
    (solta / "index.md").write_text(VISAO_GERAL, encoding="utf-8")
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "fora dos cinco módulos" in resultado.stderr


def test_manual_sem_pagina_nenhuma_sai_com_codigo_1(tmp_path):
    """Varredura que não achou página nenhuma não pode sair verde sobre nada."""
    (tmp_path / "src" / "content" / "docs").mkdir(parents=True)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 1
    assert "varredura que não rodou" in resultado.stderr


def test_sem_a_lista_de_entregues_o_relatorio_diz_o_que_nao_conferiu(tmp_path):
    """Calar sobre o que não foi conferido é o mesmo que dizer que está limpo."""
    montar(tmp_path)
    resultado = rodar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
    assert "prd-sem-novidades" in resultado.stdout
    assert "NÃO foram conferidas" in resultado.stdout
