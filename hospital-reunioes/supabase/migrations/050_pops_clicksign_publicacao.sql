-- =====================================================
-- Migration 050: POPs L1 — ClickSign e publicação (issue #87, PRD #76)
-- =====================================================
-- O fim do ciclo (docs/pops/CONTEXT.md): a aprovação do Validador dispara
-- o envio ao ClickSign (Envelope com 3 Signatários nomeados por papel);
-- com todas as assinaturas, o webhook publica a Versão na Biblioteca.
--
--   1. envelope_id_clicksign  — id do Envelope na API v3 (consultas e
--      download do PDF assinado).
--   2. envelope_key_clicksign — key do Documento (o webhook ClickSign
--      envia em document.key; é a chave de roteamento Reunião × POP).
--   3. url_pdf_assinado / data_publicacao — o PDF assinado no storage e
--      o timestamp da publicação (estado PUBLICADO).
--
-- Falha no envio mantém EM_ASSINATURA com envelope_* NULL — re-tentável
-- sem duplicar Envelope (o reenvio só cria Envelope se não há um ativo).
-- =====================================================

ALTER TABLE pops_versoes
  ADD COLUMN IF NOT EXISTS envelope_id_clicksign TEXT,
  ADD COLUMN IF NOT EXISTS envelope_key_clicksign TEXT,
  ADD COLUMN IF NOT EXISTS url_pdf_assinado TEXT,
  ADD COLUMN IF NOT EXISTS data_publicacao TIMESTAMPTZ;

-- Lookup do webhook: document.key → Versão de POP.
CREATE INDEX IF NOT EXISTS idx_pops_versoes_envelope_key
  ON pops_versoes(envelope_key_clicksign);
