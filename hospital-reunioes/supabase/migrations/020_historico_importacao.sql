-- Migration 020: Histórico de importação de ATAs migradas
-- Adiciona metadados de rastreio para exibir "Importações recentes" na UI
-- sem criar tabela dedicada — reuso de reunioes com flag status_ata='MIGRADA'.

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS nome_arquivo_original TEXT,
  ADD COLUMN IF NOT EXISTS importado_por_id VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_reunioes_importado_por
  ON reunioes(importado_por_id) WHERE importado_por_id IS NOT NULL;

COMMENT ON COLUMN reunioes.nome_arquivo_original IS
  'Nome original do arquivo PDF enviado na importação de ATA legada. NULL para reuniões que não vieram de importação.';

COMMENT ON COLUMN reunioes.importado_por_id IS
  'ID do participante (super admin) que executou a importação da ATA legada. NULL para reuniões que não vieram de importação.';
