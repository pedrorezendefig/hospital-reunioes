-- =====================================================
-- Migration 072: escada de escalonamento e critico imediato
-- (issue #336, PRD #318, ADR 0034 decisao 12)
-- =====================================================
-- A 071 entregou o degrau do vencimento (titular + substituto). Aqui entram os
-- degraus que faltam da escada: a vespera do vencimento, as 24h uteis sem
-- resposta (gestor da area) e as 48h uteis (Diretoria Executiva). Junto vem o
-- aviso que nao espera prazo nenhum: caso critico validado avisa a Diretoria
-- na hora.
--
-- O calculo dos gatilhos continua fora do banco (app/services/ouvidoria_prazos.py,
-- issue #331): esta migration so guarda os carimbos de idempotencia.
-- =====================================================

-- 1. Um carimbo por degrau. O job so sobe degrau sem carimbo, e carimba com
--    update condicional (IS NULL) antes de enviar. Rodar o job duas vezes nao
--    duplica email nem movimento (mesmo desenho de prazo_rompido_em na 071).
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS vespera_avisada_em      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS escalonado_gestor_em    TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS escalonado_diretoria_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS critico_avisado_em      TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.vespera_avisada_em IS
  'Quando o job avisou o titular do setor na vespera do vencimento (issue #336). NULL enquanto o degrau nao subiu. Carimbo de idempotencia.';
COMMENT ON COLUMN ouvidoria_protocolos.escalonado_gestor_em IS
  'Quando o caso subiu ao gestor da area, 24h uteis depois do vencimento sem resposta (issue #336). Setor sem gestor cadastrado sobe direto a Diretoria, e o carimbo e o mesmo.';
COMMENT ON COLUMN ouvidoria_protocolos.escalonado_diretoria_em IS
  'Quando o caso chegou a Diretoria Executiva, 48h uteis depois do vencimento sem resposta (issue #336).';
COMMENT ON COLUMN ouvidoria_protocolos.critico_avisado_em IS
  'Quando a Diretoria Executiva foi avisada de um caso critico recem validado (issue #336). Nao espera prazo nenhum e nao respeita a janela comercial.';

-- 2. Os gatilhos novos entram no CHECK. CHECK nao tem IF NOT EXISTS: derruba e
--    recria, como a 068 e a 071 fizeram.
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
    'critico_imediato'
  ));

-- 3. O job de escalonamento le por aqui: casos aguardando area cuja escada
--    ainda nao chegou ao ultimo degrau, do prazo mais antigo para o mais novo.
--    O filtro pelo carimbo da Diretoria e o que impede caso abandonado em
--    aguardando area de ocupar a janela de leitura do job para sempre (mesmo
--    cuidado do indice parcial da cobranca, migration 071). Os degraus do meio
--    tem colunas proprias, e a decisao de qual ja subiu continua sendo do app.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_escalonamento
  ON ouvidoria_protocolos(prazo_area_em)
  WHERE status = 'aguardando_area' AND escalonado_diretoria_em IS NULL;
