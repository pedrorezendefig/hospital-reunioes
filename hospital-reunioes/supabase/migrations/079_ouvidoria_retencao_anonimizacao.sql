-- =====================================================
-- Migration 079: retencao com anonimizacao apos 5 anos (issue #343, ADR 0034)
-- =====================================================
-- A ADR 0034 fecha a lista de controles de LGPD da Ouvidoria com "retencao de
-- 5 anos com anonimizacao". O job diario apaga o Dossie (relato, identificacao
-- de quem manifestou, anexos) da manifestacao encerrada ha mais de cinco anos
-- e preserva o que os relatorios contam: tipo, area, gravidade, canal, datas,
-- marcos e desfecho.
--
-- Nenhuma tabela nova nasce aqui (nada de RLS a ligar): a retencao precisa
-- apenas do carimbo de idempotencia e do indice da varredura.
-- =====================================================

-- 1. O carimbo. NULL enquanto o caso guarda o Dossie; preenchido no instante
--    em que a retencao o apaga. E ele que faz o job ser idempotente: o UPDATE
--    da anonimizacao so casa com `anonimizada_em IS NULL`, entao rodar de novo
--    nao acha caso para anonimizar.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS anonimizada_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.anonimizada_em IS
  'Quando a politica de retencao apagou o Dossie deste caso. NULL = Dossie ainda inteiro. Carimbo de idempotencia do job de retencao.';

-- 2. Indice da varredura, no molde parcial do resto do modulo (071/072/078):
--    o job le por status encerrado, sem carimbo, ordenando pelo marco T3.
--    O DROP vem antes do CREATE porque CREATE INDEX IF NOT EXISTS nao revisita
--    o WHERE de um indice ja existente: sem ele, um ambiente que aplicou uma
--    versao anterior desta migration ficaria com o predicado antigo, sem erro
--    e sem aviso.
DROP INDEX IF EXISTS idx_ouvidoria_protocolos_retencao;
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_retencao
  ON ouvidoria_protocolos(encerrada_em)
  WHERE status = 'encerrado' AND anonimizada_em IS NULL;

COMMENT ON INDEX idx_ouvidoria_protocolos_retencao IS
  'Fila da retencao: casos encerrados que ainda guardam o Dossie, do mais antigo para o mais novo.';

-- 3. O unico furo na imutabilidade da trilha, e ele e estreito.
--
--    Por que existe: a resposta da area viaja INTEIRA para
--    `ouvidoria_movimentos.observacao` (issue #374, app/services/
--    ouvidoria_respostas.py), e a rota GET /manifestacoes/{id}/respostas serve
--    esse texto. Sem este caminho, a retencao apagaria a copia em
--    `resposta_da_area` e deixaria o original legivel: anonimizacao que nao
--    anonimiza nada.
--
--    A ADR 0034 lista, no MESMO paragrafo de LGPD, "trilha imutavel de
--    movimentos" e "retencao de 5 anos com anonimizacao". As duas regras se
--    cruzam aqui, e o corte e este: a trilha guarda o FATO (quem, quando, de
--    que estado para qual), e o fato continua imutavel para sempre. O que sai
--    e o CONTEUDO, que e o relato de uma pessoa, nao metadado de auditoria.
--
--    O caminho e estreito em tres eixos, e cada um deles tem teste:
--      - so a coluna `observacao` pode mudar (qualquer outra coluna diferente
--        levanta excecao, como antes);
--      - so para NULL (nao da para reescrever a trilha com outro texto);
--      - so em manifestacao que a POLITICA cobre, isto e, encerrada ha mais de
--        cinco anos. Nao basta alguem ter carimbado `anonimizada_em`: o gatilho
--        confere a condicao da politica na propria linha do caso, entao
--        contornar a API nao contorna a retencao (mesmo principio da RPC de
--        transicao na 064).
--    DELETE continua barrado sem excecao nenhuma.
--
--    O intervalo de 5 anos aparece aqui e em ANOS_DE_RETENCAO
--    (app/services/ouvidoria_retencao.py). Mudar o prazo exige mexer nos dois:
--    o gatilho e a guarda externa, o servico e quem decide.
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
       AND p.encerrada_em <= now() - interval '5 years'
  ) THEN
    RAISE EXCEPTION 'Movimento de ouvidoria e imutavel: % nao e permitido', TG_OP
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Troca so o gatilho de UPDATE de `ouvidoria_movimentos`. O de DELETE, e os
-- dois de `ouvidoria_acessos`, continuam apontando para
-- ouvidoria_movimento_imutavel() e recusando tudo: o log de acesso nao guarda
-- relato nenhum, so quem abriu o que e quando.
DROP TRIGGER IF EXISTS trg_ouvidoria_movimentos_sem_update ON ouvidoria_movimentos;
CREATE TRIGGER trg_ouvidoria_movimentos_sem_update
  BEFORE UPDATE ON ouvidoria_movimentos
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_anonimizavel();

COMMENT ON FUNCTION ouvidoria_movimento_anonimizavel() IS
  'Guarda de UPDATE da trilha: recusa tudo, menos zerar a coluna observacao de manifestacao encerrada ha mais de cinco anos. O fato registrado continua imutavel; o conteudo do relato sai pela retencao (issue #343).';
