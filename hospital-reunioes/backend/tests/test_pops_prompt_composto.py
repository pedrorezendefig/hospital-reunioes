"""Testes da composição do system prompt da Elaboração por Natureza (ADR 0018).

O prompt deixou de ser um texto único ("consultor ONA/JCI" hardcoded) e passa a
ser montado por composição: núcleo comum + bloco da Natureza do Setor + índice
compacto das três Naturezas + instrução de refino. Nesta fatia só o bloco
assistencial é detalhado; administrativa e apoio entram como stubs curtos, a
detalhar nas fatias seguintes. Testes unit: chamam a função direto, sem IA.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_processor import montar_system_elaboracao  # noqa: E402


class TestComposicaoSystemPrompt:
    def test_assistencial_compoe_nucleo_bloco_indice_refino(self):
        prompt = montar_system_elaboracao("assistencial")
        # Núcleo comum (estrutura dinâmica do ADR 0016, contrato JSON, tipografia).
        assert "A estrutura do POP é DINÂMICA" in prompt
        assert "Formato de Resposta" in prompt
        assert "travessão" in prompt
        # Bloco assistencial como persona primária (ONA/JCI e corpo de normas).
        assert "ONA" in prompt
        assert "JCI" in prompt
        # Índice compacto das outras duas Naturezas.
        assert "administrativa" in prompt
        assert "apoio" in prompt
        # Instrução de refino: adaptar ao objetivo e sinalizar a divergência.
        prompt_lower = prompt.lower()
        assert "adapt" in prompt_lower or "destoa" in prompt_lower
        assert "sinaliz" in prompt_lower

    def test_administrativa_troca_persona_e_mantem_nucleo(self):
        # Especialização real (ADR 0018): um Setor administrativo não recebe a
        # persona assistencial hardcoded; recebe a sua, sobre o mesmo núcleo.
        prompt = montar_system_elaboracao("administrativa")
        assert "melhores hospitais acreditados do país" not in prompt
        assert "ONA Nível 3" not in prompt
        assert "processos administrativos" in prompt
        assert "trabalhistas" in prompt
        # O núcleo comum é o mesmo, seja qual for a Natureza.
        assert "A estrutura do POP é DINÂMICA" in prompt
        assert "Formato de Resposta" in prompt

    def test_natureza_desconhecida_cai_em_assistencial(self):
        # Setor sem Natureza (None) ou valor inesperado usa a persona assistencial,
        # âncora dos Setores existentes por backfill: nunca fica sem persona.
        for valor in (None, "financeira", ""):
            prompt = montar_system_elaboracao(valor)
            assert "melhores hospitais acreditados do país" in prompt


class TestBlocoAdministrativoDetalhado:
    """Fatia #171: o bloco administrativo deixa de ser stub (só persona) e ganha
    o corpo de normas detalhado. Ainda é composição pura (sem IA): checa que o
    corpo administrativo entra e não vaza para as outras Naturezas."""

    def test_administrativa_corpo_de_normas_presente(self):
        prompt = montar_system_elaboracao("administrativa")
        # A persona administrativa segue primária (não a assistencial hardcoded).
        assert "processos administrativos" in prompt
        assert "melhores hospitais acreditados do país" not in prompt
        # Corpo de normas administrativo: as famílias que o CONTEXT.md lista para
        # a Natureza administrativa (trabalhista/CLT, eSocial, faturamento, compras).
        assert "CLT" in prompt
        assert "eSocial" in prompt
        assert "trabalhistas" in prompt
        assert "Departamento de Pessoal" in prompt
        assert "glosa" in prompt.lower()
        assert "alçada" in prompt.lower() or "segregação de funções" in prompt.lower()
        # O núcleo comum segue montado junto do bloco detalhado.
        assert "A estrutura do POP é DINÂMICA" in prompt
        assert "Formato de Resposta" in prompt

    def test_corpo_administrativo_nao_vaza_para_assistencial(self):
        # As marcas do corpo administrativo (CLT, eSocial, glosa) pertencem ao
        # bloco da Natureza administrativa: quando a persona é assistencial elas
        # somem. O índice das três cita os setores administrativos, mas não o
        # corpo trabalhista/de faturamento.
        prompt = montar_system_elaboracao("assistencial")
        assert "CLT" not in prompt
        assert "eSocial" not in prompt
        assert "glosa" not in prompt.lower()


class TestComposicaoApoio:
    """Bloco de apoio detalhado do agente de Elaboração (ADR 0018, issue #172).

    O bloco de apoio deixa de ser um stub de um parágrafo: ganha a persona de
    consultor de serviços de apoio (técnicos e logísticos) e um corpo de normas
    derivado do que o docs/pops/CONTEXT.md lista para a Natureza de apoio (normas
    sanitárias, biossegurança, ABNT; higienização, manutenção predial, lavanderia,
    resíduos). Testes unit: chamam a composição direto, sem IA.
    """

    def test_apoio_persona_primaria(self):
        # Natureza apoio: o bloco de apoio é a persona PRIMÁRIA do prompt, sobre o
        # mesmo núcleo comum; as personas assistencial e administrativa não entram
        # como assinatura primária.
        prompt = montar_system_elaboracao("apoio")
        # Persona e corpo de normas de apoio (marcadores exclusivos do bloco:
        # ausentes do índice, do refino e do núcleo comum).
        assert "serviços de apoio" in prompt
        assert "biossegurança" in prompt
        assert "ABNT" in prompt
        assert "sanitár" in prompt  # normas sanitárias
        assert "resíduo" in prompt  # gerenciamento de resíduos de serviços de saúde
        assert "higienização" in prompt
        # Núcleo comum preservado (estrutura dinâmica, contrato JSON, tipografia).
        assert "A estrutura do POP é DINÂMICA" in prompt
        assert "Formato de Resposta" in prompt
        assert "travessão" in prompt
        # As outras personas não são a persona primária: suas assinaturas, que só
        # existem nos respectivos blocos, não entram num prompt de apoio.
        assert "melhores hospitais acreditados do país" not in prompt  # assistencial
        assert "processos administrativos" not in prompt  # administrativa

    def test_apoio_bloco_detalhado_nao_e_mais_stub(self):
        # O bloco em si (não o prompt composto) carrega um corpo de normas
        # seccionado, bem além do stub de persona de uma frase que #170 deixou.
        from app.services.prompt_loader import load_prompt

        bloco = load_prompt("chat_elaboracao_pop_natureza_apoio")
        assert "##" in bloco, "o bloco de apoio deve ter um corpo de normas seccionado"
        assert len(bloco) > 900, "o bloco de apoio deve ir bem além do stub de uma frase"
        # Temas do domínio de apoio, derivados do CONTEXT.md (apoio).
        for marcador in ("serviços de apoio", "biossegurança", "ABNT", "sanitár", "higienização", "resíduo"):
            assert marcador in bloco, f"tema de apoio ausente do bloco: {marcador}"

    def test_assistencial_indice_contem_apoio_e_refino(self):
        # Caso de borda (ADR 0018): uma higienização de superfície redigida num
        # Setor assistencial. O prompt assistencial já traz (desde #170) o índice
        # com a entrada de apoio e a instrução de refino, que juntos deixam o
        # agente adaptar ao objetivo e sinalizar sem trocar a Natureza do Setor.
        prompt = montar_system_elaboracao("assistencial")
        # Índice das três Naturezas lista a Natureza de apoio.
        assert "de apoio" in prompt
        assert "suporte técnico e logístico" in prompt
        # Refino pelo objetivo: adaptar e sinalizar a divergência.
        prompt_lower = prompt.lower()
        assert "destoa" in prompt_lower
        assert "sinaliz" in prompt_lower
