-- =====================================================
-- Migration 045: POPs L1 — fundação de acesso (issue #81, ADR 0007)
-- =====================================================
-- Segundo contexto de domínio (POPs) no mesmo app:
--   1. participantes.perfil_pop — eixo de permissão próprio do contexto POPs,
--      ortogonal ao access_profile (Reuniões). NULL = sem papel no POPs.
--   2. access_profile vira nullable — NULL passa a significar "sem papel no
--      contexto Reuniões" (ex.: Coordenador de POPs que ganhou login mas não
--      participa de Reuniões). Default 'regular' permanece para os fluxos de
--      criação do contexto Reuniões.
--   3. pops_setores — o Setor do contexto POPs (unidade do organograma do HSM),
--      com nome e sigla únicos (a sigla é a base do Código travado
--      HSM_[SIGLA]-[NNN]). NÃO confundir com a tabela `setores` (taxonomia do
--      contexto Reuniões, canonicalização do campo livre participantes.setor).
--   4. pops_setores_participantes — vínculo N:N pessoa↔Setor (Gerente: vários;
--      Coordenador: normalmente um, sem trava artificial).
-- =====================================================

-- 1. Eixo de permissão do contexto POPs
ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS perfil_pop TEXT
  CHECK (perfil_pop IS NULL OR perfil_pop IN ('superadmin', 'gestor_qualidade', 'gerente', 'coordenador'));

CREATE INDEX IF NOT EXISTS idx_participantes_perfil_pop
  ON participantes(perfil_pop) WHERE perfil_pop IS NOT NULL;

-- 2. NULL = sem papel no contexto Reuniões (não mexe nos dados existentes)
ALTER TABLE participantes
  ALTER COLUMN access_profile DROP NOT NULL;

-- 3. Setores do contexto POPs
CREATE TABLE IF NOT EXISTS pops_setores (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome       TEXT NOT NULL,
  sigla      TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS pops_setores_nome_lower_idx ON pops_setores ((lower(nome)));
CREATE UNIQUE INDEX IF NOT EXISTS pops_setores_sigla_lower_idx ON pops_setores ((lower(sigla)));

-- 4. Vínculo N:N pessoa↔Setor
CREATE TABLE IF NOT EXISTS pops_setores_participantes (
  setor_id        UUID NOT NULL REFERENCES pops_setores(id) ON DELETE CASCADE,
  participante_id VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (setor_id, participante_id)
);

CREATE INDEX IF NOT EXISTS idx_pops_setores_participantes_participante
  ON pops_setores_participantes(participante_id);
