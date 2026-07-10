"""Testes do system prompt ÚNICO da Elaboração (ADR 0021, issue #188).

O ADR 0021 reverte a composição por Natureza (ADR 0018, superseded): os quatro
arquivos da composição (bloco da Natureza + índice + refino + núcleo) colapsam
de volta em um único `chat_elaboracao_pop_system.md`, que ganha quatro reforços:

1. referência normativa compacta das três áreas (assistencial, administrativa,
   de apoio), destilada da curadoria das fatias #171/#172;
2. interpretação rasa do Setor pelo NOME (que já viaja no contexto), sem
   classificação persistida;
3. fidelidade reforçada ao modelo anexado (Material de referência), acima de
   qualquer template;
4. Fluxograma obrigatório em todo rascunho, única exceção à fidelidade
   (emenda ao ADR 0016).

Testes unit: leem o prompt e o módulo direto, sem IA.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import ai_processor  # noqa: E402
from app.services.prompt_loader import PROMPTS_DIR, load_prompt  # noqa: E402

PROMPT = load_prompt("chat_elaboracao_pop_system")


class TestComposicaoPorNaturezaRemovida:
    """A montagem por Natureza some do serviço de IA (ADR 0021)."""

    def test_funcao_de_composicao_nao_existe_mais(self):
        assert not hasattr(ai_processor, "montar_system_elaboracao")
        assert not hasattr(ai_processor, "NATUREZAS_ELABORACAO")

    def test_arquivos_da_composicao_colapsaram_no_unico(self):
        # Os quatro papéis da composição (3 blocos de Natureza, o índice e o
        # refino) saem do repositório; só o arquivo único permanece.
        for nome in (
            "chat_elaboracao_pop_natureza_assistencial",
            "chat_elaboracao_pop_natureza_administrativa",
            "chat_elaboracao_pop_natureza_apoio",
            "chat_elaboracao_pop_naturezas_indice",
            "chat_elaboracao_pop_refino",
        ):
            assert not (PROMPTS_DIR / f"{nome}.md").exists(), f"arquivo da composição ainda existe: {nome}.md"
        assert (PROMPTS_DIR / "chat_elaboracao_pop_system.md").exists()


class TestNucleoPreservado:
    """O núcleo do prompt (ADR 0016/0017/0013) sobrevive ao colapso."""

    def test_persona_e_estrutura_dinamica(self):
        # Persona de consultor de qualidade (ONA/JCI) volta ao arquivo único.
        assert "ONA" in PROMPT
        assert "JCI" in PROMPT
        # Estrutura dinâmica e contrato JSON.
        assert "A estrutura do POP é DINÂMICA" in PROMPT
        assert "Formato de Resposta" in PROMPT
        # Estrutura institucional de partida (sem modelo anexado).
        for trecho in ("Objetivo", "Responsabilidades", "Descrição do procedimento", "Referências normativas"):
            assert trecho in PROMPT, f"seção institucional ausente: {trecho}"

    def test_tipografia_sem_travessao_na_instrucao_e_no_texto(self):
        # A instrução do ADR 0013 permanece, e o próprio prompt a obedece.
        assert "travessão" in PROMPT
        assert "—" not in PROMPT, "o prompt contém travessão (U+2014)"
        assert "–" not in PROMPT, "o prompt contém meia-risca (U+2013)"


class TestReferenciaNormativaCompacta:
    """Reforço 1: as três áreas, destiladas da curadoria de #171/#172, vivem
    juntas no prompt único (a rede contra o viés assistencial, ADR 0021)."""

    def test_area_assistencial(self):
        assert "assistencial" in PROMPT.lower()
        assert "ANVISA" in PROMPT
        assert "CFM" in PROMPT
        assert "COFEN" in PROMPT

    def test_area_administrativa(self):
        assert "administrativa" in PROMPT.lower()
        assert "CLT" in PROMPT
        assert "eSocial" in PROMPT
        assert "glosa" in PROMPT.lower()

    def test_area_de_apoio(self):
        assert "apoio" in PROMPT.lower()
        assert "biossegurança" in PROMPT.lower()
        assert "ABNT" in PROMPT
        assert "sanitár" in PROMPT.lower()


class TestInterpretacaoDoSetorPeloNome:
    """Reforço 2: a IA infere a área pelo NOME do Setor que chega no contexto,
    sem classificação persistida (interpretação rasa, ADR 0021)."""

    def test_prompt_orienta_inferir_area_pelo_nome_do_setor(self):
        prompt_lower = PROMPT.lower()
        assert "nome do setor" in prompt_lower
        assert "interprete" in prompt_lower or "infira" in prompt_lower

    def test_objetivo_do_procedimento_refina_a_area(self):
        # O refino pelo objetivo (herdado da composição) segue: procedimento
        # que destoa da área do Setor adapta e sinaliza, sem travar.
        prompt_lower = PROMPT.lower()
        assert "destoa" in prompt_lower
        assert "sinaliz" in prompt_lower


class TestFidelidadeAoModeloAnexado:
    """Reforço 3: a estrutura obedece FIELMENTE ao Material de referência com
    modelo (ordem, títulos, conteúdo), acima de qualquer template."""

    def test_fidelidade_reforcada(self):
        prompt_lower = PROMPT.lower()
        assert "fielmente" in prompt_lower
        assert "modelo" in prompt_lower
        # Sem modelo, o template institucional é o ponto de partida.
        assert "estrutura institucional" in prompt_lower


class TestFluxogramaObrigatorio:
    """Reforço 4: todo rascunho sai com a seção de Fluxograma, mesmo quando o
    modelo anexado não traz uma. Única exceção à fidelidade (emenda ao ADR
    0016). Desde o ADR 0024 a seção carrega a gramática JSON, não Mermaid."""

    def test_fluxograma_sempre_presente_mesmo_sem_secao_no_modelo(self):
        prompt_lower = PROMPT.lower()
        assert "fluxograma" in prompt_lower
        assert "obrigat" in prompt_lower
        assert "mesmo quando o modelo anexado" in prompt_lower

    def test_fluxograma_e_a_unica_excecao_a_fidelidade(self):
        assert "única exceção" in PROMPT.lower()

    def test_gramatica_json_substitui_as_convencoes_mermaid(self):
        """ADR 0024: as convenções Mermaid saem; entra a gramática JSON com um
        exemplo completo (nos, decisão com 2 ramos, desvio com retorno)."""
        assert "Mermaid" not in PROMPT
        assert "flowchart" not in PROMPT.lower()
        assert '"nos"' in PROMPT
        assert '"decisao"' in PROMPT
        assert '"ramos"' in PROMPT
        assert "retorna_para" in PROMPT
        # O exemplo completo do PRD #210 está no prompt.
        assert "Material completo?" in PROMPT
