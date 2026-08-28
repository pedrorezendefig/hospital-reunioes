-- =====================================================
-- Migration 087: robustez da fila de recuperacao do relatorio (issue #434)
-- =====================================================
-- A varredura diaria de `entregar_atrasados` (migration 080) tinha tres
-- buracos, todos do mesmo tipo: a fila nao dizia em que pe cada edicao estava,
-- e por isso ela era varrida por JANELA DE DATA em vez de por ESTADO.
--
--   1. Sem teto, a edicao que falha em definitivo (endereco em quarentena no
--      provedor, dado corrompido que derruba o render daquela linha) era
--      rendida e tentada de novo todo dia, para sempre, sem ninguem saber.
--   2. Com `ORDER BY periodo_fim DESC LIMIT 3`, a quarta edicao nao enviada
--      ficava fora da janela para SEMPRE: toda rodada relia as mesmas tres.
--   3. Uma edicao morta ocupava vaga do lote e empurrava uma viva para fora.
--
-- As duas colunas abaixo dao a essa fila o estado que faltava.
-- =====================================================

-- Quantas vezes o caminho AUTOMATICO (job diario e varredura) tentou entregar
-- esta edicao e nao conseguiu. O reenvio manual do ouvidor NAO conta aqui: ele
-- e acao humana com o resultado na tela, e um ouvidor insistindo nao pode
-- enterrar a edicao para o job.
--
-- E tambem a chave de ordenacao da fila: quem tentou menos vai na frente. E
-- isso que faz a varredura girar em vez de reler as mesmas linhas.
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS tentativas INTEGER NOT NULL DEFAULT 0;

-- Quando a entrega automatica DESISTIU desta edicao, por ter batido o teto de
-- tentativas. E o estado terminal: nem o job nem a varredura tocam nela de
-- novo, e a listagem do ouvidor mostra a coluna para a linha nao ler como
-- "gerada, aguardando", que e exatamente o que ela deixou de ser.
--
-- Desistir NAO e desistir para sempre: o reenvio manual continua entregando a
-- edicao, e e o caminho previsto depois que alguem resolve o provedor.
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS desistido_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_relatorios.tentativas IS
  'Quantas vezes o caminho automatico (job e varredura) tentou entregar e falhou. Reenvio manual nao conta. E a chave de ordenacao da fila de recuperacao: quem tentou menos vai na frente.';
COMMENT ON COLUMN ouvidoria_relatorios.desistido_em IS
  'Quando a entrega automatica desistiu por bater o teto de tentativas. Estado terminal do caminho automatico; o reenvio manual continua disponivel.';

-- O indice da fila, refeito: ele existe para responder a pergunta que a
-- varredura faz, e a pergunta mudou. Agora e "quem ainda esta vivo nesta fila,
-- e quem tentou menos?", e nao "quais as tres edicoes nao enviadas mais
-- recentes". O indice antigo (periodo_fim DESC) responderia a pergunta errada
-- e ainda incluiria as linhas terminais.
DROP INDEX IF EXISTS idx_ouvidoria_relatorios_nao_enviados;
CREATE INDEX IF NOT EXISTS idx_ouvidoria_relatorios_fila_recuperacao
  ON ouvidoria_relatorios(tentativas ASC, periodo_fim ASC)
  WHERE enviado_em IS NULL AND desistido_em IS NULL;

-- Sem ENABLE ROW LEVEL SECURITY aqui: nao ha CREATE TABLE nesta migration, e
-- `ouvidoria_relatorios` ja e default-deny desde a 080.
