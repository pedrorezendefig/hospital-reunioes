-- =====================================================
-- Migration 052: Descontinuar Notas (issue #127, ADR 0011)
--
-- A Nota (ADR 0004, migrations 041/042/043) nunca foi adotada em produção:
-- zero Notas criadas, zero Pendências com id_nota. Esta migration desfaz o
-- schema de ponta a ponta e a Pendência volta a nascer de uma única porta:
-- Reunião em estado terminal (ASSINADA ou APROVADA, ADR 0003).
--
-- GATE DE SEGURANÇA: o id_nota tem ON DELETE CASCADE — com qualquer dado
-- presente, o drop apagaria Pendências. Se existir QUALQUER Nota ou
-- Pendência de Nota, a migration aborta (RAISE EXCEPTION) e a conversa
-- reabre antes de qualquer drop.
--
-- Aplicação em produção é MANUAL (protocolo do /deploy: Studio em janela
-- anônima ou psql via Coolify Terminal).
--
-- Irreversível com dados; recriar a feature = nova migration a partir dos
-- ADRs 0004 e 0011.
-- =====================================================

-- 1) Gate de segurança: aborta se houver qualquer dado de Nota.
DO $$
DECLARE
  qtd_notas BIGINT := 0;
  qtd_pendencias_nota BIGINT := 0;
BEGIN
  IF to_regclass('public.notas') IS NOT NULL THEN
    SELECT count(*) INTO qtd_notas FROM notas;
  END IF;

  IF to_regclass('public.pendencias') IS NOT NULL
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public' AND table_name = 'pendencias' AND column_name = 'id_nota'
     ) THEN
    SELECT count(*) INTO qtd_pendencias_nota FROM pendencias WHERE id_nota IS NOT NULL;
  END IF;

  IF qtd_notas > 0 OR qtd_pendencias_nota > 0 THEN
    RAISE EXCEPTION
      'ABORTADO: existem % nota(s) e % pendência(s) com origem Nota. O DROP em cascata apagaria Pendências — reabra a conversa (ADR 0011) antes de aplicar.',
      qtd_notas, qtd_pendencias_nota;
  END IF;
END $$;

-- 2) Desfaz o CHECK de origem única (migration 042).
ALTER TABLE pendencias DROP CONSTRAINT IF EXISTS chk_pendencias_origem_unica;

-- 3) Remove o FK de origem Nota (migration 042; o índice idx_pendencias_nota cai junto).
ALTER TABLE pendencias DROP COLUMN IF EXISTS id_nota;

-- 4) Derruba as tabelas da Nota (migrations 043 e 041, nesta ordem — o roster referencia notas).
DROP TABLE IF EXISTS nota_participantes;
DROP TABLE IF EXISTS notas;
