-- =====================================================
-- Migration 005: Tabela signup_requests
-- Armazena solicitações de cadastro pendentes de confirmação por email.
-- O registro em auth.users e participantes só é criado após confirmação.
-- =====================================================

CREATE TABLE IF NOT EXISTS signup_requests (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_completo TEXT NOT NULL,
  email        TEXT UNIQUE NOT NULL,
  senha_hash   TEXT NOT NULL,
  cargo        TEXT NOT NULL,
  area         TEXT,
  setor        TEXT,
  role         user_role NOT NULL DEFAULT 'coordenador',
  token        UUID NOT NULL DEFAULT gen_random_uuid(),
  confirmado   BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at   TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices para buscas frequentes
CREATE UNIQUE INDEX IF NOT EXISTS idx_signup_requests_token ON signup_requests(token);
CREATE INDEX IF NOT EXISTS idx_signup_requests_email ON signup_requests(email);
CREATE INDEX IF NOT EXISTS idx_signup_requests_expires ON signup_requests(expires_at);
