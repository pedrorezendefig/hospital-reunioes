-- =====================================================
-- Migration 194: a tela de triagem do Núcleo
-- (issue #1992, PRD #1979, ADR 0095 e ADR 0107)
-- =====================================================
-- O que entra:
--   1. a linha da pessoa em `nsp_triagens` (migration 188) ganha quem
--      decidiu, as divergências em relação à sugestão do agente (os campos
--      que a pessoa mudou; vazio quando confirmou como veio, nulo quando não
--      havia sugestão) e a frequência e a prioridade que o sistema calculou
--      pela matriz do Anexo A no momento da decisão;
--   2. uma decisão de pessoa por notificação: o índice único parcial recusa a
--      segunda, e quem chega depois recebe "já confirmada". A sugestão do
--      agente fica como está, em linha própria;
--   3. os cortes de frequência da matriz de prioridade, editáveis na
--      Configuração do módulo. Uma linha só, com a sugestão da issue #2005
--      como padrão: em 12 meses, nenhuma ocorrência anterior = remoto, 1 =
--      incomum, 2 ou 3 = ocasional, 4 ou mais = frequente.
--
-- Nenhuma pessoa entra por aqui. RLS ligado e sem política na tabela nova:
-- só o backend, com a service_role, lê e grava. Rodar duas vezes é
-- inofensivo. Aplicar à mão no Studio.
-- =====================================================

BEGIN;

-- ---------- 1. A linha da pessoa ----------
ALTER TABLE nsp_triagens
  ADD COLUMN IF NOT EXISTS autor_id VARCHAR(10) REFERENCES participantes(id) ON DELETE RESTRICT;
ALTER TABLE nsp_triagens
  ADD COLUMN IF NOT EXISTS divergencias TEXT[];
ALTER TABLE nsp_triagens
  ADD COLUMN IF NOT EXISTS frequencia TEXT CHECK (frequencia IN ('remoto', 'incomum', 'ocasional', 'frequente'));
ALTER TABLE nsp_triagens
  ADD COLUMN IF NOT EXISTS prioridade TEXT CHECK (prioridade IN ('alta', 'moderada', 'baixa'));

ALTER TABLE nsp_triagens DROP CONSTRAINT IF EXISTS nsp_triagens_pessoa_tem_autor;
ALTER TABLE nsp_triagens
  ADD CONSTRAINT nsp_triagens_pessoa_tem_autor
  CHECK (autor_tipo <> 'pessoa' OR autor_id IS NOT NULL);

COMMENT ON COLUMN nsp_triagens.autor_id IS
  'Na linha da pessoa: quem confirmou ou ajustou a triagem. Issue #1992.';
COMMENT ON COLUMN nsp_triagens.divergencias IS
  'Na linha da pessoa: os campos em que ela mudou a sugestão do agente. Vazio = confirmou como veio; nulo = não havia sugestão. Issue #1992.';
COMMENT ON COLUMN nsp_triagens.frequencia IS
  'Na linha da pessoa: a frequência pela contagem do sistema e pelos cortes da Configuração, no momento da decisão.';
COMMENT ON COLUMN nsp_triagens.prioridade IS
  'Na linha da pessoa: a prioridade pela matriz do Anexo A (gravidade por frequência), no momento da decisão.';

CREATE INDEX IF NOT EXISTS idx_nsp_triagens_autor ON nsp_triagens (autor_id);

-- ---------- 2. Uma decisão de pessoa por notificação ----------
CREATE UNIQUE INDEX IF NOT EXISTS uq_nsp_triagens_uma_decisao_por_notificacao
  ON nsp_triagens (notificacao_id) WHERE autor_tipo = 'pessoa';

-- ---------- 3. Os cortes de frequência ----------
CREATE TABLE IF NOT EXISTS nsp_cortes_de_frequencia (
  id                  BOOLEAN PRIMARY KEY DEFAULT true CHECK (id),
  janela_meses        SMALLINT NOT NULL DEFAULT 12 CHECK (janela_meses BETWEEN 1 AND 60),
  incomum_a_partir    SMALLINT NOT NULL DEFAULT 1,
  ocasional_a_partir  SMALLINT NOT NULL DEFAULT 2,
  frequente_a_partir  SMALLINT NOT NULL DEFAULT 4,
  atualizado_por      VARCHAR(10) REFERENCES participantes(id) ON DELETE RESTRICT,
  atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (1 <= incomum_a_partir AND incomum_a_partir < ocasional_a_partir AND ocasional_a_partir < frequente_a_partir)
);

COMMENT ON TABLE nsp_cortes_de_frequencia IS
  'Os cortes de frequência da matriz de prioridade do Núcleo (Anexo A, 7.2): quantas ocorrências anteriores da mesma categoria no mesmo setor, na janela, fazem cada frequência. Uma linha só. Issue #1992.';

CREATE INDEX IF NOT EXISTS idx_nsp_cortes_de_frequencia_atualizado_por ON nsp_cortes_de_frequencia (atualizado_por);

ALTER TABLE nsp_cortes_de_frequencia ENABLE ROW LEVEL SECURITY;

INSERT INTO nsp_cortes_de_frequencia (id) VALUES (true) ON CONFLICT (id) DO NOTHING;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (194) ON CONFLICT (numero) DO NOTHING;
