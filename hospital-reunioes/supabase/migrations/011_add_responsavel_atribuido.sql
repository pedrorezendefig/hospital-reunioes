-- =====================================================
-- Migration 011: Adicionar RESPONSAVEL_ATRIBUIDO ao CHECK de notificacoes.tipo
-- Necessário para notificações de atribuição de responsável em pendências
-- =====================================================

-- Remove o CHECK constraint existente e recria com o novo valor
ALTER TABLE notificacoes DROP CONSTRAINT IF EXISTS notificacoes_tipo_check;

ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_tipo_check
  CHECK (tipo IN (
    'MENCAO',
    'STATUS_ALTERADO',
    'COMENTARIO',
    'PRAZO_PROXIMO',
    'RESPONSAVEL_ATRIBUIDO'
  ));
