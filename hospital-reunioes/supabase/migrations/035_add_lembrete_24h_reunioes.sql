-- Coluna que marca quando o lembrete de 24h antes foi enviado.
-- NULL = ainda elegivel (incluindo casos em que data/hora foram editadas depois do envio
-- e a flag foi resetada pelo router para reavaliar com a nova programacao).
ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS lembrete_24h_enviado_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN reunioes.lembrete_24h_enviado_at IS
  'Quando o lembrete 24h foi enviado aos participantes. NULL = pendente ou resetado por edicao de data/hora.';

-- Index parcial otimizado para a query do job que roda a cada 15 minutos.
-- Reduz a 0 o custo de scan: so reunioes PROGRAMADA com lembrete pendente entram.
CREATE INDEX IF NOT EXISTS idx_reunioes_lembrete_pendente
  ON reunioes (data, hora_inicio)
  WHERE status_ata = 'PROGRAMADA'
    AND lembrete_24h_enviado_at IS NULL
    AND deleted_at IS NULL;
