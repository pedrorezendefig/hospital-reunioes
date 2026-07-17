-- Issue #193: envio para assinatura falhava em silencio.
-- Registro consultavel da ultima falha do fluxo ClickSign na Reuniao:
--   {"passo": "<passo que falhou>", "detalhe": "<mensagem>", "em": "<ISO-8601>"}
-- NULL = sem falha pendente. O sucesso do fluxo limpa o campo.
ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS falha_envio_assinatura JSONB;

COMMENT ON COLUMN reunioes.falha_envio_assinatura IS
  'Ultima falha do envio para assinatura (ClickSign): passo, detalhe e hora. NULL = sem falha pendente (#193).';
