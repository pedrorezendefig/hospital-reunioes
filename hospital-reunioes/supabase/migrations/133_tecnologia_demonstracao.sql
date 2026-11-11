-- =====================================================
-- Migration 133: a Demonstracao no card
-- (issue #1559, PRD #1548)
-- =====================================================
-- A sincronizacao le na issue-raiz o marcador
-- `<!-- demonstracao: https://... -->` e grava o link do video e a data em que
-- ele chegou. A lista mostra o selo "Tem demonstracao" e o Documento do card a
-- secao Demonstracao com o link.
--
-- Duas colunas novas em `tecnologia_demandas`, nulaveis (a Demanda sem video
-- fica com as duas nulas):
--
--   1. `demonstracao_url`: o link, so `https` (o backend recusa o resto, e o
--      CHECK e a segunda trava);
--   2. `demonstracao_em`: quando o link chegou. Muda so quando o link e novo
--      ou trocou; tirar o marcador da issue nao apaga nenhuma das duas.
--
-- Sem indice e sem policy nova: a tabela ja esta com RLS e o backend escreve
-- com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS demonstracao_url TEXT;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS demonstracao_em TIMESTAMPTZ;

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_demonstracao_url_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_demonstracao_url_check
  CHECK (demonstracao_url IS NULL OR demonstracao_url LIKE 'https://%');

INSERT INTO migracoes_aplicadas (numero) VALUES (133) ON CONFLICT (numero) DO NOTHING;
