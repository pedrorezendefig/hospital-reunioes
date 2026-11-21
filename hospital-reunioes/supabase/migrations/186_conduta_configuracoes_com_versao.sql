-- =====================================================
-- Migration 186: Canal de Conduta, as configurações e os textos com versão
-- (issue #1826, PRD #1786, especificação seção 15)
-- =====================================================
-- Cada alteração de um item vira uma linha nova, com autor e data, e a
-- anterior fica. A vigente é a de maior versão. As telas públicas gravam o
-- `id` da versão que mostraram.
--
-- Os itens são os da especificação, menos o "E-mail do DP" (decisão 4 do
-- diretor): o encaminhamento ao DP não sai por e-mail, a página só mostra o
-- contato. A lista do CHECK é a mesma de `app/services/conduta/configuracoes.py`.
--
-- Nenhum perfil apaga nem troca uma versão: o banco recusa UPDATE, DELETE e
-- TRUNCATE, inclusive para a `service_role`.
--
-- RLS default-deny: só o backend, com a service_role, lê e grava. Nenhuma
-- policy de propósito. Nenhum texto entra por aqui: quem escreve é a
-- coordenação, pela tela. Rodar duas vezes é inofensivo. Aplicar à mão no
-- Studio, depois da 175.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS conduta_configuracoes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chave       TEXT NOT NULL CHECK (chave IN (
                'contato_dp',
                'orientacao_nsp',
                'aviso_p1_anonimato',
                'aviso_p1_protocolo',
                'aviso_p1_boa_fe',
                'protecao_abertura',
                'protecao_quem_relata',
                'protecao_quem_e_citado',
                'protecao_quem_le',
                'protecao_direcao',
                'protecao_prazos',
                'protecao_nao_garante',
                'consentimento_gravacao',
                'local_guarda_envelopes'
              )),
  versao      INTEGER NOT NULL CHECK (versao > 0),
  texto       TEXT NOT NULL CHECK (btrim(texto) <> ''),
  autor_id    VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT conduta_configuracoes_chave_versao_key UNIQUE (chave, versao)
);

COMMENT ON TABLE conduta_configuracoes IS
  'Configurações e textos do Canal de Conduta, uma linha por versão (especificação seção 15). Vigente = maior versão da chave. Imutável. Issue #1826.';

ALTER TABLE conduta_configuracoes ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION conduta_configuracao_imutavel() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'As versões das configurações do Canal são imutáveis: % não é permitido', TG_OP
    USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conduta_configuracao_imutavel ON conduta_configuracoes;
CREATE TRIGGER trg_conduta_configuracao_imutavel
  BEFORE UPDATE OR DELETE ON conduta_configuracoes
  FOR EACH ROW EXECUTE FUNCTION conduta_configuracao_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_configuracao_sem_truncate ON conduta_configuracoes;
CREATE TRIGGER trg_conduta_configuracao_sem_truncate
  BEFORE TRUNCATE ON conduta_configuracoes
  FOR EACH STATEMENT EXECUTE FUNCTION conduta_configuracao_imutavel();

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (186) ON CONFLICT (numero) DO NOTHING;
