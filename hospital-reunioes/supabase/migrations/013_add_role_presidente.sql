-- =====================================================
-- Migration 013: Adicionar role presidente ao enum user_role
-- ALTER TYPE ADD VALUE não suporta transação — migration isolada
-- =====================================================

ALTER TYPE user_role ADD VALUE 'presidente';
