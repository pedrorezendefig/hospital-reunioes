-- =====================================================
-- Migration 049: POPs L1 — Materiais de referência (issue #84, PRD #76)
-- =====================================================
-- Materiais de referência (docs/pops/CONTEXT.md): arquivos que o Elaborador
-- sobe na Elaboração (POPs antigos, RDCs, resoluções, artigos em
-- .pdf/.docx/.txt/.md). O agente os lê e usa ATIVAMENTE — conduta oposta ao
-- Documento de apoio da Ata Guiada. O texto extraído persiste vinculado à
-- Versão (é o insumo do agente em toda interação); o arquivo original vai ao
-- storage (bucket materiais-pops, best-effort — storage_path nulo se falhar).
-- =====================================================

CREATE TABLE IF NOT EXISTS pops_materiais_referencia (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  versao_id UUID NOT NULL REFERENCES pops_versoes(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  extensao TEXT NOT NULL,
  tamanho_bytes INTEGER NOT NULL CHECK (tamanho_bytes > 0),
  storage_path TEXT,
  texto TEXT NOT NULL,
  criado_por VARCHAR(10) REFERENCES participantes(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pops_materiais_versao
  ON pops_materiais_referencia(versao_id);

-- RLS default-deny (padrão das migrations 009/041): backend usa service_role
-- (bypassa RLS); sem policy, o acesso via anon_key fica bloqueado — o texto
-- extraído dos materiais não vaza pelo PostgREST.
ALTER TABLE pops_materiais_referencia ENABLE ROW LEVEL SECURITY;

-- Bucket privado para os arquivos originais (padrão da migration 006)
INSERT INTO storage.buckets (id, name, public)
VALUES ('materiais-pops', 'materiais-pops', false)
ON CONFLICT (id) DO NOTHING;

-- Idempotente: CREATE POLICY não tem IF NOT EXISTS no Postgres
DROP POLICY IF EXISTS "Authenticated Access materiais-pops" ON storage.objects;
CREATE POLICY "Authenticated Access materiais-pops" ON storage.objects
  FOR SELECT USING (
    auth.role() = 'authenticated'
    AND bucket_id = 'materiais-pops'
  );
