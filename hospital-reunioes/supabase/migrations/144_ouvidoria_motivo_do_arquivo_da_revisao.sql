-- =====================================================
-- Migration 144: o motivo de arquivar a revisao da Avaliacao
-- (issue #1626, PRD #1527, ADR 0086 decisoes 4 e 8, ADR 0087 decisao 2)
-- =====================================================
-- A aba Avaliacoes da Ouvidoria tira a marca Para revisar de dois jeitos:
-- convertendo a avaliacao em caso ou arquivando a revisao com um motivo
-- curto (secao 4.5 da especificacao da Diretoria). As colunas do desfecho,
-- de quem revisou e de quando ja existem desde a migration 140; falta onde
-- guardar o motivo do arquivo. Tres mudancas:
--
--   1. `revisao_motivo`: o motivo curto de quem arquivou, ate 200
--      caracteres. Obrigatorio quando o desfecho e `arquivada`, e so nele:
--      a conversao nao pede motivo, o caso que nasce ja diz o que foi feito.
--
--   2. Um indice parcial para o que ainda espera revisao: a marca do agente
--      sem desfecho. E o filtro Para revisar da aba e o contador do Painel.
--
--   3. Um indice por `criada_em, id`: a aba abre lendo a faixa do periodo
--      (30 dias ou todo o historico) em todos os pontos, ordenada por
--      `criada_em, id`. Os indices de antes comecam por `ponto_id` ou sao
--      parciais, e a tabela cresce pelo canal publico sem teto.
--
-- A marca do agente (`revisar`, `revisar_motivo`) fica como esta depois do
-- desfecho: e o historico do que o agente apontou. "Para revisar" e a marca
-- SEM desfecho.
--
-- RETENCAO: o motivo e texto do ouvidor, nao de quem avaliou, e fica com a
-- nota e os motivos.
--
-- A tabela ja tem RLS ligado e nenhuma policy (migration 140): so o backend
-- le e escreve, pela service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE ouvidoria_avaliacoes ADD COLUMN IF NOT EXISTS revisao_motivo TEXT;

ALTER TABLE ouvidoria_avaliacoes DROP CONSTRAINT IF EXISTS ck_ouvidoria_avaliacoes_revisao_motivo;
ALTER TABLE ouvidoria_avaliacoes
  ADD CONSTRAINT ck_ouvidoria_avaliacoes_revisao_motivo
  CHECK (
    (revisao_motivo IS NULL OR char_length(btrim(revisao_motivo)) BETWEEN 1 AND 200)
    AND (revisao_desfecho IS DISTINCT FROM 'arquivada' OR revisao_motivo IS NOT NULL)
  );

COMMENT ON COLUMN ouvidoria_avaliacoes.revisao_motivo IS
  'Motivo curto de quem arquivou a revisao na aba Avaliacoes (issue #1626). Obrigatorio quando revisao_desfecho = arquivada.';

CREATE INDEX IF NOT EXISTS idx_ouvidoria_avaliacoes_para_revisar
  ON ouvidoria_avaliacoes(criada_em)
  WHERE revisar AND revisao_desfecho IS NULL;

CREATE INDEX IF NOT EXISTS idx_ouvidoria_avaliacoes_criada_em ON ouvidoria_avaliacoes(criada_em, id);


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (144) ON CONFLICT (numero) DO NOTHING;
