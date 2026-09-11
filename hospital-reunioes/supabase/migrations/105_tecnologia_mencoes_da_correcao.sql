-- =====================================================
-- Migration 105: quais mencoes entraram na ULTIMA correcao
-- (issue #693, achado da review da issue #670)
-- =====================================================
-- A correcao de uma resposta, dentro dos 10 minutos, carimba `editado_em`, e
-- desde a #670 a chamada de uma linha corrigida conta a partir DESSE instante.
-- Como a linha nao guardava QUAIS mencoes tinham entrado na correcao, o
-- carimbo valia para TODAS elas: uma virgula corrigida reabria "Minha vez" de
-- quem ja tinha respondido aquela mesma fala.
--
-- Esta coluna guarda quem entrou na ultima correcao. Quem esta nela conta do
-- `editado_em`; os demais contam do `criado_em`, que e a ordem do fio.
--
-- Nenhuma tabela nova: uma coluna em `tecnologia_conversas`. RLS fica como
-- esta (default-deny, ligado na 102): nao ha CREATE TABLE aqui, entao nao ha
-- superficie nova para proteger.
--
-- IF NOT EXISTS porque a migration e aplicada a mao no Studio, e rodar duas
-- vezes tem que ser inofensivo.
-- =====================================================

-- Nula por padrao, e nula em quase toda linha: so a resposta CORRIGIDA depois
-- desta migration carrega lista. Os tres valores dizem coisas diferentes, e a
-- diferenca entre os dois ultimos e o conserto inteiro:
--
--   NULL  linha nunca corrigida, OU corrigida antes desta coluna existir. No
--         segundo caso nao ha como saber quem entrou, e vale o comportamento
--         da #670 (todos contam do `editado_em`): chamar de novo e o lado
--         seguro do erro, porque a Demanda reaparece na aba em vez de uma
--         chamada sumir de vista.
--   '{}'  corrigida SEM acrescentar mencao (a virgula): nao chama ninguem.
--   {ids} corrigida acrescentando gente: so ESSA gente conta do `editado_em`.
--
-- Mesmo tipo da coluna `mencoes` (102), que guarda ids de participante.
-- Substituida por inteiro a cada correcao, como o `editado_em`: as duas falam
-- sempre da ULTIMA.
ALTER TABLE tecnologia_conversas ADD COLUMN IF NOT EXISTS mencoes_da_correcao VARCHAR(10)[];

COMMENT ON COLUMN tecnologia_conversas.mencoes_da_correcao IS
  'Quem entrou na ULTIMA correcao desta resposta (issue #693). NULL = nunca corrigida, ou corrigida antes desta coluna (vale o comportamento da issue #670, todos do editado_em). Lista vazia = correcao sem mencao nova, nao chama ninguem. Nunca sai para a tela: e so para "Minha vez" saber para quem o editado_em vale.';
