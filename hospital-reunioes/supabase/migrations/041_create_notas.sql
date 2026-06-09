-- =====================================================
-- Migration 041: Tabela notas (entidade Nota — issue #32, ADR 0004)
--
-- A Nota é um registro leve do Facilitador — corpo de texto livre, paralela à
-- Reunião (não variante). Esta fatia fundadora cria só a tabela `notas`
-- (CRUD + histórico + acesso). O roster de Participantes, o FK `id_nota` em
-- `pendencias` e a voz chegam em fatias/migrations seguintes.
--
-- Acesso espelha a Reunião: controlado no backend (service_role). RLS
-- habilitado default-deny (sem policy) — anon_key não acessa (migration 009).
--
-- Reversível via: DROP TABLE notas.
-- =====================================================

CREATE TABLE IF NOT EXISTS notas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  corpo TEXT NOT NULL,
  autor_id VARCHAR(10) NOT NULL REFERENCES participantes(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  deleted_at TIMESTAMPTZ NULL
);

-- Histórico por autor + índice parcial das vivas por data (a vasta maioria das
-- consultas: listagem do histórico ativo, mais recentes primeiro).
CREATE INDEX IF NOT EXISTS idx_notas_autor ON notas(autor_id);
CREATE INDEX IF NOT EXISTS idx_notas_live
  ON notas(created_at DESC) WHERE deleted_at IS NULL;

-- updated_at automático (função compartilhada criada na migration 002).
DROP TRIGGER IF EXISTS trigger_notas_updated_at ON notas;
CREATE TRIGGER trigger_notas_updated_at
  BEFORE UPDATE ON notas
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- RLS default-deny: backend usa service_role (bypassa RLS). Sem policy, o
-- acesso via anon_key fica bloqueado por padrão (mesmo modelo da migration 009).
ALTER TABLE notas ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE notas IS
  'Nota (ADR 0004): registro leve do Facilitador — corpo de texto livre, paralela à Reunião. Acesso: autor vê as suas; Secretária e Super admin veem todas.';
COMMENT ON COLUMN notas.deleted_at IS
  'Soft delete. NULL = viva, timestamp = arquivada em. O histórico ativo filtra deleted_at IS NULL.';
