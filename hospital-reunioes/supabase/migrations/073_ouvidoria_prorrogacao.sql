-- =====================================================
-- Migration 073: prorrogacao de prazo como entidade propria
-- (issue #333, PRD #318, ADR 0034 decisao 12)
-- =====================================================
-- O responsavel do setor pede mais prazo pelo proprio link tokenizado do
-- portal (issue #326), com justificativa. O ouvidor aprova ou nega. O sistema
-- recusa sozinho pedido pos-vencimento e segundo pedido, sem depender da
-- atencao de ninguem.
--
-- O calculo do prazo novo NAO vive aqui: e funcao pura em
-- app/services/ouvidoria_prazos.py (`vencimento_prorrogado`), que ja corta no
-- teto de 30 dias uteis da entrada. O banco guarda o pedido, a decisao e o
-- vencimento resultante, como a 065 estabeleceu para o resto do motor.
--
-- Nasceu como 072 e foi renumerada: a 072 ficou com a escada de escalonamento
-- (issue #336), que rodava em paralelo. O conteudo nao mudou.
-- =====================================================

-- 1. O pedido de prorrogacao. Uma linha por pedido ADMITIDO: recusa
--    automatica (pos-vencimento, segundo pedido) nao vira linha, porque ela
--    nao e ato do caso, e sim a porta que nao abriu.
CREATE TABLE IF NOT EXISTS ouvidoria_prorrogacoes (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id       UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  justificativa         TEXT NOT NULL CHECK (btrim(justificativa) <> ''),
  dias_uteis_pedidos    INTEGER NOT NULL CHECK (dias_uteis_pedidos > 0),
  -- Prazo anterior e novo ficam gravados no pedido: o vencimento do caso muda
  -- na aprovacao, e sem estes dois o painel nao consegue mais dizer de onde
  -- para onde o prazo andou.
  prazo_anterior        TIMESTAMPTZ,
  prazo_novo            TIMESTAMPTZ,
  status                TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'aprovada', 'negada')),
  solicitada_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
  solicitante_nome      TEXT NOT NULL,
  solicitante_email     TEXT,
  decidida_em           TIMESTAMPTZ,
  decidida_por          VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  decidida_por_nome     TEXT,
  decisao_justificativa TEXT
);

-- A regra "so um pedido por caso" tem guarda no banco tambem: contornar a API
-- nao pode contornar a regra (mesmo principio da RPC de transicao na 064).
CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_prorrogacoes_unica
  ON ouvidoria_prorrogacoes(manifestacao_id);

COMMENT ON TABLE ouvidoria_prorrogacoes IS
  'Pedido de prorrogacao de prazo da area (PRD #318, issue #333). Um por manifestacao: o segundo pedido e recusado automaticamente.';
COMMENT ON COLUMN ouvidoria_prorrogacoes.prazo_novo IS
  'O vencimento proposto, ja limitado ao teto de 30 dias uteis da entrada. Vira prazo_area_em do caso quando o ouvidor aprova.';
COMMENT ON COLUMN ouvidoria_prorrogacoes.solicitante_nome IS
  'Nome do responsavel no momento do pedido: nao muda se ele sair do papel depois.';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/068/069).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_prorrogacoes ENABLE ROW LEVEL SECURITY;

-- 2. Os dois gatilhos novos entram no CHECK. CHECK nao tem IF NOT EXISTS:
--    derruba e recria, como a 068 e a 071 fizeram. Como esta migration roda
--    DEPOIS da 072, a lista precisa carregar tambem os gatilhos da escada de
--    escalonamento (issue #336): o ultimo CHECK a ser criado e o que vale.
ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN (
    'nova_demanda',
    'alerta_sem_titular',
    'prazo_rompido',
    -- Da 072 (escada de escalonamento, issue #336): repetidos aqui porque este
    -- CHECK e o ultimo a ser criado e substitui o de la.
    'vespera_vencimento',
    'escalonamento_gestor',
    'escalonamento_diretoria',
    'critico_imediato',
    -- Desta migration.
    'prorrogacao_solicitada',
    'prorrogacao_decidida'
  ));
