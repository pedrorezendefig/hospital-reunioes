-- =====================================================
-- Migration 006: Criação de Buckets no Storage (PRIVADOS)
-- Buckets para o pipeline de reunião — LGPD compliance
-- =====================================================

-- 1. Inserir buckets como PRIVADOS
INSERT INTO storage.buckets (id, name, public)
VALUES
  ('audios', 'audios', false),
  ('transcricoes', 'transcricoes', false),
  ('pdfs', 'pdfs', false),
  ('pdfs-assinados', 'pdfs-assinados', false)
ON CONFLICT (id) DO NOTHING;

-- 2. Acesso apenas para usuários autenticados
CREATE POLICY "Authenticated Access" ON storage.objects
  FOR SELECT USING (
    auth.role() = 'authenticated'
    AND bucket_id IN ('audios', 'transcricoes', 'pdfs', 'pdfs-assinados')
  );

-- 3. Permitir que o service_role gerencie todos os arquivos
CREATE POLICY "Service Role Management" ON storage.objects
  FOR ALL TO service_role USING (true) WITH CHECK (true);
