-- =====================================================
-- Migration 098: Devolucao a Ouvidoria
-- (issue #600, PRD #598, ADR 0048)
-- =====================================================
-- A area que recebe um caso que nao e dela devolve ao ouvidor pelo proprio
-- link do email, com motivo obrigatorio. O caso volta para a fila de quem
-- despacha, o relogio da area para e o link deixa de valer.
--
-- Duas mudancas, nenhuma tabela nova:
--
-- 1. O grafo da RPC ganha a aresta `aguardando_area -> em_classificacao`. A
--    regra vive em dois lugares de proposito (app/services/
--    ouvidoria_estados.py e aqui), como a 064 estabeleceu: contornar a API
--    nao pode contornar a maquina de estados. Nenhum estado novo: o caso
--    devolvido e um caso a despachar de novo, e a fila, o Dossie e a
--    validacao ja sabem lidar com quem espera o ouvidor (ADR 0048, decisao 1).
--
-- 2. O gatilho `devolvido_a_ouvidoria` entra no CHECK de gatilhos. O aviso a
--    Ouvidoria e a fatia seguinte, e ela so USA o gatilho: deixa-lo pronto
--    aqui evita uma migration so para acrescentar uma palavra a uma lista.
--
-- O motivo escrito pela area NAO ganha coluna: ele vive no movimento da
-- trilha, como a 074 estabeleceu para a devolucao por insuficiencia, e por
-- isso a Retencao ja o alcanca sem lugar novo para varrer.
-- =====================================================

-- 1. O grafo, recriado inteiro. `CREATE OR REPLACE` substitui o corpo da 075,
--    entao a lista abaixo precisa carregar TODAS as arestas anteriores: o
--    ultimo corpo criado e o que vale.
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
    -- `em_classificacao` desta linha e a Devolucao a Ouvidoria (issue #600).
    OR (v_atual = 'aguardando_area'         AND p_estado_novo IN ('respondido', 'encerrado', 'aguardando_area', 'aguardando_manifestante', 'em_classificacao'))
    OR (v_atual = 'aguardando_manifestante' AND p_estado_novo IN ('aguardando_area', 'encerrado'))
    OR (v_atual = 'respondido'              AND p_estado_novo IN ('encerrado', 'aguardando_area'))
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

-- `CREATE OR REPLACE` nao mexe nos GRANTs, mas a 095 deixou a regra escrita e
-- repeti-la e barato: esta RPC e do backend, nunca da anon_key do bundle.
--
-- `PUBLIC` na frente, como a 095 e a 097 escrevem, e nao e enfeite: no dia em
-- que a funcao NASCER nesta migration (banco novo montado so com as recentes,
-- ou ordem trocada), o Postgres concede EXECUTE a PUBLIC no nascimento, e
-- `anon` (a chave que vive no bundle do frontend) herda por PUBLIC mesmo com o
-- revoke nominal logo abaixo.
REVOKE EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION ouvidoria_transicionar(UUID, TEXT, VARCHAR, TEXT, TEXT, TEXT, TEXT) TO service_role;

-- 2. O gatilho novo no CHECK. CHECK nao tem IF NOT EXISTS: derruba e recria
--    com a lista INTEIRA, como a 096 fez, e dentro de uma transacao, porque
--    isto roda a mao em producao e a tabela nao pode ficar sem constraint se a
--    segunda metade falhar.
BEGIN;

ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN (
    'nova_demanda',
    'alerta_sem_titular',
    'prazo_rompido',
    'vespera_vencimento',
    'escalonamento_gestor',
    'escalonamento_diretoria',
    'alerta_cadastro_setor',
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    'resposta_devolvida',
    'caso_reaberto',
    'acusar_recebimento',
    'encerramento_manifestante',
    -- Desta migration (issue #600): a area devolveu o caso e a Ouvidoria
    -- precisa agir no mesmo dia. O setor e o motivo viajam no `detalhe`.
    'devolvido_a_ouvidoria'
  ));

COMMIT;
