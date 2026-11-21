-- =====================================================
-- Migration 196: Avisos por e-mail do Canal de Conduta (PRD #1786; issue #1840)
-- =====================================================
-- Cada linha e um aviso a um membro do Comite: a tarefa nova num caso, ou o
-- lembrete a cinco dias e a um dia do prazo. O e-mail nao leva nada do caso
-- ("Ha uma tarefa no Canal de Conduta."), e a linha guarda so os ids, o
-- motivo e a referencia (a acao pendente, ou o prazo do lembrete).
--
-- `na_hora` marca o aviso do rito Completo e da Rota Especial, que sai pelo
-- job de minuto em minuto; os outros saem na rodada diaria das 08:00.
--
-- A chave (caso, pessoa, motivo, referencia) faz o segundo registro do mesmo
-- aviso bater na guarda: nada sai duas vezes. A prorrogacao muda o prazo, e a
-- referencia nova recomeca os lembretes.
--
-- So o backend (service_role) le e grava: RLS default-deny, sem policy.
-- Rodar duas vezes e inofensivo. Aplicar a mao no Studio.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS conduta_avisos (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id          UUID NOT NULL REFERENCES conduta_casos(id) ON DELETE RESTRICT,
  participante_id  VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  motivo           TEXT NOT NULL CHECK (motivo IN ('tarefa', 'lembrete_5', 'lembrete_1')),
  referencia       TEXT NOT NULL,
  na_hora          BOOLEAN NOT NULL DEFAULT false,
  situacao         TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente', 'enviado', 'dispensado')),
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  enviado_em       TIMESTAMPTZ,
  CONSTRAINT conduta_avisos_uma_vez UNIQUE (caso_id, participante_id, motivo, referencia)
);

COMMENT ON TABLE conduta_avisos IS
  'Aviso por e-mail a um membro do Comite de Conduta, sem conteudo do caso (issue #1840). Quem relatou nunca recebe.';

-- Os dois jobs procuram so os pendentes.
CREATE INDEX IF NOT EXISTS idx_conduta_avisos_pendentes
  ON conduta_avisos (na_hora, criado_em) WHERE situacao = 'pendente';

ALTER TABLE conduta_avisos ENABLE ROW LEVEL SECURITY;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (196) ON CONFLICT (numero) DO NOTHING;
