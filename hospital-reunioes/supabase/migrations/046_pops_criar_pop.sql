-- =====================================================
-- Migration 046: POPs L1 — criar POP (issue #82, PRD #76)
-- =====================================================
-- O nascimento de um POP (docs/pops/CONTEXT.md):
--   1. pops — a entidade permanente: Código travado HSM_[SIGLA]-[NNN] com
--      sequência por Setor (UNIQUE setor_id+numero é a garantia final contra
--      corrida; UNIQUE codigo sela a imutabilidade global), formulário
--      institucional (DRF §3.2: criticidade, base normativa, periodicidade,
--      prazos com defaults 15 dias úteis / 30 dias) e os responsáveis
--      designados (Elaborador, Revisor, Validador).
--   2. pops_versoes — a Versão que percorre o fluxo. O enum COMPLETO de
--      estados entra nesta fatia; as transições chegam nas seguintes (#83+).
--      A Versão 1.0 nasce em A_ELABORAR.
-- =====================================================

-- 1. POP — entidade permanente, Código travado
CREATE TABLE IF NOT EXISTS pops (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  setor_id              UUID NOT NULL REFERENCES pops_setores(id),
  numero                INT NOT NULL CHECK (numero > 0),
  codigo                TEXT NOT NULL,
  nome                  TEXT NOT NULL,
  criticidade           TEXT NOT NULL CHECK (criticidade IN ('CRITICA', 'ALTA', 'MEDIA')),
  base_normativa        TEXT,
  periodicidade_revisao TEXT NOT NULL CHECK (periodicidade_revisao IN ('3_meses', '6_meses', '1_ano', '2_anos')),
  prazo_elaboracao_dias INT NOT NULL DEFAULT 15 CHECK (prazo_elaboracao_dias > 0),
  prazo_revisao_dias    INT NOT NULL DEFAULT 30 CHECK (prazo_revisao_dias > 0),
  elaborador_id         VARCHAR(10) NOT NULL REFERENCES participantes(id),
  revisor_id            VARCHAR(10) NOT NULL REFERENCES participantes(id),
  validador_id          VARCHAR(10) NOT NULL REFERENCES participantes(id),
  criado_por            VARCHAR(10) REFERENCES participantes(id),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pops_setor_numero_unique UNIQUE (setor_id, numero),
  CONSTRAINT pops_codigo_unique UNIQUE (codigo)
);

CREATE INDEX IF NOT EXISTS idx_pops_setor ON pops(setor_id);
CREATE INDEX IF NOT EXISTS idx_pops_elaborador ON pops(elaborador_id);

DROP TRIGGER IF EXISTS trigger_pops_updated_at ON pops;
CREATE TRIGGER trigger_pops_updated_at
  BEFORE UPDATE ON pops
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- 2. Versão — enum completo do fluxo; transições nas fatias seguintes
CREATE TABLE IF NOT EXISTS pops_versoes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pop_id        UUID NOT NULL REFERENCES pops(id) ON DELETE CASCADE,
  numero_versao TEXT NOT NULL DEFAULT '1.0',
  estado        TEXT NOT NULL DEFAULT 'A_ELABORAR' CHECK (
    estado IN ('A_ELABORAR', 'EM_ELABORACAO', 'EM_REVISAO', 'EM_VALIDACAO', 'EM_ASSINATURA', 'PUBLICADO')
  ),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT pops_versoes_pop_numero_unique UNIQUE (pop_id, numero_versao)
);

CREATE INDEX IF NOT EXISTS idx_pops_versoes_pop ON pops_versoes(pop_id);
CREATE INDEX IF NOT EXISTS idx_pops_versoes_estado ON pops_versoes(estado);

DROP TRIGGER IF EXISTS trigger_pops_versoes_updated_at ON pops_versoes;
CREATE TRIGGER trigger_pops_versoes_updated_at
  BEFORE UPDATE ON pops_versoes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();
