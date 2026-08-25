-- =====================================================
-- Migration 074: devolucao por insuficiencia
-- (issue #334, PRD #318, ADR 0034 decisao 12)
-- =====================================================
-- Resposta fraca nao encerra o caso: o ouvidor devolve ao setor com motivo
-- obrigatorio, e a area volta a dever resposta com METADE do prazo original da
-- gravidade contada da devolucao. O relogio nao zera.
--
-- Nao ha tabela nova. A devolucao e um ato, nao uma entidade: o motivo vive no
-- movimento da trilha (fonte da verdade do ato) e no `detalhe` da notificacao
-- que leva o motivo ao setor. O calculo do meio prazo e funcao pura em
-- app/services/ouvidoria_prazos.py (`vencimento_apos_devolucao`, issue #331).
--
-- Esta migration so abre as duas portas que o banco mantinha fechadas: a
-- transicao na RPC e o gatilho novo no catalogo de notificacoes.
-- =====================================================

-- 1. O grafo da RPC ganha a devolucao. A regra vive em dois lugares de
--    proposito (app/services/ouvidoria_estados.py e aqui), como a 064
--    estabeleceu: contornar a API nao pode contornar a maquina de estados.
--
--    Duas origens, conforme o PRD #318: de `respondido` (o caso comum, a
--    resposta que voltou e nao resolve) e de `aguardando_area` para
--    `aguardando_area` (o ouvidor devolve um caso que ja voltou a esperar a
--    area por outro caminho). O laco e inofensivo: o UPDATE reescreve o mesmo
--    status e o movimento registra o ato.
--
--    O motivo obrigatorio NAO entra como CHECK aqui: ele viaja em
--    `p_observacao`, que os outros atos usam como texto livre opcional, e
--    exigi-lo no banco quebraria toda transicao sem observacao. A guarda do
--    motivo e da camada de aplicacao (`validar_transicao`), que sabe distinguir
--    o acionamento (`em_classificacao` -> `aguardando_area`, sem motivo) da
--    devolucao.
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
       (v_atual = 'novo'             AND p_estado_novo = 'em_classificacao')
    OR (v_atual = 'em_classificacao' AND p_estado_novo IN ('aguardando_area', 'encerrado'))
    OR (v_atual = 'aguardando_area'  AND p_estado_novo IN ('respondido', 'encerrado', 'aguardando_area'))
    OR (v_atual = 'respondido'       AND p_estado_novo IN ('encerrado', 'aguardando_area'))
  ) THEN
    RAISE EXCEPTION 'Transicao invalida: % para %', v_atual, p_estado_novo USING ERRCODE = 'check_violation';
  END IF;

  IF p_estado_novo = 'encerrado' AND (
       p_desfecho IS NULL
    OR p_desfecho NOT IN ('procedente', 'improcedente', 'parcialmente_procedente', 'sem_condicoes_de_apuracao')
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

-- 2. O gatilho novo entra no CHECK. CHECK nao tem IF NOT EXISTS: derruba e
--    recria, como a 068, a 071, a 072 e a 073 fizeram. A lista carrega tambem
--    os gatilhos anteriores, porque o ultimo CHECK criado e o que vale.
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
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    -- Desta migration (issue #334): o motivo da devolucao viaja no `detalhe`.
    'resposta_devolvida'
  ));
