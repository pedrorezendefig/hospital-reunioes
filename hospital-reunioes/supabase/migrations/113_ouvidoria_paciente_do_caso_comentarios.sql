-- =====================================================
-- Migration 113: os comentarios do Paciente do caso passam a dizer a verdade
-- (issue #664, PRD #659, ADR 0052)
-- =====================================================
-- A migration 110 criou `paciente_nome` e `paciente_referencia` com os dois
-- COMMENT ON COLUMN marcando como PENDENTES as duas guardas do ADR 0052: a
-- Retencao ainda nao varria as colunas (issue #665) e o paciente ainda nao
-- viajava para a area (issue #664). A 110 ja esta aplicada e e imutavel, e o
-- proprio bloco dela pede que quem vier depois da #664 e da #665 atualize o
-- comentario: comentario de coluna que promete guarda inexistente e pior que
-- comentario nenhum.
--
-- Estado real com esta migration:
--   * a Retencao apaga as duas colunas pelas duas portas (o cron dos cinco
--     anos e a porta antecipada da Diretoria), desde a issue #665;
--   * o paciente viaja para a area (email de acionamento, reenvio e tela do
--     responsavel) no caso comum e no caso anonimo, e NAO viaja no sigilo
--     reforcado. Quem decide e uma funcao so, `paciente_do_caso` em
--     app/services/ouvidoria_blocos.py (issue #664).
--
-- So comentario: nenhuma coluna, dado, indice ou policy muda. Reaplicar e
-- inofensivo, e nada no app depende desta migration para funcionar.
-- =====================================================

COMMENT ON COLUMN ouvidoria_protocolos.paciente_nome IS
  'Nome do Paciente do caso, quando quem manifestou disse que o relato e sobre outra pessoa (issue #666, ADR 0052). Dado pessoal de TERCEIRO: o anonimato do manifestante NAO apaga esta coluna, porque o anonimato protege quem fala e o paciente e outra pessoa. NULL significa que ninguem informou, o que e opcional de proposito. Nasce com o caso e nao e editavel depois, como o resto da identificacao. Viaja para a area (email de acionamento, reenvio e tela do responsavel) no caso comum e no caso anonimo, e NAO viaja no sigilo reforcado: quem decide e ouvidoria_blocos.paciente_do_caso (issue #664). A Retencao apaga esta coluna pelas duas portas, o cron dos cinco anos e a porta antecipada da Diretoria (issue #665).';

COMMENT ON COLUMN ouvidoria_protocolos.paciente_referencia IS
  'Quando ou onde foi o atendimento do Paciente do caso: data, setor ou leito, em texto curto (issue #666, ADR 0052). Serve para a area distinguir o paciente de outros com o mesmo nome e achar o atendimento sem devolver o caso. Mesma regra da coluna paciente_nome: opcional, dado de terceiro e preservada no caso anonimo; viaja para a area junto do nome, nunca no sigilo reforcado (issue #664), e a Retencao a apaga pelas duas portas (issue #665). Cuidado extra: leito e data reidentificam quem manifestou, foi por isso que a migration 084 tirou o canal_ponto do caso anonimo.';
