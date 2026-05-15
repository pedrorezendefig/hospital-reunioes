-- =====================================================
-- Migration 036: Perfil de acesso (access_profile) + criada_por em reunioes
-- =====================================================
-- Cria enum único de "perfil de acesso" (regular / secretaria / super_admin)
-- substituindo a flag boolean is_super_admin. Mutuamente exclusivo por
-- construção. Mantém is_super_admin intacta nessa fase (zero quebra em prod);
-- a coluna antiga será dropada numa migration futura, após validação.
--
-- Também adiciona reunioes.criada_por, necessário pra rastrear autoria da
-- reunião quando uma secretária marca pra outro facilitador.
-- =====================================================

-- 1. participantes.access_profile (nullable primeiro, backfill, depois NOT NULL)
ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS access_profile TEXT
  CHECK (access_profile IS NULL OR access_profile IN ('regular', 'secretaria', 'super_admin'));

-- Backfill espelhando o estado atual: super_admin onde a flag está true, regular no resto.
UPDATE participantes
SET access_profile = CASE
  WHEN is_super_admin = true THEN 'super_admin'
  ELSE 'regular'
END
WHERE access_profile IS NULL;

-- Agora torna obrigatório com default.
ALTER TABLE participantes
  ALTER COLUMN access_profile SET NOT NULL,
  ALTER COLUMN access_profile SET DEFAULT 'regular';

CREATE INDEX IF NOT EXISTS idx_participantes_access_profile ON participantes(access_profile);

-- 2. Secretária pode não ter cargo hospitalar; torna role nullable.
ALTER TABLE participantes
  ALTER COLUMN role DROP NOT NULL;

-- 3. reunioes.criada_por (rastreia quem criou a reunião)
ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS criada_por VARCHAR(10) REFERENCES participantes(id);

-- Backfill: usa facilitador_id (assumindo que historicamente o facilitador foi quem criou).
UPDATE reunioes
SET criada_por = facilitador_id
WHERE criada_por IS NULL AND facilitador_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reunioes_criada_por ON reunioes(criada_por);
