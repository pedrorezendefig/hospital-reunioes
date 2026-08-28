-- =====================================================
-- Migration 084: apagar o ponto do cartaz dos casos anonimos (issue #375, item 12)
-- =====================================================
-- A decisao 5 da issue diz que caso anonimo nao grava `canal_ponto`: em sala
-- pequena, "Poltrona 12" em tal dia identifica a pessoa cruzando com o registro
-- de atendimento do proprio hospital, e o ponto serve so para o ouvidor achar o
-- cartaz.
--
-- A rota publica parou de gravar, mas o que ja esta gravado continua la, e a
-- mesma issue passou a EXIBIR `canal_ponto` no Dossie (item 11). Sem este
-- backfill, a fatia que existe para proteger o anonimato levaria a poltrona dos
-- casos antigos para a tela do ouvidor e da Diretoria: o risco de
-- reidentificacao que a decisao 5 quer evitar, sobre as linhas que ja existem.
--
-- A retencao da 079 nao alcanca esta coluna (ela preserva canal e datas), entao
-- o conserto e aqui.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar.
-- =====================================================

-- Idempotente pelo proprio WHERE: rodar de novo nao acha linha para limpar.
UPDATE ouvidoria_protocolos
   SET canal_ponto = NULL
 WHERE anonimo IS TRUE
   AND canal_ponto IS NOT NULL;

COMMENT ON COLUMN ouvidoria_protocolos.canal_ponto IS
  'Lugar exato do cartaz que a pessoa leu ("Poltrona 12"). Serve para o ouvidor achar o cartaz. NUNCA e gravado em caso anonimo (issue #375, decisao 5): cruzado com o registro de atendimento, o ponto reidentifica quem pediu anonimato.';
