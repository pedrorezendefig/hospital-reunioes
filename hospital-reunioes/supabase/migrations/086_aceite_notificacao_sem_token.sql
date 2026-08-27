-- =====================================================
-- Migration 086: tira o token de Aceite interno em claro
--                das notificacoes (issue #295)
-- =====================================================
-- A migration 060 alargou `notificacoes.referencia_id` para TEXT justamente
-- para caber o token do aceite, e o PR #294 passou a grava-lo ali em claro
-- para o sino navegar direto ate /aceite/{token}. Isso furava o invariante
-- hash-only de `reuniao_aceite_tokens`, onde so o SHA-256 vive: num vazamento
-- do banco, os tokens saiam utilizaveis.
--
-- O codigo novo grava o id da Reuniao na referencia e o sino pede o link a
-- POST /aceite/meu-link, autenticado. Esta migration limpa o que ja esta
-- gravado. E so DML: a coluna continua TEXT, porque os ids MIG_* tem 21+
-- caracteres e nao cabem no VARCHAR(10) original.
-- =====================================================

-- 1. Onde da para recuperar o destino, a referencia vira o id da Reuniao e o
--    sino continua funcionando. So o caso sem ambiguidade entra: destinatario
--    com exatamente UM token de aceite em aberto. Com dois ou mais nao ha como
--    saber de qual notificacao se trata, e chutar mandaria a pessoa para a ata
--    errada.
UPDATE notificacoes n
   SET referencia_id = c.id_reuniao
  FROM (
    SELECT participante_id, min(id_reuniao) AS id_reuniao
      FROM reuniao_aceite_tokens
     WHERE usado_em IS NULL
     GROUP BY participante_id
    HAVING count(*) = 1
  ) c
 WHERE n.tipo = 'ACEITE_INTERNO'
   AND n.destinatario_id = c.participante_id
   AND n.referencia_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM reunioes r WHERE r.id_reuniao = n.referencia_id);

-- 2. O que sobrou continua sendo token em claro (nao casa com Reuniao nenhuma)
--    e nao tem destino recuperavel: sai do banco. A notificacao permanece na
--    lista, so perde o atalho de clique. O frontend ja trata referencia vazia
--    sem navegar, entao nada quebra.
UPDATE notificacoes
   SET referencia_id = NULL
 WHERE tipo = 'ACEITE_INTERNO'
   AND referencia_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM reunioes r WHERE r.id_reuniao = notificacoes.referencia_id);

COMMENT ON COLUMN notificacoes.referencia_id IS
  'Id do recurso que a notificacao aponta (pendencia, ou Reuniao no ACEITE_INTERNO). Nunca token nem segredo: o link de aceite sai por POST /aceite/meu-link, autenticado (issue #295).';
