-- =====================================================
-- Migration 194: Canal de Conduta, o Código de Conduta com versões
-- (issue #1841, PRD #1786, decisão 37 do diretor)
-- =====================================================
-- A coordenação do Comitê publica o Código de Conduta em PDF, e cada
-- publicação vira uma linha nova, com data de vigência e autor. A versão que
-- valia numa data é a de maior `vigente_desde` até aquele dia; na mesma
-- vigência, a de maior número. O caso usa isso para citar o item do Código
-- que valia na data do fato.
--
-- Nenhum perfil apaga nem troca uma versão: o banco recusa UPDATE, DELETE e
-- TRUNCATE, inclusive para a `service_role`.
--
-- O PDF fica no bucket privado `conduta-codigo`, sem policy para
-- `authenticated`: sai só pelo backend, na rota pública (a vigente) ou na da
-- coordenação (qualquer versão).
--
-- RLS default-deny: só o backend, com a service_role, lê e grava. Nenhuma
-- policy de propósito. Nenhuma versão entra por aqui: quem publica é a
-- coordenação, pela tela. Rodar duas vezes é inofensivo. Aplicar à mão no
-- Studio, depois da 175.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS conduta_codigo_versoes (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  versao         INTEGER NOT NULL CHECK (versao > 0),
  vigente_desde  DATE NOT NULL,
  storage_path   TEXT NOT NULL CHECK (btrim(storage_path) <> ''),
  nome_arquivo   TEXT NOT NULL CHECK (char_length(nome_arquivo) BETWEEN 1 AND 255),
  tamanho_bytes  INTEGER NOT NULL CHECK (tamanho_bytes > 0),
  autor_id       VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT conduta_codigo_versoes_versao_key UNIQUE (versao)
);

COMMENT ON TABLE conduta_codigo_versoes IS
  'Código de Conduta do Canal, uma linha por versão publicada (decisão 37). Vale numa data a de maior vigente_desde até ela. Imutável. Issue #1841.';

ALTER TABLE conduta_codigo_versoes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION conduta_codigo_imutavel() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'As versões do Código de Conduta são imutáveis: % não é permitido', TG_OP
    USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conduta_codigo_imutavel ON conduta_codigo_versoes;
CREATE TRIGGER trg_conduta_codigo_imutavel
  BEFORE UPDATE OR DELETE ON conduta_codigo_versoes
  FOR EACH ROW EXECUTE FUNCTION conduta_codigo_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_codigo_sem_truncate ON conduta_codigo_versoes;
CREATE TRIGGER trg_conduta_codigo_sem_truncate
  BEFORE TRUNCATE ON conduta_codigo_versoes
  FOR EACH STATEMENT EXECUTE FUNCTION conduta_codigo_imutavel();

-- O bucket privado, só PDF, até 20 MB (o mesmo teto da rota).
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('conduta-codigo', 'conduta-codigo', false, 20971520, ARRAY['application/pdf'])
ON CONFLICT (id) DO NOTHING;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (194) ON CONFLICT (numero) DO NOTHING;
