-- =====================================================
-- Migration 059: flag do modo interno da Reuniao (ADR 0030, issue #276)
-- =====================================================
-- Recusa, cancelamento manual ou deadline com zero assinaturas matam o
-- Envelope sem reenvio: a Reuniao permanece em AGUARDANDO_ASSINATURA num
-- sub-modo interno (sem estado novo na maquina). A flag e o proprio
-- timestamp de abertura: NULL = fora do modo interno.
-- =====================================================

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS modo_interno_desde TIMESTAMPTZ;

COMMENT ON COLUMN reunioes.modo_interno_desde IS
  'Abertura do modo interno de aceites (ADR 0030): Envelope morto (refusal/cancel/deadline sem assinaturas), coleta segue por Aceite interno. NULL = fora do modo interno.';
