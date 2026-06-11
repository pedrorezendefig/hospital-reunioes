-- =====================================================
-- Migration 044: metodo_geracao em reunioes (issue #48, ADR 0005)
--
-- A Ata passa a ter DOIS modos de geração: por Transcrição (Pipeline de IA →
-- Ata completa → PDF → assinatura) e Guiada (conversa com um agente → Ata
-- enxuta, sem PDF nem assinatura). Esta coluna distingue os dois.
--
-- Default TRANSCRICAO para NÃO afetar as Reuniões existentes — todas vieram do
-- modo por Transcrição. Campo separado de `fonte` de propósito: `fonte` responde
-- "de onde veio o conteúdo bruto" (FIREFLIES/MOCK/IMPORTACAO_LEGADA) e é um enum
-- tipado na resposta da API; um valor novo ali quebraria a serialização da lista.
--
-- Reversível via: ALTER TABLE reunioes DROP COLUMN metodo_geracao;
-- =====================================================

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS metodo_geracao TEXT NOT NULL DEFAULT 'TRANSCRICAO';

COMMENT ON COLUMN reunioes.metodo_geracao IS
  'Modo de geração da Ata (ADR 0005): TRANSCRICAO (Pipeline de IA → PDF → assinatura) ou GUIADA (conversa com agente → Ata enxuta, sem PDF/assinatura). Default TRANSCRICAO para as Reuniões pré-existentes.';
