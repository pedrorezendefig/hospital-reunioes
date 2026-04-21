-- =====================================================
-- Migration 001: Tabela participantes
-- Cadastro de todas as pessoas que participam de reuniões
-- Hierarquia: diretor > gerente > coordenador
-- =====================================================

-- Enum de roles (3 níveis)
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('diretor', 'gerente', 'coordenador');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Sequência atômica para IDs (P001, P002...)
CREATE SEQUENCE IF NOT EXISTS participantes_id_seq START WITH 1;

-- Função geradora de IDs usando SEQUENCE
CREATE OR REPLACE FUNCTION generate_participant_id()
RETURNS VARCHAR AS $$
BEGIN
  RETURN 'P' || LPAD(nextval('participantes_id_seq')::TEXT, 3, '0');
END;
$$ LANGUAGE plpgsql;

-- Tabela principal
CREATE TABLE IF NOT EXISTS participantes (
  id VARCHAR(10) PRIMARY KEY DEFAULT generate_participant_id(),
  nome_completo TEXT NOT NULL,
  cargo TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  area TEXT,
  setor TEXT,
  role user_role NOT NULL DEFAULT 'coordenador',
  ativo BOOLEAN DEFAULT TRUE,
  auth_user_id UUID REFERENCES auth.users(id),
  data_cadastro DATE DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices para buscas frequentes
CREATE INDEX IF NOT EXISTS idx_participantes_email ON participantes(email);
CREATE INDEX IF NOT EXISTS idx_participantes_setor ON participantes(setor);
CREATE INDEX IF NOT EXISTS idx_participantes_ativo ON participantes(ativo);
CREATE INDEX IF NOT EXISTS idx_participantes_auth ON participantes(auth_user_id);
