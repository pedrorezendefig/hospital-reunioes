-- =====================================================
-- Migration 103: vinculo da Demanda com a issue do GitHub
-- (issue #674, PRD #673, ADR 0054)
-- =====================================================
-- A aba Tecnologia (migration 102) nao sabe nada do que acontece no GitHub,
-- onde o trabalho e planejado e entregue. Esta migration abre as colunas do
-- Vinculo: a Demanda passa a guardar o numero da issue-raiz, a Etapa derivada
-- dela e a foto do que o GitHub respondeu na ultima sincronizacao.
--
-- Nenhuma tabela nova: sao colunas em `participantes` e em
-- `tecnologia_demandas`, mais um CHECK afrouxado em `tecnologia_conversas`.
-- RLS fica exatamente como esta (default-deny nas tres tabelas de Tecnologia,
-- ligado na 102, e a politica de `participantes`, que nao se toca): nao ha
-- CREATE TABLE aqui, entao nao ha superficie nova para proteger.
--
-- Tudo com IF NOT EXISTS / DROP antes de CREATE: a migration e aplicada a mao
-- no Studio, e rodar duas vezes tem que ser inofensivo.
-- =====================================================

-- ---------- 1. O login do GitHub da pessoa ----------
-- Campo OPCIONAL, e um fato sobre a pessoa, nao um lado (ADR 0054, decisao 4).
-- E ele que separa quem e da Vitta (ve numero de issue, campo de vincular e
-- link para o GitHub) de quem e do hospital (ve so a Etapa em palavras).
ALTER TABLE participantes ADD COLUMN IF NOT EXISTS github_login TEXT;

-- Unico sem distinguir maiusculas e ignorando quem nao tem login: o app grava
-- sempre em minusculas, e o indice parcial e o que impede dois participantes
-- de responderem pelo mesmo login (WHERE ... IS NOT NULL porque a coluna e
-- nula na esmagadora maioria das linhas, e NULL nao colide com NULL de todo
-- jeito).
CREATE UNIQUE INDEX IF NOT EXISTS participantes_github_login_lower_idx
  ON participantes ((lower(github_login)))
  WHERE github_login IS NOT NULL;

COMMENT ON COLUMN participantes.github_login IS
  'Login no GitHub, em minusculas (ADR 0054, decisao 4). Quem tem ve os controles do Vinculo na aba Tecnologia; quem nao tem ve so a Etapa. Nulo = nao e da Vitta.';

-- ---------- 2. As colunas do Vinculo na Demanda ----------
-- Uma Demanda para UMA issue-raiz (o PRD, ou uma issue simples de correcao).
-- As fatias sao as sub-issues dessa raiz e nunca se vinculam uma a uma
-- (ADR 0054, decisao 1).
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS github_issue_numero INTEGER;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS etapa TEXT NOT NULL DEFAULT 'registrada';
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS partes_entregues INTEGER;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS partes_total INTEGER;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS o_que_muda JSONB;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS partes JSONB;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS github_foto JSONB;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS github_sincronizado_em TIMESTAMPTZ;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS vinculado_por VARCHAR(10)
  REFERENCES participantes(id) ON DELETE SET NULL;

-- Uma issue nao serve a duas Demandas: o par e guardado dos dois lados (a
-- Demanda guarda o numero, a issue guarda o id da Demanda num marcador oculto
-- no corpo), e dois donos do mesmo numero fariam o marcador mentir. O indice e
-- parcial pelo mesmo motivo do de cima: Demanda sem Vinculo e a regra.
--
-- A API ja recusa com 422 e frase de gente antes de chegar aqui; este indice e
-- o piso, para o caso de duas pessoas vincularem o mesmo numero ao mesmo tempo.
CREATE UNIQUE INDEX IF NOT EXISTS tecnologia_demandas_github_issue_numero_idx
  ON tecnologia_demandas (github_issue_numero)
  WHERE github_issue_numero IS NOT NULL;

-- A Etapa e DERIVADA do GitHub e nunca digitada (ADR 0054, decisao 3). O CHECK
-- e a mesma lista fechada do servico puro que a calcula; o teste amarra as duas
-- pontas.
ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_etapa_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_etapa_check
  CHECK (etapa IN ('registrada', 'em_analise', 'planejada', 'em_desenvolvimento', 'entregue', 'nao_sera_feita'));

COMMENT ON COLUMN tecnologia_demandas.github_issue_numero IS
  'Numero da issue-raiz no repositorio da integracao (ADR 0054, decisao 1). Nulo = Demanda sem Vinculo, que e a Etapa `registrada`.';
COMMENT ON COLUMN tecnologia_demandas.etapa IS
  'Onde o desenvolvimento esta, em palavras do diretor. DERIVADA das labels, das sub-issues e do fechamento da issue; o PATCH da Demanda nao a aceita (ADR 0054, decisao 3).';
COMMENT ON COLUMN tecnologia_demandas.partes_entregues IS
  'Quantas sub-issues ja fecharam como concluidas. Nulo quando a issue nao tem sub-issues: "0 de 0 partes" seria uma barra vazia onde nao ha partes.';
COMMENT ON COLUMN tecnologia_demandas.partes_total IS
  'Quantas sub-issues a issue-raiz tem. Nulo quando nao tem nenhuma, pelo mesmo motivo de `partes_entregues`.';
COMMENT ON COLUMN tecnologia_demandas.o_que_muda IS
  'O bloco "Para o diretor" da issue-raiz, lido do GitHub e nunca digitado no app (ADR 0054, decisao 7). Preenchido pela fatia seguinte; nasce nulo aqui.';
COMMENT ON COLUMN tecnologia_demandas.partes IS
  'O "Para o diretor" de cada sub-issue com a situacao dela (ADR 0054, decisao 7). Preenchido pela fatia seguinte; nasce nulo aqui.';
COMMENT ON COLUMN tecnologia_demandas.github_foto IS
  'A ultima foto que o GitHub respondeu (estado, motivo do fechamento, labels e as sub-issues). Guardada inteira para a sincronizacao seguinte saber se algo MUDOU: foto igual a esta nao grava linha nenhuma na Conversa.';
COMMENT ON COLUMN tecnologia_demandas.github_sincronizado_em IS
  'Quando a foto acima foi tirada. E o que a tela mostra para dizer ha quanto tempo a Etapa foi conferida.';
COMMENT ON COLUMN tecnologia_demandas.vinculado_por IS
  'Quem criou o Vinculo. ON DELETE SET NULL porque a pessoa pode sair, e o Vinculo continua valendo.';

-- ---------- 3. A Conversa passa a registrar Etapa e Vinculo ----------
-- O fio ja tinha linha automatica de `estado` e `responsavel` (migration 102).
-- Vincular, desvincular e cada mudanca de Etapa tambem viram linha (ADR 0054,
-- decisao 5): e por elas que o diretor fica sabendo do desenvolvimento, sem ver
-- nada do GitHub.
ALTER TABLE tecnologia_conversas DROP CONSTRAINT IF EXISTS tecnologia_conversas_movimento_campo_check;
ALTER TABLE tecnologia_conversas
  ADD CONSTRAINT tecnologia_conversas_movimento_campo_check
  CHECK (movimento_campo IS NULL OR movimento_campo IN ('estado', 'responsavel', 'etapa', 'vinculo'));

COMMENT ON COLUMN tecnologia_conversas.movimento_campo IS
  'O que mudou na linha de movimento: `estado`, `responsavel`, `etapa` ou `vinculo`. O de/para fica em `movimento_de` e `movimento_para`; o texto legivel e montado pelo backend na hora de gravar.';
