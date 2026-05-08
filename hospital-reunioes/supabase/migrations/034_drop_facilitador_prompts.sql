-- =====================================================
-- Migration 034: limpa tabelas experimentais de prompts
--
-- Remove `facilitador_prompts` e `facilitador_prompt_versoes` que ficaram em
-- prod sem codigo de aplicacao referenciando. CASCADE remove as constraints e
-- indices junto. IF EXISTS deixa a migration idempotente em ambientes que
-- nunca chegaram a aplicar a 033.
--
-- Reversivel via: re-aplicar a 033 (que esta fora do repo).
-- =====================================================

DROP TABLE IF EXISTS facilitador_prompts CASCADE;
DROP TABLE IF EXISTS facilitador_prompt_versoes CASCADE;
