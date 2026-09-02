-- =====================================================
-- Migration 094: acuse de recebimento ao manifestante (issue #493, ADR 0042)
-- =====================================================
-- A migration 065 deixou o marco "acusar recebimento" FORA da tabela de
-- prazos de proposito, com a nota de que ele e prazo em calendario corrido e
-- pertence ao catalogo de notificacoes. O catalogo nunca o recebeu, e o
-- manifestante seguiu sem nenhum retorno depois do protocolo (D-07).
--
-- Esta migration abre as tres portas que faltavam:
--   1. o marco `acusar_recebimento` e a unidade `horas_corridas` na tabela de
--      prazos, com o seed da spec da Diretoria (RN-56);
--   2. o gatilho `acusar_recebimento` no catalogo de notificacoes, o primeiro
--      da casa com o MANIFESTANTE como destinatario (ADR 0042, decisao 2);
--   3. os dois carimbos do caso: o acuse que saiu e a marcacao propria de quem
--      nao tinha para onde receber (ADR 0042, decisao 4).
--
-- Roda a mao em producao, entao cada troca de CHECK vai numa transacao: a
-- tabela nunca fica sem constraint se a segunda metade falhar.
-- =====================================================

-- 1. O marco novo e a unidade corrida na tabela de prazos.
--    CHECK nao tem IF NOT EXISTS: derruba e recria, como a 071 a 078 fizeram
--    com o CHECK de gatilho. As listas repetem os valores anteriores, porque o
--    ultimo CHECK criado e o que vale.
BEGIN;

ALTER TABLE ouvidoria_prazos DROP CONSTRAINT IF EXISTS ouvidoria_prazos_marco_check;
ALTER TABLE ouvidoria_prazos
  ADD CONSTRAINT ouvidoria_prazos_marco_check
  CHECK (marco IN ('triagem', 'area_resposta', 'conclusiva', 'acusar_recebimento'));

ALTER TABLE ouvidoria_prazos DROP CONSTRAINT IF EXISTS ouvidoria_prazos_unidade_check;
ALTER TABLE ouvidoria_prazos
  ADD CONSTRAINT ouvidoria_prazos_unidade_check
  CHECK (unidade IN ('horas_uteis', 'dias_uteis', 'horas_corridas'));

COMMIT;

COMMENT ON COLUMN ouvidoria_prazos.unidade IS
  'Regua do prazo. As duas primeiras correm no Calendario util (segunda a sexta, 08h as 17h, sem feriados). `horas_corridas` corre em relogio de parede e existe para um unico marco, o acuse de recebimento (RN-56, ADR 0042): acuse e promessa ao paciente, e quem manifesta sexta a noite nao espera ate terca.';

-- Seed da RN-56: 24 horas corridas para todas as gravidades; o critico e
-- "mesmo dia". Zero em horas corridas significa "ainda hoje", e nao "ja
-- vencido": nas unidades uteis o zero quer dizer "sem esperar a proxima
-- abertura do expediente", porque ali existe janela; no calendario corrido nao
-- ha janela nenhuma para esperar, e o que sobra do dia e o prazo.
INSERT INTO ouvidoria_prazos (gravidade, marco, valor, unidade) VALUES
  ('critico', 'acusar_recebimento', 0, 'horas_corridas'),
  ('alto', 'acusar_recebimento', 24, 'horas_corridas'),
  ('medio', 'acusar_recebimento', 24, 'horas_corridas'),
  ('baixo', 'acusar_recebimento', 24, 'horas_corridas')
ON CONFLICT (gravidade, marco) DO NOTHING;

-- 2. O gatilho novo no catalogo de notificacoes. Mesma mecanica das migrations
--    071 a 078: derruba e recria com a lista inteira.
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
    -- Desta migration (issue #493, ADR 0042): o primeiro gatilho da casa cujo
    -- destinatario e o MANIFESTANTE, e nao o setor, o gestor ou a Diretoria.
    -- O corpo dele e minimo (protocolo e o que acontece agora), sem relato e
    -- sem identificacao de terceiros.
    'acusar_recebimento'
  ));

COMMIT;

-- 3. Os dois carimbos do caso. Exclusivos entre si por desenho: ou havia para
--    onde mandar o acuse, ou nao havia.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS acuse_recebimento_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS acuse_sem_contato_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.acuse_recebimento_em IS
  'Quando o acuse de recebimento ao manifestante foi registrado na fila de notificacoes, na abertura do caso (RN-56, ADR 0042). E o marco cumprido: o prazo de 24 horas corridas da tabela e rede de seguranca para falha de envio, nao meta de trabalho manual.';
COMMENT ON COLUMN ouvidoria_protocolos.acuse_sem_contato_em IS
  'A marcacao propria de quem nao podia ser avisado: caso anonimo ou contato sem email utilizavel (ADR 0042, decisao 4). Existe para o caso nao passar por "o hospital deixou de avisar" e para o indicador de retorno ao manifestante nao contar no denominador quem nunca teve canal.';
