-- =====================================================
-- Migration 190: Canal de Conduta, o depoimento da Apuração
-- (issue #1830, PRD #1786, ADR 0097, decisão 2; especificação, 7.1 e 7.2)
-- =====================================================
-- O que entra:
--   1. o cartão de cada pessoa ouvida: nome e cargo cifrados, o papel
--      (acusado, testemunha ou denunciante identificado), o registro sem
--      gravação (motivo e pontos da conversa, cifrados) e a conclusão. O
--      depoimento concluído não muda mais, e nenhum se apaga;
--   2. os arquivos do depoimento (transcrição, áudio e termo assinado): o
--      binário vai cifrado ao bucket do Canal, e aqui fica só o caminho, o
--      tipo, a versão e a página. Uma versão nova não apaga a anterior: o
--      banco recusa UPDATE, DELETE e TRUNCATE;
--   3. as quatro declarações da lista de conferência, com quem marcou e
--      quando. Também não se alteram nem se apagam;
--   4. a etapa Apuração só avança com todos os depoimentos concluídos;
--   5. o teto do bucket sobe para caber o áudio de 300 MB já cifrado.
--
-- RLS default-deny em toda tabela nova: só o backend, com a service_role, lê
-- e grava. Nenhuma policy de propósito. Nenhum dado de pessoa entra aqui.
-- Rodar duas vezes é inofensivo. Aplicar à mão no Studio.
-- =====================================================

BEGIN;

-- ---------- 1. O depoimento ----------
CREATE TABLE IF NOT EXISTS conduta_depoimentos (
  id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id                      UUID NOT NULL REFERENCES conduta_casos(id) ON DELETE RESTRICT,
  nome_cifrado                 TEXT NOT NULL CHECK (nome_cifrado LIKE 'v1:%'),
  cargo_cifrado                TEXT NOT NULL CHECK (cargo_cifrado LIKE 'v1:%'),
  papel                        TEXT NOT NULL CHECK (papel IN ('acusado', 'testemunha', 'denunciante')),
  criado_por                   VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  criado_em                    TIMESTAMPTZ NOT NULL DEFAULT now(),
  sem_gravacao_em              TIMESTAMPTZ,
  sem_gravacao_por             VARCHAR(10) REFERENCES participantes(id) ON DELETE RESTRICT,
  sem_gravacao_motivo_cifrado  TEXT,
  pontos_cifrados              TEXT,
  concluido_em                 TIMESTAMPTZ,
  concluido_por                VARCHAR(10) REFERENCES participantes(id) ON DELETE RESTRICT,
  CONSTRAINT conduta_depoimentos_sem_gravacao_check CHECK (
    (sem_gravacao_em IS NULL AND sem_gravacao_por IS NULL
      AND sem_gravacao_motivo_cifrado IS NULL AND pontos_cifrados IS NULL)
    OR (sem_gravacao_em IS NOT NULL AND sem_gravacao_por IS NOT NULL
      AND sem_gravacao_motivo_cifrado LIKE 'v1:%' AND pontos_cifrados LIKE 'v1:%')
  ),
  CONSTRAINT conduta_depoimentos_conclusao_check CHECK ((concluido_em IS NULL) = (concluido_por IS NULL))
);

COMMENT ON TABLE conduta_depoimentos IS
  'Cartão de cada pessoa ouvida na Apuração do Canal de Conduta (issue #1830). Nome, cargo, motivo e pontos cifrados pela aplicação. Concluído, não muda.';

CREATE INDEX IF NOT EXISTS idx_conduta_depoimentos_caso ON conduta_depoimentos (caso_id);
CREATE INDEX IF NOT EXISTS idx_conduta_depoimentos_criado_por ON conduta_depoimentos (criado_por);
CREATE INDEX IF NOT EXISTS idx_conduta_depoimentos_sem_gravacao_por ON conduta_depoimentos (sem_gravacao_por);
CREATE INDEX IF NOT EXISTS idx_conduta_depoimentos_concluido_por ON conduta_depoimentos (concluido_por);

ALTER TABLE conduta_depoimentos ENABLE ROW LEVEL SECURITY;

-- O concluído não muda, o sem gravação não volta atrás, e nenhum se apaga.
CREATE OR REPLACE FUNCTION conduta_depoimento_guardado() RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP <> 'UPDATE' THEN
    RAISE EXCEPTION 'O depoimento fica guardado: % não é permitido', TG_OP
      USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.concluido_em IS NOT NULL THEN
    RAISE EXCEPTION 'O depoimento concluído não muda'
      USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.sem_gravacao_em IS NOT NULL AND (
       NEW.sem_gravacao_em IS DISTINCT FROM OLD.sem_gravacao_em
       OR NEW.sem_gravacao_motivo_cifrado IS DISTINCT FROM OLD.sem_gravacao_motivo_cifrado
       OR NEW.pontos_cifrados IS DISTINCT FROM OLD.pontos_cifrados
     ) THEN
    RAISE EXCEPTION 'O registro sem gravação não muda'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conduta_depoimento_guardado ON conduta_depoimentos;
CREATE TRIGGER trg_conduta_depoimento_guardado
  BEFORE UPDATE OR DELETE ON conduta_depoimentos
  FOR EACH ROW EXECUTE FUNCTION conduta_depoimento_guardado();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_sem_truncate ON conduta_depoimentos;
CREATE TRIGGER trg_conduta_depoimento_sem_truncate
  BEFORE TRUNCATE ON conduta_depoimentos
  FOR EACH STATEMENT EXECUTE FUNCTION conduta_depoimento_guardado();

-- ---------- 2. Os arquivos, em versões ----------
CREATE TABLE IF NOT EXISTS conduta_depoimento_arquivos (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  depoimento_id  UUID NOT NULL REFERENCES conduta_depoimentos(id) ON DELETE RESTRICT,
  tipo           TEXT NOT NULL CHECK (tipo IN ('transcricao', 'audio', 'termo_assinado')),
  versao         INTEGER NOT NULL CHECK (versao >= 1),
  pagina         INTEGER NOT NULL DEFAULT 1 CHECK (pagina BETWEEN 1 AND 5),
  storage_path   TEXT NOT NULL UNIQUE,
  content_type   TEXT NOT NULL,
  tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes > 0),
  enviado_por    VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  enviado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (depoimento_id, tipo, versao, pagina)
);

