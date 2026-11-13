-- =====================================================
-- Migration 145: o Projeto na Demanda
-- (issue #1713, PRD #1710, ADR 0093, decisoes 2 e 3)
-- =====================================================
-- A aba Tecnologia passa a ter dois Projetos: o Aplicativo do Hospital e a
-- Ana, cada um com o seu repositorio no GitHub. A issue #50 da Ana e a #50 do
-- Hospital sao Demandas diferentes, e o indice unico do Vinculo, so pelo
-- numero da issue (migration 103), nao deixa as duas existirem juntas. Tres
-- mudancas, na tabela que ja existe:
--
--   1. `projeto`: `hospital` ou `ana`, obrigatorio. O default `hospital` da
--      as Demandas de hoje o Projeto delas no proprio ADD COLUMN (default
--      constante, sem reescrever a tabela) e vale para a conversa nova do
--      chat, que o Assistente so abre no Hospital.
--
--   2. O CHECK com a mesma lista do `github_client.PROJETOS`; o teste amarra
--      as duas pontas.
--
--   3. O indice unico do Vinculo passa a ser projeto mais numero da issue,
--      parcial como o de antes: Demanda sem Vinculo e a regra. O velho sai
--      antes, e os dois cabem na mesma transacao.
--
-- A sequencia do Numero da Demanda (migration 134) nao muda: "Demanda 42" e
-- uma so, seja do Hospital ou da Ana (ADR 0093, decisao 3).
--
-- Sem policy nova: a tabela ja esta com RLS e o backend escreve com a
-- service role (migration 102).
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

BEGIN;

ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS projeto TEXT NOT NULL DEFAULT 'hospital';

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_projeto_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_projeto_check
  CHECK (projeto IN ('hospital', 'ana'));

DROP INDEX IF EXISTS tecnologia_demandas_github_issue_numero_idx;
CREATE UNIQUE INDEX IF NOT EXISTS tecnologia_demandas_projeto_github_issue_numero_idx
  ON tecnologia_demandas (projeto, github_issue_numero)
  WHERE github_issue_numero IS NOT NULL;

COMMENT ON COLUMN tecnologia_demandas.projeto IS
  'O Projeto da Demanda (ADR 0093, decisao 2): hospital (o Aplicativo do Hospital) ou ana. Diz de qual repositorio e a issue do Vinculo; a chave do Vinculo e projeto mais github_issue_numero.';
COMMENT ON COLUMN tecnologia_demandas.github_issue_numero IS
  'Numero da issue-raiz no repositorio do Projeto (ADR 0054, decisao 1; ADR 0093, decisao 2). Nulo = Demanda sem Vinculo, que e a Etapa `registrada`.';

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (145) ON CONFLICT (numero) DO NOTHING;
