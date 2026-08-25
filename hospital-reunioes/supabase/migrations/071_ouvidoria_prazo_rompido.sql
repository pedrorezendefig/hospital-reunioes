-- =====================================================
-- Migration 071: cobranca de prazo rompido
-- (issue #327, PRD #317, ADR 0034 decisao 7)
-- =====================================================
-- A 068 criou a fila de notificacoes com dois gatilhos. Aqui entra o degrau do
-- vencimento: o job periodico varre os casos aguardando area, acha os prazos
-- vencidos e cobra titular e substituto. A escada completa de escalonamento
-- (vespera, gestor, Diretoria) e do PRD #318 e acrescenta os proprios valores.
--
-- Nasceu como 069 e foi renumerada: a 069 e a 070 ficaram com o portal do
-- setor (issue #326), que mergeou primeiro. O conteudo nao mudou.
-- =====================================================

-- 1. O carimbo de idempotencia da cobranca: o job so cobra caso sem carimbo, e
--    carimba com update condicional antes de enviar. Rodar o job duas vezes
--    nao duplica email nem movimento (precedente: lembrete_24h_enviado_at em
--    reunioes).
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS prazo_rompido_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.prazo_rompido_em IS
  'Quando o job de estouro cobrou o prazo rompido da area (issue #327). NULL enquanto o prazo nao venceu ou a area respondeu antes. E o carimbo de idempotencia: o job so cobra caso com a coluna NULL.';

-- 2. O gatilho novo entra no CHECK. CHECK nao tem IF NOT EXISTS: derruba e
--    recria, como a 068 fez com o CHECK de status.
ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN ('nova_demanda', 'alerta_sem_titular', 'prazo_rompido'));

-- 3. O job le exatamente por aqui: casos aguardando area, ainda sem carimbo.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_cobranca
  ON ouvidoria_protocolos(prazo_area_em)
  WHERE status = 'aguardando_area' AND prazo_rompido_em IS NULL;
