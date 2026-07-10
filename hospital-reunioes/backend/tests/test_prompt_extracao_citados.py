"""Testes de contrato dos prompts de extração de ata (issue #204).

Ajuste leve e cirúrgico nos dois prompts de extração para reduzir a inclusão
indevida de pessoas apenas citadas na transcrição como se fossem participantes:

1. `user_extracao.md` perde o incentivo contraditório que mandava "incluir
   normalmente" no campo "participantes" quem não estivesse na lista de
   pré-cadastrados, mesmo que a pessoa tivesse sido apenas citada.
2. `extracao_ata.md` (system prompt) reforça, em mais de um ponto, que só
   quem participou da reunião entra em `participantes`; quem foi apenas
   citado/mencionado fica em `discussao`/`contribuicoes`.

É mitigação, não substitui o controle manual do Facilitador. Não muda schema
nem contrato de saída da IA. Testes leem os arquivos .md direto, sem chamar IA.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.prompt_loader import load_prompt  # noqa: E402

PROMPT_USER = load_prompt("user_extracao")
PROMPT_SYSTEM = load_prompt("extracao_ata")


class TestIncentivoContraditorioRemovido:
    """O prompt de usuário não manda mais incluir quem só foi citado (#204)."""

    def test_nao_manda_incluir_normalmente_quem_nao_esta_na_lista(self):
        # Frase original do bug: mandava incluir "normalmente" qualquer pessoa
        # mencionada que não estivesse nos pré-cadastrados, citada ou não.
        assert "inclua-o normalmente" not in PROMPT_USER

    def test_prompt_de_usuario_orienta_excluir_quem_foi_so_citado(self):
        assert "Não inclua quem foi apenas citado ou mencionado" in PROMPT_USER


class TestSystemPromptReforcaRegraDeParticipantes:
    """O system prompt deixa inequívoco que citados não entram em participantes (#204)."""

    def test_definicao_da_secao_participantes_exclui_citados(self):
        assert "Quem foi apenas citado ou mencionado na conversa NÃO entra" in PROMPT_SYSTEM

    def test_regra_critica_de_exclusao_de_citados_presente(self):
        assert "REGRA CRÍTICA" in PROMPT_SYSTEM
        assert "NÃO a inclua" in PROMPT_SYSTEM
        # Vale mesmo se a pessoa constar no diretório: citação não é participação.
        assert "mesmo que ela conste no diretório" in PROMPT_SYSTEM


class TestContratoDeSaidaInalterado:
    """Ajuste é só de prompt: schema/contrato de saída da IA não muda (#204)."""

    def test_schema_de_participantes_nao_muda(self):
        assert (
            '{{"nome": "nome completo", "cargo": "cargo", "setor": "setor ou null", "presente": true}}' in PROMPT_SYSTEM
        )
