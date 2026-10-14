"""Testes do lint do Manual (tools/lint_manual.py).

Cada teste monta um site mínimo num diretório temporário e roda o lint contra
ele, como o `publicar.sh` e o CI fazem. Os caracteres proibidos entram por
escape (`\u2014`, `\u2013`) para este arquivo não ter nenhum
literal deles.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import lint_manual  # noqa: E402

LINT = Path(__file__).resolve().parent / "lint_manual.py"
TRAVESSAO = "\u2014"
MEIA_RISCA = "\u2013"

PAGINA_VALIDA = """---
title: Registrar uma manifestação
description: Como abrir um caso na Ouvidoria.
prd: [731]
draft: false
papel: [Ouvidoria]
---

## Quando usar

Quando alguém traz uma reclamação pelo telefone.

## Passo a passo

1. Clique em **Nova manifestação**.
2. Escolha o canal de origem.
"""


def escrever(raiz: Path, caminho: str, conteudo: str) -> Path:
    arquivo = raiz / "src" / "content" / "docs" / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_pagina_de_tarefa_no_molde_passa(tmp_path):
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", PAGINA_VALIDA)
    erros, avisos = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []
    assert avisos == []


def test_travessao_no_texto_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace(
            "pelo telefone.", f"pelo telefone {TRAVESSAO} e você registra."
        ),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "registrar-manifestacao.md" in erros[0]


def test_hifen_no_lugar_do_travessao_passa(tmp_path):
    """Mutação da fixture ruim: com hífen, o mesmo texto fica verde."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("pelo telefone.", "pelo telefone - e você registra."),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_meia_risca_no_texto_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("pelo telefone.", f"pelo telefone {MEIA_RISCA} sempre."),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1


def test_jargao_no_texto_visivel_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace(
            "Escolha o canal de origem.", "Escolha o canal de origem no endpoint."
        ),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "endpoint" in erros[0]


def test_jargao_dentro_de_bloco_de_codigo_passa(tmp_path):
    """Bloco de código não é texto visível para quem lê o manual."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA + "\n```bash\ncurl https://exemplo/endpoint\n```\n",
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_palavra_comum_que_contem_jargao_passa(tmp_path):
    """'rapidez' contém 'api'; a regra é palavra inteira, não pedaço."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("Escolha o canal", "Escolha com rapidez o canal"),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_pagina_de_tarefa_sem_prd_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("prd: [731]\n", ""),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    # O marcador inteiro: a cauda fixa da mensagem cita os quatro nomes, entao
    # procurar so "prd" passaria com a lista de faltantes errada.
    assert "frontmatter sem prd" in erros[0]


def test_pagina_de_tarefa_sem_papel_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("papel: [Ouvidoria]\n", ""),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "frontmatter sem papel" in erros[0]