COMMENT ON TABLE conduta_depoimento_arquivos IS
  'Arquivo do depoimento do Canal de Conduta (issue #1830): o binário vai cifrado ao bucket conduta-arquivos e só sai pelo backend, nunca por URL. Sem o nome original. Imutável: a versão nova fica ao lado da anterior.';

CREATE INDEX IF NOT EXISTS idx_conduta_depoimento_arquivos_enviado_por ON conduta_depoimento_arquivos (enviado_por);

ALTER TABLE conduta_depoimento_arquivos ENABLE ROW LEVEL SECURITY;

-- ---------- 3. As declarações da lista de conferência ----------
CREATE TABLE IF NOT EXISTS conduta_depoimento_conferencia (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  depoimento_id  UUID NOT NULL REFERENCES conduta_depoimentos(id) ON DELETE RESTRICT,
  item           TEXT NOT NULL CHECK (item IN ('arquivos_corretos', 'gravacao_apagada', 'arquivos_apagados', 'original_no_envelope')),
  marcado_por    VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE RESTRICT,
  marcado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (depoimento_id, item)
);

COMMENT ON TABLE conduta_depoimento_conferencia IS
  'Declaração de quem conduziu o depoimento, item a item da lista de conferência (issue #1830): quem marcou e quando. Imutável.';

CREATE INDEX IF NOT EXISTS idx_conduta_depoimento_conferencia_marcado_por ON conduta_depoimento_conferencia (marcado_por);

