-- =====================================================================
-- DIAGNOSTICO DA ATUALIZACAO DE E-MAILS  (SOMENTE LEITURA)
-- Rodar no SQL Editor do Supabase Studio de PRODUCAO.
-- Nenhum comando altera dado. Pode rodar quantas vezes quiser.
--
-- Sao 2 blocos. Rode um de cada vez.
--   BLOCO A: foto do cadastro em JSON (1 celula). Copie e mande pro Claude.
--   BLOCO B: o mesmo em tabela, para conferir no olho.
-- =====================================================================


-- =====================================================================
-- BLOCO A  ->  copie a celula unica do resultado
-- =====================================================================
WITH depara(antigo, novo, nome_pdf) AS (
  VALUES
    ('adm_custos',            'vanessa.expedito',  'Vanessa Expedito'),
    ('administracao',         'nayani.lima',       'Nayani Lima'),
    ('almoxarifado',          'janaina.ferreira',  'Janaina Ferreira'),
    ('almoxarifado',          'oto.xavier',        'Oto Xavier'),
    ('callcenter_adm',        'giselle.nunes',     'Giselle Nunes'),
    ('compras.coord',         'marcia.bevenuto',   'Marcia Bevenuto'),
    ('coordenacao.arquivo',   'matheus.arrepia',   'Matheus Arrepia'),
    ('arquivo',               'matheus.arrepia',   'Matheus Arrepia (variante)'),
    ('coordenacao.dp',        'levi.santos',       'Levi Santos'),
    ('coordenacao.repasse',   'laryssa.oliveira',  'Laryssa Oliveira'),
    ('coordenacao.revglosas', 'flavia.rodrigues',  'Flavia Rodrigues'),
    ('coodenacao.revglosas',  'flavia.rodrigues',  'Flavia Rodrigues (variante)'),
    ('faturamento.adm',       'adriana.araujo',    'Adriana Araujo'),
    ('ger_fin',               'denize.antunes',    'Denize Antunes'),
    ('gestaocm',              'rosiane.gomes',     'Rosiane Gomes'),
    ('hotelaria',             'ronildo.souza',     'Ronildo Souza'),
    ('hotelaria',             'uliandra.dutra',    'Uliandra Dutra'),
    ('recep_coordenacao',     'cristiane.xavier',  'Cristiane Xavier')
),
pessoas AS (
  SELECT
    p.id, p.nome_completo, p.cargo, p.setor, p.area, p.email,
    p.role::text AS role, p.access_profile, p.ativo, p.is_externo,
    (p.auth_user_id IS NOT NULL)               AS tem_login,
    au.email                                   AS email_do_login,
    (p.email IS DISTINCT FROM au.email)        AS login_divergente,
    p.data_cadastro,
    (SELECT count(*) FROM reuniao_participantes rp WHERE rp.participante_id = p.id)                          AS reunioes,
    (SELECT count(*) FROM pendencias pe WHERE pe.responsavel_id = p.id AND pe.status <> 'CONCLUIDO')         AS pendencias_abertas
  FROM participantes p
  LEFT JOIN auth.users au ON au.id = p.auth_user_id
),
envelopes_abertos AS (
  SELECT r.id_reuniao, r.data, r.titulo, r.status_ata,
         coalesce(r.envelope_id_clicksign, r.envelope_key_clicksign) AS envelope,
         (SELECT jsonb_agg(pp.email ORDER BY pp.email)
            FROM reuniao_participantes rp
            JOIN participantes pp ON pp.id = rp.participante_id
           WHERE rp.id_reuniao = r.id_reuniao AND pp.email IS NOT NULL) AS signatarios
  FROM reunioes r
  WHERE r.status_ata = 'AGUARDANDO_ASSINATURA'
)
SELECT jsonb_pretty(jsonb_build_object(
  'gerado_em', now(),
  'totais', (SELECT jsonb_build_object(
      'pessoas',            count(*),
      'ativas',             count(*) FILTER (WHERE ativo),
      'sem_email',          count(*) FILTER (WHERE email IS NULL OR btrim(email) = ''),
      'externos',           count(*) FILTER (WHERE is_externo),
      'com_login',          count(*) FILTER (WHERE tem_login),
      'login_divergente',   count(*) FILTER (WHERE tem_login AND login_divergente),
      'envelopes_abertos',  (SELECT count(*) FROM envelopes_abertos)
    ) FROM pessoas),
  'cadastro', (SELECT jsonb_agg(to_jsonb(x) ORDER BY x.nome_completo) FROM pessoas x),
  'depara_16', (SELECT jsonb_agg(jsonb_build_object(
      'nome_pdf', d.nome_pdf,
      'antigo',   d.antigo || '@hospitalsaomatheus.com.br',
      'novo',     d.novo   || '@hospitalsaomatheus.com.br',
      'achou_pelo_antigo', (SELECT jsonb_agg(jsonb_build_object('id', a.id, 'nome', a.nome_completo, 'ativo', a.ativo))
                              FROM pessoas a WHERE lower(a.email) LIKE d.antigo || '@%'),
      'ja_esta_no_novo',   (SELECT jsonb_agg(jsonb_build_object('id', b.id, 'nome', b.nome_completo))
                              FROM pessoas b WHERE lower(b.email) LIKE d.novo || '@%'),
      'achou_pelo_nome',   (SELECT jsonb_agg(jsonb_build_object('id', c.id, 'nome', c.nome_completo, 'email', c.email))
                              FROM pessoas c WHERE lower(c.nome_completo) LIKE '%' || lower(split_part(d.nome_pdf, ' ', 1)) || '%')
    ) ORDER BY d.nome_pdf) FROM depara d),
  'envelopes_abertos', (SELECT jsonb_agg(to_jsonb(e)) FROM envelopes_abertos e),
  'emails_repetidos', (SELECT jsonb_agg(jsonb_build_object('email', lower(email), 'quantas', n))
                         FROM (SELECT lower(email) AS email, count(*) AS n FROM participantes
                                WHERE email IS NOT NULL GROUP BY 1 HAVING count(*) > 1) r),
  'dominio_sem_br', (SELECT jsonb_agg(email) FROM participantes
                      WHERE email LIKE '%@hospitalsaomatheus.com')
)) AS foto_do_cadastro;


-- =====================================================================
-- BLOCO B  ->  a mesma coisa em tabela, para ler no olho
-- =====================================================================
SELECT
  p.id,
  p.nome_completo,
  p.cargo,
  p.setor,
  p.email,
  p.role::text                                  AS papel,
  p.access_profile                              AS perfil,
  p.ativo,
  p.is_externo                                  AS externo,
  (p.auth_user_id IS NOT NULL)                  AS tem_login,
  au.email                                      AS email_do_login,
  CASE
    WHEN p.email IS NULL THEN 'SEM E-MAIL'
    WHEN p.email LIKE '%@hospitalsaomatheus.com' THEN 'DOMINIO SEM .BR'
    WHEN p.auth_user_id IS NOT NULL AND p.email IS DISTINCT FROM au.email THEN 'LOGIN DIVERGENTE'
    WHEN p.email NOT LIKE '%@hospitalsaomatheus.com.br' THEN 'E-MAIL EXTERNO'
    ELSE 'ok'
  END                                           AS alerta
FROM participantes p
LEFT JOIN auth.users au ON au.id = p.auth_user_id
ORDER BY (CASE WHEN p.email IS NULL THEN 0 ELSE 1 END), p.nome_completo;
