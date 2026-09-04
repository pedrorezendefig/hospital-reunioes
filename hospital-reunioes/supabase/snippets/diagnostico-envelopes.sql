-- SOMENTE LEITURA. Reunioes com assinatura em aberto e quem precisa assinar.
-- Se vier VAZIO: pode trocar os e-mails hoje, sem risco nenhum.
--
-- A LISTA DE E-MAILS AFETADOS SAIU DAQUI. Eram enderecos de pessoas reais, e
-- num repositorio publico isso e dado pessoal exposto. A lista original esta em
-- `local/diagnostico-envelopes_com_lista_real.sql` (pasta `local/`, ADR 0044).
--
-- Para rodar com uma lista: crie a tabela temporaria abaixo, cole os enderecos
-- e execute o SELECT na mesma sessao do SQL Editor.
--
--   CREATE TEMP TABLE emails_afetados (email TEXT PRIMARY KEY);
--   INSERT INTO emails_afetados (email) VALUES ('...'), ('...');

SELECT
  r.id_reuniao,
  r.data,
  r.titulo,
  r.status_ata,
  coalesce(r.envelope_id_clicksign, r.envelope_key_clicksign) AS envelope,
  p.nome_completo                                             AS signatario,
  p.email                                                     AS email_no_envelope,
  CASE WHEN EXISTS (
      SELECT 1 FROM emails_afetados e WHERE e.email = lower(p.email)
  ) THEN 'AFETADO PELA TROCA' ELSE '' END                     AS atencao
FROM reunioes r
JOIN reuniao_participantes rp ON rp.id_reuniao = r.id_reuniao
JOIN participantes p          ON p.id = rp.participante_id
WHERE r.status_ata = 'AGUARDANDO_ASSINATURA'
ORDER BY r.data DESC, p.nome_completo;
