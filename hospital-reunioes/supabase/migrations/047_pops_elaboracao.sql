-- =====================================================
-- Migration 047: POPs L1 — elaboração (issue #83, PRD #76)
-- =====================================================
-- A Elaboração com agente de IA (docs/pops/CONTEXT.md):
--   1. rascunho — o POP vivo: as seções de conteúdo do template institucional
--      (DRF §4.2) tomando forma na conversa. Diferença deliberada da Ata
--      Guiada: PERSISTE na Versão a cada interação (elaboração dura dias;
--      reabrir a tela recupera o estado). O histórico do chat é efêmero.
--      A seção 1 (Identificação) NÃO vive aqui — deriva do POP (código
--      travado, nome, setor, responsáveis), imune ao agente.
--   2. periodicidade_sugerida — a sugestão do agente, gravada para auditoria
--      da decisão; a escolha final do Elaborador vive em
--      pops.periodicidade_revisao (campo institucional já existente).
-- =====================================================

ALTER TABLE pops_versoes
  ADD COLUMN IF NOT EXISTS rascunho JSONB,
  ADD COLUMN IF NOT EXISTS periodicidade_sugerida TEXT
    CHECK (periodicidade_sugerida IN ('3_meses', '6_meses', '1_ano', '2_anos'));
