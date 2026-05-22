-- 039_add_envelope_id_clicksign.sql
--
-- Adiciona coluna `envelope_id_clicksign` em `reunioes`.
--
-- Contexto: hoje `envelope_key_clicksign` guarda, na verdade, o `document_id`
-- do ClickSign (o webhook entrega esse campo em `document.key`). Pra novos
-- endpoints que listam signatarios via API v3 (`GET /api/v3/envelopes/{id}/signers`)
-- e reenviam lembrete por signer, precisamos do `envelope_id` real, que
-- nao era persistido.
--
-- Esta migration e ADITIVA e idempotente. Reunioes pre-PR2 ficam com
-- `envelope_id_clicksign = NULL` e o endpoint /signatarios/status cai em
-- modo degradado (retorna lista local sem timestamps reais + legacy_warning
-- pra UI exibir faixa amarela explicativa).

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS envelope_id_clicksign TEXT;

COMMENT ON COLUMN reunioes.envelope_id_clicksign IS
  'ID do envelope ClickSign API v3. Preenchido por start_signature_flow no '
  'clicksign_service.py. Reunioes enviadas antes da migration 039 ficam NULL '
  'e o endpoint /signatarios/status retorna modo degradado.';
