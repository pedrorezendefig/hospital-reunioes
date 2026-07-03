-- =====================================================
-- Migration 054: backfill da Natureza dos Setores pelo nome (issue #173, ADR 0018)
-- =====================================================
-- A migration 053 criou a coluna natureza com DEFAULT 'assistencial', deixando
-- TODOS os Setores existentes provisoriamente assistenciais. Aqui reinferimos a
-- Natureza a partir do nome, do mesmo jeito que o cadastro passa a sugerir.
--
-- Fonte viva da verdade: app/services/natureza.py (inferir_natureza). Este SQL é
-- um RETRATO CONGELADO dela para o backfill; se a heurística mudar, ela muda lá,
-- e um novo backfill (se necessário) vira outra migration. Paridade com o Python:
--   normalização: unaccent + lower + espaços colapsados (== _normalizar);
--   casamento: palavra inteira (\y no Postgres == \b no Python);
--   precedência: administrativa > apoio > assistencial (ordem do CASE).
--
-- Guarda (não pisar em escolha manual): só toca linhas AINDA no default
-- provisório (natureza = 'assistencial') e só quando a inferência dá um valor
-- DIFERENTE (administrativa/apoio). Uma Natureza que um admin ajustou à mão, ou
-- um Setor que segue assistencial, ficam intactos.
-- unaccent é extensão contrib padrão; habilitada aqui de forma idempotente.
-- =====================================================

CREATE EXTENSION IF NOT EXISTS unaccent;

WITH normalizado AS (
  SELECT
    id,
    regexp_replace(unaccent(lower(nome)), '\s+', ' ', 'g') AS n
  FROM pops_setores
  WHERE natureza = 'assistencial'
),
inferencia AS (
  SELECT
    id,
    CASE
      WHEN n ~ '\y(faturamento|cobranca|financeiro|financas|contabilidade|contabil|tesouraria|recursos humanos|rh|departamento de pessoal|gestao de pessoas|compras|suprimentos|recepcao|administracao|administrativo|administrativa|juridico|comercial|marketing|ouvidoria)\y'
        THEN 'administrativa'
      WHEN n ~ '\y(higienizacao|higiene|limpeza|zeladoria|manutencao|engenharia|infraestrutura|predial|almoxarifado|estoque|logistica|cme|esterilizacao|central de material|lavanderia|rouparia|nutricao|dietetica|cozinha|refeitorio|ti|tecnologia da informacao|informatica|transporte|portaria)\y'
        THEN 'apoio'
      ELSE 'assistencial'
    END AS natureza_inferida
  FROM normalizado
)
UPDATE pops_setores AS s
SET natureza = i.natureza_inferida
FROM inferencia AS i
WHERE s.id = i.id
  AND i.natureza_inferida <> 'assistencial';
