-- =====================================================
-- Migration 042: Pendência com origem Nota (issue #33, ADR 0004)
--
-- A Pendência passa a nascer de duas origens: de uma Reunião que chega a
-- estado terminal (ASSINADA/APROVADA) ou direto de uma Nota. `pendencias`
-- ganha `id_nota` nulável (FK → notas) ao lado de `id_reuniao`, com CHECK
-- garantindo exatamente UMA origem preenchida.
--
-- ON DELETE CASCADE só dispara em hard-delete da Nota (o app usa soft-delete
-- via deleted_at — as Pendências sobrevivem ao arquivamento).
--
-- Reversível via: ALTER TABLE pendencias DROP CONSTRAINT chk_pendencias_origem_unica;
--                 ALTER TABLE pendencias DROP COLUMN id_nota;
-- =====================================================

ALTER TABLE pendencias
  ADD COLUMN IF NOT EXISTS id_nota UUID REFERENCES notas(id) ON DELETE CASCADE;

-- Exatamente uma origem: Reunião XOR Nota. As linhas existentes têm
-- id_reuniao preenchido e id_nota nulo — já satisfazem o CHECK.
ALTER TABLE pendencias DROP CONSTRAINT IF EXISTS chk_pendencias_origem_unica;
ALTER TABLE pendencias ADD CONSTRAINT chk_pendencias_origem_unica
  CHECK ((id_reuniao IS NOT NULL) <> (id_nota IS NOT NULL));

-- Índice do FK (padrão da migration 038): lookups por Nota no painel e na
-- idempotência da criação.
CREATE INDEX IF NOT EXISTS idx_pendencias_nota ON pendencias(id_nota);

COMMENT ON COLUMN pendencias.id_nota IS
  'Origem Nota (ADR 0004): exclusiva com id_reuniao (CHECK chk_pendencias_origem_unica). Pendência de Nota cai no mesmo acompanhamento das demais.';
