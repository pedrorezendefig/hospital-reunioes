-- =====================================================
-- Migration 003: Tabelas pendencias e agendamentos_email
-- Ações/compromissos extraídos das atas + fila de follow-up
-- Inclui status REPACTUADA
-- =====================================================

CREATE TABLE IF NOT EXISTS pendencias (
  id_acao VARCHAR(10) PRIMARY KEY,
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  descricao_acao TEXT NOT NULL,
  responsavel_id VARCHAR(10) REFERENCES participantes(id),
  responsavel_nome TEXT,
  cargo TEXT,
  prazo DATE,
  meta_entregavel TEXT,
  status TEXT DEFAULT 'PENDENTE' CHECK (status IN (
    'PENDENTE', 'EM_PROGRESSO', 'CONCLUIDO', 'ATRASADO', 'CANCELADO', 'REPACTUADA'
  )),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agendamentos_email (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_acao VARCHAR(10) REFERENCES pendencias(id_acao) ON DELETE CASCADE,
  tipo TEXT CHECK (tipo IN ('D1_INDIVIDUAL', 'D7_LEMBRETE', 'D3_ALERTA')),
  data_disparo DATE NOT NULL,
  enviado BOOLEAN DEFAULT FALSE,
  enviado_em TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_pendencias_reuniao ON pendencias(id_reuniao);
CREATE INDEX IF NOT EXISTS idx_pendencias_responsavel ON pendencias(responsavel_id);
CREATE INDEX IF NOT EXISTS idx_pendencias_status ON pendencias(status);
CREATE INDEX IF NOT EXISTS idx_pendencias_prazo ON pendencias(prazo);
CREATE INDEX IF NOT EXISTS idx_agendamentos_disparo ON agendamentos_email(data_disparo, enviado);

-- Trigger updated_at
DROP TRIGGER IF EXISTS trigger_pendencias_updated_at ON pendencias;
CREATE TRIGGER trigger_pendencias_updated_at
  BEFORE UPDATE ON pendencias
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
