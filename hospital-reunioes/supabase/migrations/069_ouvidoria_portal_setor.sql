-- =====================================================
-- Migration 069: Portal do setor por link tokenizado (issue #326, ADR 0034 decisao 4)
-- =====================================================
-- O titular do setor responde a manifestacao por um link seguro sem login,
-- no padrao do Aceite interno (migration 060): token aleatorio de uso unico,
-- so o hash SHA-256 no banco, restrito a uma manifestacao e um destinatario.
-- A resposta da area grava o marco T2; o encerramento do ouvidor grava o T3.
-- =====================================================

-- 1. Tokens do portal do setor. Diferencas deliberadas em relacao a 060:
--    - expira_em: o link do email nao pode viver para sempre (a manifestacao
--      pode ficar meses aberta); 30 dias cobre toda a cadeia de escalonamento.
--    - o indice unico por destinatario vale so para token NAO usado: o reenvio
--      do acionamento emite token novo e apaga o antigo nao usado, e o usado
--      fica como rastro de quem respondeu.
CREATE TABLE IF NOT EXISTS ouvidoria_setor_tokens (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id    UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  destinatario_nome  TEXT NOT NULL,
  destinatario_email TEXT NOT NULL,
  token_hash         TEXT NOT NULL,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
  expira_em          TIMESTAMPTZ NOT NULL DEFAULT now() + interval '30 days',
  usado_em           TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_setor_tokens_hash
  ON ouvidoria_setor_tokens(token_hash);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_setor_tokens_vigente
  ON ouvidoria_setor_tokens(manifestacao_id, destinatario_email)
  WHERE usado_em IS NULL;

COMMENT ON TABLE ouvidoria_setor_tokens IS
  'Tokens do portal do setor (ADR 0034, decisao 4). So o hash fica no banco: vazar a tabela nao vaza o link do email.';
COMMENT ON COLUMN ouvidoria_setor_tokens.usado_em IS
  'Preenchido no claim atomico da resposta: token e de uso unico e a segunda tentativa nao duplica nada.';

ALTER TABLE ouvidoria_setor_tokens ENABLE ROW LEVEL SECURITY;

-- 2. Marcos T2 (resposta da area) e T3 (encerramento), no padrao do T1 da 068
--    (validada_em/validada_por). A trilha de movimentos ja registra os atos;
--    as colunas dao ao painel e aos relatorios o acesso direto, sem varrer a
--    trilha.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS respondida_em       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resposta_da_area    TEXT,
  ADD COLUMN IF NOT EXISTS respondida_por_nome TEXT,
  ADD COLUMN IF NOT EXISTS encerrada_em        TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.respondida_em IS
  'T2: quando a area respondeu pelo portal do setor.';
COMMENT ON COLUMN ouvidoria_protocolos.resposta_da_area IS
  'O que a area declarou ter FEITO para corrigir, com as palavras do titular.';
COMMENT ON COLUMN ouvidoria_protocolos.respondida_por_nome IS
  'Nome do responsavel no momento da resposta: nao muda se ele sair do papel depois.';
COMMENT ON COLUMN ouvidoria_protocolos.encerrada_em IS
  'T3: quando o ouvidor encerrou com desfecho e descricao.';
