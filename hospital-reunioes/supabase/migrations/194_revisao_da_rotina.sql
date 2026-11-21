-- =====================================================
-- Migration 194: a revisao de 90 dias da Rotina (issue #1944; decisao 72 da #1757)
-- =====================================================
-- O Facilitador revisa cada Rotina a cada 90 dias: mantem ou encerra. Sem
-- revisao a Rotina continua, e a revisao espera na Minha Fila dele. Manter e
-- um clique no Inicio e grava aqui o dia; a proxima revisao vence 90 dias
-- depois dele (ou do nascimento, enquanto nunca foi revisada).
--
-- So duas colunas novas em `rotinas`, que ja tem RLS default-deny (177): so o
-- backend, com a service_role, le e grava. Rodar duas vezes e inofensivo.
-- Aplicar a mao no Studio.
-- =====================================================

BEGIN;

ALTER TABLE rotinas ADD COLUMN IF NOT EXISTS revisada_em DATE;
ALTER TABLE rotinas ADD COLUMN IF NOT EXISTS revisada_por_nome TEXT;

COMMENT ON COLUMN rotinas.revisada_em IS
  'Ultima revisao que manteve a Rotina (decisao 72 da #1757). A proxima vence 90 dias depois. Issue #1944.';

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (194) ON CONFLICT (numero) DO NOTHING;
