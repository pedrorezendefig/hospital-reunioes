-- =====================================================
-- Migration 192: Canal de Conduta, as assinaturas pela ClickSign
-- (issue #1823, PRD #1786, ADR 0097, decisões 2 e 13)
-- =====================================================
-- O que entra:
--   1. uma tabela só para todo documento do Canal que vai à ClickSign
--      (`conduta_assinaturas`): o tipo do documento, o caso quando houver, a
--      Participação quando o documento é do membro, os signatários, a
--      situação e o caminho da cópia cifrada do PDF assinado no bucket
--      `conduta-arquivos` (migration 175). O webhook acha o envio pela chave
--      do documento (`documento_key`). O primeiro tipo em uso é o Termo de
--      Confidencialidade e Posse; os outros da seção 8 da especificação já
--      cabem aqui.
--
-- Nenhuma pessoa entra por aqui. RLS default-deny, sem policy: só o backend,
-- com a service_role, lê e grava. Linha não se apaga: o envio cancelado fica
-- como cancelado.
-- Rodar duas vezes é inofensivo. Aplicar à mão no Studio.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS conduta_assinaturas (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo                   TEXT NOT NULL CHECK (tipo IN (
                           'termo_de_posse',
                           'termo_do_apurador',
                           'relatorio_de_apuracao',
                           'ata_de_deliberacao',
                           'certidao_de_recusa'
                         )),
  caso_id                UUID REFERENCES conduta_casos(id) ON DELETE RESTRICT,
  participacao_id        UUID REFERENCES participacoes(id) ON DELETE RESTRICT,
  -- Os participantes que assinam, na ordem do envelope.
  signatarios            VARCHAR(10)[] NOT NULL CHECK (cardinality(signatarios) > 0),
  situacao               TEXT NOT NULL DEFAULT 'gerado'
                           CHECK (situacao IN ('gerado', 'enviado', 'assinado', 'cancelado')),
  envelope_id            TEXT,
  documento_key          TEXT UNIQUE,
  -- A cópia do PDF assinado, cifrada pela aplicação (ADR 0097, decisão 2).
  arquivo_assinado_path  TEXT,
  erro                   TEXT,
  enviado_em             TIMESTAMPTZ,
  assinado_em            TIMESTAMPTZ,
  cancelado_em           TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT conduta_assinaturas_termo_da_participacao CHECK (
    tipo <> 'termo_de_posse' OR participacao_id IS NOT NULL
  )
);

COMMENT ON TABLE conduta_assinaturas IS
  'Todo documento do Canal de Conduta enviado à ClickSign (ADR 0097, decisão 13): tipo, caso, signatários, situação e a cópia cifrada do PDF assinado. Destino do webhook da ClickSign pela documento_key. Issue #1823.';

CREATE INDEX IF NOT EXISTS idx_conduta_assinaturas_participacao
  ON conduta_assinaturas (participacao_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conduta_assinaturas_caso
  ON conduta_assinaturas (caso_id);

ALTER TABLE conduta_assinaturas ENABLE ROW LEVEL SECURITY;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (192) ON CONFLICT (numero) DO NOTHING;
