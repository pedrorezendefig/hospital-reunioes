-- =====================================================
-- Migration 122: Contas medicas, o Codigo do erro da conta
-- (issue #1337, PRD #1335)
-- =====================================================
-- Toda conta em Erro passa a dizer a causa de verdade: um codigo curto em
-- quatro familias (CM-ARQ, CM-CFG, CM-IA e CM-APP) e um detalhe tecnico para a
-- TI. O motivo de hoje (`erro_motivo`) continua como a frase que quem enviou
-- le.
--
-- O que entra:
--   1. `erro_codigo` na conta, com o CHECK das quatro familias;
--   2. `erro_detalhe` na conta: o tipo do erro, o codigo HTTP, a etapa, o
--      arquivo e a linha do codigo e a hora do erro. Nunca texto do
--      prontuario nem a mensagem da resposta da IA (o backend so grava esses
--      campos). Enquanto a conta esta PROCESSANDO, guarda a etapa em curso,
--      para a analise que o restart interrompeu dizer onde parou;
--   3. as contas que ja estao em Erro com o motivo antigo "Tente de novo em
--      alguns minutos" ganham o codigo CM-IA-ANTIGO, que a tela le como erro
--      da IA (o botao Analisar de novo, da issue #1339).
--
-- Sem tabela nova, sem policy nova: `cm_conta` tem RLS default-deny desde a
-- 116 (quem le e escreve e o backend com a service_role).
--
-- Tudo com IF NOT EXISTS / DROP antes de ADD / WHERE erro_codigo IS NULL:
-- rodar duas vezes e inofensivo. Aplicar a mao no Studio, depois da 121: o
-- deploy nao aplica SQL, e o backend novo grava as duas colunas.
-- =====================================================

-- ---------- 1 e 2. As duas colunas ----------
ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS erro_codigo TEXT;

ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS erro_detalhe JSONB;

ALTER TABLE cm_conta DROP CONSTRAINT IF EXISTS cm_conta_erro_codigo_check;
ALTER TABLE cm_conta
  ADD CONSTRAINT cm_conta_erro_codigo_check
  CHECK (erro_codigo IS NULL OR erro_codigo ~ '^CM-(ARQ|CFG|IA|APP)-[A-Z]+(-[A-Z]+)*$');

COMMENT ON COLUMN cm_conta.erro_codigo IS
  'Codigo do erro da conta em Erro (issue #1337): CM-ARQ (o PDF), CM-CFG (configuracao da gestao), CM-IA (a IA) ou CM-APP (defeito do app). A frase continua em erro_motivo.';
COMMENT ON COLUMN cm_conta.erro_detalhe IS
  'Detalhe tecnico do Erro para a TI: tipo, http, etapa, arquivo, linha e em (a hora). Nunca leva texto do prontuario.';

-- ---------- 3. As contas em Erro com o motivo antigo ----------
UPDATE cm_conta
   SET erro_codigo = 'CM-IA-ANTIGO'
 WHERE situacao = 'ERRO'
   AND erro_motivo = 'Tente de novo em alguns minutos'
   AND erro_codigo IS NULL;

INSERT INTO migracoes_aplicadas (numero) VALUES (122) ON CONFLICT (numero) DO NOTHING;