ALTER TABLE conduta_depoimento_conferencia ENABLE ROW LEVEL SECURITY;

-- Arquivo e declaração guardados não se alteram nem se apagam.
CREATE OR REPLACE FUNCTION conduta_depoimento_registro_imutavel() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'O registro do depoimento fica guardado: % não é permitido', TG_OP
    USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

-- E não entram em depoimento concluído.
CREATE OR REPLACE FUNCTION conduta_depoimento_em_aberto() RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM conduta_depoimentos WHERE id = NEW.depoimento_id AND concluido_em IS NOT NULL) THEN
    RAISE EXCEPTION 'O depoimento concluído não recebe mais nada'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conduta_depoimento_arquivos_imutavel ON conduta_depoimento_arquivos;
CREATE TRIGGER trg_conduta_depoimento_arquivos_imutavel
  BEFORE UPDATE OR DELETE ON conduta_depoimento_arquivos
  FOR EACH ROW EXECUTE FUNCTION conduta_depoimento_registro_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_arquivos_sem_truncate ON conduta_depoimento_arquivos;
CREATE TRIGGER trg_conduta_depoimento_arquivos_sem_truncate
  BEFORE TRUNCATE ON conduta_depoimento_arquivos
  FOR EACH STATEMENT EXECUTE FUNCTION conduta_depoimento_registro_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_arquivos_em_aberto ON conduta_depoimento_arquivos;
CREATE TRIGGER trg_conduta_depoimento_arquivos_em_aberto
  BEFORE INSERT ON conduta_depoimento_arquivos
  FOR EACH ROW EXECUTE FUNCTION conduta_depoimento_em_aberto();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_conferencia_imutavel ON conduta_depoimento_conferencia;
CREATE TRIGGER trg_conduta_depoimento_conferencia_imutavel
  BEFORE UPDATE OR DELETE ON conduta_depoimento_conferencia
  FOR EACH ROW EXECUTE FUNCTION conduta_depoimento_registro_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_conferencia_sem_truncate ON conduta_depoimento_conferencia;
CREATE TRIGGER trg_conduta_depoimento_conferencia_sem_truncate
  BEFORE TRUNCATE ON conduta_depoimento_conferencia
  FOR EACH STATEMENT EXECUTE FUNCTION conduta_depoimento_registro_imutavel();

DROP TRIGGER IF EXISTS trg_conduta_depoimento_conferencia_em_aberto ON conduta_depoimento_conferencia;
CREATE TRIGGER trg_conduta_depoimento_conferencia_em_aberto
  BEFORE INSERT ON conduta_depoimento_conferencia
  FOR EACH ROW EXECUTE FUNCTION conduta_depoimento_em_aberto();

-- ---------- 4. A Apuração só avança com os depoimentos concluídos ----------
CREATE OR REPLACE FUNCTION conduta_apuracao_com_depoimentos_concluidos() RETURNS TRIGGER AS $$
BEGIN
  IF OLD.etapa = 'apuracao' AND NEW.etapa IS DISTINCT FROM 'apuracao' AND EXISTS (
       SELECT 1 FROM conduta_depoimentos WHERE caso_id = NEW.id AND concluido_em IS NULL
     ) THEN
    RAISE EXCEPTION 'A Apuração só avança com todos os depoimentos concluídos'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_conduta_apuracao_com_depoimentos_concluidos ON conduta_casos;
CREATE TRIGGER trg_conduta_apuracao_com_depoimentos_concluidos
  BEFORE UPDATE OF etapa ON conduta_casos
  FOR EACH ROW EXECUTE FUNCTION conduta_apuracao_com_depoimentos_concluidos();

-- ---------- 5. O teto do bucket ----------
-- O áudio aceita até 300 MB; cifrado, ganha 28 bytes (nonce e etiqueta). 301
-- MB cabem com folga.
UPDATE storage.buckets SET file_size_limit = 315621376 WHERE id = 'conduta-arquivos';

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (190) ON CONFLICT (numero) DO NOTHING;
