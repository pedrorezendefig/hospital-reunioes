-- =====================================================
-- Migration 030: Soft delete em reunioes e pendencias
--
-- Motivação (Fase 3 do super-admin CRUD): ata assinada e imutavel por
-- compliance (nao-repudio), mas o super-admin precisa poder arquivar
-- entradas erradas sem perder historico. Solucao: coluna deleted_at
-- TIMESTAMPTZ em reunioes e pendencias. Consultas normais filtram
-- `deleted_at IS NULL`. Admin pode ver arquivadas via toggle e
-- restaurar (seta NULL de volta).
--
-- Index parcial acelera a listagem normal (a clausula WHERE limita a
-- arvore para so as linhas "vivas"), que sao a vasta maioria.
--
-- Reversível via: ALTER TABLE ... DROP COLUMN deleted_at.
-- =====================================================

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

ALTER TABLE pendencias
  ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

-- Index parcial para consultas "vivas" (99% dos casos).
CREATE INDEX IF NOT EXISTS idx_reunioes_live
  ON reunioes(data DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pendencias_live
  ON pendencias(prazo) WHERE deleted_at IS NULL;

COMMENT ON COLUMN reunioes.deleted_at IS
  'Soft delete. NULL = viva, timestamp = arquivada em. Listagens normais filtram NULL; admin inclui arquivadas via toggle.';
COMMENT ON COLUMN pendencias.deleted_at IS
  'Soft delete. NULL = viva, timestamp = arquivada em. Listagens normais filtram NULL; admin inclui arquivadas via toggle.';
