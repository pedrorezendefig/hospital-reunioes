-- =====================================================
-- Migration 048: POPs L1 — revisão e validação (issue #85, PRD #76)
-- =====================================================
-- A Devolução (docs/pops/CONTEXT.md): ato de Revisor ou Validador
-- retornarem a Versão ao Elaborador com comentários, registrados com
-- autor e timestamp — visíveis na elaboração e no contexto do agente.
-- A Devolução grava a ETAPA DE RETORNO: no reenvio, a Versão volta
-- direto a quem devolveu (Devolução do Validador não repassa pelo
-- Revisor — decisão do grilling). Sem limite de ciclos.
--
-- As transições em si (EM_REVISAO → EM_VALIDACAO → EM_ASSINATURA e as
-- devoluções → EM_ELABORACAO) usam o enum completo criado na 046 — a
-- máquina de estados vive no módulo de domínio da aplicação.
-- =====================================================

CREATE TABLE IF NOT EXISTS pops_devolucoes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  versao_id     UUID NOT NULL REFERENCES pops_versoes(id) ON DELETE CASCADE,
  autor_id      VARCHAR(10) NOT NULL REFERENCES participantes(id),
  etapa_retorno TEXT NOT NULL CHECK (etapa_retorno IN ('EM_REVISAO', 'EM_VALIDACAO')),
  comentarios   TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pops_devolucoes_versao ON pops_devolucoes(versao_id);
