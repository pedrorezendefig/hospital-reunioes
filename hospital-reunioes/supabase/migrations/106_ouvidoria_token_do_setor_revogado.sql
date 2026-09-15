-- =====================================================
-- Migration 106: o token do portal do setor pode ser REVOGADO
-- (issue #707, PRD #706, ADR 0055)
-- =====================================================
-- Hoje o token nao sabe de que acionamento veio. Depois que o caso volta a
-- `em_classificacao` (Devolucao a Ouvidoria) e o ouvidor reaciona OUTRA area,
-- os links vivos da area antiga (o acionamento e cada cobranca) continuam
-- abrindo o portal: a area errada responde pelo caso da area certa, e o T2
-- entra em nome de quem ja nao e mais responsavel pelo caso.
--
-- A marca nova fecha isso. `revogado_em` diz "este link foi derrubado por um
-- acionamento posterior", e o `carregar` do servico recusa quem a tem.
--
-- Ela e SEPARADA de `usado_em` de proposito. Revogar nao toca a marca de uso,
-- porque as duas contam coisas diferentes na trilha: `usado_em` prova que
-- alguem respondeu por aquele link, e sobrescrever isso apagaria o rastro de
-- quem respondeu. Uma coluna so obrigaria a escolher entre as duas verdades.
--
-- Nullable e sem backfill: link revogado e a excecao, e NULL e o link vivo.
-- Carimbar os links ja existentes agora derrubaria o link que esta na caixa de
-- entrada de quem esta com o caso neste momento.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar. O RLS default-deny de
-- `ouvidoria_setor_tokens` (migration 069) segue valendo para a linha inteira,
-- coluna nova inclusa.
-- =====================================================

ALTER TABLE ouvidoria_setor_tokens
  ADD COLUMN IF NOT EXISTS revogado_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_setor_tokens.revogado_em IS
  'Quando este link foi derrubado por um acionamento posterior do mesmo caso (issue #707, ADR 0055). NULL = link vivo. Nao substitui usado_em: revogar nao toca a marca de uso, para a trilha continuar distinguindo link usado de link revogado.';
