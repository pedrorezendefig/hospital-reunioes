"""A reescrita única da seção Valor entregue dos PRs da janela do Hospital OS
(issue #1222, ADR 0071, decisão 4).

O par Antes e Depois vira o parágrafo "O que muda"; `Closes #N`, a seção de
migration conferida por hash e o resto do corpo ficam byte a byte iguais. A
transformação é pura (sem API); o `main` recebe o `gh` por injeção, e o teste
do `--dry-run` confere que nenhuma chamada de escrita sai.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reescrever_valor_entregue as rv  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "workflow-dashboard"))
from collect import resumo_funcional  # noqa: E402

PARAGRAFO = "o secretário baixa a Ata pronta em PDF com um clique e manda por email."

CABECA = "<!-- automacao -->\nCloses #812\n\n"
VALOR_ANTIGO = "## 💬 Valor entregue\n\n**Antes:** a Ata saía só na tela.\n**Depois:** a Ata sai em PDF.\n\n"
RESTO = (
    "## 🎯 Contexto\n\nO secretário copiava a Ata para o Word.\n\n"
    "## 🗄️ Migration\n\n"
    "sha256 `9f2c1e0b7a`, conferido contra `hospital-reunioes/supabase/migrations/151_ata_pdf.sql`\n\n"
    "```sql\nALTER TABLE atas ADD COLUMN pdf_path text;\n```\n\n"
    "## Closes\n\nCloses #812\n"
)
CORPO_ANTIGO = CABECA + VALOR_ANTIGO + RESTO


def test_antes_e_depois_viram_o_que_muda_e_o_resto_fica_igual():
    novo = rv.reescrever_corpo(CORPO_ANTIGO, PARAGRAFO)

    assert novo == CABECA + "## 💬 Valor entregue\n\n**O que muda:** " + PARAGRAFO + "\n\n" + RESTO
    # o hover do Hospital OS lê o parágrafo novo
    assert resumo_funcional(novo)["o_que_muda"] == PARAGRAFO


def test_antes_e_depois_separados_por_linha_em_branco_viram_um_paragrafo_so():
    corpo = "## 💬 Valor entregue\n\n**Antes:** a.\n\n**Depois:** b.\n\n" + RESTO

    novo = rv.reescrever_corpo(corpo, PARAGRAFO)

    assert novo == "## 💬 Valor entregue\n\n**O que muda:** " + PARAGRAFO + "\n\n" + RESTO


def test_pr_sem_a_secao_ganha_valor_entregue_logo_abaixo_do_marcador():
    corpo = "<!-- automacao -->\nRegistro do deploy de producao.\n\nCloses #942\n"

    novo = rv.reescrever_corpo(corpo, PARAGRAFO)

    assert novo == (
        "<!-- automacao -->\n## 💬 Valor entregue\n\n**O que muda:** "
        + PARAGRAFO
        + "\n\nRegistro do deploy de producao.\n\nCloses #942\n"
    )
    assert resumo_funcional(novo)["o_que_muda"] == PARAGRAFO


class GhFalso:
    """O `gh` da janela: lista os corpos e guarda cada PATCH no lugar do GitHub."""

    def __init__(self, corpos: dict[int, str]):
        self.corpos = dict(corpos)
        self.escritas: list[int] = []

    def __call__(self, args: list[str], entrada: str | None = None) -> str:
        if args[:2] == ["pr", "list"]:
            return json.dumps([{"number": n, "body": b} for n, b in self.corpos.items()])
        if args[:3] == ["api", "-X", "PATCH"]:
            numero = int(args[3].rsplit("/", 1)[1])
            self.escritas.append(numero)
            self.corpos[numero] = json.loads(entrada)["body"]
            return "{}"
        raise AssertionError(f"chamada inesperada ao gh: {args}")


def _paragrafos(tmp_path: Path) -> str:
    arquivo = tmp_path / "paragrafos.json"
    arquivo.write_text(json.dumps({"812": PARAGRAFO, "900": "outro parágrafo."}), encoding="utf-8")
    return str(arquivo)


def test_pr_ja_reescrito_e_pulado_na_segunda_execucao(tmp_path, capsys):
    ja_feito = rv.reescrever_corpo(CORPO_ANTIGO, "outro parágrafo.")
    gh = GhFalso({812: CORPO_ANTIGO, 900: ja_feito})

    assert rv.main(["--paragrafos", _paragrafos(tmp_path)], gh=gh) == 0
    assert gh.escritas == [812]
    assert resumo_funcional(gh.corpos[812])["o_que_muda"] == PARAGRAFO
    assert gh.corpos[900] == ja_feito

    # segunda execução: os dois já têm o parágrafo, ninguém é gravado
    assert rv.main(["--paragrafos", _paragrafos(tmp_path)], gh=gh) == 0
    assert gh.escritas == [812]
    assert "#812: já reescrito" in capsys.readouterr().out


def test_dry_run_imprime_o_diff_por_pr_e_nao_grava(tmp_path, capsys):
    gh = GhFalso({812: CORPO_ANTIGO, 900: "<!-- automacao -->\nCloses #942\n"})

    assert rv.main(["--paragrafos", _paragrafos(tmp_path), "--dry-run"], gh=gh) == 0

    saida = capsys.readouterr().out
    assert gh.escritas == []
    assert gh.corpos[812] == CORPO_ANTIGO
    assert "--- PR #812 (atual)" in saida and "+++ PR #812 (novo)" in saida
    assert "-**Antes:** a Ata saía só na tela." in saida
    assert "+**O que muda:** " + PARAGRAFO in saida
    assert "+++ PR #900 (novo)" in saida and "+**O que muda:** outro parágrafo." in saida
    # o resto do corpo não aparece como mudança
    assert "-Closes #812" not in saida and "+Closes #812" not in saida


def test_pr_sem_paragrafo_no_arquivo_nao_e_gravado_e_a_saida_acusa(tmp_path, capsys):
    gh = GhFalso({812: CORPO_ANTIGO, 777: CORPO_ANTIGO})

    assert rv.main(["--paragrafos", _paragrafos(tmp_path)], gh=gh) == 1
    assert gh.escritas == [812]
    assert "#777: sem parágrafo" in capsys.readouterr().out
