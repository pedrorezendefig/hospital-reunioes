-- =====================================================
-- Migration 136: o registro de acionamento e o elogio como ciencia
-- (issue #1618, PRD #1527, ADR 0088)
-- =====================================================
-- Duas coisas:
--
--   1. Nasce `ouvidoria_acionamentos`, o envio de um caso a um setor, com o
--      tipo decidido pelo sistema: `resposta` (a area responde no prazo) ou
--      `ciencia` (a area so confirma que recebeu). Nesta fase o registro guarda
--      so as ciencias, e a primeira e o elogio; o acionamento de resposta
--      continua no caso e passa para ca na fase 2 (ADR 0088, decisao 1).
--
--      O elogio nao tem prazo de area (`prazo` fica nulo) e o caso dele nao
--      grava `prazo_area_em`: e a ausencia que o deixa fora da cobranca e dos
--      vencidos. O link do botao "Elogio recebido" segue o padrao do portal
--      do setor: so o hash do token fica no banco, e cada envio grava o hash
--      do link novo. O uso unico e da ciencia, que so passa de `pendente` para
--      `ciente` uma vez. `reenviado_em` e o carimbo do reenvio unico depois de
--      5 dias uteis sem clique.
--
--      Quem responde vai como nome e email congelados no ato, como na fila de
--      notificacoes: o cadastro de responsaveis muda e tem remocao, e o
--      registro precisa dizer para quem o elogio foi.
--
--   2. O gatilho `ciencia_elogio` entra no CHECK de gatilhos das notificacoes.
--      Sem ele o INSERT volta 23514, o registro devolve None e o elogio nunca
--      chega ao setor, em silencio.
--
-- RLS ligado e nenhuma policy: so o backend le e escreve, pela service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

CREATE TABLE IF NOT EXISTS ouvidoria_acionamentos (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id   UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  setor             TEXT NOT NULL CHECK (btrim(setor) <> ''),
  responsavel_nome  TEXT NOT NULL,
  responsavel_email TEXT NOT NULL CHECK (btrim(responsavel_email) <> ''),
  tipo              TEXT NOT NULL CHECK (tipo IN ('resposta', 'ciencia')),
  motivo_ciencia    TEXT CHECK (motivo_ciencia IN ('elogio', 'nsp')),
  status            TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente', 'respondido', 'ciente', 'devolvido', 'sem_resposta')),
  prazo             TIMESTAMPTZ,
  enviado_em        TIMESTAMPTZ,
  respondido_em     TIMESTAMPTZ,
  resposta_texto    TEXT,
  token_hash        TEXT,
  reenviado_em      TIMESTAMPTZ,
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- So a ciencia tem motivo, e toda ciencia tem um.
  CONSTRAINT ouvidoria_acionamentos_motivo_check
    CHECK ((tipo = 'ciencia') = (motivo_ciencia IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_acionamentos_token
  ON ouvidoria_acionamentos(token_hash)
  WHERE token_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ouvidoria_acionamentos_caso
  ON ouvidoria_acionamentos(manifestacao_id, criado_em);

-- A varredura do reenvio: so a ciencia que ainda espera o clique.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_acionamentos_pendentes
  ON ouvidoria_acionamentos(enviado_em)
  WHERE status = 'pendente' AND reenviado_em IS NULL;

COMMENT ON TABLE ouvidoria_acionamentos IS
  'Registro de acionamento (ADR 0088). Nesta fase so as ciencias: o elogio enviado ao setor para confirmar que recebeu. So o backend le.';
COMMENT ON COLUMN ouvidoria_acionamentos.token_hash IS
  'Hash do link do botao do email. Cada envio grava o do link novo; o token em claro so existe no email.';
COMMENT ON COLUMN ouvidoria_acionamentos.reenviado_em IS
  'Quando o email saiu de novo, depois de 5 dias uteis sem clique. Uma vez so.';

ALTER TABLE ouvidoria_acionamentos ENABLE ROW LEVEL SECURITY;

-- CHECK nao tem IF NOT EXISTS: derruba e recria com a lista INTEIRA, como a 108,
-- e dentro de uma transacao, porque isto roda a mao em producao e a tabela nao
-- pode ficar sem constraint se a segunda metade falhar.
BEGIN;

ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN (
    'nova_demanda',
    'alerta_sem_titular',
    'prazo_rompido',
    'vespera_vencimento',
    'escalonamento_gestor',
    'escalonamento_diretoria',
    'alerta_cadastro_setor',
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    'resposta_devolvida',
    'caso_reaberto',
    'acusar_recebimento',
    'encerramento_manifestante',
    'devolvido_a_ouvidoria',
    'redirecionamento_area',
    -- Desta migration: o elogio enviado ao setor com o botao "Elogio recebido".
    'ciencia_elogio'
  ));

COMMIT;

INSERT INTO migracoes_aplicadas (numero) VALUES (136) ON CONFLICT (numero) DO NOTHING;
