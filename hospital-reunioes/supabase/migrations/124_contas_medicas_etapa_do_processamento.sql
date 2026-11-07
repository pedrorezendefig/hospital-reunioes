-- =====================================================
-- Migration 124: Contas medicas, a Etapa do processamento
-- (issue #1416, PRD #1415)
-- =====================================================
-- A unica migration do PRD #1415. O Motor passa a gravar em que Etapa do
-- processamento cada conta esta, e a aba Envios le dali.
--
-- O que entra:
--   1. em `cm_conta`, a etapa da tela (`etapa_atual`, uma das cinco: Lendo a
--      conta, Lendo o prontuario, IA lendo o prontuario, Conferindo e IA
--      montando o Guia), desde quando ela comecou (`etapa_desde`) e, no
--      Passo A, a parte em curso e quantas sao (`etapa_parte`,
--      `etapa_partes`). Tudo nulo fora de PROCESSANDO: o Motor limpa quando a
--      conta fica pronta, vai para Erro ou volta para a fila;
--   2. em `cm_arquivo`, `paginas_ocr`: quantas paginas do Prontuario foram
--      lidas por OCR. Nasce nula; quem preenche e a fatia dos dados do cartao
--      (issue #1419).
--
-- So acrescenta colunas, todas nulas e sem DEFAULT: o backend de antes segue
-- funcionando entre a aplicacao e a subida. Sem tabela nova, sem policy nova:
-- `cm_conta` e `cm_arquivo` tem RLS default-deny desde a 116 (quem le e
-- escreve e o backend com a service_role).
--
-- Tudo com IF NOT EXISTS / DROP antes de ADD: rodar duas vezes e inofensivo.
-- Aplicar a mao no Studio ANTES da subida: o deploy nao aplica SQL, e o
-- backend novo grava as colunas da etapa.
-- =====================================================

-- ---------- 1. A etapa da conta ----------
ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS etapa_atual TEXT;

ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS etapa_desde TIMESTAMPTZ;

ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS etapa_parte INTEGER;

ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS etapa_partes INTEGER;

ALTER TABLE cm_conta DROP CONSTRAINT IF EXISTS cm_conta_etapa_atual_check;
ALTER TABLE cm_conta
  ADD CONSTRAINT cm_conta_etapa_atual_check
  CHECK (etapa_atual IS NULL OR etapa_atual IN ('LENDO_CONTA', 'LENDO_PRONTUARIO', 'IA_LENDO_PRONTUARIO', 'CONFERINDO', 'IA_MONTANDO_GUIA'));

COMMENT ON COLUMN cm_conta.etapa_atual IS
  'A Etapa do processamento na tela (issue #1416): LENDO_CONTA, LENDO_PRONTUARIO, IA_LENDO_PRONTUARIO, CONFERINDO ou IA_MONTANDO_GUIA. Nula fora de PROCESSANDO.';
COMMENT ON COLUMN cm_conta.etapa_desde IS
  'Quando a etapa atual comecou. Nula fora de PROCESSANDO.';
COMMENT ON COLUMN cm_conta.etapa_parte IS
  'No Passo A, a parte do prontuario em leitura ("parte 3 de 7"). Nula nas outras etapas e com o Passo A vindo do cache do atendimento.';
COMMENT ON COLUMN cm_conta.etapa_partes IS
  'No Passo A, em quantas partes o prontuario vai para a IA. Nula nas outras etapas e com o Passo A vindo do cache do atendimento.';

-- ---------- 2. As paginas por OCR do Prontuario ----------
ALTER TABLE cm_arquivo
  ADD COLUMN IF NOT EXISTS paginas_ocr INTEGER;

ALTER TABLE cm_arquivo DROP CONSTRAINT IF EXISTS cm_arquivo_paginas_ocr_check;
ALTER TABLE cm_arquivo
  ADD CONSTRAINT cm_arquivo_paginas_ocr_check
  CHECK (paginas_ocr IS NULL OR paginas_ocr >= 0);

COMMENT ON COLUMN cm_arquivo.paginas_ocr IS
  'Quantas paginas do Prontuario foram lidas por OCR (issue #1419). Nula no arquivo enviado antes dela e na Conta.';

INSERT INTO migracoes_aplicadas (numero) VALUES (124) ON CONFLICT (numero) DO NOTHING;
