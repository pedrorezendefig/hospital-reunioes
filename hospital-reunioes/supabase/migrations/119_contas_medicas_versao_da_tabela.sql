-- =====================================================
-- Migration 119: Contas medicas, a versao da tabela de preco que a linha usou
-- (issue #1206, PRD #1129, ADR 0070)
-- =====================================================
-- A linha do Guia passa a gravar de qual tabela (de qual versao) saiu o
-- `preco_tabela`. Fica na linha, e nao na conta: uma conta usa varias tabelas
-- ao mesmo tempo (materiais, medicamentos, diarias e taxas, pacotes), cada uma
-- com a sua versao.
--
-- NULL quando o preco nao veio de tabela: o preco validado na memoria da
-- operadora, o preco lancado na conta, nenhum preco. As linhas gravadas antes
-- desta migration ficam NULL (sem backfill): a versao ainda se reconstroi pela
-- data de vigencia.
--
-- "Nova versao" de uma tabela cria outra linha em `cm_tabela_preco` e nao toca
-- nenhuma linha do Guia ja gravada. Apagar a tabela solta a referencia
-- (ON DELETE SET NULL) sem apagar a linha da conta.
--
-- Sem tabela nova, sem policy nova: `cm_guia_linha` ja tem RLS default-deny
-- desde a 116 (quem le e escreve e o backend com a service_role).
--
-- Tudo com IF NOT EXISTS: rodar duas vezes tem que ser inofensivo. Aplicar a
-- mao no Studio, depois da 118: o deploy nao aplica SQL.
-- =====================================================

ALTER TABLE cm_guia_linha
  ADD COLUMN IF NOT EXISTS tabela_id UUID REFERENCES cm_tabela_preco(id) ON DELETE SET NULL;

COMMENT ON COLUMN cm_guia_linha.tabela_id IS
  'Versao da tabela de preco de onde saiu o preco_tabela; NULL quando o preco nao veio de tabela (issue #1206).';

-- Indice da FK: o ON DELETE SET NULL procura as linhas pela tabela. Parcial,
-- porque a maioria das linhas nao tem preco de tabela.
CREATE INDEX IF NOT EXISTS idx_cm_guia_linha_tabela
  ON cm_guia_linha (tabela_id)
  WHERE tabela_id IS NOT NULL;

INSERT INTO migracoes_aplicadas (numero) VALUES (119) ON CONFLICT (numero) DO NOTHING;
