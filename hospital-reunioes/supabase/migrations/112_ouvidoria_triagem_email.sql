-- =====================================================
-- Migration 112: Triagem de e-mail da Ouvidoria (issue #648, PRD #646, ADR 0051)
-- =====================================================
-- O e-mail que chega em ouvidoria@ e copiado para o subdominio de recebimento
-- do Resend, e o Resend chama o webhook do app. Aqui ele vira um E-MAIL
-- RECEBIDO: um item da Triagem de e-mail, que so o Perfil da Ouvidoria ve e
-- que NAO e manifestacao. Nenhum e-mail vira caso sem ato do ouvidor (ADR 0051,
-- decisao 1).
--
-- Esta e a UNICA migration do PRD #646. As fatias seguintes (descartar, virar
-- manifestacao, juntar a um caso, novidade do menu) usam as colunas daqui e nao
-- abrem migration nova: a migration e aplicada a mao no Studio, e uma por
-- fatia multiplicaria o passo humano. Por isso nascem aqui colunas que esta
-- fatia ainda nao escreve (quem decidiu, quando, o caso ligado).
--
-- Tres coisas entram, e so elas:
--   1. o e-mail recebido;
--   2. o anexo do e-mail recebido (metadados aqui, binario no bucket privado
--      anexos-ouvidoria, que ja existe desde a 066);
--   3. o log de acesso da Ouvidoria passa a aceitar o e-mail recebido como alvo.
--
-- Idempotente de verdade: rodar de novo nao falha, e num banco onde uma versao
-- anterior desta 112 ja rodou ela completa o que faltava. Por isso as colunas
-- que entraram depois da primeira versao (as do teto dos anexos) vem por
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS depois do CREATE, e toda constraint
-- nomeada sai (DROP CONSTRAINT IF EXISTS) antes de entrar: o CREATE TABLE IF
-- NOT EXISTS de uma tabela que ja existe nao acrescenta coluna nenhuma.
-- =====================================================

