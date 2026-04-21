-- Bulk jobs: tracking de acoes em massa administrativas executadas em background.
--
-- Cada linha representa uma requisicao POST /admin/bulk/* (reenviar-clicksign,
-- reprocessar-ia, reenviar-email). O endpoint cria a linha com status='pending',
-- retorna 202 com job_id e dispara um FastAPI BackgroundTask que:
--   1. muda para 'running' + started_at
--   2. itera sobre target_ids, atualizando sucessos/falhas incrementalmente
--   3. finaliza com 'completed' ou 'failed' + finished_at
--
-- Falhas individuais NAO interrompem o loop: ficam em `falhas` JSONB ([{id, erro}]).
-- Se um job crashar (processo reiniciou), fica 'running' para sempre — follow-up
-- de observabilidade e um cron que marca jobs `running` ha > 30min como 'timeout'.

CREATE TABLE bulk_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_id VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  actor_email TEXT NOT NULL,
  job_type TEXT NOT NULL,          -- reenviar_clicksign, reprocessar_ia, reenviar_email
  status TEXT NOT NULL,            -- pending, running, completed, failed
  target_ids JSONB NOT NULL,       -- IDs alvo (reunioes ou participantes)
  total INTEGER NOT NULL DEFAULT 0,
  sucessos INTEGER NOT NULL DEFAULT 0,
  falhas JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{id, erro}]
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb, -- extras (ex: assunto/corpo do email)
  reason TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE INDEX idx_bulk_jobs_actor ON bulk_jobs(actor_id);
CREATE INDEX idx_bulk_jobs_status ON bulk_jobs(status);
CREATE INDEX idx_bulk_jobs_created_at ON bulk_jobs(created_at DESC);
