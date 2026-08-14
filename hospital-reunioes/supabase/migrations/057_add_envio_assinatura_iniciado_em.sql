-- #273: trava de envio duplicado de Envelope no /aprovar.
-- A guarda por status nao cobre a janela do background task (o status so vira
-- AGUARDANDO_ASSINATURA no fim do fluxo ClickSign): dois POSTs nessa janela
-- criavam dois Envelopes ativos. A marca e gravada antes de agendar o fluxo e
-- limpa em sucesso e em falha; marca velha (> 10 min) nao bloqueia o retry.

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS envio_assinatura_iniciado_em TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN reunioes.envio_assinatura_iniciado_em IS
  'Marca de envio para assinatura em andamento (#273): gravada pelo /aprovar antes do background task; limpa no fim do fluxo (sucesso ou falha).';
