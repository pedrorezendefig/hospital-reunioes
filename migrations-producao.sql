-- ============================================================
-- Migration: 001_create_participantes.sql
-- ============================================================
-- =====================================================
-- Migration 001: Tabela participantes
-- Cadastro de todas as pessoas que participam de reuniões
-- =====================================================

-- Função para gerar IDs sequenciais: P001, P002...
CREATE OR REPLACE FUNCTION generate_participant_id()
RETURNS VARCHAR AS $$
DECLARE next_id INTEGER;
BEGIN
  SELECT COALESCE(MAX(CAST(SUBSTRING(id FROM 2) AS INTEGER)), 0) + 1
  INTO next_id FROM participantes;
  RETURN 'P' || LPAD(next_id::TEXT, 3, '0');
END;
$$ LANGUAGE plpgsql;

-- Enum de roles (hierarquia completa: diretor > gerente > coordenador > analista)
CREATE TYPE user_role AS ENUM ('diretor', 'gerente', 'coordenador', 'analista');

-- Tabela principal
CREATE TABLE participantes (
  id VARCHAR(10) PRIMARY KEY DEFAULT generate_participant_id(),
  nome_completo TEXT NOT NULL,
  cargo TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  area TEXT,
  setor TEXT,
  role user_role NOT NULL DEFAULT 'coordenador',
  ativo BOOLEAN DEFAULT TRUE,
  auth_user_id UUID REFERENCES auth.users(id),
  data_cadastro DATE DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices para buscas frequentes
CREATE INDEX idx_participantes_email ON participantes(email);
CREATE INDEX idx_participantes_setor ON participantes(setor);
CREATE INDEX idx_participantes_ativo ON participantes(ativo);
CREATE INDEX idx_participantes_auth ON participantes(auth_user_id);

-- ============================================================
-- Migration: 002_create_reunioes.sql
-- ============================================================
-- =====================================================
-- Migration 002: Tabelas reunioes e reuniao_participantes
-- Registro mestre de reuniões e junção N:M com participantes
-- =====================================================

CREATE TABLE reunioes (
  id_reuniao VARCHAR(20) PRIMARY KEY,
  data DATE NOT NULL,
  hora_inicio TIME,
  hora_fim TIME,
  tipo TEXT CHECK (tipo IN (
    'Diretoria', 'Gerencial', 'Coordenação', 'Mensal', 'Extraordinária'
  )),
  facilitador_id VARCHAR(10) REFERENCES participantes(id),
  setor TEXT,
  objetivo TEXT,
  status_ata TEXT DEFAULT 'PROCESSANDO' CHECK (status_ata IN (
    'PROCESSANDO', 'ERRO', 'AGUARDANDO_VALIDACAO',
    'AGUARDANDO_ASSINATURA', 'ASSINADA'
  )),
  total_acoes INTEGER DEFAULT 0,
  acoes_concluidas INTEGER DEFAULT 0,
  data_assinatura DATE,
  url_audio TEXT,
  url_transcricao TEXT,
  url_pdf_preliminar TEXT,
  url_pdf_assinado TEXT,
  envelope_key_clicksign TEXT,
  json_ata JSONB,
  fireflies_meeting_id TEXT,
  fonte TEXT DEFAULT 'MOCK' CHECK (fonte IN ('FIREFLIES', 'MOCK')),
  ciclo_correcao INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reuniao_participantes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  participante_id VARCHAR(10) REFERENCES participantes(id),
  sequence_assinatura INTEGER DEFAULT 2,
  UNIQUE(id_reuniao, participante_id)
);

-- Índices
CREATE INDEX idx_reunioes_status ON reunioes(status_ata);
CREATE INDEX idx_reunioes_data ON reunioes(data DESC);
CREATE INDEX idx_reunioes_setor ON reunioes(setor);
CREATE INDEX idx_reunioes_fireflies ON reunioes(fireflies_meeting_id);
CREATE INDEX idx_reuniao_part_reuniao ON reuniao_participantes(id_reuniao);
CREATE INDEX idx_reuniao_part_participante ON reuniao_participantes(participante_id);

-- Trigger para updated_at automático
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_reunioes_updated_at
  BEFORE UPDATE ON reunioes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Migration: 003_create_pendencias.sql
-- ============================================================
-- =====================================================
-- Migration 003: Tabelas pendencias e agendamentos_email
-- Ações/compromissos extraídos das atas + fila de follow-up
-- =====================================================

CREATE TABLE pendencias (
  id_acao VARCHAR(10) PRIMARY KEY,
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  descricao_acao TEXT NOT NULL,
  responsavel_id VARCHAR(10) REFERENCES participantes(id),
  responsavel_nome TEXT,
  cargo TEXT,
  prazo DATE,
  meta_entregavel TEXT,
  status TEXT DEFAULT 'PENDENTE' CHECK (status IN (
    'PENDENTE', 'EM_PROGRESSO', 'CONCLUIDO', 'ATRASADO', 'CANCELADO'
  )),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE agendamentos_email (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_acao VARCHAR(10) REFERENCES pendencias(id_acao) ON DELETE CASCADE,
  tipo TEXT CHECK (tipo IN ('D1_INDIVIDUAL', 'D7_LEMBRETE', 'D3_ALERTA')),
  data_disparo DATE NOT NULL,
  enviado BOOLEAN DEFAULT FALSE,
  enviado_em TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX idx_pendencias_reuniao ON pendencias(id_reuniao);
CREATE INDEX idx_pendencias_responsavel ON pendencias(responsavel_id);
CREATE INDEX idx_pendencias_status ON pendencias(status);
CREATE INDEX idx_pendencias_prazo ON pendencias(prazo);
CREATE INDEX idx_agendamentos_disparo ON agendamentos_email(data_disparo, enviado);

-- Trigger updated_at
CREATE TRIGGER trigger_pendencias_updated_at
  BEFORE UPDATE ON pendencias
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Migration: 003b_add_cancelada_status.sql
-- ============================================================
-- =====================================================
-- Migration 003: Adiciona status CANCELADA às reuniões
-- Permite soft-delete de reuniões PROGRAMADAS
-- =====================================================

ALTER TABLE reunioes DROP CONSTRAINT IF EXISTS reunioes_status_ata_check;

ALTER TABLE reunioes ADD CONSTRAINT reunioes_status_ata_check
  CHECK (status_ata IN (
    'PROGRAMADA', 'PROCESSANDO', 'ERRO',
    'AGUARDANDO_VALIDACAO', 'AGUARDANDO_ASSINATURA',
    'ASSINADA', 'CANCELADA'
  ));

-- ============================================================
-- Migration: 004_create_tokens_validacao.sql
-- ============================================================
-- =====================================================
-- Migration 004: Tabela tokens_validacao
-- Tokens para botões Aprovar/Corrigir no email do facilitador
-- =====================================================

CREATE TABLE tokens_validacao (
  token UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reuniao VARCHAR(20) REFERENCES reunioes(id_reuniao) ON DELETE CASCADE,
  tipo TEXT CHECK (tipo IN ('APROVACAO', 'CORRECAO')),
  usado BOOLEAN DEFAULT FALSE,
  ciclo_correcao INTEGER DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tokens_reuniao ON tokens_validacao(id_reuniao);
CREATE INDEX idx_tokens_expires ON tokens_validacao(expires_at);

-- ============================================================
-- Migration: 005_enable_rls.sql
-- ============================================================
-- =====================================================
-- Migration 005: Row Level Security (RLS)
-- Controle de acesso hierárquico por role
-- =====================================================

-- Habilitar RLS em todas as tabelas
ALTER TABLE participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reunioes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reuniao_participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pendencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE tokens_validacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE agendamentos_email ENABLE ROW LEVEL SECURITY;

-- Função auxiliar: busca role do usuário logado
CREATE OR REPLACE FUNCTION get_user_role()
RETURNS user_role AS $$
  SELECT role FROM participantes
  WHERE auth_user_id = auth.uid()
  LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER;

-- Função auxiliar: busca setor do usuário logado
CREATE OR REPLACE FUNCTION get_user_setor()
RETURNS TEXT AS $$
  SELECT setor FROM participantes
  WHERE auth_user_id = auth.uid()
  LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER;

-- === PARTICIPANTES ===
-- Diretor: vê todos
CREATE POLICY "diretor_read_all_participantes" ON participantes
  FOR SELECT USING (get_user_role() = 'diretor');

-- Gerente: vê participantes do seu setor
CREATE POLICY "gerente_read_setor_participantes" ON participantes
  FOR SELECT USING (
    get_user_role() = 'gerente'
    AND setor = get_user_setor()
  );

-- Coordenador e Analista: veem seu próprio registro
CREATE POLICY "coordenador_analista_read_self" ON participantes
  FOR SELECT USING (
    get_user_role() IN ('coordenador', 'analista')
    AND auth_user_id = auth.uid()
  );

-- === REUNIÕES ===
-- Diretor: vê todas
CREATE POLICY "diretor_read_all_reunioes" ON reunioes
  FOR SELECT USING (get_user_role() = 'diretor');

-- Gerente: vê reuniões do seu setor
CREATE POLICY "gerente_read_setor_reunioes" ON reunioes
  FOR SELECT USING (
    get_user_role() = 'gerente'
    AND setor = get_user_setor()
  );

-- Coordenador e Analista: veem reuniões em que participaram
CREATE POLICY "coordenador_analista_read_own_reunioes" ON reunioes
  FOR SELECT USING (
    get_user_role() IN ('coordenador', 'analista')
    AND id_reuniao IN (
      SELECT rp.id_reuniao FROM reuniao_participantes rp
      INNER JOIN participantes p ON p.id = rp.participante_id
      WHERE p.auth_user_id = auth.uid()
    )
  );

-- === PENDÊNCIAS ===
-- Diretor: vê todas
CREATE POLICY "diretor_read_all_pendencias" ON pendencias
  FOR SELECT USING (get_user_role() = 'diretor');

-- Gerente: vê pendências do seu setor
CREATE POLICY "gerente_read_setor_pendencias" ON pendencias
  FOR SELECT USING (
    get_user_role() = 'gerente'
    AND id_reuniao IN (
      SELECT id_reuniao FROM reunioes WHERE setor = get_user_setor()
    )
  );

-- Coordenador e Analista: veem suas próprias pendências
CREATE POLICY "coordenador_analista_read_own_pendencias" ON pendencias
  FOR SELECT USING (
    get_user_role() IN ('coordenador', 'analista')
    AND responsavel_id IN (
      SELECT id FROM participantes WHERE auth_user_id = auth.uid()
    )
  );

-- === SERVICE ROLE bypass ===
-- O FastAPI usa service_role_key que bypassa RLS automaticamente


-- ============================================================
-- Migration: 006_expand_roles_hierarchy.sql
-- ============================================================
-- =====================================================
-- Migration 006: Expansão da hierarquia de roles
-- Adiciona 'analista' ao enum user_role
-- =====================================================

-- Adicionar nível 'analista' para colaboradores e técnicos operacionais
-- Hierarquia: diretor > gerente > coordenador > analista
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'analista';

-- ============================================================
-- Migration: 007_onboarding_policy.sql
-- ============================================================
-- =====================================================
-- Migration 007: Políticas de Onboarding via Google OAuth
-- Permite que um usuário autenticado (sem registro em participantes)
-- crie seu próprio registro durante o fluxo de primeiro acesso.
-- =====================================================

-- Policy: usuário autenticado pode inserir seu próprio registro em participantes
-- (auth_user_id deve ser o próprio auth.uid())
CREATE POLICY "self_onboarding_insert" ON participantes
  FOR INSERT WITH CHECK (auth_user_id = auth.uid());

-- Policy: usuário autenticado pode ler/atualizar seu próprio registro
-- (necessário para middleware checar se onboarding já foi feito)
CREATE POLICY "self_read_own" ON participantes
  FOR SELECT USING (auth_user_id = auth.uid());

-- ============================================================
-- Migration: 008_create_signup_requests.sql
-- ============================================================
-- =====================================================
-- Migration 008: Tabela signup_requests
-- Armazena solicitações de cadastro pendentes de confirmação por email.
-- O registro em auth.users e participantes só é criado após confirmação.
-- =====================================================

CREATE TABLE signup_requests (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_completo TEXT NOT NULL,
  email        TEXT UNIQUE NOT NULL,
  senha_hash   TEXT NOT NULL,
  cargo        TEXT NOT NULL,
  area         TEXT,
  setor        TEXT,
  role         user_role NOT NULL DEFAULT 'analista',
  token        UUID NOT NULL DEFAULT gen_random_uuid(),
  confirmado   BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at   TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '24 hours'),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices para buscas frequentes
CREATE UNIQUE INDEX idx_signup_requests_token ON signup_requests(token);
CREATE INDEX idx_signup_requests_email ON signup_requests(email);
CREATE INDEX idx_signup_requests_expires ON signup_requests(expires_at);

-- ============================================================
-- Migration: 009_create_storage_buckets.sql
-- ============================================================
-- =====================================================
-- Migration 009: Criação de Buckets no Storage
-- Adiciona buckets necessários para o pipeline de reunião
-- =====================================================

-- 1. Inserir buckets se não existirem
INSERT INTO storage.buckets (id, name, public)
VALUES 
  ('audios', 'audios', true),
  ('transcricoes', 'transcricoes', true),
  ('pdfs', 'pdfs', true),
  ('pdfs-assinados', 'pdfs-assinados', true)
ON CONFLICT (id) DO NOTHING;

-- 2. Permitir acesso público de leitura para todos os buckets
-- (Necessário para o frontend poder exibir links e carregar documentos)
CREATE POLICY "Public Access" ON storage.objects
  FOR SELECT USING (bucket_id IN ('audios', 'transcricoes', 'pdfs', 'pdfs-assinados'));

-- 3. Permitir que o service_role gerencie todos os arquivos
-- (O backend usa service_role_key para bypassar RLS, mas é boa prática ter políticas)
CREATE POLICY "Service Role Management" ON storage.objects
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 4. Opcional: Permitir que usuários autenticados façam upload para seus próprios caminhos
-- (Ainda não implementado, mas deixa o terreno pronto)
-- CREATE POLICY "Authenticated Users Upload" ON storage.objects
--   FOR INSERT TO authenticated WITH CHECK (bucket_id IN ('audios', 'transcricoes', 'pdfs', 'pdfs-assinados'));

-- ============================================================
-- Migration: 010_create_comentarios_pendencias.sql
-- ============================================================
-- =====================================================
-- Migration 010: Tabela comentarios_pendencias
-- Comentários em pendências com suporte a menções
-- =====================================================

CREATE TABLE comentarios_pendencias (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_acao VARCHAR(10) NOT NULL REFERENCES pendencias(id_acao) ON DELETE CASCADE,
  autor_id VARCHAR(10) NOT NULL REFERENCES participantes(id),
  autor_nome TEXT NOT NULL,
  conteudo TEXT NOT NULL,
  mencoes VARCHAR(10)[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX idx_comentarios_id_acao ON comentarios_pendencias(id_acao);
CREATE INDEX idx_comentarios_autor ON comentarios_pendencias(autor_id);
CREATE INDEX idx_comentarios_created ON comentarios_pendencias(created_at DESC);

-- Trigger updated_at
CREATE TRIGGER trigger_comentarios_updated_at
  BEFORE UPDATE ON comentarios_pendencias
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Migration: 011_create_notificacoes.sql
-- ============================================================
-- =====================================================
-- Migration 011: Tabela notificacoes
-- Sistema de notificações para menções, status e alertas
-- =====================================================

CREATE TABLE notificacoes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  destinatario_id VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN (
    'MENCAO', 'STATUS_ALTERADO', 'COMENTARIO', 'PRAZO_PROXIMO'
  )),
  titulo TEXT NOT NULL,
  mensagem TEXT,
  referencia_id VARCHAR(10),
  lida BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Índices
CREATE INDEX idx_notificacoes_destinatario ON notificacoes(destinatario_id, lida);
CREATE INDEX idx_notificacoes_created ON notificacoes(created_at DESC);
CREATE INDEX idx_notificacoes_referencia ON notificacoes(referencia_id);

-- ============================================================
-- Migration: 012_add_status_programada.sql
-- ============================================================
-- =====================================================
-- Migration 012: Status PROGRAMADA e campo local
-- Permite agendar reuniões presenciais no calendário
-- antes de haver transcrição/ata
-- =====================================================

-- 1. Adicionar coluna local (sala da reunião)
ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS local TEXT;

-- 2. Recriar o CHECK constraint de status_ata incluindo PROGRAMADA
--    O nome do constraint gerado pelo Postgres é: reunioes_status_ata_check
ALTER TABLE reunioes
  DROP CONSTRAINT IF EXISTS reunioes_status_ata_check;

ALTER TABLE reunioes
  ADD CONSTRAINT reunioes_status_ata_check
  CHECK (status_ata IN (
    'PROGRAMADA',
    'PROCESSANDO',
    'ERRO',
    'AGUARDANDO_VALIDACAO',
    'AGUARDANDO_ASSINATURA',
    'ASSINADA'
  ));

-- 3. Índice para consultas de calendário (reuniões futuras programadas)
CREATE INDEX IF NOT EXISTS idx_reunioes_programada
  ON reunioes(data, status_ata)
  WHERE status_ata = 'PROGRAMADA';

-- ============================================================
-- Migration: 012b_add_status_repactuada.sql
-- ============================================================
-- Migration para adicionar o status REPACTUADA no check constraint da tabela pendencias
ALTER TABLE pendencias DROP CONSTRAINT pendencias_status_check;
ALTER TABLE pendencias ADD CONSTRAINT pendencias_status_check CHECK (status IN (
    'PENDENTE', 'EM_PROGRESSO', 'CONCLUIDO', 'ATRASADO', 'CANCELADO', 'REPACTUADA'
));

-- ============================================================
-- Migration: 013_add_titulo_column.sql
-- ============================================================
-- =====================================================
-- Migration 013: Adiciona coluna titulo à tabela reunioes
-- e corrige constraint para incluir CANCELADA
-- =====================================================

-- 1. Adicionar coluna titulo (nullable para compatibilidade retroativa)
ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS titulo TEXT;

-- 2. Recriar constraint incluindo CANCELADA
--    (foi removida inadvertidamente na migration 012)
ALTER TABLE reunioes DROP CONSTRAINT IF EXISTS reunioes_status_ata_check;

ALTER TABLE reunioes ADD CONSTRAINT reunioes_status_ata_check
  CHECK (status_ata IN (
    'PROGRAMADA',
    'PROCESSANDO',
    'ERRO',
    'AGUARDANDO_VALIDACAO',
    'AGUARDANDO_ASSINATURA',
    'ASSINADA',
    'CANCELADA'
  ));

-- ============================================================
-- Migration: 014_private_storage_buckets.sql
-- ============================================================
-- =====================================================
-- Migration 014: Tornar buckets de storage privados
-- CRÍTICO: PDFs de atas médicas não devem ser públicos (LGPD)
-- =====================================================

-- 1. Tornar todos os buckets privados
UPDATE storage.buckets SET public = false
WHERE id IN ('pdfs', 'pdfs-assinados', 'audios', 'transcricoes');

-- 2. Remover policy de acesso público
DROP POLICY IF EXISTS "Public Access" ON storage.objects;

-- 3. Acesso apenas para usuários autenticados
DROP POLICY IF EXISTS "Authenticated Access" ON storage.objects;
CREATE POLICY "Authenticated Access" ON storage.objects
  FOR SELECT USING (
    auth.role() = 'authenticated'
    AND bucket_id IN ('audios', 'transcricoes', 'pdfs', 'pdfs-assinados')
  );

-- ============================================================
-- Migration: 015_signup_requests_rls.sql
-- ============================================================
-- =====================================================
-- Migration 015: Habilitar RLS em signup_requests
-- CRÍTICO: Sem RLS, qualquer client autenticado pode ler senha_hash e tokens
-- Backend acessa via service_role (bypassa RLS), sem necessidade de policies
-- =====================================================

ALTER TABLE signup_requests ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Migration: 016_fix_participantes_role_default.sql
-- ============================================================
-- Alinha o default de role em participantes com signup_requests (ambos usam 'analista')
-- 'analista' é o menor privilégio e o default mais seguro para novos usuários
ALTER TABLE participantes ALTER COLUMN role SET DEFAULT 'analista';

-- ============================================================
-- Migration: 017_atomic_acoes_concluidas.sql
-- ============================================================
-- =====================================================
-- Migration 017: RPCs atômicas para acoes_concluidas
-- Substitui o padrão read-then-write em pendencias.py
-- evitando race condition em atualizações concorrentes
-- =====================================================

CREATE OR REPLACE FUNCTION incrementar_acoes_concluidas(p_id_reuniao TEXT)
RETURNS void AS $$
  UPDATE reunioes
  SET acoes_concluidas = COALESCE(acoes_concluidas, 0) + 1
  WHERE id_reuniao = p_id_reuniao;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION decrementar_acoes_concluidas(p_id_reuniao TEXT)
RETURNS void AS $$
  UPDATE reunioes
  SET acoes_concluidas = GREATEST(COALESCE(acoes_concluidas, 0) - 1, 0)
  WHERE id_reuniao = p_id_reuniao;
$$ LANGUAGE sql;

-- ============================================================
-- Migration: 018_participantes_id_sequence.sql
-- ============================================================
-- =====================================================
-- Migration 018: SEQUENCE para PK de participantes
-- Substitui SELECT MAX + 1 (race condition) por uma
-- sequência atômica do Postgres
-- =====================================================

-- Criar sequência começando após o maior ID existente
CREATE SEQUENCE IF NOT EXISTS participantes_id_seq START WITH 1;

-- Sincronizar com os dados existentes
SELECT setval(
  'participantes_id_seq',
  COALESCE(
    (SELECT MAX(CAST(SUBSTRING(id FROM 2) AS INTEGER)) FROM participantes),
    0
  )
);

-- Substituir a função por uma versão usando SEQUENCE
CREATE OR REPLACE FUNCTION generate_participant_id()
RETURNS VARCHAR AS $$
BEGIN
  RETURN 'P' || LPAD(nextval('participantes_id_seq')::TEXT, 3, '0');
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Migration: 019_rls_comentarios_notificacoes.sql
-- ============================================================
-- =====================================================
-- Migration 019: RLS em comentarios_pendencias e notificacoes
-- Qualquer client autenticado podia ler/escrever todos os
-- registros diretamente. Agora cada usuário acessa apenas
-- os seus próprios dados.
-- =====================================================

-- === COMENTARIOS_PENDENCIAS ===
ALTER TABLE comentarios_pendencias ENABLE ROW LEVEL SECURITY;

-- Diretor vê todos os comentários
CREATE POLICY "diretor_all_comentarios" ON comentarios_pendencias
  FOR ALL USING (get_user_role() = 'diretor');

-- Demais usuários veem comentários das suas pendências
CREATE POLICY "participante_acessa_comentarios_proprios" ON comentarios_pendencias
  FOR ALL USING (
    autor_id IN (
      SELECT id FROM participantes WHERE auth_user_id = auth.uid()
    )
    OR id_acao IN (
      SELECT id_acao FROM pendencias
      WHERE responsavel_id IN (
        SELECT id FROM participantes WHERE auth_user_id = auth.uid()
      )
    )
  );

-- === NOTIFICACOES ===
ALTER TABLE notificacoes ENABLE ROW LEVEL SECURITY;

-- Diretor vê todas as notificações
CREATE POLICY "diretor_all_notificacoes" ON notificacoes
  FOR ALL USING (get_user_role() = 'diretor');

-- Cada usuário acessa apenas as notificações destinadas a ele
CREATE POLICY "notificacoes_do_proprio_usuario" ON notificacoes
  FOR ALL USING (
    destinatario_id IN (
      SELECT id FROM participantes WHERE auth_user_id = auth.uid()
    )
  );

-- ============================================================
-- Migration: 020_reuniao_participantes_policies.sql
-- ============================================================
-- =====================================================
-- Migration 020: Policies para reuniao_participantes
-- RLS estava habilitado (migration 005) mas sem nenhuma
-- policy, resultando em bloqueio total para clients.
-- =====================================================

-- Diretor vê todas as associações
CREATE POLICY "diretor_all_reuniao_participantes" ON reuniao_participantes
  FOR ALL USING (get_user_role() = 'diretor');

-- Gerente vê associações de reuniões do seu setor
CREATE POLICY "gerente_setor_reuniao_participantes" ON reuniao_participantes
  FOR SELECT USING (
    get_user_role() = 'gerente'
    AND id_reuniao IN (
      SELECT id_reuniao FROM reunioes WHERE setor = get_user_setor()
    )
  );

-- Coordenador e Analista veem apenas as reuniões em que participaram
CREATE POLICY "participante_acessa_proprias_reunioes" ON reuniao_participantes
  FOR SELECT USING (
    participante_id IN (
      SELECT id FROM participantes WHERE auth_user_id = auth.uid()
    )
  );

-- ============================================================
-- Migration: 20260401151824_add_recurrence_group_fields.sql
-- ============================================================
ALTER TABLE reunioes
ADD COLUMN IF NOT EXISTS id_grupo_recorrencia TEXT,
ADD COLUMN IF NOT EXISTS nome_grupo_recorrencia TEXT;

-- ============================================================
-- Migration: 021_remove_onboarding_policies.sql
-- ============================================================
-- Remove RLS policies created exclusively for Google OAuth onboarding flow
-- Google authentication has been removed from the application
DROP POLICY IF EXISTS "self_onboarding_insert" ON participantes;
DROP POLICY IF EXISTS "self_read_own" ON participantes;
