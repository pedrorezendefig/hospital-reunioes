-- =====================================================
-- Migration 055: Remove a Natureza do Setor (issue #189, ADR 0021)
-- =====================================================
-- Rollback do ADR 0018 (superseded pelo ADR 0021): com o prompt único da
-- Elaboração (issue #188), a classificação persistida do Setor virou código
-- morto. A coluna criada pela migration 053 sai; o DROP COLUMN também remove
-- o CHECK associado. A migration 054 (backfill por heurística) NUNCA foi
-- aplicada em produção e foi removida do repositório sem ser executada.
-- =====================================================

ALTER TABLE pops_setores
  DROP COLUMN IF EXISTS natureza;
