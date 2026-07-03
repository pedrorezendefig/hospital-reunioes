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
