-- =====================================================
-- Migration 114: recibo de migration aplicada (issue #969, PRD #963, ADR 0063)
-- =====================================================
-- A migration e a unica parada humana do fluxo ate producao: o Postgres nao e
-- exposto e o SQL e colado no Studio. Ate aqui a subida (`fechar_onda.py`) nao
-- tinha como saber se a colagem aconteceu. Com esta tabela, toda migration
-- termina gravando o proprio numero, o `/api/health` devolve o maior numero
-- gravado, e a subida espera esse numero aparecer antes do merge (teto de 24 h).
--
-- O CI (`tools/checar_recibo_da_migration.py`) reprova migration nova que nao
-- termina com o insert do proprio numero. As migrations 001 a 113 sao
-- anteriores ao recibo e nao aparecem aqui: so o maior numero importa.
--
-- Reaplicar e inofensivo: IF NOT EXISTS na tabela e ON CONFLICT no recibo.
-- =====================================================

CREATE TABLE IF NOT EXISTS migracoes_aplicadas (
  numero INTEGER PRIMARY KEY,
  aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE migracoes_aplicadas IS
  'Recibo de migration aplicada (issue #969): toda migration termina gravando o proprio numero aqui, o /api/health devolve o maior e o rabo do deploy espera esse numero antes do merge.';

-- RLS default-deny (padrao da casa): o backend le com service_role; a anon_key
-- do bundle do frontend fica de fora. Nenhuma policy.
ALTER TABLE migracoes_aplicadas ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (114) ON CONFLICT (numero) DO NOTHING;
