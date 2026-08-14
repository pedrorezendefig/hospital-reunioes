-- =====================================================
-- Migration 060: tokens do Aceite interno + notificacao in-app (ADR 0030, issue #277)
-- =====================================================
-- 1. reuniao_aceite_tokens: link publico tokenizado do Aceite interno, um por
--    signatario pendente com acoes. O token opaco (secrets.token_urlsafe) vai
--    so no email; o banco guarda apenas o SHA-256 (vazamento de banco nao
--    expoe link valido). usado_em marca o uso unico.
-- 2. notificacoes: tipo novo ACEITE_INTERNO (sino do Facilitador pendente) e
--    referencia_id alargado para TEXT (carrega o token do aceite; o legado
--    VARCHAR(10) so cabia id_acao A###).
-- =====================================================

CREATE TABLE IF NOT EXISTS reuniao_aceite_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- VARCHAR(30): a migration 025 alargou id_reuniao (ids MIG_* tem 21+ chars)
  id_reuniao VARCHAR(30) NOT NULL REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  participante_id VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  usado_em TIMESTAMPTZ
);

COMMENT ON TABLE reuniao_aceite_tokens IS
  'Tokens do link publico de Aceite interno (ADR 0030): um por signatario pendente com acoes, uso unico.';
COMMENT ON COLUMN reuniao_aceite_tokens.token_hash IS
  'SHA-256 hex do token opaco enviado por email. O token em claro nunca e persistido aqui.';
COMMENT ON COLUMN reuniao_aceite_tokens.usado_em IS
  'Momento do aceite (uso unico). NULL = link ainda valido.';

CREATE UNIQUE INDEX IF NOT EXISTS ux_reuniao_aceite_tokens_hash
  ON reuniao_aceite_tokens (token_hash);
-- Um link por signatario por Reuniao (idempotencia sob redelivery do webhook)
CREATE UNIQUE INDEX IF NOT EXISTS ux_reuniao_aceite_tokens_participante
  ON reuniao_aceite_tokens (id_reuniao, participante_id);
CREATE INDEX IF NOT EXISTS idx_reuniao_aceite_tokens_reuniao
  ON reuniao_aceite_tokens (id_reuniao);

-- RLS default-deny (padrao da casa: 009/041/051/057). Backend usa service_role.
ALTER TABLE reuniao_aceite_tokens ENABLE ROW LEVEL SECURITY;

-- Notificacao in-app do Aceite interno: referencia_id carrega o token (TEXT)
ALTER TABLE notificacoes ALTER COLUMN referencia_id TYPE TEXT;

ALTER TABLE notificacoes DROP CONSTRAINT IF EXISTS notificacoes_tipo_check;
ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_tipo_check
  CHECK (tipo IN (
    'MENCAO',
    'STATUS_ALTERADO',
    'COMENTARIO',
    'PRAZO_PROXIMO',
    'RESPONSAVEL_ATRIBUIDO',
    'ACEITE_INTERNO'
  ));
