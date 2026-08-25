-- =====================================================
-- Migration 075: aguardando manifestante, sem retorno e reincidencia
-- (issue #335, PRD #318, ADR 0034 decisao 12)
-- =====================================================
-- Tres regras que a 064 deixou anotadas para esta fatia:
--
-- 1. PAUSA: falta dado de quem reclamou, o caso vai para
--    'aguardando_manifestante' e o relogio da area para. Na volta, o
--    vencimento anda para frente exatamente o expediente que ficou parado, e o
--    acumulado guarda esse tempo para o relato separado da Diretoria. Empurrar
--    o vencimento (em vez de descontar so na hora de medir) e o que faz a
--    escada de cobranca parar de cobrar: todo degrau le `prazo_area_em`.
--
-- 2. SEM RETORNO: o manifestante sumiu. O ouvidor encerra depois de duas
--    tentativas de contato registradas e cinco dias uteis de espera. O
--    desfecho novo fica NEUTRO no indicador de resolucao (nem resolvido, nem
--    nao resolvido), e essa neutralidade vive em app/services/
--    ouvidoria_estados.py (DESFECHOS_NEUTROS), nao aqui: o banco so precisa
--    aceitar o desfecho.
--
-- 3. REINCIDENCIA: o manifestante volta em ate 30 dias corridos e o caso
--    ORIGINAL reabre. Nao nasce protocolo novo, e e isso que impede a
--    reincidencia de inflar o volume de casos novos do PRD 3.
--
-- A tentativa de contato e a unica entidade nova. As outras tres regras sao
-- atos, e atos vivem no movimento da trilha, como a 074 estabeleceu para a
-- devolucao. A tentativa e diferente: a regra dos "dois contatos em cinco dias
-- uteis" precisa consultar quando cada um aconteceu, e contar isso lendo o
-- texto dos movimentos seria fragil.
-- =====================================================

-- 1. O estado da pausa entra no CHECK. A ordem nao importa aqui (nenhuma linha
--    existente usa o valor novo), mas o CHECK e derrubado e recriado inteiro
--    porque CHECK nao tem IF NOT EXISTS, como a 064 fez.
ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_status_check;

ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_status_check
  CHECK (status IN ('novo', 'em_classificacao', 'aguardando_area', 'aguardando_manifestante', 'respondido', 'encerrado'));

-- 2. O estado da pausa e a marca da reincidencia no caso.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS pausada_em       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS minutos_pausados INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reincidencia     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS reaberta_em      TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.pausada_em IS
  'Quando o relogio da area parou esperando o manifestante. NULL quando o caso nao esta parado. E daqui que a retomada conta o desconto.';
COMMENT ON COLUMN ouvidoria_protocolos.minutos_pausados IS
  'Minutos de EXPEDIENTE que o caso passou aguardando o manifestante, somados em todas as pausas. O desconto ja esta dentro de prazo_area_em; este numero existe para o relato separado, que impede o desconto de esconder lentidao real (PRD #318, historia 10).';
COMMENT ON COLUMN ouvidoria_protocolos.reincidencia IS
  'Caso que o manifestante voltou a cobrar dentro de 30 dias corridos do encerramento. Nao conta como caso novo no volume (PRD #318, historia 13).';

-- 3. A tentativa de contato com o manifestante. E o que libera (ou nao) o
--    encerramento por abandono, e o que o ouvidor le para saber o que ja
--    tentou. `canal` e texto livre de proposito: a Ouvidoria liga, manda email,
--    manda mensagem e as vezes deixa recado, e fechar a lista aqui travaria o
--    ouvidor no dia em que aparecer um caminho novo.
CREATE TABLE IF NOT EXISTS ouvidoria_tentativas_contato (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  tentada_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  canal           TEXT NOT NULL,
  observacao      TEXT,
  autor_id        VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  autor_nome      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_tentativas_manifestacao
  ON ouvidoria_tentativas_contato(manifestacao_id, tentada_em);

COMMENT ON TABLE ouvidoria_tentativas_contato IS
  'Cada vez que a Ouvidoria tentou falar com o manifestante. Encerrar por sem retorno exige duas destas e cinco dias uteis desde a primeira (PRD #318, historia 11).';
COMMENT ON COLUMN ouvidoria_tentativas_contato.autor_nome IS
  'Nome no momento do ato: o registro nao muda se a pessoa for renomeada ou removida depois, no padrao da trilha de movimentos.';

-- RLS default-deny na tabela nova (padrao da casa: 009/041/051/063/064).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_tentativas_contato ENABLE ROW LEVEL SECURITY;

-- 4. O grafo da RPC ganha as tres arestas da pausa e a da reabertura, e o
--    desfecho novo entra na lista aceita. A regra vive em dois lugares de
--    proposito (app/services/ouvidoria_estados.py e aqui), como a 064
--    estabeleceu: contornar a API nao pode contornar a maquina de estados.
--
--    'encerrado' deixa de ser terminal. Ele ganha UMA saida, e so uma: de volta
--    para 'aguardando_area', que e a reabertura por reincidencia. As guardas
--    que essa saida exige (motivo escrito, janela de 30 dias, prazo novo,
--    aviso ao setor) sao da camada de aplicacao, pelo mesmo motivo do motivo
--    da devolucao na 074: elas dependem do historico do caso, que o CHECK do
--    banco nao conhece.
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
    OR (v_atual = 'aguardando_area'         AND p_estado_novo IN ('respondido', 'encerrado', 'aguardando_area', 'aguardando_manifestante'))
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

-- 5. O gatilho novo entra no CHECK. CHECK nao tem IF NOT EXISTS: derruba e
--    recria, como a 068, a 071, a 072, a 073 e a 074 fizeram. A lista carrega
--    tambem os gatilhos anteriores, porque o ultimo CHECK criado e o que vale.
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
    'resposta_devolvida',
    -- Desta migration (issue #335): o caso encerrado voltou para a area porque
    -- o manifestante reclamou de novo. O motivo viaja no `detalhe`.
    'caso_reaberto'
  ));
