-- =====================================================
-- Migration 026: participantes.email pode ser NULL
--
-- Motivação: ATAs antigas (fonte='IMPORTACAO_LEGADA') frequentemente citam
-- pessoas externas sem registro de email (ex.: técnicos de fornecedor,
-- consultores ad-hoc). Sem poder criá-las como participantes, pendências
-- cuja responsabilidade recai sobre elas acabam silenciosamente descartadas
-- no endpoint /importacao/confirmar.
--
-- Solução: permitir email NULL → criar "stub" (participante is_externo=true,
-- ativo=false, auth_user_id=null) que serve apenas como responsavel_id de
-- pendência. UNIQUE(email) continua valendo: Postgres trata NULLs como
-- distintos em UNIQUE, então N stubs sem email coexistem sem conflito.
--
-- Reversível via: ALTER TABLE participantes ALTER COLUMN email SET NOT NULL
-- (desde que nenhum stub tenha sido criado).
-- =====================================================

ALTER TABLE participantes ALTER COLUMN email DROP NOT NULL;

COMMENT ON COLUMN participantes.email IS
  'Email único quando presente. NULL permitido para stubs de importação '
  'legada (is_externo=true, ativo=false, sem auth_user_id). Ao obter o '
  'email posteriormente, basta UPDATE + ativar o participante.';
