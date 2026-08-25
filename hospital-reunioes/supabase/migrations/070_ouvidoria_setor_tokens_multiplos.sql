-- =====================================================
-- Migration 070: o portal do setor aceita mais de um link vivo (issue #326)
-- =====================================================
-- A 069 nasceu com um indice unico parcial que garantia "no maximo um link
-- valido por destinatario". A regra parecia higiene e era uma armadilha: o
-- token em claro so existe dentro do email que ja saiu, e o despacho tenta de
-- novo quando o provedor nao confirma a entrega. Nesse retry, emitir um token
-- novo apagava o anterior, e o link que o titular tinha na caixa de entrada
-- passava a responder "link invalido".
--
-- Varios links vivos nao somam risco: cada um e de uso unico, preso a UMA
-- manifestacao e a UM destinatario, expira em 30 dias, e o primeiro que
-- responder tira o caso de `aguardando_area`, o que faz os demais recusarem
-- sozinhos. O indice continua existindo, agora so para a busca.
-- =====================================================

DROP INDEX IF EXISTS idx_ouvidoria_setor_tokens_vigente;

CREATE INDEX IF NOT EXISTS idx_ouvidoria_setor_tokens_destinatario
  ON ouvidoria_setor_tokens(manifestacao_id, destinatario_email)
  WHERE usado_em IS NULL;

COMMENT ON INDEX idx_ouvidoria_setor_tokens_destinatario IS
  'Busca dos links vigentes de um destinatario. NAO e unico de proposito: o reenvio emite token novo sem matar o que ja foi entregue.';
