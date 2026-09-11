-- =====================================================
-- Migration 104: a Conversa espelhada na issue do GitHub
-- (issue #680, PRD #673, ADR 0054, decisoes 4 e 5)
-- =====================================================
-- Toda resposta gravada numa Demanda vinculada vira um comentario na issue.
-- Esta migration guarda, na propria linha da Conversa, o id que o GitHub deu
-- a esse comentario: e por ele que a correcao da resposta (dentro dos 10
-- minutos) edita o comentario em vez de publicar outro.
--
-- Nenhuma tabela nova: uma coluna em `tecnologia_conversas`. RLS fica como
-- esta (default-deny, ligado na 102): nao ha CREATE TABLE aqui, entao nao ha
-- superficie nova para proteger.
--
-- IF NOT EXISTS porque a migration e aplicada a mao no Studio, e rodar duas
-- vezes tem que ser inofensivo.
-- =====================================================

-- Nulo por padrao, e nulo na esmagadora maioria das linhas: so a resposta de
-- gente numa Demanda vinculada, espelhada com sucesso, carrega o id. Linha
-- automatica (movimento, responsavel, Etapa, Vinculo) nunca e espelhada, e a
-- resposta cujo espelho falhou (GitHub fora, token vencido) fica sem id, com
-- o texto intacto no fio: a Conversa nunca depende do GitHub.
--
-- BIGINT porque o id de comentario do GitHub ja passou de 2^31.
ALTER TABLE tecnologia_conversas ADD COLUMN IF NOT EXISTS github_comentario_id BIGINT;

COMMENT ON COLUMN tecnologia_conversas.github_comentario_id IS
  'Id do comentario espelhado na issue vinculada (ADR 0054, decisao 4). Nulo = nao espelhada (linha automatica, Demanda sem Vinculo ou espelho que falhou). Nunca sai para a tela: e so para editar o comentario quando a resposta e corrigida.';