-- 1. O e-mail recebido.
CREATE TABLE IF NOT EXISTS ouvidoria_emails_recebidos (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- O identificador do e-mail no Resend, e a DEDUP: o Resend reentrega o
  -- evento que falhou, e a entrega concorrente do mesmo e-mail esbarra aqui.
  resend_email_id    TEXT NOT NULL UNIQUE CHECK (btrim(resend_email_id) <> ''),
  remetente_endereco TEXT NOT NULL,
  remetente_nome     TEXT,
  destinatarios      JSONB NOT NULL DEFAULT '[]'::jsonb,
  assunto            TEXT NOT NULL DEFAULT '',
  -- Quando o e-mail chegou ao Resend, e nao quando o app o processou: a
  -- reentrega de amanha nao muda a data de chegada.
  recebido_em        TIMESTAMPTZ NOT NULL,
  corpo_texto        TEXT,
  -- Guardado e NUNCA renderizado: a tela desenha so o texto (issue #648).
  corpo_html         TEXT,
  cabecalhos         JSONB NOT NULL DEFAULT '{}'::jsonb,
  estado             TEXT NOT NULL DEFAULT 'pendente'
                     CHECK (estado IN ('pendente', 'virou_manifestacao', 'juntado', 'descartado')),
  decidido_por       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  decidido_por_nome  TEXT,
  decidido_em        TIMESTAMPTZ,
  manifestacao_id    UUID REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  -- Corpo ou anexo que nao veio do Resend: o item fica visivel com o que veio,
  -- e a reentrega do evento completa.
  incompleto         BOOLEAN NOT NULL DEFAULT false,
  -- Remetente do dominio do hospital. Marca de leitura, nao permissao: o From
  -- de um e-mail se forja.
  interno            BOOLEAN NOT NULL DEFAULT false,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Pendente e o unico estado sem decisao; os outros tres tem quem e quando.
  CONSTRAINT ouvidoria_emails_recebidos_decisao_check
    CHECK ((estado = 'pendente') = (decidido_em IS NULL)),
  -- Virar manifestacao e juntar ligam o e-mail a um caso; pendente e
  -- descartado nao tem caso.
  CONSTRAINT ouvidoria_emails_recebidos_caso_check
    CHECK ((estado IN ('virou_manifestacao', 'juntado')) = (manifestacao_id IS NOT NULL))
);

-- A lista da triagem: pendentes primeiro, na ordem de chegada.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_emails_recebidos_triagem
  ON ouvidoria_emails_recebidos(estado, recebido_em, id);

COMMENT ON TABLE ouvidoria_emails_recebidos IS
  'Triagem de e-mail (ADR 0051): todo e-mail que chega em ouvidoria@, antes de virar caso. So o Perfil da Ouvidoria le, pelo backend.';
COMMENT ON COLUMN ouvidoria_emails_recebidos.resend_email_id IS
  'Identificador do e-mail no Resend. Unico: e a dedup do webhook.';
COMMENT ON COLUMN ouvidoria_emails_recebidos.corpo_html IS
  'O HTML do e-mail, guardado e nunca renderizado: a tela mostra so o corpo em texto.';
COMMENT ON COLUMN ouvidoria_emails_recebidos.estado IS
  'pendente, virou_manifestacao, juntado ou descartado. So pendente nasce no webhook; os outros sao decisao do ouvidor.';

-- Quantos anexos o e-mail anunciou alem do teto de quantidade do app. O
-- remetente e anonimo e o subdominio de recebimento tem MX proprio, sem o
-- filtro do Workspace: so os primeiros anexos, ate o teto, ganham linha, e o
-- excedente e so contado aqui. Sem isso, um e-mail com milhares de anexos
-- minusculos viraria milhares de linhas e de idas ao banco a cada entrega do
-- webhook (revisao de seguranca do PR #899). O original segue na caixa
-- ouvidoria@ do Workspace.
ALTER TABLE ouvidoria_emails_recebidos
  ADD COLUMN IF NOT EXISTS anexos_excedentes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ouvidoria_emails_recebidos
  DROP CONSTRAINT IF EXISTS ouvidoria_emails_recebidos_anexos_excedentes_check;
ALTER TABLE ouvidoria_emails_recebidos
  ADD CONSTRAINT ouvidoria_emails_recebidos_anexos_excedentes_check
  CHECK (anexos_excedentes >= 0);

COMMENT ON COLUMN ouvidoria_emails_recebidos.anexos_excedentes IS
  'Anexos anunciados alem do teto de quantidade por e-mail. Nao tem linha em ouvidoria_emails_recebidos_anexos: so a contagem, e o original fica na caixa ouvidoria@.';

-- 2. O anexo do e-mail recebido. Todo anexo que o e-mail anuncia, ate o teto de
--    quantidade, ganha linha, com o binario ou sem ele: storage_path NULL sem
--    motivo e o anexo que nao veio do Resend, e e ele que a reentrega vem
--    completar. O que passa do teto e so contado (anexos_excedentes, acima).
CREATE TABLE IF NOT EXISTS ouvidoria_emails_recebidos_anexos (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_recebido_id UUID NOT NULL REFERENCES ouvidoria_emails_recebidos(id) ON DELETE RESTRICT,
  resend_anexo_id   TEXT NOT NULL CHECK (btrim(resend_anexo_id) <> ''),
  filename          TEXT NOT NULL,
  content_type      TEXT NOT NULL,
  tamanho_bytes     BIGINT CHECK (tamanho_bytes >= 0),
  storage_path      TEXT CHECK (storage_path IS NULL OR btrim(storage_path) <> ''),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ouvidoria_emails_recebidos_anexos_unico UNIQUE (email_recebido_id, resend_anexo_id)
);

-- Por que o binario NAO foi guardado de proposito: tipo fora do catalogo ou
-- acima do teto de tamanho (por anexo ou pelo total do e-mail). O remetente e
-- anonimo, e o teto e do app. Linha com motivo nao conta como faltando e a
-- reentrega nao a baixa de novo; o original segue na caixa ouvidoria@ do
-- Workspace (revisao de seguranca do PR #899). Binario e motivo nunca juntos.
ALTER TABLE ouvidoria_emails_recebidos_anexos
  ADD COLUMN IF NOT EXISTS motivo_sem_binario TEXT;
ALTER TABLE ouvidoria_emails_recebidos_anexos
  DROP CONSTRAINT IF EXISTS ouvidoria_emails_recebidos_anexos_motivo_sem_binario_check;
ALTER TABLE ouvidoria_emails_recebidos_anexos
  ADD CONSTRAINT ouvidoria_emails_recebidos_anexos_motivo_sem_binario_check
  CHECK (motivo_sem_binario IS NULL OR btrim(motivo_sem_binario) <> '');
ALTER TABLE ouvidoria_emails_recebidos_anexos
  DROP CONSTRAINT IF EXISTS ouvidoria_emails_recebidos_anexos_binario_ou_motivo;
ALTER TABLE ouvidoria_emails_recebidos_anexos
  ADD CONSTRAINT ouvidoria_emails_recebidos_anexos_binario_ou_motivo
  CHECK (storage_path IS NULL OR motivo_sem_binario IS NULL);

COMMENT ON TABLE ouvidoria_emails_recebidos_anexos IS
  'Anexos do e-mail recebido (ADR 0051). Metadados aqui, binario no bucket privado anexos-ouvidoria, leitura por URL assinada.';
COMMENT ON COLUMN ouvidoria_emails_recebidos_anexos.storage_path IS
  'Caminho no bucket privado, nome sorteado. NULL sem motivo_sem_binario = o binario nao veio do Resend (item incompleto); NULL com motivo = recusado pelo teto ou pelo tipo.';
COMMENT ON COLUMN ouvidoria_emails_recebidos_anexos.motivo_sem_binario IS
  'Por que o binario foi recusado de proposito (tipo fora do catalogo ou acima do teto de tamanho), com o lugar do original. Nunca junto de storage_path.';

-- 3. RLS default-deny (padrao da casa: 009/041/051/063/064/066). O backend usa
--    service_role; a anon_key do bundle do frontend fica de fora. Nenhuma
--    policy: o corpo de um e-mail pode trazer nome, CPF e leito.
ALTER TABLE ouvidoria_emails_recebidos ENABLE ROW LEVEL SECURITY;
ALTER TABLE ouvidoria_emails_recebidos_anexos ENABLE ROW LEVEL SECURITY;

-- 4. O log de acesso da Ouvidoria (064) passa a aceitar o e-mail recebido como
--    alvo: todo acesso do Perfil da Ouvidoria gera log, e ler um e-mail que
--    ainda nao e caso tambem e acesso a dado pessoal. As fatias de descartar,
--    virar e juntar gravam aqui sem abrir migration nova.
--
--    manifestacao_id deixa de ser obrigatorio, e o CHECK garante que toda
--    linha continua tendo um alvo. Nenhuma linha existente muda: todas tem
--    manifestacao_id, e os gatilhos de imutabilidade da 064 seguem valendo.
ALTER TABLE ouvidoria_acessos
  ADD COLUMN IF NOT EXISTS email_recebido_id UUID REFERENCES ouvidoria_emails_recebidos(id) ON DELETE RESTRICT;

ALTER TABLE ouvidoria_acessos ALTER COLUMN manifestacao_id DROP NOT NULL;

ALTER TABLE ouvidoria_acessos DROP CONSTRAINT IF EXISTS ouvidoria_acessos_alvo_check;
ALTER TABLE ouvidoria_acessos
  ADD CONSTRAINT ouvidoria_acessos_alvo_check
  CHECK (manifestacao_id IS NOT NULL OR email_recebido_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_acessos_email_recebido
  ON ouvidoria_acessos(email_recebido_id, ocorrido_em DESC)
  WHERE email_recebido_id IS NOT NULL;

COMMENT ON COLUMN ouvidoria_acessos.email_recebido_id IS
  'O e-mail recebido da Triagem de e-mail que foi acessado (ADR 0051). Toda linha tem manifestacao_id, email_recebido_id ou os dois.';
