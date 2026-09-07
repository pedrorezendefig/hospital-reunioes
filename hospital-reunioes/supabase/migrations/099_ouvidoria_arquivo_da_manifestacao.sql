-- =====================================================
-- Migration 099: o Arquivo da Manifestacao
-- (issue #592, PRD #591, ADR 0047)
-- =====================================================
-- A lista da Ouvidoria mostra todo caso encerrado para sempre, e o grupo
-- Encerrado cresce sem parar. O ouvidor passa a tirar da vista o que ja
-- acabou, e a lista nasce sem os arquivados.
--
-- Arquivar NAO e estado da maquina (ADR 0047, decisao 3): o `status` continua
-- `encerrado`, nenhum movimento entra na trilha e nada passa pela RPC
-- `ouvidoria_transicionar`. Por isso a migration nao toca no grafo da 098: o
-- arquivo e organizacao da lista, nao fato do caso.
--
-- Duas colunas, e so elas. Desarquivar volta as duas a NULL, que e o valor com
-- que TODO caso existente entra aqui: sem backfill, porque ninguem arquivou
-- nada ainda e carimbar uma data agora esconderia da fila casos que o ouvidor
-- nunca escolheu esconder.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos (migration 064) seguem valendo para a linha inteira,
-- colunas novas inclusas. A leitura e a escrita continuam sendo do backend com
-- a service_role, e o gate de papel vive na rota.
--
-- Nenhum indice: a fila da Ouvidoria e uma tabela do tamanho do historico de um
-- hospital, e o filtro por `arquivada_em IS NULL` anda junto com o mesmo
-- `select` que ja varre a tabela inteira hoje. Indice aqui seria custo de
-- escrita sem leitura que o justifique.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS arquivada_em  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS arquivada_por VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL;

COMMENT ON COLUMN ouvidoria_protocolos.arquivada_em IS
  'Quando a Ouvidoria tirou este caso da vista da lista (issue #592, ADR 0047). NULL = nao arquivado, e e assim que a lista nasce filtrando. Desarquivar volta a NULL. Nao e estado: o `status` continua `encerrado` e nenhum movimento e gravado.';

COMMENT ON COLUMN ouvidoria_protocolos.arquivada_por IS
  'Quem arquivou o caso (issue #592, ADR 0047). Anda junto com `arquivada_em`: os dois sao gravados no mesmo ato e os dois voltam a NULL ao desarquivar. ON DELETE SET NULL porque o participante pode sair do hospital, e o arquivo continua valendo sem ele.';
