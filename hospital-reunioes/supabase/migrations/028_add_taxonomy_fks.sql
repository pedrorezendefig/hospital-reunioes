-- =====================================================
-- Migration 028: FKs de taxonomia em participantes e reunioes
--
-- Depende de 027 (tabelas setores/cargos/tipos_reuniao já criadas e
-- populadas com distincts normalizados).
--
-- Estratégia: adiciona colunas `setor_id`, `cargo_id` em `participantes`
-- e `tipo_id` em `reunioes` como FK para as tabelas de taxonomia. Faz
-- backfill matchando por `lower(trim(nome))` em cada linha existente.
--
-- IMPORTANTE: mantemos as colunas TEXT antigas (`setor`, `cargo`,
-- `tipo`) por compatibilidade durante um ciclo. Elas serão dropadas
-- só na Fase 3, depois de auditar todos os consumidores. Toda escrita
-- nova via admin deverá preencher AMBOS os campos (FK + TEXT) até o
-- drop final. Leitura pode preferir o TEXT (rápido, sem JOIN) ou JOIN
-- via FK; ambos estão garantidamente em sincronia após este backfill.
--
-- Validação: ao final, um bloco DO reporta via RAISE NOTICE quantas
-- linhas ficaram órfãs (setor não-nulo em participantes sem setor_id).
-- Em dev esperamos 0 órfãos. Em prod, se algum valor legado não bater
-- com os seeds (por ex. variação ortográfica não capturada pelo
-- `initcap(trim)`), o órfão fica registrado e pode ser corrigido com
-- INSERT manual em setores + re-run desta migration.
--
-- Reversível via: DROP COLUMN setor_id, cargo_id, tipo_id. Colunas
-- TEXT preservam os valores operacionais.
-- =====================================================

ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS setor_id UUID REFERENCES setores(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS cargo_id UUID REFERENCES cargos(id)  ON DELETE SET NULL;

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS tipo_id UUID REFERENCES tipos_reuniao(id) ON DELETE SET NULL;

-- ---------- Backfill participantes.setor_id ----------
UPDATE participantes p
SET setor_id = s.id
FROM setores s
WHERE p.setor IS NOT NULL
  AND lower(trim(p.setor)) = lower(s.nome)
  AND p.setor_id IS NULL;

-- ---------- Backfill participantes.cargo_id ----------
UPDATE participantes p
SET cargo_id = c.id
FROM cargos c
WHERE p.cargo IS NOT NULL
  AND lower(trim(p.cargo)) = lower(c.nome)
  AND p.cargo_id IS NULL;

-- ---------- Backfill reunioes.tipo_id ----------
UPDATE reunioes r
SET tipo_id = t.id
FROM tipos_reuniao t
WHERE r.tipo IS NOT NULL
  AND lower(trim(r.tipo)) = lower(t.nome)
  AND r.tipo_id IS NULL;

-- ---------- Validação por logs ----------
DO $$
DECLARE
  setor_orfaos INT;
  cargo_orfaos INT;
  tipo_orfaos  INT;
BEGIN
  SELECT COUNT(*) INTO setor_orfaos
  FROM participantes
  WHERE setor IS NOT NULL AND trim(setor) <> '' AND setor_id IS NULL;

  SELECT COUNT(*) INTO cargo_orfaos
  FROM participantes
  WHERE cargo IS NOT NULL AND trim(cargo) <> '' AND cargo_id IS NULL;

  SELECT COUNT(*) INTO tipo_orfaos
  FROM reunioes
  WHERE tipo IS NOT NULL AND trim(tipo) <> '' AND tipo_id IS NULL;

  RAISE NOTICE 'Backfill 028: setor_orfaos=%, cargo_orfaos=%, tipo_orfaos=%',
    setor_orfaos, cargo_orfaos, tipo_orfaos;
END $$;

COMMENT ON COLUMN participantes.setor_id IS
  'FK para setores.id. Mantido em sincronia com a coluna TEXT setor até drop da TEXT em migration futura.';
COMMENT ON COLUMN participantes.cargo_id IS
  'FK para cargos.id. Mantido em sincronia com a coluna TEXT cargo até drop da TEXT em migration futura.';
COMMENT ON COLUMN reunioes.tipo_id IS
  'FK para tipos_reuniao.id. Mantido em sincronia com a coluna TEXT tipo até drop da TEXT em migration futura.';
