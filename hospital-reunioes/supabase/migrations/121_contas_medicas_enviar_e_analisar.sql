-- =====================================================
-- Migration 121: Contas medicas, Enviar contas e Analisar contas separados
-- (issue #1308, PRD #1303, ADR 0073 decisao 4)
-- =====================================================
-- Quem sobe a conta nao e, necessariamente, quem analisa: a secretaria envia
-- e as faturistas puxam da Fila. A chave `enviar_corrigir_contas` NAO muda de
-- nome (a tela passa a chama-la "Analisar contas"); soma-se a chave
-- `enviar_contas` e o perfil `apoio_faturamento`, so com ela.
--
-- So acrescenta: amplia as tres listas fechadas e insere linhas novas na
-- matriz. Nada e renomeado nem apagado, e o codigo de antes desta migration
-- continua funcionando ate a subida (o guard dele so le a chave antiga).
--
-- Sem tabela nova, sem policy nova: `cm_perfil_permissao` tem RLS
-- default-deny desde a 116 (quem le e escreve e o backend com a service_role).
--
-- Tudo com DROP antes de ADD e ON CONFLICT DO NOTHING: rodar duas vezes e
-- inofensivo e nao desfaz o que a Habilitacao mudou. Aplicar a mao no Studio,
-- depois da 120: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. As listas fechadas ----------
-- O perfil da pessoa. O nome de tela "Apoio ao faturamento" ainda espera o
-- diretor; se mudar, muda so o rotulo, nao a chave.
ALTER TABLE participantes DROP CONSTRAINT IF EXISTS participantes_perfil_contas_medicas_check;
ALTER TABLE participantes
  ADD CONSTRAINT participantes_perfil_contas_medicas_check
  CHECK (perfil_contas_medicas IS NULL OR perfil_contas_medicas IN (
    'faturista',
    'coordenadora',
    'gestao_contas_medicas',
    'diretoria_medica',
    'diretoria_executiva',
    'credenciamento',
    'apoio_faturamento'
  ));

-- Os CHECKs da 116 nasceram na coluna, sem nome: o Postgres os chamou de
-- <tabela>_<coluna>_check. Voltam com o mesmo nome e a lista ampliada.
ALTER TABLE cm_perfil_permissao DROP CONSTRAINT IF EXISTS cm_perfil_permissao_perfil_check;
ALTER TABLE cm_perfil_permissao
  ADD CONSTRAINT cm_perfil_permissao_perfil_check
  CHECK (perfil IN (
    'faturista', 'coordenadora', 'gestao_contas_medicas',
    'diretoria_medica', 'diretoria_executiva', 'credenciamento',
    'apoio_faturamento'
  ));

ALTER TABLE cm_perfil_permissao DROP CONSTRAINT IF EXISTS cm_perfil_permissao_permissao_check;
ALTER TABLE cm_perfil_permissao
  ADD CONSTRAINT cm_perfil_permissao_permissao_check
  CHECK (permissao IN (
    'enviar_contas',
    'enviar_corrigir_contas', 'decidir_validacao', 'incluir_regra_operacional',
    'regra_contratual_tabelas', 'contratos_avisos', 'painel_completo',
    'habilitar_pessoas', 'conferencia_coordenacao'
  ));

-- ---------- 2. "Enviar contas" para quem ja enviava ----------
-- Copia do banco, e nao da carga da 116: vale o que a Habilitacao deixou.
-- Cada perfil ganha a linha nova com o mesmo `ligada` da antiga, entao toda
-- celula existe para a Habilitacao ligar ou desligar depois.
INSERT INTO cm_perfil_permissao (perfil, permissao, ligada)
SELECT perfil, 'enviar_contas', ligada
FROM cm_perfil_permissao
WHERE permissao = 'enviar_corrigir_contas'
ON CONFLICT (perfil, permissao) DO NOTHING;

-- ---------- 3. O perfil Apoio ao faturamento ----------
-- So "Enviar contas" ligada; as outras oito existem desligadas, para a
-- Habilitacao ter o que ligar.
INSERT INTO cm_perfil_permissao (perfil, permissao, ligada) VALUES
  ('apoio_faturamento', 'enviar_contas', true),
  ('apoio_faturamento', 'enviar_corrigir_contas', false),
  ('apoio_faturamento', 'decidir_validacao', false),
  ('apoio_faturamento', 'incluir_regra_operacional', false),
  ('apoio_faturamento', 'regra_contratual_tabelas', false),
  ('apoio_faturamento', 'contratos_avisos', false),
  ('apoio_faturamento', 'painel_completo', false),
  ('apoio_faturamento', 'habilitar_pessoas', false),
  ('apoio_faturamento', 'conferencia_coordenacao', false)
ON CONFLICT (perfil, permissao) DO NOTHING;

INSERT INTO migracoes_aplicadas (numero) VALUES (121) ON CONFLICT (numero) DO NOTHING;
