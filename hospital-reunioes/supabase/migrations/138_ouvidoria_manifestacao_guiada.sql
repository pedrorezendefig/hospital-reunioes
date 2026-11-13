-- =====================================================
-- Migration 138: a Manifestacao guiada em cinco passos
-- (issue #1620, PRD #1527, ADR 0086 decisoes 3, 6 e 9)
-- =====================================================
-- O formulario publico vira um passo a passo que pergunta quando, onde e quem
-- estava envolvido, para a Ouvidoria receber o caso com o que precisa para
-- apurar. Nove colunas novas em `ouvidoria_protocolos`:
--
--   1. `data_ocorrencia`, `periodo` e `hora_aprox`: quando foi. Data e periodo
--      sao obrigatorios no passo a passo; a hora e opcional;
--   2. `local_informado`: o lugar que o manifestante escolheu na lista de
--      nomes publicos dos cartazes. NAO e a area responsavel, que continua
--      sendo do ouvidor. No caso anonimo vindo de um cartaz e o que fica: o
--      codigo e o ponto do cartaz nao sao gravados (ADR 0086, decisao 3);
--   3. `quarto`: so quando o lugar e ala de internacao;
--   4. `profissionais`: nome ou funcao de quem atendeu, se a pessoa souber;
--   5. `paciente_nascimento`: ao lado do `paciente_nome` da migration 110;
--   6. `expectativa`: o que a pessoa espera (resposta, providencia ou so
--      registrar);
--   7. `manifestante_telefone`: o telefone ganha coluna propria. O e-mail
--      continua em `manifestante_contato`, que e o que o acuse le.
--
-- Todas nulaveis: o caso de antes, o registro manual e a pagina velha nao as
-- preenchem. Quem exige o obrigatorio e a rota do canal aberto.
--
-- RETENCAO (ADR 0086, decisao 9): as nove saem junto com o relato, pelo cron
-- dos cinco anos e pela porta antecipada da diretoria executiva
-- (`CAMPOS_DO_DOSSIE` em app/services/ouvidoria_retencao.py).
--
-- Sem tabela nova e sem policy: a linha do caso segue com a RLS que nega por
-- padrao, e o backend escreve com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS data_ocorrencia DATE,
  ADD COLUMN IF NOT EXISTS periodo TEXT,
  ADD COLUMN IF NOT EXISTS hora_aprox TIME,
  ADD COLUMN IF NOT EXISTS local_informado TEXT,
  ADD COLUMN IF NOT EXISTS quarto TEXT,
  ADD COLUMN IF NOT EXISTS profissionais TEXT,
  ADD COLUMN IF NOT EXISTS paciente_nascimento DATE,
  ADD COLUMN IF NOT EXISTS expectativa TEXT,
  ADD COLUMN IF NOT EXISTS manifestante_telefone TEXT;

-- As duas listas fechadas. Vivem aqui e em app/routers/ouvidoria_publica.py,
-- e um teste confere que batem.
ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_periodo;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_periodo
  CHECK (periodo IS NULL OR periodo IN ('manha', 'tarde', 'noite', 'madrugada'));

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_expectativa;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_expectativa
  CHECK (expectativa IS NULL OR expectativa IN ('resposta', 'providencia', 'registro'));

-- O anti-vazio da casa nos textos, com os tetos da API.
ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_local_informado;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_local_informado
  CHECK (local_informado IS NULL OR length(btrim(local_informado)) BETWEEN 1 AND 80);

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_quarto;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_quarto
  CHECK (quarto IS NULL OR length(btrim(quarto)) BETWEEN 1 AND 40);

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_profissionais;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_profissionais
  CHECK (profissionais IS NULL OR length(btrim(profissionais)) BETWEEN 1 AND 300);

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_manifestante_telefone;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_manifestante_telefone
  CHECK (manifestante_telefone IS NULL OR length(btrim(manifestante_telefone)) BETWEEN 1 AND 30);

COMMENT ON COLUMN ouvidoria_protocolos.data_ocorrencia IS
  'Dia em que aconteceu, dito pelo manifestante na Manifestacao guiada (ADR 0086). Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.periodo IS
  'Periodo do dia em que aconteceu: manha, tarde, noite ou madrugada. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.hora_aprox IS
  'Hora aproximada, opcional. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.local_informado IS
  'O lugar que o manifestante escolheu (nome publico de um cartaz ou "Outro lugar do hospital"). Nao e a area responsavel, que e do ouvidor. No anonimo vindo de cartaz, e o que fica no lugar do codigo e do ponto (ADR 0086, decisao 3). Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.quarto IS
  'Quarto ou leito, so quando o lugar e ala de internacao. Opcional. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.profissionais IS
  'Nome ou funcao dos profissionais citados, se o manifestante souber. Opcional. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.paciente_nascimento IS
  'Data de nascimento do paciente atendido, para a area achar o atendimento. Opcional. Dado pessoal: sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.expectativa IS
  'O que o manifestante espera da Ouvidoria: resposta, providencia ou registro. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.manifestante_telefone IS
  'Telefone de quem se identificou. O e-mail fica em manifestante_contato, que e o que o acuse e o aviso de encerramento leem. Sai com o Dossie na Retencao.';


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (138) ON CONFLICT (numero) DO NOTHING;
