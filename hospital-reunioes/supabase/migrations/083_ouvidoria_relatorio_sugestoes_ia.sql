-- =====================================================
-- Migration 083: sugestoes de acao corretiva por IA no relatorio (issue #346, PRD #319)
-- =====================================================
-- O relatorio MENSAL (o do dia 1) termina numa secao de tres sugestoes de acao
-- corretiva escritas por IA a partir dos numeros do mes. Estas duas colunas
-- guardam o resultado dessa chamada.
--
-- POR QUE COLUNA PROPRIA, E NAO DENTRO DE `dados`
--
-- O COMMENT da coluna `dados` diz o que ela e: "a resposta congelada de
-- ouvidoria_metricas.metricas_do_periodo". Texto escrito por IA nao e medicao,
-- e misturar os dois no mesmo campo apagaria essa distincao justamente onde ela
-- importa. Com coluna separada, o proprio schema diz que aquele texto veio de
-- uma maquina que opina, e nao do modulo que mede.
--
-- O QUE E GRAVADO, E O QUE NAO E
--
-- Fica gravada a RESPOSTA (as tres sugestoes), porque o reenvio precisa
-- entregar o mesmo PDF do original: e a mesma regra de congelamento que vale
-- para `dados` desde a migration 080.
--
-- NAO fica gravado o texto ENVIADO a IA. Ele e montado na hora por
-- `ouvidoria_relatorio.resumo_para_a_ia`, viaja na chamada e morre ali.
-- Persisti-lo duplicaria conteudo da Ouvidoria num campo que nenhuma politica
-- de retencao varre (a anonimizacao de 5 anos conhece as colunas do Dossie,
-- nao esta tabela).
--
-- O QUE VAI PARA A IA
--
-- Apenas o agregado: volume, canais, temas, areas, prazo, reincidencia,
-- prorrogacao, tempo medio, tendencia e nota externa. Nenhum relato, nenhum
-- resumo de caso, nenhum protocolo e nenhum nome (nem o do titular do setor,
-- que e o unico nome proprio que o objeto de metricas carrega). O portao e o
-- ADR 0034, e ele tem furo conhecido de NOME registrado na issue #412: por isso
-- o desenho nao manda texto livre nenhum, em vez de confiar no portao.
-- =====================================================

-- As tres sugestoes, no formato { "itens": [ { titulo, porque, acao } ] }.
-- NULL quando a IA nao respondeu: e o `sugestoes_aviso` que explica o buraco.
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS sugestoes JSONB;

-- O que o PDF imprime no lugar da secao quando a IA falhou, esta fora do ar ou
-- devolveu resposta inutilizavel. Secao que some sem dizer nada le como "nao
-- havia o que sugerir", que e diferente de "nao deu para sugerir".
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS sugestoes_aviso TEXT;

COMMENT ON COLUMN ouvidoria_relatorios.sugestoes IS
  'Sugestoes de acao corretiva escritas por IA a partir dos numeros AGREGADOS do periodo (issue #346). Nunca a partir de relato, resumo de caso, protocolo ou nome. O texto enviado a IA nao e persistido. NULL = a chamada nao produziu sugestao; veja sugestoes_aviso.';
COMMENT ON COLUMN ouvidoria_relatorios.sugestoes_aviso IS
  'O que o PDF imprime no lugar da secao de sugestoes quando a IA nao respondeu. NULL quando as sugestoes sairam.';

-- Sem ENABLE ROW LEVEL SECURITY aqui: nao ha CREATE TABLE nesta migration, e
-- `ouvidoria_relatorios` ja e default-deny desde a 080.
