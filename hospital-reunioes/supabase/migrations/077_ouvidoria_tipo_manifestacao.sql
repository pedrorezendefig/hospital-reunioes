-- =====================================================
-- Migration 077: o tipo da manifestacao vira lista fechada
-- (issue #372, PRD #317, ADR 0034 decisao 1)
-- =====================================================
-- Ate aqui o sigilo do caso era decidido por TEXTO LIVRE: a aplicacao
-- procurava as palavras "denuncia" e "relato de conduta" na coluna `categoria`,
-- que e o que o ouvidor digitou (e, no canal da Ana, o que o cliente dela
-- mandou). Um caso classificado como "Assedio moral" nao casava com nenhuma
-- das duas: nao elevava o sigilo, e o email de acionamento chegava ao setor
-- acusado com o nome de quem manifestou.
--
-- A coluna abaixo e a lista fechada que passa a decidir. O CHECK repete a
-- lista que a aplicacao ja valida: a aplicacao recusa antes, o banco recusa
-- depois, e nenhuma das duas confia na outra.
--
-- NULL e um valor com significado: "ainda nao classificado". E onde o canal
-- aberto entra (o formulario publico nao pergunta o tipo), e e por isso que o
-- caso nasce fail-closed la. Quem tira o caso desse estado e o ouvidor, pela
-- porta de classificacao.
--
-- `categoria` NAO e renomeada nem removida: ela continua sendo o rotulo humano
-- do caso, escrito com as palavras de quem classificou, e nao decide mais
-- nada. Renomear obrigaria a app e o banco a subirem no mesmo instante (o lado
-- que subisse primeiro pediria uma coluna que o outro nao tem, e TODA rota de
-- ouvidoria daria 500 na janela); o ganho seria so o nome.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS tipo_manifestacao TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ouvidoria_protocolos_tipo_manifestacao_check'
  ) THEN
    ALTER TABLE ouvidoria_protocolos
      ADD CONSTRAINT ouvidoria_protocolos_tipo_manifestacao_check
      CHECK (tipo_manifestacao IS NULL OR tipo_manifestacao IN (
        'denuncia', 'reclamacao', 'sugestao', 'elogio', 'relato_de_conduta'
      ));
  END IF;
END $$;

COMMENT ON COLUMN ouvidoria_protocolos.tipo_manifestacao IS
  'Tipo da manifestacao em lista fechada (issue #372). E ele, e nao o texto livre de categoria, que decide o sigilo: denuncia e relato_de_conduta sao sigilosos por natureza (ADR 0034, decisao 1). NULL significa NAO CLASSIFICADO, estado em que o caso e tratado como sigiloso (fail-closed) ate o ouvidor classificar.';

-- Backfill do que ja existe. O criterio e o mesmo que a regra antiga
-- reconhecia por texto, sem acento e sem caixa, para nenhum caso hoje sigiloso
-- virar nao sigiloso por causa desta migration:
--   * casa com "denuncia"          -> denuncia
--   * casa com "relato de conduta" -> relato_de_conduta
--   * o resto                      -> reclamacao (decisao 3 da issue #372)
--
-- Excecao: o rotulo do canal aberto ("A classificar") continua NULL. Aquele
-- caso literalmente nao foi classificado, e carimba-lo de reclamacao seria
-- gravar no banco uma decisao que ninguem tomou, ainda por cima abrindo o piso
-- de sigilo de um caso que hoje esta fechado.
UPDATE ouvidoria_protocolos
SET tipo_manifestacao = CASE
  WHEN lower(categoria) LIKE '%denuncia%' OR lower(categoria) LIKE '%denúncia%' THEN 'denuncia'
  WHEN lower(categoria) LIKE '%relato de conduta%' THEN 'relato_de_conduta'
  ELSE 'reclamacao'
END,
-- O sigilo acompanha o tipo, e por isso o backfill o levanta junto. A regra
-- antiga nunca correu no canal da Ana (o insert de la nao chamava
-- `nasce_sigilosa`), entao existe caso com "denuncia" escrito na categoria e
-- `sigilo_reforcado = false`. Sem esta linha, a migration carimbaria a linha
-- de denuncia no banco e a deixaria visivel no indice de facilitador,
-- secretaria e super admin: o contrario do invariante que esta fatia cria.
-- So sobe, nunca desce: quem ja e sigiloso continua sigiloso.
sigilo_reforcado = (
  sigilo_reforcado
  OR lower(categoria) LIKE '%denuncia%'
  OR lower(categoria) LIKE '%denúncia%'
  OR lower(categoria) LIKE '%relato de conduta%'
)
WHERE tipo_manifestacao IS NULL
  AND btrim(categoria) <> 'A classificar';

-- Os relatorios do PRD 3 (#319) agrupam por tipo, e a fila do ouvidor procura
-- o que falta classificar (tipo_manifestacao IS NULL). O indice serve os dois
-- usos.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_tipo
  ON ouvidoria_protocolos(tipo_manifestacao);
