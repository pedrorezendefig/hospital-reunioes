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

# O de/para dos capítulos da página antiga (a mesma tabela do PR). A chave é
# o capítulo como estava no sumário; o valor, as páginas que o recebem.
DESTINO_DO_CAPITULO = {
    "0 Como funciona, em uma página": ["index"],
    "1 Onde fica e quem entra": ["index", "cadastrar-um-produto-e-o-dono"],
    "2 Registrar o pedido": [
        "registrar-uma-demanda-pelo-assistente",
        "registrar-uma-demanda-pelo-formulario",
        "como-funciona/os-sete-tipos",
    ],
    "3 O Quadro e o card": ["acompanhar-o-quadro", "mover-concluir-ou-cancelar-uma-demanda"],
    "4 A Conversa dentro do card": ["conversar-na-demanda", "copiar-a-demanda-para-uma-ia"],
    "5 Do pedido ao desenvolvimento": [
        "levar-a-demanda-para-o-desenvolvimento",
        "como-funciona/o-que-vai-para-a-pagina-publica",
    ],
    "6 A Etapa e o O que muda": ["como-funciona/a-etapa-e-o-que-muda"],
    "7 A entrega volta para quem pediu": ["conferir-e-concluir-uma-entrega"],
    "8 O Painel e os e-mails": ["ler-o-painel", "como-funciona/os-e-mails-da-aba"],
    "9 Onde o Quadro para, hoje": ["como-funciona/onde-a-aba-para-hoje"],
    "+ Todos os vídeos": ["index"],
}

RE_IMAGEM = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")


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


class TestOsCapitulosAntigos:
    @pytest.mark.parametrize("capitulo", sorted(DESTINO_DO_CAPITULO))
    def test_cada_capitulo_tem_destino_numa_pagina_que_existe(self, capitulo):
        faltando = [p for p in DESTINO_DO_CAPITULO[capitulo] if not (SECAO / f"{p}.md").is_file()]
        assert faltando == []

    def test_o_planejamento_da_demanda_tem_pagina_propria(self):
        """PRD #1344: a página que a página antiga não tinha."""
        assert (SECAO / "planejar-a-demanda-com-a-ia.md").is_file()


class TestOsPrints:
    def test_ha_paginas_de_tarefa(self):
        """Piso: uma seção sem tarefa nenhuma deixaria o teste de baixo verde
        sem ter olhado para nada."""
        assert len(_paginas_de_tarefa()) >= 10

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
