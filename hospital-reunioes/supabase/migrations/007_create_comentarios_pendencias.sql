-- =====================================================
-- Migration 007: Tabela comentarios_pendencias
-- Comentários em pendências com suporte a menções
-- =====================================================

CREATE TABLE IF NOT EXISTS comentarios_pendencias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_acao VARCHAR(10) NOT NULL REFERENCES pendencias(id_acao) ON DELETE CASCADE,
  autor_id VARCHAR(10) NOT NULL REFERENCES participantes(id),
  autor_nome TEXT NOT NULL,
  conteudo TEXT NOT NULL,
  mencoes VARCHAR(10)[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_comentarios_id_acao ON comentarios_pendencias(id_acao);
CREATE INDEX IF NOT EXISTS idx_comentarios_autor ON comentarios_pendencias(autor_id);
CREATE INDEX IF NOT EXISTS idx_comentarios_created ON comentarios_pendencias(created_at DESC);

-- Trigger updated_at
DROP TRIGGER IF EXISTS trigger_comentarios_updated_at ON comentarios_pendencias;
CREATE TRIGGER trigger_comentarios_updated_at
  BEFORE UPDATE ON comentarios_pendencias
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
