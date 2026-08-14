-- =====================================================
-- Migration 058: contagem de assinaturas na finalizacao do Envelope
-- (ADR 0030, issue #275)
-- =====================================================
-- No fechamento real do Envelope (close/auto_close/deadline com ao menos uma
-- assinatura) o sistema cruza os eventos `sign` com a lista de signers da
-- ClickSign e persiste a contagem na Reuniao. O banner de ASSINADA mostra o
-- selo discreto "N de M assinaram" apenas quando houve faltantes
-- (signatarios_assinaram < signatarios_total). NULL = finalizacao legada ou
-- consulta indisponivel (sem selo, visual atual intacto).
-- =====================================================

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS signatarios_total INTEGER,
  ADD COLUMN IF NOT EXISTS signatarios_assinaram INTEGER;

COMMENT ON COLUMN reunioes.signatarios_total IS
  'Total de signatarios do Envelope no fechamento (ADR 0030). NULL = legado ou consulta indisponivel.';
COMMENT ON COLUMN reunioes.signatarios_assinaram IS
  'Quantos signatarios assinaram ate o fechamento (eventos sign da ClickSign). NULL = legado.';
