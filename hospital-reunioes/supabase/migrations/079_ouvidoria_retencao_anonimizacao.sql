-- =====================================================
-- Migration 079: retencao com anonimizacao apos 5 anos (issue #343, ADR 0034)
-- =====================================================
-- A ADR 0034 fecha a lista de controles de LGPD da Ouvidoria com "retencao de
-- 5 anos com anonimizacao". O job diario apaga o Dossie (relato, identificacao
-- de quem manifestou, anexos) da manifestacao encerrada ha mais de cinco anos
-- e preserva o que os relatorios contam: tipo, area, gravidade, canal, datas,
-- marcos e desfecho.
--
-- Nenhuma tabela nova nasce aqui (nada de RLS a ligar): a retencao precisa
-- apenas do carimbo de idempotencia e do indice da varredura.
-- =====================================================

-- 1. O carimbo. NULL enquanto o caso guarda o Dossie; preenchido no instante
--    em que a retencao o apaga. E ele que faz o job ser idempotente: o UPDATE
--    da anonimizacao so casa com `anonimizada_em IS NULL`, entao rodar de novo
--    nao acha caso para anonimizar.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS anonimizada_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.anonimizada_em IS
  'Quando a politica de retencao apagou o Dossie deste caso. NULL = Dossie ainda inteiro. Carimbo de idempotencia do job de retencao.';

-- 2. Indice da varredura, no molde parcial do resto do modulo (071/072/078):
--    o job le por status encerrado, sem carimbo, ordenando pelo marco T3.
--    O DROP vem antes do CREATE porque CREATE INDEX IF NOT EXISTS nao revisita
--    o WHERE de um indice ja existente: sem ele, um ambiente que aplicou uma
--    versao anterior desta migration ficaria com o predicado antigo, sem erro
--    e sem aviso.
DROP INDEX IF EXISTS idx_ouvidoria_protocolos_retencao;
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_retencao
  ON ouvidoria_protocolos(encerrada_em)
  WHERE status = 'encerrado' AND anonimizada_em IS NULL;

COMMENT ON INDEX idx_ouvidoria_protocolos_retencao IS
  'Fila da retencao: casos encerrados que ainda guardam o Dossie, do mais antigo para o mais novo.';
