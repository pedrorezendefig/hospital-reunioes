-- =====================================================
-- Migration 095: fechar de verdade o EXECUTE das RPCs da Ouvidoria
-- (issue #520, auditoria de conclusao do PRD #470, achado (a))
-- =====================================================
-- NAO HOUVE VAZAMENTO. Esta migration repoe uma SEGUNDA camada de defesa que a
-- 092 prometeu por escrito e nao entregou em SQL.
--
-- O que estava errado
-- -------------------
-- A 092 fechou assim:
--
--     REVOKE ALL ON FUNCTION ouvidoria_ultimo_movimento() FROM PUBLIC;
--
-- e em producao a chamada com a anon_key continuou devolvendo HTTP 200. O
-- motivo e o `ALTER DEFAULT PRIVILEGES` que o Supabase mantem no schema
-- `public`: toda funcao criada ali nasce com EXECUTE concedido DIRETO as roles
-- `anon`, `authenticated` e `service_role`, por nome. `REVOKE ... FROM PUBLIC`
-- nao encosta em grant dado a role nomeada, entao a `anon` ficou com a
-- permissao dela intacta.
--
-- O que segurou foi o RLS default-deny da 064. As funcoes sao SECURITY INVOKER
-- (o padrao da casa), entao rodam com a permissao de quem chama, e o corpo
-- voltou vazio. A camada que importa estava de pe. Corpo vazio, porem, e
-- exatamente o que faz esse tipo de furo passar despercebido: quem olha a
-- resposta ve o mesmo desenho de "fechado".
--
-- A 089 ja tinha aprendido isso e escreveu `FROM PUBLIC, anon, authenticated`.
-- Esta migration alinha as outras duas ao mesmo padrao.
--
-- Reaplicavel: REVOKE e GRANT sao declaracoes de estado final, nao deltas.
-- Rodar duas vezes deixa o banco no mesmo lugar, e revogar permissao que ja
-- nao existe e um no-op. Nenhuma linha de dado e tocada aqui.
--
-- DESTRUTIVA no sentido de permissao: ela TIRA o EXECUTE de `anon` e
-- `authenticated`. E o objetivo. Nada no app chama estas funcoes com a
-- anon_key (o frontend nao fala com o PostgREST direto; toda RPC sai do
-- backend com a service_role), e o GRANT explicito abaixo garante que a
-- service_role continua entrando.
-- =====================================================

-- 1. A funcao da issue. Agregado da trilha: sem o REVOKE, a anon_key do bundle
--    do frontend poderia contar quantas manifestacoes o hospital recebeu se um
--    dia o RLS da 064 afrouxasse.
REVOKE EXECUTE ON FUNCTION ouvidoria_ultimo_movimento()
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION ouvidoria_ultimo_movimento() TO service_role;

-- 2. A porta de entrada da maquina de estados (064, redefinida na 074 e na
--    075). Nunca teve REVOKE nenhum, o que e o mesmo furo em grau maior: ela
--    ESCREVE, e o `RETURNS ouvidoria_protocolos` devolveria a linha inteira do
--    caso, com o relato e o manifestante dentro. O RLS default-deny segura
--    (o `SELECT ... FOR UPDATE` nao acha a linha e a funcao levanta
--    "Manifestacao nao encontrada"), mas a defesa fica morando num arquivo que
--    nao e este, e a casa ja tem o historico exato desse padrao (#440, #459).
REVOKE EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT) TO service_role;

-- 3. A funcao da 089 ja esta revogada corretamente e NAO e reaberta aqui. O que
--    entra e so o GRANT explicito: hoje ela depende do `ALTER DEFAULT
--    PRIVILEGES` do Supabase para a service_role continuar executando, e esse
--    default e justamente o mecanismo implicito que criou este bug. Ficar de pe
--    sozinha custa uma linha.
GRANT EXECUTE ON FUNCTION ouvidoria_relatorio_registrar_entrega(UUID, JSONB, TEXT[], BOOLEAN, JSONB)
  TO service_role;
