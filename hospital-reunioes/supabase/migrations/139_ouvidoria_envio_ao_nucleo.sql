-- =====================================================
-- Migration 139: o envio ao Nucleo de Seguranca do Paciente
-- (issue #1621, PRD #1527, ADR 0088 decisoes 3 a 8)
-- =====================================================
-- O ouvidor manda ao Nucleo de Seguranca do Paciente (NSP) o caso que fala de
-- incidente relacionado a assistencia, e o Nucleo confirma o recebimento por
-- um link sem senha. Quatro mudancas:
--
--   1. A configuracao da Ouvidoria ganha o setor do Nucleo (`nsp_setor`). O
--      Nucleo e um setor da taxonomia como os outros, com titular, substituto
--      e gestor no cadastro de responsaveis (ADR 0088, decisao 3); aqui fica
--      so QUAL setor ele e. Nasce vazio: o ouvidor escolhe na tela de
--      Responsaveis por setor, e ate la o envio ao Nucleo e recusado com a
--      frase que manda configurar.
--
--   2. O caso ganha o apontamento do agente de triagem e a decisao do
--      ouvidor (secao 4.4 do anexo da Demanda): `nsp_sugerido`, as duas
--      justificativas (a simples, para o ouvidor, e a tecnica, para o
--      Nucleo), a decisao (`confirmado` ou `descartado`), o motivo do
--      descarte, quem decidiu e quando. O agente preenche o apontamento numa
--      fatia seguinte; esta so cria os campos e a trava da validacao.
--      Descartar exige motivo, e o CHECK segura isso no banco tambem.
--
--   3. A ciencia do Nucleo mora no registro de acionamento da migration 136,
--      com `motivo_ciencia = 'nsp'`. Um caso tem no maximo uma (indice unico
--      parcial): o segundo clique em Enviar ao NSP volta 23505 e a rota
--      responde 409. Os dois carimbos da cobranca (gestor e Diretoria) moram
--      na linha da ciencia, gravados por update condicional, como os degraus
--      da escada da area.
--
--   4. Tres gatilhos novos no CHECK das notificacoes: o email ao Nucleo
--      (`ciencia_nsp`) e os dois degraus da cobranca (`cobranca_nsp_gestor`,
--      `cobranca_nsp_diretoria`). Sem eles o INSERT volta 23514 e o Nucleo
--      nunca e avisado, em silencio.
--
-- RETENCAO: as duas justificativas e o motivo do descarte descrevem o caso e
-- saem junto com o relato (`CAMPOS_DO_DOSSIE` em
-- app/services/ouvidoria_retencao.py).
--
-- Sem tabela nova e sem policy: as tres tabelas ja tem RLS que nega por
-- padrao, e o backend escreve com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

-- 1. O setor do Nucleo na configuracao da Ouvidoria.
ALTER TABLE ouvidoria_config
  ADD COLUMN IF NOT EXISTS nsp_setor TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN ouvidoria_config.nsp_setor IS
  'Qual setor da taxonomia e o Nucleo de Seguranca do Paciente (ADR 0088, decisao 3). Vazio enquanto ninguem escolheu: o envio ao Nucleo e recusado.';

-- 2. O apontamento do agente e a decisao do ouvidor.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS nsp_sugerido BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS nsp_justificativa_simples TEXT,
  ADD COLUMN IF NOT EXISTS nsp_justificativa_tecnica TEXT,
  ADD COLUMN IF NOT EXISTS nsp_decisao TEXT,
  ADD COLUMN IF NOT EXISTS nsp_decisao_motivo TEXT,
  ADD COLUMN IF NOT EXISTS nsp_decidido_por VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS nsp_decidido_em TIMESTAMPTZ;

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_nsp_decisao;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_nsp_decisao
  CHECK (nsp_decisao IS NULL OR nsp_decisao IN ('confirmado', 'descartado'));

-- Descartar o apontamento exige o motivo de uma linha (ADR 0088, decisao 4).
ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_nsp_descarte_com_motivo;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_nsp_descarte_com_motivo
  CHECK (nsp_decisao IS DISTINCT FROM 'descartado' OR length(btrim(coalesce(nsp_decisao_motivo, ''))) > 0);

COMMENT ON COLUMN ouvidoria_protocolos.nsp_sugerido IS
  'O agente de triagem apontou o caso ao Nucleo de Seguranca do Paciente (ADR 0087). Com ele, a validacao so conclui depois da decisao do ouvidor.';
COMMENT ON COLUMN ouvidoria_protocolos.nsp_justificativa_simples IS
  'Por que o agente entende que e caso do Nucleo, para o ouvidor ler no alerta. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.nsp_justificativa_tecnica IS
  'Tipo provavel de incidente, setor, data e dano, para o Nucleo ler pelo link. Nunca vai no email. Sai com o relato na Retencao.';
COMMENT ON COLUMN ouvidoria_protocolos.nsp_decisao IS
  'confirmado (o caso foi ao Nucleo e tem o selo Em analise pelo NSP) ou descartado (com motivo). Nulo enquanto ninguem decidiu.';
COMMENT ON COLUMN ouvidoria_protocolos.nsp_decisao_motivo IS
  'Por que o ouvidor descartou o apontamento, em uma linha. Sai com o relato na Retencao.';

-- 3. Uma ciencia do Nucleo por caso, e os carimbos da cobranca.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_acionamentos_um_nucleo_por_caso
  ON ouvidoria_acionamentos(manifestacao_id)
  WHERE motivo_ciencia = 'nsp';

ALTER TABLE ouvidoria_acionamentos
  ADD COLUMN IF NOT EXISTS escalonado_gestor_em TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS escalonado_diretoria_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_acionamentos.escalonado_gestor_em IS
  'Ciencia do Nucleo sem o Recebido: quando a cobranca subiu ao gestor do setor (24 horas uteis depois do prazo). Uma vez so.';
COMMENT ON COLUMN ouvidoria_acionamentos.escalonado_diretoria_em IS
  'Ciencia do Nucleo sem o Recebido: quando a cobranca subiu a Diretoria Executiva (48 horas uteis depois do prazo). Uma vez so.';

-- 4. Os gatilhos do Nucleo. CHECK nao tem IF NOT EXISTS: derruba e recria com
-- a lista INTEIRA, dentro de uma transacao, porque isto roda a mao em producao
-- e a tabela nao pode ficar sem constraint se a segunda metade falhar.
BEGIN;

ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_gatilho_check
  CHECK (gatilho IN (
    'nova_demanda',
    'alerta_sem_titular',
    'prazo_rompido',
    'vespera_vencimento',
    'escalonamento_gestor',
    'escalonamento_diretoria',
    'alerta_cadastro_setor',
    'critico_imediato',
    'prorrogacao_solicitada',
    'prorrogacao_decidida',
    'resposta_devolvida',
    'caso_reaberto',
    'acusar_recebimento',
    'encerramento_manifestante',
    'devolvido_a_ouvidoria',
    'redirecionamento_area',
    'ciencia_elogio',
    -- Desta migration: o email ao Nucleo e os dois degraus da cobranca.
    'ciencia_nsp',
    'cobranca_nsp_gestor',
    'cobranca_nsp_diretoria'
  ));

COMMIT;

INSERT INTO migracoes_aplicadas (numero) VALUES (139) ON CONFLICT (numero) DO NOTHING;
