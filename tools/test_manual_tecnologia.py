"""A Tecnologia vira módulo do Manual do usuário (issue #1367, PRD #1365).

Até aqui a aba tinha página própria, `docs/manual/tecnologia/index.html`,
publicada no projeto `manual-tecnologia-hsm`. Agora ela é a última seção do
site do Manual: abertura, Páginas de tarefa migradas dos capítulos da página
antiga, Como funciona e Novidades. O endereço antigo vira só redirecionamento.

O que dá para provar de um texto curado é a estrutura: a seção está no menu e
no fim dele, cada capítulo antigo tem destino numa página que existe, cada
Página de tarefa tem print e todo print citado existe, e o endereço antigo
manda para a seção nova pelas duas regras (a raiz e o resto).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
MANUAL = RAIZ / "docs" / "manual"
SECAO = MANUAL / "src" / "content" / "docs" / "tecnologia"
REDIRECIONAMENTO = MANUAL / "redirecionamento" / "tecnologia" / "vercel.json"
DESTINO = "https://manual-hsm.vercel.app/tecnologia/"

sys.path.insert(0, str(RAIZ / "tools"))

import inventario_manual  # noqa: E402
import lint_manual  # noqa: E402

RE_IMAGEM = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
RE_NUMERO = re.compile(r"\d+")

# As três Páginas de tarefa que o PRD #1380 manda nascer.
TAREFAS_DO_CHAT = ["relatar-um-bug", "pedir-uma-melhoria", "acompanhar-um-pedido"]
# O Como funciona que o PRD pede: o que a IA consulta, o que vai para a Vitta e o print.
COMO_FUNCIONA_DO_CHAT = ["o-que-a-ia-consulta", "o-que-vai-para-a-vitta"]
NOVIDADE_DO_PRD = (
    "A aba Tecnologia agora é uma conversa: conte o problema ou a melhoria, responda às perguntas "
    "e confirme o resumo. A lista ao lado mostra em que pé está cada pedido."
)
# A tela que saiu no #1386, pelo nome que a página antiga usava.
TELAS_ANTIGAS = {
    "Quadro": re.compile(r"\bQuadro\b"),
    "Painel": re.compile(r"\bPainel\b"),
    "Produtos": re.compile(r"\bProdutos?\b"),
    "formulário": re.compile(r"\bformulário\b", re.IGNORECASE),
    "raia": re.compile(r"\braias?\b", re.IGNORECASE),
    "Planejar com a IA": re.compile(r"Planejar com a IA"),
    "Nova Demanda": re.compile(r"Nova Demanda"),
}


def _telas_antigas(texto: str) -> list[str]:
    return [nome for nome, regra in TELAS_ANTIGAS.items() if regra.search(texto)]


def _pastas_do_menu() -> list[str]:
    return re.findall(r'pasta:\s*"([^"]+)"', (MANUAL / "src" / "modulos.mjs").read_text(encoding="utf-8"))


def _paginas_de_tarefa() -> list[Path]:
    return sorted(p for p in SECAO.glob("*.md") if p.stem not in ("index", "novidades"))


class TestASecaoNoMenu:
    def test_o_detector_le_o_menu(self):
        """Piso do detector: sem ele, uma regex que parasse de casar daria um
        menu vazio e o teste de baixo reprovaria pelo motivo errado."""
        assert len(_pastas_do_menu()) >= 6

    def test_a_tecnologia_e_o_ultimo_modulo_do_menu(self):
        assert _pastas_do_menu()[-1] == "tecnologia"

    def test_o_inventario_do_manual_conta_a_tecnologia(self):
        assert inventario_manual.MODULOS[-1] == "tecnologia"

    @pytest.mark.parametrize("pagina", ["index.md", "novidades.md"])
    def test_a_secao_tem_abertura_e_novidades(self, pagina):
        assert (SECAO / pagina).is_file()


class TestASecaoDoChat:
    """PRD #1380 (ADR 0077): a aba virou o chat do Assistente, e o módulo do
    Manual ensina só ele. As Páginas de tarefa do Quadro, do Painel, dos
    Produtos, do formulário, da Conversa espelhada e do Planejar com a IA saem."""

    @pytest.mark.parametrize("pagina", TAREFAS_DO_CHAT)
    def test_a_tarefa_do_chat_existe_em_draft_e_cita_o_prd(self, pagina):
        campos = lint_manual.ler_frontmatter((SECAO / f"{pagina}.md").read_text(encoding="utf-8"))
        assert campos.get("draft") == "true"
        assert "1380" in RE_NUMERO.findall(campos.get("prd", ""))

    def test_as_tarefas_do_modulo_sao_as_do_chat(self):
        assert [p.stem for p in _paginas_de_tarefa()] == sorted(TAREFAS_DO_CHAT)

    def test_o_detector_de_tela_antiga_ve_cada_termo(self):
        """Piso do detector: cada termo aposentado, escrito como a página
        antiga escrevia, é achado."""
        amostra = (
            "No **Quadro**, abra o **Painel** e a lista de Produtos; preencha o formulário, "
            "mova de raia e clique em **Planejar com a IA**, ou em **Nova Demanda**."
        )
        assert len(_telas_antigas(amostra)) == len(TELAS_ANTIGAS)

    @pytest.mark.parametrize(
        "pagina",
        [str(p.relative_to(SECAO)) for p in sorted(SECAO.rglob("*.md")) if p.name != "novidades.md"] or ["(nenhuma)"],
    )
    def test_nenhuma_pagina_descreve_a_tela_antiga(self, pagina):
        """Novidades fica de fora: é a linha do tempo, e as entregas antigas
        contam o que a aba era quando subiram."""
        visivel = lint_manual.texto_visivel((SECAO / pagina).read_text(encoding="utf-8"))
        assert _telas_antigas(visivel) == []

    @pytest.mark.parametrize("pagina", COMO_FUNCIONA_DO_CHAT)
    def test_o_como_funciona_do_prd_existe_e_cita_o_prd(self, pagina):
        campos = lint_manual.ler_frontmatter((SECAO / "como-funciona" / f"{pagina}.md").read_text(encoding="utf-8"))
        assert "1380" in RE_NUMERO.findall(campos.get("prd", ""))

    def test_novidades_traz_o_texto_do_prd(self):
        texto = (SECAO / "novidades.md").read_text(encoding="utf-8")
        assert "1380" in RE_NUMERO.findall(lint_manual.ler_frontmatter(texto).get("prd", ""))
        corrido = " ".join(lint_manual.texto_visivel(texto).split())
        assert NOVIDADE_DO_PRD in corrido

    def test_o_video_da_abertura_cobre_o_prd(self):
        slug = lint_manual.ler_frontmatter((SECAO / "index.md").read_text(encoding="utf-8")).get("video", "").strip()
        meta = json.loads((MANUAL / "video" / "tecnologia" / slug / "meta.json").read_text(encoding="utf-8"))
        assert 1380 in meta["prds_cobertos"]


class TestOsPrints:
    def test_ha_paginas_de_tarefa(self):
        """Piso: uma seção sem tarefa nenhuma deixaria o teste de baixo verde
        sem ter olhado para nada."""
        assert len(_paginas_de_tarefa()) >= 3

    @pytest.mark.parametrize("pagina", [p.stem for p in _paginas_de_tarefa()] or ["(nenhuma)"])
    def test_toda_pagina_de_tarefa_tem_print_que_existe(self, pagina):
        arquivo = SECAO / f"{pagina}.md"
        imagens = RE_IMAGEM.findall(arquivo.read_text(encoding="utf-8"))
        assert imagens, "Página de tarefa sem print está incompleta"
        assert [i for i in imagens if not (arquivo.parent / i).resolve().is_file()] == []

    def test_o_detector_de_imagem_ve_o_caminho(self):
        assert RE_IMAGEM.findall("1. Clique.\n   ![O Quadro](../../../assets/tecnologia/quadro.png)") == [
            "../../../assets/tecnologia/quadro.png"
        ]


class TestOEnderecoAntigo:
    def _regras(self) -> dict[str, dict]:
        return {r["source"]: r for r in json.loads(REDIRECIONAMENTO.read_text(encoding="utf-8"))["redirects"]}

    @pytest.mark.parametrize("origem", ["/", "/:caminho*"])
    def test_a_raiz_e_o_resto_vao_para_a_secao_nova(self, origem):
        """A raiz precisa de regra própria: o `/:caminho*` sozinho não pega a
        raiz (o 404 da Ouvidoria em 16/09/2026, no README ao lado)."""
        regra = self._regras()[origem]
        assert regra["destination"] == DESTINO
        assert regra["permanent"] is True


class TestAPaginaSeparadaSaiu:
    @pytest.mark.parametrize(
        "caminho",
        [
            "docs/manual/tecnologia",
            "docs/comunicacao/tecnologia/manual-cap-5-vinculo",
            "docs/comunicacao/tecnologia/manual-cap-7-entrega",
        ],
    )
    def test_a_pagina_e_os_videos_dela_nao_estao_no_repositorio(self, caminho):
        assert not (RAIZ / caminho).exists()
