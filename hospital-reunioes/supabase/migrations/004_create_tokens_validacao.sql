-- =====================================================
-- Migration 004: Tabela tokens_validacao
-- Tokens para botões Aprovar/Corrigir no email do facilitador
-- =====================================================

CREATE TABLE IF NOT EXISTS tokens_validacao (
  token UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  tipo TEXT CHECK (tipo IN ('APROVACAO', 'CORRECAO')),
  usado BOOLEAN DEFAULT FALSE,
  ciclo_correcao INTEGER DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tokens_reuniao ON tokens_validacao(id_reuniao);
CREATE INDEX IF NOT EXISTS idx_tokens_expires ON tokens_validacao(expires_at);
