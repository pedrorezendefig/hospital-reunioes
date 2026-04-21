-- =====================================================
-- Migration 014: Flag is_externo em participantes +
-- co_responsavel_id e co_responsavel_nome em pendencias
-- =====================================================

-- Flag para identificar participantes externos (cadastrados via resolver)
ALTER TABLE participantes ADD COLUMN is_externo BOOLEAN DEFAULT false NOT NULL;

-- Co-responsável interno atribuído a pendências de externos
ALTER TABLE pendencias ADD COLUMN co_responsavel_id VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL;

-- Denormalização intencional: evita JOIN no kanban para exibir nome
ALTER TABLE pendencias ADD COLUMN co_responsavel_nome TEXT;

-- Index parcial: só indexa linhas com co_responsavel preenchido
CREATE INDEX idx_pendencias_co_responsavel ON pendencias(co_responsavel_id) WHERE co_responsavel_id IS NOT NULL;
