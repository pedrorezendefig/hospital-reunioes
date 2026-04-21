-- =====================================================
-- Migration 027: Tabelas de taxonomia (setores, cargos, tipos_reuniao)
--
-- Motivação: hoje `participantes.setor`, `participantes.cargo` e
-- `reunioes.tipo` são TEXT livre sem validação — "Administrativo",
-- "administrativo" e "Adm" coexistem como valores distintos. Tipos de
-- reunião são CHECK constraint fixo, impossível editar sem migration.
-- O super-admin precisa gerir essas taxonomias como entidades de
-- primeira classe (criar, renomear, arquivar).
--
-- Estratégia (Fase 1 do plano super-admin CRUD): criar as 3 tabelas
-- com UNIQUE case-insensitive, popular com distincts normalizados
-- (`initcap(trim(...))`) dos valores existentes, adicionar RLS e
-- triggers de updated_at. As FKs em participantes/reunioes serão
-- adicionadas na migration 028 (separadas para isolar backfill).
--
-- Reversível via: DROP TABLE setores, cargos, tipos_reuniao CASCADE.
-- Os valores TEXT originais em participantes/reunioes continuam
-- intactos (não são tocados aqui).
-- =====================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------- setores ----------
CREATE TABLE IF NOT EXISTS setores (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome       TEXT NOT NULL,
  ativo      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS setores_nome_lower_idx ON setores ((lower(nome)));

CREATE TRIGGER trigger_setores_updated_at
  BEFORE UPDATE ON setores
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------- cargos ----------
CREATE TABLE IF NOT EXISTS cargos (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome       TEXT NOT NULL,
  ativo      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS cargos_nome_lower_idx ON cargos ((lower(nome)));

CREATE TRIGGER trigger_cargos_updated_at
  BEFORE UPDATE ON cargos
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------- tipos_reuniao ----------
CREATE TABLE IF NOT EXISTS tipos_reuniao (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome       TEXT NOT NULL,
  ativo      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS tipos_reuniao_nome_lower_idx ON tipos_reuniao ((lower(nome)));

CREATE TRIGGER trigger_tipos_reuniao_updated_at
  BEFORE UPDATE ON tipos_reuniao
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------- Seed: valores vindos dos campos TEXT existentes ----------
INSERT INTO setores (nome)
SELECT DISTINCT initcap(trim(setor))
FROM participantes
WHERE setor IS NOT NULL AND trim(setor) <> ''
ON CONFLICT DO NOTHING;

INSERT INTO cargos (nome)
SELECT DISTINCT initcap(trim(cargo))
FROM participantes
WHERE cargo IS NOT NULL AND trim(cargo) <> ''
ON CONFLICT DO NOTHING;

-- Tipos fixos do CHECK atual de reunioes.tipo
INSERT INTO tipos_reuniao (nome) VALUES
  ('Diretoria'),
  ('Gerencial'),
  ('Coordenação'),
  ('Mensal'),
  ('Extraordinária')
ON CONFLICT DO NOTHING;

-- Varredura por valores já usados em reunioes que não estejam na lista fixa
INSERT INTO tipos_reuniao (nome)
SELECT DISTINCT initcap(trim(tipo))
FROM reunioes
WHERE tipo IS NOT NULL AND trim(tipo) <> ''
ON CONFLICT DO NOTHING;

-- ---------- RLS ----------
-- Mutações passam sempre por backend com service_role (bypassa RLS).
-- Não criamos policies para authenticated — o admin lê via endpoint /admin/*.
ALTER TABLE setores        ENABLE ROW LEVEL SECURITY;
ALTER TABLE cargos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE tipos_reuniao  ENABLE ROW LEVEL SECURITY;

-- Comentários de schema
COMMENT ON TABLE setores       IS 'Taxonomia de setores organizacionais gerida pelo super-admin.';
COMMENT ON TABLE cargos        IS 'Taxonomia de cargos gerida pelo super-admin.';
COMMENT ON TABLE tipos_reuniao IS 'Taxonomia de tipos de reunião gerida pelo super-admin.';
