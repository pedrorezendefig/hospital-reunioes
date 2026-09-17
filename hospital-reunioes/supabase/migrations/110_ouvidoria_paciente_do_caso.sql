-- =====================================================
-- Migration 110: o Paciente do caso na Manifestacao (issue #666, PRD #659,
-- ADR 0052)
-- =====================================================
-- Quem reclama pelo QR setorial muitas vezes e acompanhante (mae, pai, conjuge)
-- em nome de um paciente. A pessoa escrevia o relato, as vezes assinava, e nao
-- dizia de quem falava: o ouvidor acionava e a area devolvia o caso porque nao
-- achava o atendimento. A Manifestacao nao tinha onde guardar isso, e o unico
-- lugar era o meio do relato.
--
-- As duas colunas abaixo guardam o Paciente do caso: o nome e uma referencia
-- curta do atendimento (data, setor ou leito). O formulario publico passa a
-- perguntar "Este relato e sobre quem?", e a resposta grava o vinculo do
-- manifestante (`paciente` ou `acompanhante`, coluna da migration 064) mais
-- estes dois dados quando o relato e sobre outra pessoa.
--
-- NULL e o normal: informar e OPCIONAL de proposito (ADR 0052, decisao 2). O
-- canal aberto nunca barra o envio por dado faltando, e nenhum caso ja gravado
-- informou nada. Sem backfill, portanto: inventar o paciente de caso antigo
-- seria por na boca de quem manifestou uma palavra que ele nao disse.
--
-- Sem CHECK: nao ha lista fechada a repetir aqui. Sao texto curto escrito por
-- quem manifestou, e o teto de 200 caracteres cada vive na aplicacao, junto do
-- mesmo teto que ja vale para o nome e o contato do manifestante.
--
-- DADO PESSOAL DE TERCEIRO, e e isso que muda a leitura das duas colunas: quem
-- o anonimato protege e QUEM MANIFESTA, e o paciente e outra pessoa (ADR 0052,
-- decisao 3). Marcar "anonimo" zera nome e contato do manifestante e NAO zera
-- estas colunas.
--
-- ATENCAO, ESTADO REAL NA DATA DESTA MIGRATION (fatia de fundacao, issue #666):
-- as duas guardas que o ADR 0052 promete para estas colunas AINDA NAO EXISTEM
-- no codigo, e sao fatias proprias do PRD #659:
--
--   * a RETENCAO NAO VARRE estas colunas. `CAMPOS_DO_DOSSIE`, em
--     app/services/ouvidoria_retencao.py, e lista fechada, e coluna que nao
--     esta nela sobrevive tanto ao cron dos cinco anos quanto a porta
--     antecipada da Diretoria (que carimba `anonimizada_em` mesmo assim).
--     Enquanto a issue #665 nao subir, o nome e o leito de um paciente
--     sobrevivem ao apagamento do resto do Dossie;
--   * a GUARDA DO CASO PROTEGIDO nao existe porque o paciente ainda nao viaja
--     para lugar nenhum: `_CAMPOS_DO_EMAIL` (ouvidoria_notificacoes.py) e
--     `_CAMPOS_DO_PORTAL` (ouvidoria_setor.py) continuam sem estas colunas, e
--     e a issue #664 que leva o paciente a area com a regra da decisao 4
--     (comum e anonimo levam, sigilo reforcado nao leva).
--
-- Quem for mexer aqui depois da #664 e da #665 atualiza este bloco: comentario
-- de coluna que promete guarda inexistente e pior que comentario nenhum.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos seguem valendo para a linha inteira, colunas novas
-- inclusas.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS paciente_nome       TEXT,
  ADD COLUMN IF NOT EXISTS paciente_referencia TEXT;

COMMENT ON COLUMN ouvidoria_protocolos.paciente_nome IS
  'Nome do Paciente do caso, quando quem manifestou disse que o relato e sobre outra pessoa (issue #666, ADR 0052). Dado pessoal de TERCEIRO: o anonimato do manifestante NAO apaga esta coluna, porque o anonimato protege quem fala e o paciente e outra pessoa. NULL significa que ninguem informou, o que e opcional de proposito. Nasce com o caso e nao e editavel depois, como o resto da identificacao. PENDENTE nesta fatia: a Retencao AINDA NAO varre esta coluna (nem o cron dos cinco anos nem a porta antecipada da Diretoria), e ela PASSARA a varrer na issue #665; o paciente tambem ainda nao viaja para a area, e a guarda do sigilo reforcado da decisao 4 chega na issue #664.';

COMMENT ON COLUMN ouvidoria_protocolos.paciente_referencia IS
  'Quando ou onde foi o atendimento do Paciente do caso: data, setor ou leito, em texto curto (issue #666, ADR 0052). Serve para a area distinguir o paciente de outros com o mesmo nome e achar o atendimento sem devolver o caso. Mesma regra da coluna paciente_nome: opcional, dado de terceiro e preservada no caso anonimo, com as mesmas duas pendencias (a Retencao ainda nao a varre, issue #665; o paciente ainda nao viaja para a area, issue #664). Cuidado extra na hora de varrer: leito e data reidentificam quem manifestou, foi por isso que a migration 084 tirou o canal_ponto do caso anonimo.';
