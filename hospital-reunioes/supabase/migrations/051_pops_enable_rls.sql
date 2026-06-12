-- =====================================================
-- Migration 051: POPs L1 — RLS default-deny nas tabelas 045–048 (issue #112)
-- =====================================================
-- As tabelas do contexto POPs criadas nas migrations 045–048 nasceram sem
-- `ENABLE ROW LEVEL SECURITY` — fora do padrão da casa (009/041/043/049:
-- RLS default-deny). Sem RLS, a anon_key (pública no bundle do frontend) lê e
-- escreve essas tabelas direto via PostgREST, contornando as guardas de papel ×
-- estado dos endpoints (require_perfil_pop, exigir_elaborador etc.).
--
-- Backend usa service_role (bypassa RLS automaticamente). Sem policies =
-- default-deny puro, igual à migration 009 — nada quebra na camada de app.
-- A tabela pops_materiais_referencia (049) já nasceu com RLS.
-- =====================================================

ALTER TABLE pops_setores ENABLE ROW LEVEL SECURITY;
ALTER TABLE pops_setores_participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pops ENABLE ROW LEVEL SECURITY;
ALTER TABLE pops_versoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pops_devolucoes ENABLE ROW LEVEL SECURITY;
