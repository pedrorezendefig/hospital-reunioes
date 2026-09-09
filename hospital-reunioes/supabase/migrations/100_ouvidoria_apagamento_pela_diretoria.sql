-- =====================================================
-- Migration 100: apagar pela Diretoria, a porta antecipada da Retencao
-- (issue #595, PRD #591, ADR 0047)
-- =====================================================
-- Apagar NAO e DELETE. A ADR 0047 decidiu que "apagar totalmente" e a mesma
-- politica de retencao da 079, feita hoje por ato humano: a diretoria_executiva
-- marca o caso encerrado, um por vez, com motivo escrito obrigatorio, e o mesmo
-- servico varre os mesmos cinco lugares. A linha da manifestacao continua de pe,
-- com protocolo, trilha, datas e desfecho: nenhum numero de relatorio ja
-- publicado muda.
--
-- Duas coisas nascem aqui, e so elas:
--   1. os tres campos do PEDIDO (quem, quando, por que), que sobrevivem a
--      anonimizacao porque sao o registro do ato;
--   2. a segunda chave da guarda de UPDATE da trilha.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos (migration 064) seguem valendo para a linha inteira,
-- colunas novas inclusas. A leitura e a escrita continuam sendo do backend com
-- a service_role, e o gate de papel vive na rota.
--
-- Nenhum indice: o apagamento e um ato por caso, sempre pelo id, e a varredura
-- do cron continua sendo a da 079 (`idx_ouvidoria_protocolos_retencao`), que ja
-- cobre `status = 'encerrado' AND anonimizada_em IS NULL`.
-- =====================================================

-- 1. Os tres campos do pedido. NULL nos tres e o normal, e e assim que todo
--    caso existente entra: o caso apagado pelos cinco anos tambem fica assim,
--    porque ali ninguem pediu nada, o prazo venceu.
--
--    Eles NAO sao apagados pela anonimizacao (a lista do que sai vive em
--    `CAMPOS_DO_DOSSIE`, no servico): sao o registro do ato, e sobrevivem junto
--    do protocolo e da trilha. Apagados junto com o Dossie, o caso apagado nao
--    saberia dizer quem mandou apagar nem por que.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS apagamento_pedido_em  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS apagamento_pedido_por VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS apagamento_motivo     TEXT;

COMMENT ON COLUMN ouvidoria_protocolos.apagamento_pedido_em IS
  'Quando a Diretoria Executiva mandou apagar o Dossie deste caso (issue #595, ADR 0047). NULL = ninguem pediu, e e assim que fica tambem o caso apagado pelos cinco anos. E esta coluna a segunda chave da guarda de UPDATE da trilha: gravada, ela abre o caminho para zerar a `observacao` dos movimentos deste caso antes dos cinco anos.';

COMMENT ON COLUMN ouvidoria_protocolos.apagamento_pedido_por IS
  'Quem pediu o apagamento (issue #595, ADR 0047). ON DELETE SET NULL porque o diretor pode sair do hospital, e o registro do ato continua valendo sem ele: o nome de quem assinou fica na trilha, que e imutavel.';

COMMENT ON COLUMN ouvidoria_protocolos.apagamento_motivo IS
  'O motivo escrito a mao pela Diretoria ao apagar (issue #595, ADR 0047). Obrigatorio na rota e preservado pela anonimizacao: junto com o movimento da trilha, e a unica coisa que sobra para explicar o buraco no lugar do relato.';

-- 2. A segunda chave da guarda de UPDATE da trilha.
--
--    A 079 abriu na trilha uma unica fresta: zerar `observacao` de caso
--    encerrado ha mais de cinco anos. A ADR 0047 (decisao 2) acrescenta a
--    segunda chave, e ela entra AO LADO da primeira, nao no lugar dela: o cron
--    continua passando pela mesma porta com o prazo dos cinco anos.
--
--    O resto do caminho continua igual de estreito, e cada eixo tem teste:
--      - so a coluna `observacao` pode mudar;
--      - so para NULL;
--      - so em manifestacao ENCERRADA e com o marco `encerrada_em`. A chave
--        nova nao afrouxa isso: ela troca "faz cinco anos" por "a Diretoria
--        pediu", e nada mais. Um caso em tramitacao nao passa por nenhuma das
--        duas, entao contornar a API continua nao contornando a politica;
--      - e so ENQUANTO o apagamento nao terminou (`anonimizada_em IS NULL`).
--        Esta condicao e nova, e vale para as DUAS chaves. Sem ela a fresta
--        ficava aberta para sempre depois do ato: o caso apagado seguiria
--        aceitando `UPDATE ... SET observacao = NULL` em qualquer movimento,
--        inclusive no movimento do proprio apagamento, que e a unica prova de
--        quem apagou e por que. Nao custa nada as duas portas, porque em
--        `apagar_caso` a limpeza da trilha roda sempre ANTES do carimbo, e
--        caso ja carimbado nunca volta ao servico (achado da revisao de
--        seguranca do PR #632).
--    DELETE continua barrado sem excecao nenhuma, e por isso esta migration
--    nao toca em gatilho nenhum: ela substitui apenas o CORPO da funcao que o
--    gatilho de UPDATE ja chama desde a 079. O gatilho de DELETE de
--    `ouvidoria_movimentos` e os dois de `ouvidoria_acessos` continuam
--    apontando para ouvidoria_movimento_imutavel() e recusando tudo.
--
--    O prazo de 5 anos continua escrito aqui e em ANOS_DE_RETENCAO
--    (app/services/ouvidoria_retencao.py), e a segunda chave tambem fica nos
--    dois lados: o servico confere a mesma regua antes de cada passo destrutivo
--    (`_caso_ainda_anonimizavel`). O gatilho e a guarda externa; o servico e
--    quem decide.
CREATE OR REPLACE FUNCTION ouvidoria_movimento_anonimizavel() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.observacao IS NOT NULL
     OR NEW.id              IS DISTINCT FROM OLD.id
     OR NEW.manifestacao_id IS DISTINCT FROM OLD.manifestacao_id
     OR NEW.ocorrido_em     IS DISTINCT FROM OLD.ocorrido_em
     OR NEW.estado_anterior IS DISTINCT FROM OLD.estado_anterior
     OR NEW.estado_novo     IS DISTINCT FROM OLD.estado_novo
     OR NEW.autor_id        IS DISTINCT FROM OLD.autor_id
     OR NEW.autor_nome      IS DISTINCT FROM OLD.autor_nome
  THEN
    RAISE EXCEPTION 'Movimento de ouvidoria e imutavel: % nao e permitido', TG_OP
      USING ERRCODE = 'check_violation';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM ouvidoria_protocolos p
     WHERE p.id = OLD.manifestacao_id
       AND p.status = 'encerrado'
       AND p.encerrada_em IS NOT NULL
       AND p.anonimizada_em IS NULL
       AND (
            p.encerrada_em <= now() - interval '5 years'
         OR p.apagamento_pedido_em IS NOT NULL
       )
  ) THEN
    RAISE EXCEPTION 'Movimento de ouvidoria e imutavel: % nao e permitido', TG_OP
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION ouvidoria_movimento_anonimizavel() IS
  'Guarda de UPDATE da trilha: recusa tudo, menos zerar a coluna observacao de manifestacao encerrada que a politica de retencao alcanca AINDA NAO ANONIMIZADA, por uma das duas chaves: cinco anos desde o encerramento (issue #343) ou pedido de apagamento gravado pela Diretoria Executiva (issue #595, ADR 0047). Terminado o ato (`anonimizada_em` carimbado), a fresta fecha e nem o movimento do apagamento pode ser zerado. O fato registrado continua imutavel; o que sai e o conteudo do relato. DELETE segue barrado sem excecao.';
