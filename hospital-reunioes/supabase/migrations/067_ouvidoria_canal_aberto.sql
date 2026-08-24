-- =====================================================
-- Migration 067: Canal aberto da Ouvidoria (issue #323, ADR 0034 decisao 9)
-- =====================================================
-- Formulario publico sem login e QR setorial. A migration do registro manual
-- (issue #321) abriu a coluna `canal` com os canais do ouvidor e deixou dito
-- que "o formulario publico e o QR entram na fatia seguinte e acrescentam o
-- valor deles ao CHECK". E o que esta migration faz, mais o ponto do cartaz.
--
-- Nenhuma tabela nova: a Manifestacao ja existe desde a 063/064, com RLS
-- default-deny. O canal aberto escreve nela pelo backend (service_role).
-- =====================================================

-- 1. A coluna do canal. O ADD COLUMN e defensivo de proposito: se por qualquer
--    motivo a migration do registro manual nao tiver rodado antes desta, o
--    canal aberto ainda entra, com o mesmo default ('ana' e o unico canal de
--    tudo que existe hoje, do atendimento da Ana e do import do NocoDB).
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS canal TEXT NOT NULL DEFAULT 'ana';

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_canal_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_canal_check
  CHECK (canal IN ('ana', 'telefone', 'presencial', 'email', 'site', 'qr'));

COMMENT ON COLUMN ouvidoria_protocolos.canal IS
  'Por onde a manifestacao chegou ao hospital. Alem dos canais do ouvidor, o canal aberto: site (formulario) e qr (cartaz setorial).';

-- 2. O ponto do cartaz: onde exatamente estava o QR que a pessoa leu
--    ("Poltrona 12", "Corredor do 3o andar"). So faz sentido com canal 'qr'.
--    Fica separado do setor porque setor e taxonomia do hospital e ponto e
--    rotulo do cartaz; misturar os dois sujaria a area da manifestacao.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS canal_ponto TEXT;

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_canal_ponto_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_canal_ponto_check
  CHECK (canal_ponto IS NULL OR (btrim(canal_ponto) <> '' AND length(canal_ponto) <= 80));

COMMENT ON COLUMN ouvidoria_protocolos.canal_ponto IS
  'Ponto fisico do cartaz de QR que originou a manifestacao. NULL nos demais canais. Contornar a API nao contorna o limite de tamanho.';
