-- =====================================================
-- Migration 008: Tabela notificacoes
-- Sistema de notificações para menções, status e alertas
-- =====================================================

CREATE TABLE IF NOT EXISTS notificacoes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  destinatario_id VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN (
    'MENCAO', 'STATUS_ALTERADO', 'COMENTARIO', 'PRAZO_PROXIMO'
  )),
  titulo TEXT NOT NULL,
  mensagem TEXT,
  referencia_id VARCHAR(10),
  lida BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_notificacoes_destinatario ON notificacoes(destinatario_id, lida);
CREATE INDEX IF NOT EXISTS idx_notificacoes_created ON notificacoes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notificacoes_referencia ON notificacoes(referencia_id);
