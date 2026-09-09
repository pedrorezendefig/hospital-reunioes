-- =====================================================
-- Migration 101: o lote do Arquivo e o log de acesso na MESMA transacao
-- (issue #627, PRD #591, ADR 0047)
-- =====================================================
-- O lote do Arquivo (issue #594, migration 099) faz duas coisas em sequencia, e
-- elas sao duas idas ao banco: um UPDATE que carimba `arquivada_em` e
-- `arquivada_por` em todo caso encerrado sem arquivo, e um INSERT em
-- `ouvidoria_acessos`, uma linha por caso guardado.
--
-- Entre as duas ha uma janela. No timeout, o cliente desiste de esperar, mas o
-- UPDATE pode ter COMMITADO no servidor assim mesmo; o INSERT nunca roda. O
-- resultado sao N casos arquivados sem rastro nenhum, enquanto a tela diz ao
-- ouvidor que a operacao falhou.
--
-- O rastro some POR INTEIRO porque arquivar, por decisao do ADR 0047 (decisao
-- 4), nao grava movimento na trilha: gravar acenderia o ponto de novidade num
-- caso em que ninguem mexeu. E desarquivar apaga os dois carimbos. Entao
-- `ouvidoria_acessos` e o unico vestigio que existe de que o caso saiu da
-- vista, por quem e quando.
--
-- Nenhum `except` do lado do cliente fecha esta janela: a excecao acontece
-- aqui, do lado de ca, e o commit acontece la, do lado de la. Capturar decide o
-- que dizer ao ouvidor, nao o que ficou gravado. O conserto e uma ida so: as
-- duas escritas dentro da MESMA transacao, que e o que esta funcao faz.
--
-- SO O LOTE
-- ---------
-- Esta funcao substitui o par `update` + `registrar_acessos_em_lote` apenas em
-- `POST /manifestacoes/arquivo-dos-encerrados`. O ato de UM caso
-- (`POST`/`DELETE /manifestacoes/{id}/arquivo`) nao muda: a janela existe la
-- igual, mas o raio dela e 1, e o log continua fail-open. Se a auditoria pedir,
-- vira issue propria.
--
-- O LOG NAO E FAIL-OPEN AQUI DENTRO
-- ---------------------------------
-- Nao ha bloco EXCEPTION nesta funcao, e a ausencia dele e a feature: uma falha
-- no INSERT do log aborta a transacao e DESFAZ o UPDATE. Dentro de uma
-- transacao a pergunta do fail-open muda de sinal, porque o custo dele deixa de
-- ser "o ouvidor perde o log" e passa a ser "o lote fica sem rastro", que e
-- exatamente o que a issue existe para impedir. Um `EXCEPTION WHEN OTHERS` aqui
-- reintroduziria o bug em silencio, com a transacao inteira verde.
--
-- RETURNS TABLE, E NAO RETURNS INTEGER
-- ------------------------------------
-- A contagem volta como UMA LINHA de uma coluna, e nao como escalar. O
-- PostgREST devolve funcao escalar como escalar nu (`3`), e o `APIResponse` do
-- postgrest-py declara `data: List[JSON]`: o corpo escalar levanta
-- ValidationError antes de a rota ver numero nenhum, e o lote inteiro viraria
-- 500 depois de ja ter commitado. `RETURNS TABLE` faz o corpo ser
-- `[{"arquivadas": N}]`, que e o formato que o cliente aceita.
-- `test_o_cliente_de_verdade_recusa_a_contagem_escalar` prende esta escolha ao
-- cliente REAL, e nao ao Supabase falso.
--
-- SECURITY INVOKER, o padrao da casa
-- ----------------------------------
-- A triagem da issue sugeriu SECURITY DEFINER. Esta migration NAO usa, e a
-- diferenca esta escrita aqui para o humano poder reverter antes do merge com
-- uma palavra. Motivo: quem chama e o backend com a `service_role`, que ja
-- passa por cima do RLS, entao DEFINER nao habilita nada que hoje nao funcione;
-- o que ele faria e apagar a segunda camada de defesa que as migrations 095 e
-- 097 descrevem por extenso (as funcoes sao SECURITY INVOKER, entao uma chave
-- indevida esbarra no RLS default-deny da 064 por baixo). O repositorio inteiro
-- nao tem um SECURITY DEFINER sequer, e esta funcao ESCREVE em duas tabelas:
-- seria a pior primeira.
--
-- O que a triagem realmente pedia, e que esta aqui, e o alcance: EXECUTE
-- revogado de `anon` e `authenticated` e concedido so a `service_role`, no
-- padrao das 095 e 097.
--
-- SEM INDICE
-- ----------
-- Coerente com a decisao da 099, e nem havia o que criar: `ouvidoria_acessos` ja
-- tem `idx_ouvidoria_acessos_manifestacao` desde a 064.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar. As policies default-deny
-- da 064 seguem valendo para `ouvidoria_acessos` e as da mesma migration para
-- `ouvidoria_protocolos`.
--
-- Reaplicavel: CREATE OR REPLACE, REVOKE e GRANT sao declaracoes de estado
-- final. Rodar duas vezes deixa o banco no mesmo lugar, e nenhuma linha de dado
-- e tocada pela aplicacao desta migration.
-- =====================================================

CREATE OR REPLACE FUNCTION ouvidoria_arquivar_encerrados(
  p_ator_id   VARCHAR,
  p_ator_nome TEXT
)
RETURNS TABLE (arquivadas INTEGER)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  v_guardadas UUID[];
BEGIN
  -- O recorte vive no proprio UPDATE, e nao numa leitura anterior. E ele que
  -- faz a segunda rodada devolver zero, e e ele que impede o lote de reescrever
  -- quem e quando de uma leva antiga. `status` filtrado aqui (e nao so conferido
  -- antes) e a trava contra a reabertura que caia no meio.
  WITH carimbadas AS (
    UPDATE ouvidoria_protocolos
       SET arquivada_em  = now(),
           arquivada_por = p_ator_id
     WHERE status = 'encerrado'
       AND arquivada_em IS NULL
    RETURNING id
  )
  SELECT array_agg(id) INTO v_guardadas FROM carimbadas;

  -- Lote vazio nao registra acesso: o log e de ATO, e ato que nao aconteceu nao
  -- se registra. `array_agg` de conjunto vazio devolve NULL, e nao array vazio.
  IF v_guardadas IS NOT NULL THEN
    INSERT INTO ouvidoria_acessos (manifestacao_id, ator_id, ator_nome, acao)
    SELECT caso, p_ator_id, p_ator_nome, 'arquivar'
      FROM unnest(v_guardadas) AS caso;
  END IF;

  arquivadas := COALESCE(array_length(v_guardadas, 1), 0);
  RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION ouvidoria_arquivar_encerrados(VARCHAR, TEXT) IS
  'Arquiva de uma vez todo caso encerrado sem arquivo e grava o log de acesso de cada um na MESMA transacao (issue #627, ADR 0047). Devolve a contagem das linhas carimbadas. Sem bloco EXCEPTION de proposito: falha no log desfaz o arquivamento, porque lote arquivado sem rastro e o que esta funcao existe para impedir.';

-- O alcance, no padrao das migrations 095 e 097: o `ALTER DEFAULT PRIVILEGES`
-- que o Supabase mantem no schema `public` faz toda funcao criada ali nascer com
-- EXECUTE concedido DIRETO a `anon`, `authenticated` e `service_role`, por nome.
-- `REVOKE ... FROM PUBLIC` nao encosta em grant dado a role nomeada, e esta
-- funcao ESCREVE: sem as duas linhas abaixo, a anon_key do bundle do frontend
-- chegaria ao corpo dela.
REVOKE EXECUTE ON FUNCTION ouvidoria_arquivar_encerrados(VARCHAR, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION ouvidoria_arquivar_encerrados(VARCHAR, TEXT) TO service_role;
