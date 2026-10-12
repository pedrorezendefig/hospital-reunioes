-- =====================================================
-- Migration 116: Contas medicas, a fundacao (issue #1114, PRD #1113, ADR 0070)
-- =====================================================
-- A unica migration do PRD 1 de Contas medicas (ADR 0070, decisao 11): todas
-- as tabelas do motor, do Guia e da carga das operadoras nascem aqui, para as
-- fatias seguintes andarem em paralelo sem pedir outra parada no Studio.
--
-- O que entra:
--   1. o eixo de permissao `perfil_contas_medicas` em `participantes`;
--   2. a matriz perfil x permissao, com a carga inicial da spec do diretor;
--   3. operadoras, planos do MV, memoria, regras, tabelas de preco, setores e
--      dicionario de itens;
--   4. envio, arquivo, atendimento e o que a leitura do prontuario estrutura;
--   5. a conta, os itens dela, as linhas do Guia e as observacoes;
--   6. o tipo CONTAS_MEDICAS no sino;
--   7. o bucket privado `contas-medicas`, com teto de 100 MiB por arquivo;
--   8. o Produto "Contas medicas" na aba Tecnologia.
--
-- Dado de paciente: rotulo ("Maria S.") e idade em anos, mais nada (ADR 0070,
-- decisao 8). Nenhuma tabela daqui tem nome completo, CPF, carteira ou data de
-- nascimento.
--
-- Prefixo `cm_` em tudo. RLS default-deny em toda tabela (padrao da casa:
-- 009/041/051/063/064/066/102/115): quem le e escreve e o backend com a
-- service_role. Nenhuma policy de proposito.
--
-- Tudo com IF NOT EXISTS / DROP antes de ADD / ON CONFLICT: rodar duas vezes
-- tem que ser inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. O eixo de permissao ----------
-- Quarto eixo, ortogonal aos de Reunioes, POPs e Ouvidoria (ADR 0070, decisao
-- 10). Nulo = fora do modulo. O perfil e so o conjunto inicial: o que vale e a
-- matriz da secao 2.
ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS perfil_contas_medicas TEXT;

ALTER TABLE participantes DROP CONSTRAINT IF EXISTS participantes_perfil_contas_medicas_check;
ALTER TABLE participantes
  ADD CONSTRAINT participantes_perfil_contas_medicas_check
  CHECK (perfil_contas_medicas IS NULL OR perfil_contas_medicas IN (
    'faturista',
    'coordenadora',
    'gestao_contas_medicas',
    'diretoria_medica',
    'diretoria_executiva',
    'credenciamento'
  ));

CREATE INDEX IF NOT EXISTS idx_participantes_perfil_contas_medicas
  ON participantes(perfil_contas_medicas) WHERE perfil_contas_medicas IS NOT NULL;

COMMENT ON COLUMN participantes.perfil_contas_medicas IS
  'Eixo de permissao de Contas medicas (ADR 0070, decisao 10). Nulo = fora do modulo. As permissoes de cada perfil vivem em cm_perfil_permissao.';

-- ---------- 2. A matriz perfil x permissao ----------
-- Oito permissoes, da spec do diretor (secao 3) e do adendo v1.1 (Conferencia
-- da coordenacao). A tela de Habilitacao (PRD 3) liga e desliga cada uma por
-- perfil; ate la, vale a carga abaixo. "Incluir regra operacional" nasce
-- DESLIGADA para a coordenadora (em avaliacao pelo diretor): a linha existe,
-- com `ligada = false`, para a Habilitacao ter o que ligar.
CREATE TABLE IF NOT EXISTS cm_perfil_permissao (
  perfil     TEXT NOT NULL CHECK (perfil IN (
    'faturista', 'coordenadora', 'gestao_contas_medicas',
    'diretoria_medica', 'diretoria_executiva', 'credenciamento'
  )),
  permissao  TEXT NOT NULL CHECK (permissao IN (
    'enviar_corrigir_contas', 'decidir_validacao', 'incluir_regra_operacional',
    'regra_contratual_tabelas', 'contratos_avisos', 'painel_completo',
    'habilitar_pessoas', 'conferencia_coordenacao'
  )),
  ligada     BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (perfil, permissao)
);

COMMENT ON TABLE cm_perfil_permissao IS
  'Matriz perfil x permissao de Contas medicas (ADR 0070, decisao 10). O guard require_permissao_cm le daqui.';

ALTER TABLE cm_perfil_permissao ENABLE ROW LEVEL SECURITY;

-- ON CONFLICT DO NOTHING: reaplicar nao desfaz o que a Habilitacao mudou.
INSERT INTO cm_perfil_permissao (perfil, permissao, ligada) VALUES
  ('faturista', 'enviar_corrigir_contas', true),
  ('faturista', 'decidir_validacao', false),
  ('faturista', 'incluir_regra_operacional', false),
  ('faturista', 'regra_contratual_tabelas', false),
  ('faturista', 'contratos_avisos', false),
  ('faturista', 'painel_completo', false),
  ('faturista', 'habilitar_pessoas', false),
  ('faturista', 'conferencia_coordenacao', false),
  ('coordenadora', 'enviar_corrigir_contas', true),
  ('coordenadora', 'decidir_validacao', false),
  ('coordenadora', 'incluir_regra_operacional', false),
  ('coordenadora', 'regra_contratual_tabelas', false),
  ('coordenadora', 'contratos_avisos', false),
  ('coordenadora', 'painel_completo', true),
  ('coordenadora', 'habilitar_pessoas', false),
  ('coordenadora', 'conferencia_coordenacao', true),
  ('gestao_contas_medicas', 'enviar_corrigir_contas', true),
  ('gestao_contas_medicas', 'decidir_validacao', true),
  ('gestao_contas_medicas', 'incluir_regra_operacional', true),
  ('gestao_contas_medicas', 'regra_contratual_tabelas', true),
  ('gestao_contas_medicas', 'contratos_avisos', true),
  ('gestao_contas_medicas', 'painel_completo', true),
  ('gestao_contas_medicas', 'habilitar_pessoas', false),
  ('gestao_contas_medicas', 'conferencia_coordenacao', true),
  ('diretoria_medica', 'enviar_corrigir_contas', true),
  ('diretoria_medica', 'decidir_validacao', true),
  ('diretoria_medica', 'incluir_regra_operacional', true),
  ('diretoria_medica', 'regra_contratual_tabelas', true),
  ('diretoria_medica', 'contratos_avisos', true),
  ('diretoria_medica', 'painel_completo', true),
  ('diretoria_medica', 'habilitar_pessoas', true),
  ('diretoria_medica', 'conferencia_coordenacao', true),
  ('diretoria_executiva', 'enviar_corrigir_contas', true),
  ('diretoria_executiva', 'decidir_validacao', true),
  ('diretoria_executiva', 'incluir_regra_operacional', true),
  ('diretoria_executiva', 'regra_contratual_tabelas', true),
  ('diretoria_executiva', 'contratos_avisos', true),
  ('diretoria_executiva', 'painel_completo', true),
  ('diretoria_executiva', 'habilitar_pessoas', true),
  ('diretoria_executiva', 'conferencia_coordenacao', true),
  ('credenciamento', 'enviar_corrigir_contas', false),
  ('credenciamento', 'decidir_validacao', false),
  ('credenciamento', 'incluir_regra_operacional', false),
  ('credenciamento', 'regra_contratual_tabelas', false),
  ('credenciamento', 'contratos_avisos', true),
  ('credenciamento', 'painel_completo', false),
  ('credenciamento', 'habilitar_pessoas', false),
  ('credenciamento', 'conferencia_coordenacao', false)
ON CONFLICT (perfil, permissao) DO NOTHING;

INSERT INTO migracoes_aplicadas (numero) VALUES (116) ON CONFLICT (numero) DO NOTHING;
