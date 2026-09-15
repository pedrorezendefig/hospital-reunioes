-- =====================================================
-- Migration 107: o Redirecionamento pelo ouvidor
-- (issue #708, PRD #706, ADR 0055)
-- =====================================================
-- Uma aresta so: `respondido -> em_classificacao`.
--
-- O Redirecionamento e o ato do ouvidor que tira o caso de uma area e o aciona
-- em outra numa requisicao. Ele vale para caso em `aguardando_area`, que a 098
-- ja liberou pela Devolucao a Ouvidoria, e tambem para caso `respondido`: a
-- area errada que responde "isso e do Centro Medico" em vez de devolver pelo
-- link. Essa segunda origem e o que falta no grafo.
--
-- A regra vive em dois lugares de proposito (app/services/
-- ouvidoria_estados.py e aqui), como a 064 estabeleceu e a 098 repetiu:
-- contornar a API nao pode contornar a maquina de estados.
--
-- Nenhum estado novo, nenhuma coluna nova. O caso redirecionado e um caso a
-- despachar de novo, e a fila, o Dossie e a validacao ja sabem lidar com quem
-- espera o ouvidor (ADR 0048, decisao 1, que o ADR 0055 emenda). O motivo e o
-- setor antigo vivem na `observacao` do movimento, como a 074 estabeleceu para
-- a devolucao por insuficiencia e a 098 para a Devolucao a Ouvidoria: e por
-- isso que a Retencao ja os alcanca sem lugar novo para varrer.
--
-- O gatilho `redirecionamento_area` do aviso a area antiga NAO entra aqui: ele
-- e de outra fatia, e esta migration nao mexe no CHECK de gatilhos das
-- notificacoes (o vigente e o da 098).
-- =====================================================

-- O grafo, recriado inteiro. `CREATE OR REPLACE` substitui o corpo da 098,
-- entao a lista abaixo carrega TODAS as arestas anteriores: o ultimo corpo
-- criado e o que vale.
CREATE OR REPLACE FUNCTION ouvidoria_transicionar(
  p_manifestacao_id   UUID,
  p_estado_novo       TEXT,
  p_autor_id          VARCHAR(10),
  p_autor_nome        TEXT,
  p_observacao        TEXT DEFAULT NULL,
  p_desfecho          TEXT DEFAULT NULL,
  p_desfecho_descricao TEXT DEFAULT NULL
) RETURNS ouvidoria_protocolos AS $$
DECLARE
  v_atual   TEXT;
  v_destino ouvidoria_protocolos;
BEGIN
  -- FOR UPDATE: duas transicoes simultaneas na mesma manifestacao serializam,
  -- em vez de as duas lerem o mesmo estado atual e ambas passarem na regra.
  SELECT status INTO v_atual FROM ouvidoria_protocolos WHERE id = p_manifestacao_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Manifestacao nao encontrada' USING ERRCODE = 'no_data_found';
  END IF;

  IF NOT (
       (v_atual = 'novo'                    AND p_estado_novo = 'em_classificacao')
    OR (v_atual = 'em_classificacao'        AND p_estado_novo IN ('aguardando_area', 'encerrado'))
    -- `em_classificacao` desta linha e a Devolucao a Ouvidoria (issue #600) e,
    -- desde a issue #708, tambem o Redirecionamento pelo ouvidor.
    OR (v_atual = 'aguardando_area'         AND p_estado_novo IN ('respondido', 'encerrado', 'aguardando_area', 'aguardando_manifestante', 'em_classificacao'))
    OR (v_atual = 'aguardando_manifestante' AND p_estado_novo IN ('aguardando_area', 'encerrado'))
    -- `em_classificacao` desta linha e a aresta NOVA da issue #708: o
    -- Redirecionamento de um caso que a area errada ja respondeu.
    OR (v_atual = 'respondido'              AND p_estado_novo IN ('encerrado', 'aguardando_area', 'em_classificacao'))
    OR (v_atual = 'encerrado'               AND p_estado_novo = 'aguardando_area')
  ) THEN
    RAISE EXCEPTION 'Transicao invalida: % para %', v_atual, p_estado_novo USING ERRCODE = 'check_violation';
  END IF;

  IF p_estado_novo = 'encerrado' AND (
       p_desfecho IS NULL
    OR p_desfecho NOT IN ('procedente', 'improcedente', 'parcialmente_procedente', 'sem_condicoes_de_apuracao', 'sem_retorno_do_manifestante')
    OR btrim(COALESCE(p_desfecho_descricao, '')) = ''
  ) THEN
    RAISE EXCEPTION 'Encerrar exige desfecho e descricao' USING ERRCODE = 'check_violation';
  END IF;

  UPDATE ouvidoria_protocolos
     SET status             = p_estado_novo,
         desfecho           = COALESCE(p_desfecho, desfecho),
         desfecho_descricao = COALESCE(p_desfecho_descricao, desfecho_descricao)
   WHERE id = p_manifestacao_id
  RETURNING * INTO v_destino;

  INSERT INTO ouvidoria_movimentos (manifestacao_id, estado_anterior, estado_novo, autor_id, autor_nome, observacao)
  VALUES (p_manifestacao_id, v_atual, p_estado_novo, p_autor_id, p_autor_nome, p_observacao);

  RETURN v_destino;
END;
$$ LANGUAGE plpgsql;

-- `CREATE OR REPLACE` nao mexe nos GRANTs, mas a 095 deixou a regra escrita e a
-- 098 a repetiu: esta RPC e do backend, nunca da anon_key do bundle.
--
-- `PUBLIC` na frente nao e enfeite: no dia em que a funcao NASCER nesta
-- migration (banco novo montado so com as recentes, ou ordem trocada), o
-- Postgres concede EXECUTE a PUBLIC no nascimento, e `anon` (a chave que vive
-- no bundle do frontend) herda por PUBLIC mesmo com o revoke nominal abaixo.
REVOKE EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT) TO service_role;
