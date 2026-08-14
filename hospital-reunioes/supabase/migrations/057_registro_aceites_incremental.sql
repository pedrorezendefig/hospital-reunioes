-- =====================================================
-- Migration 057: Registro de Aceites + nascimento incremental (ADR 0030, issue #274)
-- =====================================================
-- 1. reuniao_aceites: persiste, por Reuniao e Signatario, a origem do
--    compromisso ('clicksign', 'aceite_interno', 'super_admin') e o timestamp.
--    Correlacao com Participante por signer_key da ClickSign, com fallback por
--    email normalizado (mesmo padrao da tela de signatarios).
-- 2. pendencias.quadro_pos: chave estavel da idempotencia por acao do quadro
--    (posicao da acao no quadro_atribuicoes do json_ata). O indice unico
--    parcial protege contra webhooks `sign` concorrentes.
-- =====================================================

CREATE TABLE IF NOT EXISTS reuniao_aceites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- VARCHAR(30): a migration 025 alargou id_reuniao (ids MIG_* tem 21+ chars)
  id_reuniao VARCHAR(30) NOT NULL REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  participante_id VARCHAR(10) REFERENCES participantes(id),
  signer_key TEXT,
  email TEXT,
  origem TEXT NOT NULL CHECK (origem IN ('clicksign', 'aceite_interno', 'super_admin')),
  aceito_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE reuniao_aceites IS
  'Registro de Aceites (ADR 0030): compromisso firmado por signatario, com origem e timestamp.';
COMMENT ON COLUMN reuniao_aceites.signer_key IS
  'Chave do signatario na ClickSign (event.data.signer.key). NULL em aceites sem envelope.';
COMMENT ON COLUMN reuniao_aceites.email IS
  'Email normalizado (lowercase) do signatario; fallback de correlacao.';

-- Um aceite por signatario por Reuniao (idempotencia sob webhooks concorrentes)
CREATE UNIQUE INDEX IF NOT EXISTS ux_reuniao_aceites_signer_key
  ON reuniao_aceites (id_reuniao, signer_key) WHERE signer_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_reuniao_aceites_email
  ON reuniao_aceites (id_reuniao, email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_reuniao_aceites_participante
  ON reuniao_aceites (id_reuniao, participante_id) WHERE participante_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reuniao_aceites_reuniao ON reuniao_aceites(id_reuniao);
CREATE INDEX IF NOT EXISTS idx_reuniao_aceites_participante ON reuniao_aceites(participante_id);

-- RLS default-deny (padrao da casa: 009/041/051). Backend usa service_role.
ALTER TABLE reuniao_aceites ENABLE ROW LEVEL SECURITY;

-- Idempotencia por acao do quadro (ADR 0030): posicao estavel da acao no
-- quadro_atribuicoes. NULL = pendencia legada (liberacao total pre-incremental).
ALTER TABLE pendencias
  ADD COLUMN IF NOT EXISTS quadro_pos INTEGER;

COMMENT ON COLUMN pendencias.quadro_pos IS
  'Posicao da acao no quadro_atribuicoes de origem (chave da idempotencia incremental, ADR 0030). NULL = legado.';

CREATE UNIQUE INDEX IF NOT EXISTS ux_pendencias_reuniao_quadro_pos
  ON pendencias (id_reuniao, quadro_pos) WHERE quadro_pos IS NOT NULL;
