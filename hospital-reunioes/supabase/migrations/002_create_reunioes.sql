-- =====================================================
-- Migration 002: Tabelas reunioes e reuniao_participantes
-- Registro mestre de reuniões e junção N:M com participantes
-- Inclui: local, titulo, recorrência, participantes_nao_reconhecidos
-- Status completo: 11 estados do pipeline + CANCELADA
-- =====================================================

-- Função compartilhada para updated_at automático
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS reunioes (
  id_reuniao VARCHAR(20) PRIMARY KEY,
  data DATE NOT NULL,
  hora_inicio TIME,
  hora_fim TIME,
  titulo TEXT,
  tipo TEXT CHECK (tipo IN (
    'Diretoria', 'Gerencial', 'Coordenação', 'Mensal', 'Extraordinária'
  )),
  facilitador_id VARCHAR(10) REFERENCES participantes(id),
  setor TEXT,
  objetivo TEXT,
  local TEXT,
  status_ata TEXT DEFAULT 'PROCESSANDO' CHECK (status_ata IN (
    'PROGRAMADA',
    'PROCESSANDO',
    'ERRO',
    'ERRO_UPLOAD_TRANSCRICAO',
    'ERRO_GERACAO_PDF',
    'ERRO_ENVIO_EMAIL',
    'AGUARDANDO_RESOLUCAO',
    'AGUARDANDO_VALIDACAO',
    'AGUARDANDO_ASSINATURA',
    'ASSINADA',
    'CANCELADA'
  )),
  total_acoes INTEGER DEFAULT 0,
  acoes_concluidas INTEGER DEFAULT 0,
  data_assinatura DATE,
  url_audio TEXT,
  url_transcricao TEXT,
  url_pdf_preliminar TEXT,
  url_pdf_assinado TEXT,
  envelope_key_clicksign TEXT,
  json_ata JSONB,
  fireflies_meeting_id TEXT,
  fonte TEXT DEFAULT 'MOCK' CHECK (fonte IN ('FIREFLIES', 'MOCK')),
  ciclo_correcao INTEGER DEFAULT 0,
  participantes_nao_reconhecidos JSONB DEFAULT '[]'::jsonb,
  id_grupo_recorrencia TEXT,
  nome_grupo_recorrencia TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reuniao_participantes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  participante_id VARCHAR(10) REFERENCES participantes(id),
  sequence_assinatura INTEGER DEFAULT 2,
  UNIQUE(id_reuniao, participante_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_reunioes_status ON reunioes(status_ata);
CREATE INDEX IF NOT EXISTS idx_reunioes_data ON reunioes(data DESC);
CREATE INDEX IF NOT EXISTS idx_reunioes_setor ON reunioes(setor);
CREATE INDEX IF NOT EXISTS idx_reunioes_fireflies ON reunioes(fireflies_meeting_id);
CREATE INDEX IF NOT EXISTS idx_reunioes_programada ON reunioes(data, status_ata)
  WHERE status_ata = 'PROGRAMADA';
CREATE INDEX IF NOT EXISTS idx_reuniao_part_reuniao ON reuniao_participantes(id_reuniao);
CREATE INDEX IF NOT EXISTS idx_reuniao_part_participante ON reuniao_participantes(participante_id);

-- Trigger para updated_at automático
DROP TRIGGER IF EXISTS trigger_reunioes_updated_at ON reunioes;
CREATE TRIGGER trigger_reunioes_updated_at
  BEFORE UPDATE ON reunioes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
