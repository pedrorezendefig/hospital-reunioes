-- =====================================================
-- Migration 003: Remove coluna `local` da tabela reunioes
-- Justificativa: todas as reuniões acontecem na mesma sala —
-- o metadado deixou de agregar valor e passou a poluir UI e prompts da IA.
-- =====================================================

ALTER TABLE reunioes DROP COLUMN IF EXISTS local;
