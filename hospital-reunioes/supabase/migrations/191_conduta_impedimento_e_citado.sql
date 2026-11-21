-- =====================================================
-- Migration 191: Canal de Conduta, impedimento, suplente convocado e Citado
-- (issue #1828, PRD #1786, ADR 0097, decisões 4 e 5; especificação, 3.3 e 6.9)
-- =====================================================
-- O que entra:
--   1. na atribuição ao caso, o motivo do impedimento (parte, chefia direta
--      de envolvido, parentesco, relação pessoal, interesse no resultado, ou
--      Citado, quando o impedimento é automático) e, no suplente convocado,
--      quem ele substitui e o papel que passa a ter naquele caso;
--   2. a contestação da participação de um membro no caso, decidida pelos
--      demais membros sem o contestado, e o voto de cada um.
--
-- A tabela do Citado já existe (migration 175). RLS default-deny em toda
-- tabela nova: só o backend, com a service_role, lê e grava. Nenhuma policy
-- de propósito. Nenhum dado de pessoa entra aqui.
-- Rodar duas vezes é inofensivo. Aplicar à mão no Studio.
-- =====================================================

BEGIN;

-- ---------- 1. O impedimento e a convocação na atribuição ----------
ALTER TABLE conduta_atribuicoes
  ADD COLUMN IF NOT EXISTS impedimento_motivo  TEXT,
  ADD COLUMN IF NOT EXISTS substitui_id        VARCHAR(10) REFERENCES participantes(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS substitui_papel     TEXT;

ALTER TABLE conduta_atribuicoes DROP CONSTRAINT IF EXISTS conduta_atribuicoes_impedimento_motivo_check;
ALTER TABLE conduta_atribuicoes
  ADD CONSTRAINT conduta_atribuicoes_impedimento_motivo_check
  CHECK (
    impedimento_motivo IS NULL
    OR impedimento_motivo IN ('parte', 'chefia_direta', 'parentesco', 'relacao_pessoal', 'interesse', 'citado')
  );

-- O suplente convocado faz o que o substituído fazia: o papel vem junto.
ALTER TABLE conduta_atribuicoes DROP CONSTRAINT IF EXISTS conduta_atribuicoes_substitui_papel_check;
ALTER TABLE conduta_atribuicoes
  ADD CONSTRAINT conduta_atribuicoes_substitui_papel_check
  CHECK (
    substitui_papel IS NULL
    OR (motivo = 'suplente_convocado' AND substitui_papel IN ('coordenacao', 'segundo_leitor', 'membro'))
  );

COMMENT ON COLUMN conduta_atribuicoes.impedimento_motivo IS
  'Por que a pessoa está impedida no caso (issue #1828). citado = impedimento automático do membro Citado.';
COMMENT ON COLUMN conduta_atribuicoes.substitui_papel IS
  'Suplente convocado: o papel do substituído, que o suplente passa a ter só neste caso (issue #1828).';

CREATE INDEX IF NOT EXISTS idx_conduta_atribuicoes_substitui ON conduta_atribuicoes (substitui_id);

-- ---------- 2. A contestação da participação ----------
CREATE TABLE IF NOT EXISTS conduta_contestacoes_de_participacao (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id         UUID NOT NULL REFERENCES conduta_casos(id) ON DELETE RESTRICT,
  contestado_id   VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  autor_id        VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  motivo          TEXT NOT NULL CHECK (motivo IN ('parte', 'chefia_direta', 'parentesco', 'relacao_pessoal', 'interesse')),
  resultado       TEXT CHECK (resultado IS NULL OR resultado IN ('confirmada', 'rejeitada')),
  decidida_em     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT conduta_contestacoes_de_participacao_outro_check CHECK (contestado_id <> autor_id)
);

COMMENT ON TABLE conduta_contestacoes_de_participacao IS
  'Um membro contesta a participação de outro num caso; os demais decidem, sem o contestado (issue #1828). confirmada = o contestado fica impedido.';

-- Uma contestação aberta por pessoa em cada caso.
CREATE UNIQUE INDEX IF NOT EXISTS idx_conduta_contestacoes_de_participacao_aberta
  ON conduta_contestacoes_de_participacao (caso_id, contestado_id)
  WHERE decidida_em IS NULL;
-- A tela do caso, a contestação e a decisão leem as contestações só por caso.
CREATE INDEX IF NOT EXISTS idx_conduta_contestacoes_de_participacao_caso
  ON conduta_contestacoes_de_participacao (caso_id);
CREATE INDEX IF NOT EXISTS idx_conduta_contestacoes_de_participacao_contestado
  ON conduta_contestacoes_de_participacao (contestado_id);
CREATE INDEX IF NOT EXISTS idx_conduta_contestacoes_de_participacao_autor
  ON conduta_contestacoes_de_participacao (autor_id);

ALTER TABLE conduta_contestacoes_de_participacao ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS conduta_participacao_votos (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contestacao_id   UUID NOT NULL REFERENCES conduta_contestacoes_de_participacao(id) ON DELETE RESTRICT,
  participante_id  VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  escolha          TEXT NOT NULL CHECK (escolha IN ('confirmar', 'manter')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (contestacao_id, participante_id)
);

COMMENT ON TABLE conduta_participacao_votos IS
  'O voto de cada membro na contestação da participação (issue #1828). Um por pessoa; o contestado não vota.';

CREATE INDEX IF NOT EXISTS idx_conduta_participacao_votos_pessoa ON conduta_participacao_votos (participante_id);

ALTER TABLE conduta_participacao_votos ENABLE ROW LEVEL SECURITY;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (191) ON CONFLICT (numero) DO NOTHING;
