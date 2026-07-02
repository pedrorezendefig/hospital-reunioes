-- =====================================================
-- Migration 053: POPs — Natureza do Setor (issue #170, ADR 0018)
-- =====================================================
-- Cada Setor ganha a Natureza (área de domínio) que orienta qual corpo de
-- normas o agente de Elaboração evoca ao redigir os POPs daquele Setor:
--   assistencial  — cuidado direto ao paciente (ONA, JCI, COFEN, CFM, ANVISA);
--   administrativa — gestão e processos (normas trabalhistas, eSocial);
--   apoio          — técnica e logística (normas sanitárias, ABNT, biossegurança).
-- É atributo do Setor; todo POP a herda do seu Setor sem o Elaborador escolher.
--
-- Backfill: os Setores existentes ficam 'assistencial' (o DEFAULT preenche as
-- linhas atuais), preservando o comportamento vigente. No cadastro a seleção é
-- manual editável; a inferência automática a partir do nome vem em fatia própria.
-- pops_setores já tem RLS habilitada (migration 051): nova COLUNA, sem ENABLE.
-- =====================================================

ALTER TABLE pops_setores
  ADD COLUMN IF NOT EXISTS natureza TEXT NOT NULL DEFAULT 'assistencial'
  CHECK (natureza IN ('assistencial', 'administrativa', 'apoio'));
