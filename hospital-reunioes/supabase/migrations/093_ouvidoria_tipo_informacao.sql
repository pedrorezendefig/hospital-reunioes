-- =====================================================
-- Migration 093: `informacao` entra na lista fechada de tipos
-- (issue #490, PRD #471, ADR 0040 decisao 1, RN-57, D-11)
-- =====================================================
-- A lista de tipos do ouvidor tinha cinco valores desde a migration 077, e
-- nenhum deles era `informacao`. O cartaz do ponto de escuta, ja em arte
-- final, promete quatro naturezas a quem le o QR (RN-88), e uma delas e
-- informacao: o formulario publico ja a aceita como sugestao do manifestante
-- (coluna `natureza_informada`, migration 090), mas na hora de CLASSIFICAR o
-- ouvidor nao tinha onde pousa-la, e o pedido de informacao acabava carimbado
-- de reclamacao. O que o papel promete passa a existir na triagem.
--
-- O CHECK abaixo repete a lista que a aplicacao ja valida (`TIPOS_MANIFESTACAO`
-- em ouvidoria_taxonomia.py e o Literal `TipoManifestacao` que os dois schemas
-- do router usam): a aplicacao recusa antes, o banco recusa depois, e nenhuma
-- das duas confia na outra.
--
-- SEM SIGILO POR NATUREZA. `informacao` nao entra em `TIPOS_SIGILOSOS`: as
-- duas naturezas que prendem o caso continuam sendo `denuncia` e
-- `relato_de_conduta` (ADR 0034 decisao 1, ADR 0037), e o caso sem tipo
-- continua fail-closed. Esta migration abre a lista, nao mexe em sigilo.
--
-- `relato_de_conduta` NAO e renomeado (ADR 0040 decisao 2). A RN-57 escreveu
-- `relato_conduta`, mas renomear valor em uso em producao seria migration de
-- dado com risco e sem ganho funcional: todo caso ja gravado e toda linha de
-- trilha apontariam para um valor que o CHECK novo nao aceita mais.
--
-- SEM BACKFILL, de proposito. A migration so abre a lista: carimbar
-- `informacao` num caso ja gravado seria escrever no banco uma decisao que
-- ouvidor nenhum tomou, ainda por cima trocando um numero errado por outro no
-- relatorio da Diretoria.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos seguem valendo para a linha inteira.
--
-- Reaplicavel: o DROP e condicional e o ADD recria a constraint com o mesmo
-- nome, entao rodar de novo termina no mesmo estado. O DROP vem ANTES do ADD
-- porque `ADD CONSTRAINT` com nome ja existente e erro, e nao no-op.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_tipo_manifestacao_check;

ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_tipo_manifestacao_check
  CHECK (tipo_manifestacao IS NULL OR tipo_manifestacao IN (
    'denuncia', 'reclamacao', 'sugestao', 'elogio', 'relato_de_conduta', 'informacao'
  ));

COMMENT ON COLUMN ouvidoria_protocolos.tipo_manifestacao IS
  'Tipo da manifestacao em lista fechada de seis valores (issues #372 e #490, ADR 0040): denuncia, reclamacao, sugestao, elogio, relato_de_conduta e informacao. E ele, e nao o texto livre de categoria, que decide o sigilo: denuncia e relato_de_conduta sao sigilosos por natureza (ADR 0034, decisao 1); informacao nao e. NULL significa NAO CLASSIFICADO, estado em que o caso e tratado como sigiloso (fail-closed) ate o ouvidor classificar.';
