-- =====================================================
-- Migration 097: fechar o EXECUTE das cinco RPCs de fora da Ouvidoria
-- (issue #541, achado das duas revisoes do PR #537)
-- =====================================================
-- NAO HOUVE VAZAMENTO. Esta e a irma da 095 para as funcoes que ficaram de
-- fora dela: a 095 fechou o modulo da Ouvidoria, e estas cinco nasceram antes
-- do modulo existir, em quatro migrations diferentes (001, 010, 024 e 029),
-- sem REVOKE nenhum.
--
-- A causa raiz e a mesma da #520, e esta escrita por extenso no cabecalho da
-- 095: o `ALTER DEFAULT PRIVILEGES` que o Supabase mantem no schema `public`
-- faz toda funcao criada ali nascer com EXECUTE concedido DIRETO as roles
-- `anon`, `authenticated` e `service_role`, por nome. `REVOKE ... FROM PUBLIC`
-- nao encosta em grant dado a role nomeada, e nenhuma destas cinco tinha nem
-- isso.
--
-- Quem lidera a fila: `generate_participant_id()`
-- ----------------------------------------------
-- E a UNICA das cinco onde o RLS nao e defesa alguma. O corpo dela e
-- `nextval('participantes_id_seq')`, e sequence nao passa por RLS: a chamada
-- anonima ia ate o fim e queimava um ID `P###` de verdade. O impacto e baixo
-- (nao vaza dado, e o `VARCHAR(10)` pediria bilhoes de chamadas para esgotar),
-- mas ela e a unica sem segunda camada, e por isso e a que justifica a
-- migration sozinha.
--
-- Nas outras quatro o RLS default-deny da 009 segura de fato: as funcoes sao
-- SECURITY INVOKER (o padrao da casa, e o repositorio inteiro nao tem um
-- SECURITY DEFINER sequer), entao o UPDATE nao acha linha e o INSERT e negado.
-- A defesa, porem, mora num arquivo que nao e este, que e exatamente o arranjo
-- que a #520 veio corrigir.
--
-- Quem chama estas funcoes
-- ------------------------
-- So o backend, e o backend fala com o PostgREST pela service_role
-- (`app/dependencies.py`, `create_client(..., supabase_service_role_key)`):
--
--   * `incrementar_acoes_concluidas` e `decrementar_acoes_concluidas`:
--     `app/routers/pendencias.py`;
--   * `merge_participante_externo`: `app/routers/admin/usuarios.py`;
--   * `confirmar_importacao_atomico`: sem chamador no codigo de hoje, a funcao
--     continua viva no banco;
--   * `generate_participant_id`: ninguem chama por RPC, ela e o DEFAULT da
--     coluna `participantes.id` (001). DEFAULT roda com a permissao de quem
--     insere, entao um INSERT em `participantes` feito por `anon` ou
--     `authenticated` passa a falhar com 42501 em vez de falhar pelo RLS. Isso
--     e aceitavel porque nao existe esse caminho: o frontend nao fala com o
--     PostgREST direto (nao ha um `.rpc(` nem um `from("participantes")` nele),
--     e todo INSERT sai do backend com a service_role.
--
-- Reaplicavel: REVOKE e GRANT sao declaracoes de estado final, nao deltas.
-- Rodar duas vezes deixa o banco no mesmo lugar, e revogar permissao que ja nao
-- existe e um no-op. Nenhuma linha de dado e tocada aqui.
--
-- DESTRUTIVA no sentido de permissao: ela TIRA o EXECUTE de `anon` e
-- `authenticated`. E o objetivo. O GRANT explicito ao lado de cada REVOKE
-- garante que a service_role continua entrando, e de quebra tira o backend da
-- dependencia do default implicito do Supabase, que e o mecanismo que criou
-- este bug.
-- =====================================================

-- 1. A que lidera. Sem segunda camada: sequence nao passa por RLS.
REVOKE EXECUTE ON FUNCTION generate_participant_id()
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION generate_participant_id() TO service_role;

-- 2 e 3. As duas RPCs atomicas de `acoes_concluidas` (010). Escrevem em
--    `reunioes`; o RLS da 009 segura, mas o REVOKE e a camada que faltava.
REVOKE EXECUTE ON FUNCTION incrementar_acoes_concluidas(TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION incrementar_acoes_concluidas(TEXT) TO service_role;

REVOKE EXECUTE ON FUNCTION decrementar_acoes_concluidas(TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION decrementar_acoes_concluidas(TEXT) TO service_role;

-- 4. A confirmacao de importacao (024). Insere reuniao e pendencias em bloco
--    atomico a partir de JSONB cru.
REVOKE EXECUTE ON FUNCTION confirmar_importacao_atomico(JSONB, JSONB, JSONB)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION confirmar_importacao_atomico(JSONB, JSONB, JSONB) TO service_role;

-- 5. O merge de participante externo (029). A mais pesada das cinco: reescreve
--    FKs em varias tabelas e a propria migration a descreve como NAO reversivel.
REVOKE EXECUTE ON FUNCTION merge_participante_externo(VARCHAR, VARCHAR, TEXT, VARCHAR, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION merge_participante_externo(VARCHAR, VARCHAR, TEXT, VARCHAR, TEXT) TO service_role;
