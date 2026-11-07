-- =====================================================
-- Migration 125: a troca da memoria vigente numa transacao so
-- (issue #1471, PRD #1415)
-- =====================================================
-- Ate aqui, marcar uma versao nova da memoria como a vigente eram duas idas
-- ao banco: um UPDATE que desmarcava a vigente da operadora e outro que
-- marcava a nova. Entre as duas havia uma janela. Em 05/11, na edicao da
-- ASSIM-PRI-09, o primeiro rodou e o segundo nao: as 19 versoes da ASSIM
-- ficaram com `vigente = false` e toda conta da ASSIM parou com
-- CM-CFG-MEMORIA ("sem memoria carregada").
--
-- Esta funcao faz as duas escritas dentro da MESMA transacao. Se a segunda
-- falhar, a primeira e desfeita e a versao anterior continua vigente. O
-- backend a chama em `importar_memoria` (operadoras.py) e em `_gravar_versao`
-- (memoria_edicao.py: editar, decidir e "Aplicar a todas").
--
-- A versao nova nasce nao vigente e recebe as regras antes de chegar aqui.
-- Se a troca falhar, ela fica orfa fora de uso, que e o comportamento que a
-- docstring de operadoras.py ja descreve.
--
-- Sem bloco EXCEPTION de proposito: qualquer falha aborta a transacao
-- inteira, que e o que impede a operadora de ficar sem vigente.
--
-- A funcao recusa versao de outra operadora: sem isso, um id trocado no
-- backend desmarcaria a vigente de uma operadora e marcaria a versao de outra,
-- e a primeira ficaria sem memoria do mesmo jeito.
--
-- SECURITY INVOKER e o alcance no molde da migration 101: quem chama e o
-- backend com a `service_role`, e EXECUTE fica revogado de `anon` e
-- `authenticated`.
--
-- O indice unico parcial `idx_cm_memoria_versao_vigente` (migration 116)
-- continua valendo: a ordem desmarca-depois-marca respeita ele dentro da
-- transacao. Nenhuma tabela nova nasce aqui, nada de RLS a ligar.
--
-- Reaplicavel: CREATE OR REPLACE, REVOKE e GRANT sao declaracoes de estado
-- final, e o recibo no fim usa ON CONFLICT DO NOTHING. A unica linha de dado
-- que a aplicacao toca e o recibo em `migracoes_aplicadas` (issue #969);
-- nenhuma linha de `cm_memoria_versao` muda.
-- =====================================================

CREATE OR REPLACE FUNCTION cm_trocar_memoria_vigente(
  p_operadora_id UUID,
  p_versao_id    UUID
)
RETURNS TABLE (versao_vigente UUID)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM cm_memoria_versao
     WHERE id = p_versao_id
       AND operadora_id = p_operadora_id
  ) THEN
    RAISE EXCEPTION 'A versao % nao e da operadora %', p_versao_id, p_operadora_id;
  END IF;

  UPDATE cm_memoria_versao
     SET vigente = false
   WHERE operadora_id = p_operadora_id
     AND vigente
     AND id <> p_versao_id;

  UPDATE cm_memoria_versao
     SET vigente = true
   WHERE id = p_versao_id;

  -- Uma linha de uma coluna, e nao void nem escalar: e o formato que o
  -- postgrest-py aceita sem tropeco (ver a migration 101).
  versao_vigente := p_versao_id;
  RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION cm_trocar_memoria_vigente(UUID, UUID) IS
  'Marca a versao como a memoria vigente da operadora e desmarca a anterior na MESMA transacao (issue #1471). Recusa versao de outra operadora. Sem bloco EXCEPTION: falha no meio desfaz a troca e a anterior continua vigente.';

-- Toda funcao criada em `public` nasce com EXECUTE concedido por nome a
-- `anon`, `authenticated` e `service_role` (padrao do Supabase). Esta funcao
-- ESCREVE: sem o REVOKE, a anon_key do bundle do frontend chegaria a ela.
REVOKE EXECUTE ON FUNCTION cm_trocar_memoria_vigente(UUID, UUID)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION cm_trocar_memoria_vigente(UUID, UUID) TO service_role;

INSERT INTO migracoes_aplicadas (numero) VALUES (125) ON CONFLICT (numero) DO NOTHING;