def test_pagina_de_tarefa_sem_draft_trava(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("draft: false\n", ""),
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "frontmatter sem draft" in erros[0]


def test_visao_geral_do_modulo_nao_precisa_de_papel(tmp_path):
    """Selo é da Página de tarefa; a Visão geral do módulo não tem quem faz."""
    escrever(
        tmp_path,
        "ouvidoria/index.md",
        """---
title: Ouvidoria
description: O que o módulo faz.
prd: [731]
draft: true
---

O módulo da Ouvidoria recebe as manifestações de quem passa pelo hospital.
""",
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_home_do_site_nao_precisa_de_prd_nem_papel(tmp_path):
    escrever(
        tmp_path,
        "index.mdx",
        """---
title: Manual da plataforma
template: splash
---

Escolha o módulo.
""",
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_pagina_de_tarefa_longa_avisa_sem_travar(tmp_path):
    """300 palavras passam do teto de 250: é aviso, não trava a publicação."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA + "\n" + ("palavra " * 300),
    )
    erros, avisos = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []
    assert len(avisos) == 1
    assert "250" in avisos[0]


def rodar(pasta: Path) -> subprocess.CompletedProcess[str]:
    """O lint como o CI chama: pela linha de comando, olhando o código de saída."""
    return subprocess.run(
        [sys.executable, str(LINT), "--dir", str(pasta)],
        capture_output=True,
        text=True,
    )


def test_pagina_ruim_sai_com_codigo_1(tmp_path):
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA.replace("pelo telefone.", f"pelo telefone {TRAVESSAO} sempre."),
    )
    resultado = rodar(tmp_path / "src" / "content" / "docs")
    assert resultado.returncode == 1
    assert "Lint do Manual falhou" in resultado.stderr


def test_site_limpo_sai_com_codigo_0(tmp_path):
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", PAGINA_VALIDA)
    resultado = rodar(tmp_path / "src" / "content" / "docs")
    assert resultado.returncode == 0, resultado.stderr


def test_pasta_inexistente_sai_com_codigo_1(tmp_path):
    resultado = rodar(tmp_path / "nao-existe")
    assert resultado.returncode == 1


FRONTMATTER_DE_TAREFA = """---
title: Registrar uma manifestação
description: Como abrir um caso na Ouvidoria.
prd: [731]
draft: false
papel: [Ouvidoria]
---

"""


def test_alternativo_da_imagem_nao_conta_no_teto(tmp_path):
    """240 palavras de texto e 30 de alternativo: ninguém lê o `alt`.

    Com três Prints de passo por página, o alternativo sozinho empurraria toda
    Página de tarefa para o aviso (ADR 0057, emenda de 17/09/2026, decisão 10).
    """
    alt = " ".join(["figura"] * 30)
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        FRONTMATTER_DE_TAREFA
        + " ".join(["palavra"] * 240)
        + f"\n\n![{alt}](../../../assets/ouvidoria/painel.png)\n",
    )
    erros, avisos = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []
    assert avisos == []


def test_as_mesmas_30_palavras_no_corpo_avisam(tmp_path):
    """Mutação da fixture: o que muda é estar no `alt`, não o total de palavras."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        FRONTMATTER_DE_TAREFA + " ".join(["palavra"] * 270) + "\n",
    )
    erros, avisos = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []
    assert len(avisos) == 1
    assert "270 palavras" in avisos[0]


def test_jargao_dentro_do_alternativo_continua_travando(tmp_path):
    """O leitor de tela lê o `alt`: sai da contagem, não da varredura de jargão."""
    escrever(
        tmp_path,
        "ouvidoria/registrar-manifestacao.md",
        PAGINA_VALIDA
        + "\n![Tela do endpoint da Ouvidoria](../../../assets/ouvidoria/painel.png)\n",
    )
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "endpoint" in erros[0]


# Cacoetes regexáveis de texto gerado (ADR 0071, decisão 1). A lista mora em
# tools/tells_texto.py; aqui só se prova que o lint do Manual a chama.
CONTRASTE = "A ata não é um resumo, é a memória da reunião."
CORRIGIDA = "A ata guarda o que a reunião decidiu."


def pagina_com(frase: str) -> str:
    return PAGINA_VALIDA.replace("pelo telefone.", f"pelo telefone. {frase}")


def test_contraste_nao_e_x_e_y_reprova_a_pagina(tmp_path):
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CONTRASTE))
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert len(erros) == 1
    assert "registrar-manifestacao.md" in erros[0]
    assert '(nao-e-x-e-y): "não é um resumo, é"' in erros[0]


def test_a_mesma_pagina_corrigida_passa(tmp_path):
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CORRIGIDA))
    erros, _ = lint_manual.checar(tmp_path / "src" / "content" / "docs")
    assert erros == []


def test_contraste_pela_linha_de_comando_sai_com_codigo_1(tmp_path):
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CONTRASTE))
    resultado = rodar(tmp_path / "src" / "content" / "docs")
    assert resultado.returncode == 1
    assert "(nao-e-x-e-y)" in resultado.stderr


def test_cacoete_conhecido_passa_e_avisa_quando_sai(tmp_path):
    """A lista de conhecidos segura o que já estava no ar até a reescrita."""
    pasta = tmp_path / "src" / "content" / "docs"
    conhecidos = {"ouvidoria/registrar-manifestacao.md": ["não é um resumo, é"]}
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CONTRASTE))
    erros, avisos = lint_manual.checar(pasta, conhecidos)
    assert erros == []
    assert avisos == []

    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CORRIGIDA))
    erros, avisos = lint_manual.checar(pasta, conhecidos)
    assert erros == []
    assert len(avisos) == 1
    assert 'cacoete conhecido "não é um resumo, é" já saiu' in avisos[0]


def test_conhecido_de_outra_pagina_nao_segura(tmp_path):
    pasta = tmp_path / "src" / "content" / "docs"
    conhecidos = {"ouvidoria/outra-pagina.md": ["não é um resumo, é"]}
    escrever(tmp_path, "ouvidoria/registrar-manifestacao.md", pagina_com(CONTRASTE))
    erros, _ = lint_manual.checar(pasta, conhecidos)
    assert len(erros) == 1


def test_os_conhecidos_do_manual_atual_seguram_o_que_esta_no_ar():
    """O Manual de hoje passa com a lista; a reescrita por módulo a esvazia."""
    raiz = Path(__file__).resolve().parent.parent
    resultado = subprocess.run(
        [sys.executable, str(LINT), "--dir", "docs/manual/src/content/docs"],
        cwd=raiz,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
