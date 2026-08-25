-- SOMENTE LEITURA. Reunioes com assinatura em aberto e quem precisa assinar.
-- Se vier VAZIO: pode trocar os e-mails hoje, sem risco nenhum.

SELECT
  r.id_reuniao,
  r.data,
  r.titulo,
  r.status_ata,
  coalesce(r.envelope_id_clicksign, r.envelope_key_clicksign) AS envelope,
  p.nome_completo                                             AS signatario,
  p.email                                                     AS email_no_envelope,
  CASE WHEN lower(p.email) IN (
      'adm_custos@hospitalsaomatheus.com.br',
      'administracao@hospitalsaomatheus.com.br',
      'almoxarifado@hospitalsaomatheus.com.br',
      'oxofgp@gmail.com',
      'callcenter_adm@hospitalsaomatheus.com.br',
      'compras.coord@hospitalsaomatheus.com.br',
      'coordenacao.dp@hospitalsaomatheus.com.br',
      'coordenacao.repasse@hospitalsaomatheus.com.br',
      'revglosas@hospitalsaomatheus.com.br',
      'faturamento.adm@hospitalsaomatheus.com.br',
      'ger_fin@hospitalsaomatheus.com.br',
      'ronildonem3080@gmail.com',
      'hotelaria@hospitalsaomatheus.com.br',
      'recep_coordenacao@hospitalsaomatheus.com.br'
  ) THEN 'AFETADO PELA TROCA' ELSE '' END                     AS atencao
FROM reunioes r
JOIN reuniao_participantes rp ON rp.id_reuniao = r.id_reuniao
JOIN participantes p          ON p.id = rp.participante_id
WHERE r.status_ata = 'AGUARDANDO_ASSINATURA'
ORDER BY r.data DESC, p.nome_completo;
