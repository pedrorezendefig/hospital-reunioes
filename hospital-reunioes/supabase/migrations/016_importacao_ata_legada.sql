-- =====================================================
-- Migration 016: Importação de ATAs antigas (migradas do sistema antigo)
--
-- Adiciona:
--   • fonte='IMPORTACAO_LEGADA' no CHECK de reunioes.fonte
--   • status_ata='MIGRADA' no CHECK de reunioes.status_ata
--   • reunioes.documento_id_origem (TEXT) — id do documento no sistema antigo
--     (ex: ATA-ALIN-HSM-190326 extraído do cabeçalho do PDF)
--   • reunioes.arquivo_hash (TEXT) — SHA-256 do PDF importado
--   • Índices únicos parciais para deduplicação
--
-- ATAs MIGRADA já foram assinadas no sistema antigo; não passam pelo
-- ClickSign nem pelo pipeline de validação. Pendências ficam ativas
-- desde a criação.
-- =====================================================

-- 1. Expandir CHECK de fonte (preservar FIREFLIES e MOCK)
ALTER TABLE reunioes DROP CONSTRAINT IF EXISTS reunioes_fonte_check;
ALTER TABLE reunioes ADD CONSTRAINT reunioes_fonte_check
  CHECK (fonte IN ('FIREFLIES', 'MOCK', 'IMPORTACAO_LEGADA'));

-- 2. Expandir CHECK de status_ata (preservar todos os 11 valores + MIGRADA)
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
    'CANCELADA',
    'MIGRADA'
  ));

-- 3. Colunas para deduplicação e rastreio da origem
ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS documento_id_origem TEXT,
  ADD COLUMN IF NOT EXISTS arquivo_hash TEXT;

COMMENT ON COLUMN reunioes.documento_id_origem IS
  'ID do documento no sistema antigo (ex: ATA-ALIN-HSM-190326). NULL para reuniões nativas.';

COMMENT ON COLUMN reunioes.arquivo_hash IS
  'SHA-256 hex do PDF importado. NULL para reuniões nativas.';

-- 4. Índices únicos parciais (só vigoram quando coluna não é NULL)
CREATE UNIQUE INDEX IF NOT EXISTS idx_reunioes_documento_id_origem
  ON reunioes(documento_id_origem)
  WHERE documento_id_origem IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_reunioes_arquivo_hash
  ON reunioes(arquivo_hash)
  WHERE arquivo_hash IS NOT NULL;
