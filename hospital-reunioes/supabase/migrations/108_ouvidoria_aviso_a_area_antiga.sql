-- =====================================================
-- Migration 108: o aviso a area antiga no Redirecionamento
-- (issue #709, PRD #706, ADR 0055, decisao 4)
-- =====================================================
-- Uma coisa so: o gatilho `redirecionamento_area` entra no CHECK de gatilhos
-- das notificacoes da Ouvidoria.
--
-- Quando o ouvidor redireciona um caso, a area que estava com ele recebe um
-- email curto: a demanda daquele protocolo foi encaminhada a outra area e nao
-- e preciso responder. Sem motivo, sem dizer qual e a area nova e SEM LINK
-- NENHUM, porque a issue #707 acabou de derrubar os links dela de proposito.
-- O protocolo e o setor antigo viajam congelados no `detalhe` da linha: o
-- acionamento da area nova sobrescreve `setor` no caso na MESMA requisicao, e
-- lido de la o aviso diria a area antiga justamente o nome que ele nao pode
-- dizer.
--
-- A 107 (issue #708) deixou este gatilho de fora por escrito: "O gatilho
-- `redirecionamento_area` do aviso a area antiga NAO entra aqui: ele e de outra
-- fatia". Esta e a fatia. Sem esta migration o INSERT volta 23514, o registro
-- devolve None e a area antiga nunca e avisada, em silencio.
--
-- Nenhuma tabela nova, nenhuma coluna nova e nenhuma mudanca na RPC
-- `ouvidoria_transicionar`: o grafo de estados continua sendo o da 107, e o
-- aviso nao movimenta caso nenhum.
-- =====================================================

-- CHECK nao tem IF NOT EXISTS: derruba e recria com a lista INTEIRA, como a 096
-- e a 098 fizeram, e dentro de uma transacao, porque isto roda a mao em
-- producao e a tabela nao pode ficar sem constraint se a segunda metade falhar.
BEGIN;

ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN (
    'nova_demanda',
    'alerta_sem_titular',
    'prazo_rompido',
    'vespera_vencimento',
    'escalonamento_gestor',
    'escalonamento_diretoria',
    'alerta_cadastro_setor',
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    'resposta_devolvida',
    'caso_reaberto',
    'acusar_recebimento',
    'encerramento_manifestante',
    'devolvido_a_ouvidoria',
    -- Desta migration (issue #709): o caso saiu de uma area e entrou em outra,
    -- e a ANTIGA fica sabendo que nao responde mais por ele. O unico gatilho do
    -- catalogo cujo destinatario, por definicao, ja nao pertence ao cadastro do
    -- setor do caso.
    'redirecionamento_area'
  ));

COMMIT;
