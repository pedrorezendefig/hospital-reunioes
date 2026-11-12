-- =====================================================
-- Migration 134: o Numero da Demanda
-- (issue #1585, PRD #1584)
-- =====================================================
-- Toda Demanda ganha um numero proprio, sequencial no app ("Demanda 42" na
-- tela), que o diretor e a Vitta usam para falar do mesmo pedido. Nao e o
-- numero da issue, que continua so do Desenvolvedor.
--
-- Quem numera e o banco, no insert, pelo default da coluna (o padrao do
-- protocolo da Ouvidoria, migration 063): as duas Origens (a conversa do
-- diretor e a Demanda da Vitta aberta pelo terminal) ganham numero sem codigo
-- novo nos caminhos de criacao.
--
--   1. a coluna `numero` nasce sem default, para o preenchimento seguir a
--      ordem de criacao, e nao a ordem fisica das linhas;
--   2. as Demandas que ja existem ganham numero por `criado_em`, empate
--      desfeito pelo `id`. As apagadas (lapide) entram na conta: o numero
--      delas nao volta para a fila;
--   3. a sequence segue do maior numero ja usado, sem nunca andar para tras
--      (rodar de novo depois de uma Demanda apagada nao reaproveita o numero);
--   4. so entao o default, o NOT NULL e o UNIQUE.
--
-- Uma transacao so, com a tabela travada: uma conversa nova no meio do
-- caminho nasceria sem numero e derrubaria o NOT NULL.
--
-- Sem policy nova: a tabela ja esta com RLS e o backend escreve com a
-- service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

BEGIN;

LOCK TABLE tecnologia_demandas IN SHARE ROW EXCLUSIVE MODE;

CREATE SEQUENCE IF NOT EXISTS tecnologia_demandas_numero_seq;

ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS numero BIGINT;

ALTER SEQUENCE tecnologia_demandas_numero_seq OWNED BY tecnologia_demandas.numero;

WITH ordem AS (
  SELECT id, row_number() OVER (ORDER BY criado_em, id) AS posicao
  FROM tecnologia_demandas
  WHERE numero IS NULL
)
UPDATE tecnologia_demandas d
SET numero = (SELECT coalesce(max(numero), 0) FROM tecnologia_demandas) + ordem.posicao
FROM ordem
WHERE d.id = ordem.id;

SELECT setval(
  'tecnologia_demandas_numero_seq',
  greatest(
    (SELECT coalesce(max(numero), 0) FROM tecnologia_demandas),
    (SELECT CASE WHEN is_called THEN last_value ELSE last_value - 1 END FROM tecnologia_demandas_numero_seq)
  ) + 1,
  false
);

ALTER TABLE tecnologia_demandas
  ALTER COLUMN numero SET DEFAULT nextval('tecnologia_demandas_numero_seq');
ALTER TABLE tecnologia_demandas ALTER COLUMN numero SET NOT NULL;

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_numero_key;
ALTER TABLE tecnologia_demandas ADD CONSTRAINT tecnologia_demandas_numero_key UNIQUE (numero);

COMMENT ON COLUMN tecnologia_demandas.numero IS
  'O Numero da Demanda ("Demanda 42"), gerado pela sequence no insert. Para todo mundo que ve a Demanda; nao e o numero da issue.';

INSERT INTO migracoes_aplicadas (numero) VALUES (134) ON CONFLICT (numero) DO NOTHING;

COMMIT;
