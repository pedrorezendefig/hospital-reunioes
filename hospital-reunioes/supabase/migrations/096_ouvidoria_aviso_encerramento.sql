-- =====================================================
-- Migration 096: aviso de encerramento ao manifestante (issue #494, ADR 0042)
-- =====================================================
-- A migration 094 abriu a primeira ponta do ADR 0042: o acuse de recebimento,
-- o primeiro email da casa com o MANIFESTANTE como destinatario. Esta abre a
-- segunda e ultima: encerrar o caso no sistema passa a encerrar tambem para
-- quem manifestou (RN-80). Sem ela, o paciente recebia o aviso de que a
-- manifestacao chegou e nunca ficava sabendo no que deu.
--
-- Duas portas:
--   1. o gatilho `encerramento_manifestante` no catalogo de notificacoes;
--   2. os dois carimbos do caso, no mesmo par exclusivo que a 094 criou para o
--      acuse: ou havia para onde mandar o desfecho, ou nao havia.
--
-- Roda a mao em producao, entao a troca de CHECK vai numa transacao: a tabela
-- nunca fica sem constraint se a segunda metade falhar.
-- =====================================================

-- 1. O gatilho novo. Mesma mecanica das migrations 071 a 078 e da 094:
--    derruba e recria com a lista INTEIRA, porque o ultimo CHECK criado e o
--    que vale e CHECK nao tem IF NOT EXISTS.
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
    -- Desta migration (issue #494, ADR 0042, decisao 3): o segundo e ultimo
    -- gatilho com o manifestante como destinatario. Dispara na transicao de
    -- encerramento e leva protocolo, o desfecho em linguagem simples que o
    -- ouvidor escreveu para a pessoa e o canal para voltar. Nao leva relato,
    -- nao leva o codigo interno do desfecho e nao leva identificacao de
    -- terceiros.
    'encerramento_manifestante'
  ));

COMMIT;

-- 2. Os dois carimbos do caso, espelho exato do par que a 094 criou para o
--    acuse. Exclusivos entre si por desenho.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS encerramento_avisado_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS encerramento_sem_contato_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.encerramento_avisado_em IS
  'Quando o aviso de encerramento ao manifestante foi registrado na fila de notificacoes, na transicao de encerramento (RN-80, ADR 0042). Diz que o aviso foi GERADO: quem sabe se o email chegou e o status da linha em ouvidoria_notificacoes.';
COMMENT ON COLUMN ouvidoria_protocolos.encerramento_sem_contato_em IS
  'A marcacao propria de quem nao podia ser avisado do desfecho: caso anonimo ou contato sem email utilizavel (ADR 0042, decisao 4; RN-81). Caso com esta marcacao fica FORA do denominador do indicador de resposta conclusiva: ele nunca teve canal, e conta-lo ali carimbaria como falha do hospital uma escolha de quem manifestou.';
