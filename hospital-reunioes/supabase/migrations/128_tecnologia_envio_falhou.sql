-- =====================================================
-- Migration 128: o Envio falhou da Demanda
-- (issue #1535, PRD #1529, ADR 0083, decisao 7)
-- =====================================================
-- O "Criar o card" que nao chega ao GitHub deixa de ser so um erro na tela: a
-- Demanda guarda o estado do envio e o motivo, a lista mostra o selo "Envio
-- falhou" e "Reenviar" tenta de novo. O cron nao reenvia.
--
-- Tres colunas novas em `tecnologia_demandas`, todas nulaveis (a Demanda que
-- nunca tentou criar o card fica com as tres nulas):
--
--   1. `envio_estado`: `enviando` (a vez de criar esta tomada, a trava contra o
--      duplo clique), `falhou` (o GitHub nao criou a issue) e
--      `designacao_falhou` (a issue nasceu e a designacao nao: ja entra no CHECK
--      para a fatia seguinte, #1536, nao pedir outra parada no Studio);
--   2. `envio_motivo`: o motivo tecnico da falha, que so o Desenvolvedor le;
--   3. `envio_em`: o instante da ultima mudanca do envio. E o carimbo do
--      compare-and-swap da trava e o que solta uma trava de processo morto.
--
-- Estas colunas substituem o `github_sincronizado_em` como trava do duplo
-- clique: aquele carimbo e da sincronizacao com o GitHub, e a trava nao tem
-- mais nada com ele.
--
-- Sem indice: a tabela e pequena (dezenas de Demandas) e o filtro "Envio
-- falhou" le o que a lista ja le. Sem policy nova: a tabela ja esta com RLS e o
-- backend escreve com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS envio_estado TEXT;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS envio_motivo TEXT;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS envio_em TIMESTAMPTZ;

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_envio_estado_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_envio_estado_check
  CHECK (envio_estado IS NULL OR envio_estado IN ('enviando', 'falhou', 'designacao_falhou'));

COMMENT ON COLUMN tecnologia_demandas.envio_estado IS
  'O envio do card ao GitHub (ADR 0083, decisao 7): enviando (a vez de criar tomada, trava do duplo clique), falhou (o GitHub nao criou a issue; a lista mostra Envio falhou e Reenviar resolve) ou designacao_falhou (a issue nasceu sem o Responsavel). Nulo quando nao ha envio pendente. O cron nunca reenvia.';
COMMENT ON COLUMN tecnologia_demandas.envio_motivo IS
  'O motivo tecnico da ultima falha de envio. So o Desenvolvedor le; o diretor ve so o selo Envio falhou.';
COMMENT ON COLUMN tecnologia_demandas.envio_em IS
  'O instante da ultima mudanca do envio: o carimbo do compare-and-swap da trava e o que solta, depois de 60 s, a trava de um processo que morreu no meio.';

INSERT INTO migracoes_aplicadas (numero) VALUES (128) ON CONFLICT (numero) DO NOTHING;
