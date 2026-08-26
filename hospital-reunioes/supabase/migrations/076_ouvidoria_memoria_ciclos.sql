-- =====================================================
-- Migration 076: memoria do estouro consumado pela area
-- (issue #374, PRD #318 historias 5 e 22, ADR 0034)
-- =====================================================
-- A devolucao por insuficiencia (074) apaga o marco T2 de proposito: sem
-- apagar, o indicador de cumprimento diria "cumprido" para um caso que ainda
-- deve resposta. O efeito colateral era apagar junto o estouro JA CONSUMADO:
-- quem respondeu DEPOIS do prazo voltava a ler "em_prazo" no ciclo seguinte,
-- porque `respondida_em` some e o vencimento novo esta no futuro.
--
-- Na pratica, responder atrasado E mal limpava a ficha da area. E o contrario
-- do que a historia 5 do PRD #318 quer ("o numero refletir comportamento, nao
-- sorte").
--
-- A coluna abaixo e a memoria disso. Ela guarda o instante do PRIMEIRO estouro
-- da area no caso, e a devolucao nao a apaga.
--
-- Nao serve `prazo_rompido_em`: aquele carimbo e da fila do job de cobranca
-- (071), a devolucao o zera de proposito (senao nenhum degrau da escada cobra
-- o prazo novo), e ele so existe se o job tiver rodado. Sao dois fatos
-- diferentes com o mesmo nome, e por isso duas colunas.
--
-- O TEXTO das respostas nao ganha coluna nenhuma: ele vive na trilha imutavel
-- (`ouvidoria_movimentos`, criada na 064), onde nada sobrescreve o que ja foi
-- gravado. Contar ciclos e contar movimentos, e por isso esta migration mexe
-- em uma coluna so.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS area_estourou_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.area_estourou_em IS
  'Instante do PRIMEIRO estouro de prazo da area neste caso (issue #374). A devolucao por insuficiencia NAO apaga: o estouro e fato consumado e o indicador de cumprimento le esta coluna antes de tudo. A reabertura por reincidencia (075) apaga, porque ali comeca uma tramitacao nova com prazo inteiro. Diferente de prazo_rompido_em, que e carimbo da fila do job de cobranca e e zerado a cada prazo novo.';

-- O indice acompanha o uso previsto: os relatorios do PRD 3 (#319) varrem os
-- casos com estouro consumado, nunca os sem. O parcial e o menor que serve.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_area_estourou
  ON ouvidoria_protocolos(area_estourou_em)
  WHERE area_estourou_em IS NOT NULL;
