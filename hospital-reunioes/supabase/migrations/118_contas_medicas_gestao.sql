-- =====================================================
-- Migration 118: Contas medicas, as telas de gestao (issue #1139, PRD #1129, ADR 0070)
-- =====================================================
-- A unica migration do PRD 3 de Contas medicas: todas as tabelas das telas de
-- gestao nascem aqui, para as fatias seguintes andarem em paralelo sem pedir
-- outra parada no Studio.
--
-- O que entra:
--   1. o registro de quem mudou o que (Habilitacao e regra);
--   2. o historico da regra e o `modelo_id` dela (Memoria por tela);
--   3. os temas da Validacao e as linhas de cada tema;
--   4. os cenarios e os lembretes da Conferencia da coordenacao;
--   5. o contrato da operadora e o aviso de reajuste;
--   6. o mapeamento e o arquivo original da tabela de preco lida por IA.
--
-- A situacao RETORNO da conta e o estado DECIDIDA da linha do Guia ja estao
-- nos CHECKs desde a 116.
--
-- Dado de paciente: nenhum (ADR 0070, decisao 8). O lembrete guarda pagina e
-- trecho do prontuario, como a linha do Guia, com o mesmo teto de 300.
--
-- RLS default-deny em toda tabela, sem policy de proposito: quem le e escreve
-- e o backend com a service_role (padrao da casa, como na 116).
--
-- Tudo com IF NOT EXISTS: rodar duas vezes tem que ser inofensivo. Aplicar a
-- mao no Studio, depois da 117: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. O registro ----------
-- Uma linha por mudanca na Habilitacao (matriz e perfil da pessoa) e na
-- memoria: quem, quando, em que e como estava antes e depois.
CREATE TABLE IF NOT EXISTS cm_registro (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  autor_id     VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  data         TIMESTAMPTZ NOT NULL DEFAULT now(),
  entidade     TEXT NOT NULL CHECK (btrim(entidade) <> ''),
  entidade_id  TEXT NOT NULL CHECK (btrim(entidade_id) <> ''),
  antes_json   JSONB,
  depois_json  JSONB
);

CREATE INDEX IF NOT EXISTS idx_cm_registro_entidade
  ON cm_registro (entidade, entidade_id, data DESC);

-- ---------- 2. O historico da regra ----------
-- Editar ou decidir uma regra pela tela cria versao nova da memoria e guarda
-- aqui o texto de antes.
CREATE TABLE IF NOT EXISTS cm_regra_historico (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  regra_id           UUID NOT NULL REFERENCES cm_regra(id) ON DELETE CASCADE,
  memoria_versao_id  UUID REFERENCES cm_memoria_versao(id) ON DELETE SET NULL,
  texto_anterior     TEXT,
  texto_novo         TEXT NOT NULL,
  autor_id           VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_regra_historico_regra
  ON cm_regra_historico (regra_id, criado_em DESC);

-- A regra do Modelo HSM de origem (spec v1.0, tabela de dados; adendo v1.1).
-- E por ela que "aplicar a todas as operadoras" acha as regras irmas. A 116
-- nao trouxe a coluna.
ALTER TABLE cm_regra
  ADD COLUMN IF NOT EXISTS modelo_id TEXT;

CREATE INDEX IF NOT EXISTS idx_cm_regra_modelo
  ON cm_regra (modelo_id) WHERE modelo_id IS NOT NULL;

-- ---------- 3. A Validacao ----------
-- Um tema por regra pendente e operadora, por codigo bloqueado, por regra
-- citada em observacao e por termo proposto ao dicionario. A leitura da IA
-- sobre a observacao fica no tema (uma chamada por observacao); a resposta ao
-- time e o texto que a faturista ve no Guia.
CREATE TABLE IF NOT EXISTS cm_validacao_tema (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id        UUID REFERENCES cm_operadora(id) ON DELETE CASCADE,
  tipo                TEXT NOT NULL CHECK (tipo IN ('REGRA_PENDENTE', 'BLOQUEADO', 'OBSERVACAO', 'DICIONARIO')),
  regra_codigo        TEXT,
  codigo_item         TEXT,
  item_dicionario_id  UUID REFERENCES cm_item_dicionario(id) ON DELETE CASCADE,
  titulo              TEXT NOT NULL CHECK (btrim(titulo) <> ''),
  estado              TEXT NOT NULL DEFAULT 'ABERTO' CHECK (estado IN ('ABERTO', 'DECIDIDO')),
  decisao             TEXT,
  resposta            TEXT,
  leitura_ia          TEXT,
  decidido_por        VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  decidido_em         TIMESTAMPTZ,
  criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_validacao_tema_estado
  ON cm_validacao_tema (estado, tipo);

-- O que cada tema junta: as linhas do Guia (Validar, Bloqueado, Nao procede)
-- ou a observacao do time.
CREATE TABLE IF NOT EXISTS cm_validacao_tema_linha (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tema_id        UUID NOT NULL REFERENCES cm_validacao_tema(id) ON DELETE CASCADE,
  guia_linha_id  UUID REFERENCES cm_guia_linha(id) ON DELETE CASCADE,
  observacao_id  UUID REFERENCES cm_observacao(id) ON DELETE CASCADE,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (guia_linha_id IS NOT NULL OR observacao_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_cm_validacao_tema_linha_tema
  ON cm_validacao_tema_linha (tema_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_validacao_tema_linha_guia
  ON cm_validacao_tema_linha (tema_id, guia_linha_id) WHERE guia_linha_id IS NOT NULL;

-- ---------- 4. A Conferencia da coordenacao ----------
-- O cenario (adendo v1.1): codigo CEN-NNN, operadora ou todas (nulo), gatilho
-- em texto livre e os insumos que ele pede. Nunca entra no Passo B nem no Guia.
CREATE TABLE IF NOT EXISTS cm_cenario (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  codigo         TEXT NOT NULL UNIQUE CHECK (btrim(codigo) <> ''),
  nome           TEXT NOT NULL CHECK (btrim(nome) <> ''),
  operadora_id   UUID REFERENCES cm_operadora(id) ON DELETE CASCADE,
  gatilho_texto  TEXT NOT NULL CHECK (btrim(gatilho_texto) <> ''),
  orientacao     TEXT,
  ativo          BOOLEAN NOT NULL DEFAULT true,
  autor_id       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cm_cenario_item (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cenario_id  UUID NOT NULL REFERENCES cm_cenario(id) ON DELETE CASCADE,
  codigo      TEXT NOT NULL CHECK (btrim(codigo) <> ''),
  descricao   TEXT,
  quantidade  NUMERIC(14, 4) NOT NULL DEFAULT 1 CHECK (quantidade > 0)
);

CREATE INDEX IF NOT EXISTS idx_cm_cenario_item_cenario
  ON cm_cenario_item (cenario_id);

-- O lembrete do Passo C: a ocorrencia do cenario na conta com os insumos que
-- faltam. Some para quem nao tem "conferencia da coordenacao".
CREATE TABLE IF NOT EXISTS cm_lembrete (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id          UUID NOT NULL REFERENCES cm_conta(id) ON DELETE CASCADE,
  cenario_id        UUID NOT NULL REFERENCES cm_cenario(id),
  data              DATE,
  setor             TEXT,
  evidencia_pagina  INTEGER,
  evidencia_trecho  TEXT CHECK (evidencia_trecho IS NULL OR char_length(evidencia_trecho) <= 300),
  estado            TEXT NOT NULL DEFAULT 'ABERTO' CHECK (estado IN ('ABERTO', 'INCLUIDO', 'NAO_SE_APLICA')),
  observacao        TEXT,
  marcado_por       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  marcado_em        TIMESTAMPTZ,
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_lembrete_conta
  ON cm_lembrete (conta_id);

CREATE INDEX IF NOT EXISTS idx_cm_lembrete_estado
  ON cm_lembrete (estado, criado_em);

CREATE TABLE IF NOT EXISTS cm_lembrete_item (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lembrete_id   UUID NOT NULL REFERENCES cm_lembrete(id) ON DELETE CASCADE,
  codigo        TEXT NOT NULL CHECK (btrim(codigo) <> ''),
  descricao     TEXT,
  quantidade    NUMERIC(14, 4),
  preco_tabela  NUMERIC(14, 4),
  valor         NUMERIC(14, 2)
);

CREATE INDEX IF NOT EXISTS idx_cm_lembrete_item_lembrete
  ON cm_lembrete_item (lembrete_id);

-- ---------- 5. O contrato e o aviso de reajuste ----------
-- Um contrato por operadora, da memoria (`parametros_json.contrato`) ou do
-- envio confirmado pela pessoa. `vencimento_calculado`: veio de vigencia + 1
-- ano. `vencimento_e_negociacao`: a memoria diz que a data abre o debate do
-- reajuste e nao e vencimento. `arquivo`: a chave no bucket `contas-medicas`.
CREATE TABLE IF NOT EXISTS cm_contrato (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id             UUID NOT NULL UNIQUE REFERENCES cm_operadora(id) ON DELETE CASCADE,
  data_assinatura          DATE,
  aditivo_numero           TEXT,
  aditivo_data             DATE,
  vigencia_inicio          DATE,
  vencimento               DATE,
  vencimento_calculado     BOOLEAN NOT NULL DEFAULT false,
  vencimento_e_negociacao  BOOLEAN NOT NULL DEFAULT false,
  aviso_dias               INTEGER CHECK (aviso_dias IS NULL OR aviso_dias >= 0),
  arquivo                  TEXT,
  confirmado_por           VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  confirmado_em            TIMESTAMPTZ,
  criado_em                TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O aviso unico na data (vencimento menos antecedencia): o UNIQUE impede a
-- rotina diaria de avisar duas vezes a mesma data.
CREATE TABLE IF NOT EXISTS cm_aviso (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contrato_id    UUID NOT NULL REFERENCES cm_contrato(id) ON DELETE CASCADE,
  data_prevista  DATE NOT NULL,
  enviado_em     TIMESTAMPTZ,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (contrato_id, data_prevista)
);

-- ---------- 6. A tabela de preco lida por mapeamento ----------
-- O mapeamento de colunas confirmado pela pessoa (para reaproveitar sem IA no
-- arquivo de mesmo cabecalho) e a chave do arquivo enviado.
ALTER TABLE cm_tabela_preco
  ADD COLUMN IF NOT EXISTS mapeamento_json JSONB;

ALTER TABLE cm_tabela_preco
  ADD COLUMN IF NOT EXISTS arquivo_original TEXT;

-- RLS default-deny em todas: nenhuma policy de proposito.
ALTER TABLE cm_registro ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_regra_historico ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_validacao_tema ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_validacao_tema_linha ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_cenario ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_cenario_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_lembrete ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_lembrete_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_contrato ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_aviso ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (118) ON CONFLICT (numero) DO NOTHING;
