-- =====================================================
-- Migration 040: Estado terminal APROVADA (aprovação sem ClickSign)
--
-- Issue #26: o Facilitador pode finalizar a Ata sem assinatura digital —
-- as Pendências nascem na hora e a Reunião vai para o estado terminal
-- APROVADA, paralelo a ASSINADA, sem passar pelo ClickSign nem aguardar
-- assinaturas.
--
-- Adiciona 'APROVADA' ao CHECK de reunioes.status_ata (padrão da 016).
-- =====================================================

ALTER TABLE reunioes DROP CONSTRAINT IF EXISTS reunioes_status_ata_check;
ALTER TABLE reunioes ADD CONSTRAINT reunioes_status_ata_check
  CHECK (status_ata IN (
    'PROGRAMADA',
    'PROCESSANDO',
    'ERRO',
    'ERRO_UPLOAD_TRANSCRICAO',
    'ERRO_GERACAO_PDF',
    'ERRO_ENVIO_EMAIL',
    'AGUARDANDO_RESOLUCAO',
    'AGUARDANDO_VALIDACAO',
    'AGUARDANDO_ASSINATURA',
    'ASSINADA',
    'APROVADA',
    'CANCELADA',
    'MIGRADA'
  ));
