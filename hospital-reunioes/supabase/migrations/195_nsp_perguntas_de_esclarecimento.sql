-- =====================================================
-- Migration 195: as respostas às perguntas de esclarecimento do Núcleo
-- (issue #1991, PRD #1979, ADR 0107)
-- =====================================================
-- O agente de triagem propõe até duas perguntas a quem notificou, na linha de
-- triagem dele (`nsp_triagens.perguntas_ao_notificante`, migration 188).
-- Quem notificou responde na confirmação ou na página de acompanhamento, e
-- cada resposta fica aqui, com a linha de triagem que fez a pergunta.
--
-- Uma pergunta se responde uma vez por notificação: a mesma pergunta repetida
-- numa rodada nova do agente não volta para quem notificou.
--
-- Nenhuma pessoa entra por aqui. RLS ligado e sem política: só o backend,
-- com a service_role, lê e grava (o padrão das tabelas do Núcleo). Rodar duas
-- vezes é inofensivo. Aplicar à mão no Studio.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS nsp_esclarecimentos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notificacao_id  UUID NOT NULL REFERENCES nsp_notificacoes(id) ON DELETE RESTRICT,
  triagem_id      UUID NOT NULL REFERENCES nsp_triagens(id) ON DELETE RESTRICT,
  pergunta        TEXT NOT NULL CHECK (char_length(pergunta) BETWEEN 1 AND 1000),
  resposta        TEXT NOT NULL CHECK (char_length(btrim(resposta)) BETWEEN 1 AND 500),
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (notificacao_id, pergunta)
);

COMMENT ON TABLE nsp_esclarecimentos IS
  'As respostas de quem notificou às perguntas de esclarecimento do agente do Núcleo. Antes da confirmação da triagem, cada resposta roda o agente de novo. Issue #1991.';
COMMENT ON COLUMN nsp_esclarecimentos.triagem_id IS
  'A linha de triagem do agente que fez a pergunta.';

CREATE INDEX IF NOT EXISTS idx_nsp_esclarecimentos_triagem ON nsp_esclarecimentos (triagem_id);

ALTER TABLE nsp_esclarecimentos ENABLE ROW LEVEL SECURITY;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (195) ON CONFLICT (numero) DO NOTHING;
