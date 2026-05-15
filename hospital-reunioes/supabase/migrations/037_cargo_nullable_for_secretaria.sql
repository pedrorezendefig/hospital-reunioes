-- =====================================================
-- Migration 037: cargo nullable pra suportar perfil secretária
-- =====================================================
-- Secretária é uma função sistêmica (access_profile = 'secretaria') e
-- não tem cargo hospitalar atrelado. A migration 001 criou cargo como
-- NOT NULL; aqui relaxamos a constraint.
-- =====================================================

ALTER TABLE participantes
  ALTER COLUMN cargo DROP NOT NULL;
