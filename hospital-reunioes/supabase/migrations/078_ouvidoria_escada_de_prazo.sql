-- =====================================================
-- Migration 078: a escada de prazo para de mentir e de entupir
-- (issue #373, PRD #318, ADR 0034 decisao 12)
-- =====================================================
-- Dois defeitos da escada entregue na 072 precisam de banco:
--
-- 1. Caso cujo setor nao tem NINGUEM e cuja Diretoria Executiva esta vazia
--    nunca carimbava degrau nenhum. Ele voltava em toda rodada da varredura e,
--    por ser o mais antigo, vinha primeiro na ordenacao por `prazo_area_em`.
--    Passando de 200 casos assim (a janela de leitura do job), nenhum caso novo
--    entrava e o escalonamento parava para o hospital inteiro.
--
--    A saida e um carimbo PROPRIO. Gastar `escalonado_diretoria_em` tiraria o
--    caso da varredura, mas queimaria o ultimo degrau sem avisar ninguem: o
--    caso ficaria para sempre sem cobranca. Com coluna propria, o caso sai da
--    varredura intacto e volta a escada do degrau em que parou assim que o
--    cadastro do setor for corrigido (a rota do cadastro limpa a coluna).
--
-- 2. O degrau de +24h uteis de um setor sem gestor virava alerta a Diretoria
--    pelo gatilho `escalonamento_diretoria`, que esta em
--    GATILHOS_QUE_COBRAM_A_AREA. A guarda do despacho cancela esse conjunto
--    inteiro quando a area responde durante a janela de retencao: a area
--    respondia a tempo, o alerta era descartado, e o buraco de cadastro ficava
--    invisivel caso apos caso.
--
--    A saida e um gatilho separado. Olhar o `detalhe` na guarda seria frouxo:
--    some na primeira mudanca de texto.
--
-- Reaplicavel sem quebrar, como as anteriores.
-- =====================================================

-- 1. O carimbo do caso que nao tem a quem escalonar.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS escalonamento_impossivel_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.escalonamento_impossivel_em IS
  'Quando a varredura do escalonamento desistiu deste caso por nao haver a quem avisar: nem responsavel vigente no setor, nem participante com perfil de Diretoria Executiva (issue #373). NAO queima degrau nenhum: e so o que tira o caso da janela de leitura do job. A rota de cadastro de responsavel limpa a coluna, e a escada volta a subir do degrau em que parou.';

-- 2. O gatilho novo entra no CHECK. CHECK nao tem IF NOT EXISTS: derruba e
--    recria, como a 068, a 071, a 072, a 073, a 074 e a 075 fizeram. A lista
--    repete os gatilhos anteriores, porque o ultimo CHECK criado e o que vale.
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
    -- Desta migration (issue #373): o degrau de +24h de um setor SEM gestor,
    -- que vira alerta de cadastro a Diretoria. Fica FORA do conjunto que a
    -- guarda de retencao cancela, porque o buraco de cadastro continua la
    -- mesmo quando a area responde a tempo.
    'alerta_cadastro_setor',
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    'resposta_devolvida',
    'caso_reaberto'
  ));

-- 3. O indice parcial da varredura passa a excluir tambem o caso travado, para
--    o filtro do app ter indice por tras dele.
--
--    O DROP vem antes de proposito: CREATE INDEX IF NOT EXISTS nao REDEFINE
--    indice que ja existe. Sem ele, quem ja tem a versao da 072 ficaria com o
--    WHERE antigo, sem erro e sem aviso.
DROP INDEX IF EXISTS idx_ouvidoria_protocolos_escalonamento;
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_escalonamento
  ON ouvidoria_protocolos(prazo_area_em)
  WHERE status = 'aguardando_area'
    AND escalonado_diretoria_em IS NULL
    AND escalonamento_impossivel_em IS NULL;
