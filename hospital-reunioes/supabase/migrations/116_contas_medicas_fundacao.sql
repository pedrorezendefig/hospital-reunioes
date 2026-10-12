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

-- ---------- 3. Operadora, memoria, tabelas de preco, setores, dicionario ----------

-- A operadora com contrato proprio (ASSIM, Unimed, Leve...). A situacao segue
-- a spec (11.5): SEM_MEMORIA nao recebe conta; PARCIAL ja recebe.
CREATE TABLE IF NOT EXISTS cm_operadora (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sigla      TEXT NOT NULL UNIQUE CHECK (btrim(sigla) <> ''),
  nome       TEXT NOT NULL CHECK (btrim(nome) <> ''),
  situacao   TEXT NOT NULL DEFAULT 'SEM_MEMORIA' CHECK (situacao IN ('PRONTA', 'PARCIAL', 'SEM_MEMORIA')),
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O nome do plano como o MV imprime no campo `Plano:` da conta, ligado a
-- operadora e a coluna de preco (ADR 0070, decisao 4). Plano sem linha aqui
-- recusa a conta no envio.
CREATE TABLE IF NOT EXISTS cm_operadora_plano (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id  UUID NOT NULL REFERENCES cm_operadora(id) ON DELETE CASCADE,
  nome_mv       TEXT NOT NULL CHECK (btrim(nome_mv) <> ''),
  coluna_preco  TEXT,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_operadora_plano_nome_mv
  ON cm_operadora_plano ((lower(nome_mv)));

-- Uma versao da memoria da operadora (ADR 0070, decisao 3). O cabecalho YAML
-- vira `parametros_json` inteiro, inclusive o que o codigo ainda nao le.
CREATE TABLE IF NOT EXISTS cm_memoria_versao (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id     UUID NOT NULL REFERENCES cm_operadora(id) ON DELETE CASCADE,
  versao           TEXT NOT NULL CHECK (btrim(versao) <> ''),
  parametros_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
  texto_md         TEXT,
  vigente          BOOLEAN NOT NULL DEFAULT false,
  autor_id         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  resumo           TEXT
);

-- Uma versao vigente por operadora: importar marca a anterior como nao vigente.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_memoria_versao_vigente
  ON cm_memoria_versao (operadora_id) WHERE vigente;

-- Uma regra da memoria (`ASSIM-DIA-01`). Regra PENDENTE nunca gera ordem para
-- a faturista: gera a acao VALIDAR.
CREATE TABLE IF NOT EXISTS cm_regra (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id       UUID NOT NULL REFERENCES cm_operadora(id) ON DELETE CASCADE,
  memoria_versao_id  UUID REFERENCES cm_memoria_versao(id) ON DELETE CASCADE,
  codigo             TEXT NOT NULL CHECK (btrim(codigo) <> ''),
  secao              TEXT,
  texto              TEXT NOT NULL,
  tipo               TEXT CHECK (tipo IS NULL OR tipo IN ('CONTRATUAL', 'OPERACIONAL')),
  origem             TEXT,
  status             TEXT NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('VIGENTE', 'PENDENTE')),
  contrato_diz       TEXT,
  validado_por       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  validado_em        TIMESTAMPTZ,
  ativa              BOOLEAN NOT NULL DEFAULT true,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_regra_operadora_codigo
  ON cm_regra (operadora_id, codigo);

-- Uma tabela de preco e a versao dela, com vigencia por data. A busca recebe a
-- data do item e escolhe a versao vigente; sem versao para a data, o preco sai
-- "Nao conferido".
CREATE TABLE IF NOT EXISTS cm_tabela_preco (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome             TEXT NOT NULL CHECK (btrim(nome) <> ''),
  tipo             TEXT,
  versao           TEXT,
  vigencia_inicio  DATE,
  vigencia_fim     DATE,
  situacao         TEXT,
  arquivo_nome     TEXT,
  autor_id         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `precos_json`: `{comum, carioca}`, `{valor}` ou `{lpm}`, conforme a tabela.
CREATE TABLE IF NOT EXISTS cm_tabela_preco_item (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tabela_id           UUID NOT NULL REFERENCES cm_tabela_preco(id) ON DELETE CASCADE,
  codigo              TEXT NOT NULL,
  codigo_alternativo  TEXT,
  descricao           TEXT,
  grupo               TEXT,
  unidade             TEXT,
  precos_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
  extra_json          JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_cm_tabela_preco_item_tabela_codigo
  ON cm_tabela_preco_item (tabela_id, codigo);

-- Para onde a operadora aponta, por categoria. `regra_uso_json` guarda a regra
-- de preco (COLUNA, PMC, PF, PF_MAIS_PERCENTUAL, LPM), a chave de busca e o
-- deflator. HONORARIO existe desde ja e, sem tabela, sai "Nao conferido".
CREATE TABLE IF NOT EXISTS cm_operadora_tabela (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id    UUID NOT NULL REFERENCES cm_operadora(id) ON DELETE CASCADE,
  categoria       TEXT NOT NULL CHECK (categoria IN ('MEDICAMENTO', 'MATERIAL', 'DIARIA_TAXA', 'PACOTE', 'HONORARIO')),
  tabela_id       UUID NOT NULL REFERENCES cm_tabela_preco(id) ON DELETE CASCADE,
  regra_uso_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_operadora_tabela_operadora
  ON cm_operadora_tabela (operadora_id, categoria);

-- O setor como o MV imprime, ligado a acomodacao. Nao e o Setor dos POPs nem
-- o das Reunioes: sem FK entre eles.
CREATE TABLE IF NOT EXISTS cm_setor (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_mv      TEXT NOT NULL CHECK (btrim(nome_mv) <> ''),
  acomodacao   TEXT CHECK (acomodacao IS NULL OR acomodacao IN (
    'CTI', 'ENFERMARIA', 'APARTAMENTO', 'ISOLAMENTO', 'CENTRO_CIRURGICO',
    'HOSPITAL_DIA', 'PEDIATRIA', 'UTI_PEDIATRICA', 'UTI_NEONATAL'
  )),
  grupo_gases  TEXT,
  criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_setor_nome_mv
  ON cm_setor ((lower(nome_mv)));

-- O dicionario do hospital (nao da operadora): o nome do produto na
-- prescricao e na ficha anestesica ligado ao codigo da conta.
CREATE TABLE IF NOT EXISTS cm_item_dicionario (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  termo                 TEXT NOT NULL CHECK (btrim(termo) <> ''),
  codigo_conta          TEXT,
  descricao_conta       TEXT,
  unidade_cobranca      TEXT,
  conteudo_por_unidade  TEXT,
  origem                TEXT NOT NULL DEFAULT 'GESTAO' CHECK (origem IN ('IA', 'GESTAO')),
  situacao              TEXT NOT NULL DEFAULT 'PROPOSTO' CHECK (situacao IN ('PROPOSTO', 'CONFIRMADO')),
  autor_id              VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_item_dicionario_termo
  ON cm_item_dicionario ((lower(termo)));

-- ---------- 4. Envio, arquivo, atendimento e a leitura do prontuario ----------

-- Um envio da faturista: varios arquivos de uma vez.
CREATE TABLE IF NOT EXISTS cm_envio (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id   VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O atendimento (numero da internacao no MV): a identificacao de tudo no
-- modulo. Da paciente ficam so o rotulo ("Maria S.") e a idade em anos.
CREATE TABLE IF NOT EXISTS cm_atendimento (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  numero_atendimento     TEXT NOT NULL CHECK (btrim(numero_atendimento) <> ''),
  paciente_rotulo        TEXT,
  idade_anos             INTEGER CHECK (idade_anos IS NULL OR idade_anos BETWEEN 0 AND 150),
  operadora_id           UUID REFERENCES cm_operadora(id),
  plano                  TEXT,
  coluna_preco           TEXT,
  acomodacao_contratada  TEXT,
  criado_em              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cm_atendimento_numero
  ON cm_atendimento (numero_atendimento);

-- O PDF enviado (conta ou prontuario). O binario vive no bucket privado e sai
-- de la 7 dias depois do envio; a linha fica, com `apagado_em` preenchido.
CREATE TABLE IF NOT EXISTS cm_arquivo (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  envio_id            UUID NOT NULL REFERENCES cm_envio(id) ON DELETE CASCADE,
  tipo                TEXT NOT NULL CHECK (tipo IN ('CONTA', 'PRONTUARIO')),
  atendimento_id      UUID REFERENCES cm_atendimento(id),
  numero_atendimento  TEXT,
  paginas             INTEGER CHECK (paginas IS NULL OR paginas >= 0),
  chave_bucket        TEXT,
  hash                TEXT,
  apagar_em           TIMESTAMPTZ,
  apagado_em          TIMESTAMPTZ,
  criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_arquivo_apagar_em
  ON cm_arquivo (apagar_em) WHERE apagado_em IS NULL;

-- Os eventos estruturados do prontuario, ja desidentificados. Uma linha por
-- atendimento, que serve a todas as parciais e ao reenvio.
CREATE TABLE IF NOT EXISTS cm_eventos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  atendimento_id  UUID NOT NULL REFERENCES cm_atendimento(id) ON DELETE CASCADE,
  eventos_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
  prontuario_ate  DATE,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_eventos_atendimento
  ON cm_eventos (atendimento_id);

-- A prescricao lida do prontuario. Fica no atendimento, e nao na conta (o
-- adendo v1.3 sugeria a conta): o prontuario e lido uma vez por atendimento e
-- serve a todas as parciais.
CREATE TABLE IF NOT EXISTS cm_prescricao (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  atendimento_id  UUID NOT NULL REFERENCES cm_atendimento(id) ON DELETE CASCADE,
  data            DATE,
  hora            TIME,
  subtipo         TEXT,
  pagina          INTEGER
);

CREATE INDEX IF NOT EXISTS idx_cm_prescricao_atendimento
  ON cm_prescricao (atendimento_id, data);

CREATE TABLE IF NOT EXISTS cm_prescricao_item (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prescricao_id     UUID NOT NULL REFERENCES cm_prescricao(id) ON DELETE CASCADE,
  secao             TEXT,
  n                 INTEGER,
  nome              TEXT,
  generico          TEXT,
  colunas           JSONB,
  doses_por_dia     NUMERIC(10, 2),
  se_necessario     BOOLEAN NOT NULL DEFAULT false,
  suspenso          BOOLEAN NOT NULL DEFAULT false,
  obs               TEXT,
  componentes_json  JSONB,
  pedido            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cm_prescricao_item_prescricao
  ON cm_prescricao_item (prescricao_id);

-- A cirurgia: descricao cirurgica e ficha anestesica estruturadas.
CREATE TABLE IF NOT EXISTS cm_cirurgia (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  atendimento_id           UUID NOT NULL REFERENCES cm_atendimento(id) ON DELETE CASCADE,
  procedimentos_json       JSONB,
  inicio                   TIMESTAMPTZ,
  fim                      TIMESTAMPTZ,
  anestesia_inicio         TIMESTAMPTZ,
  anestesia_fim            TIMESTAMPTZ,
  tecnica                  TEXT,
  gases_json               JSONB,
  medicamentos_ficha_json  JSONB
);

CREATE INDEX IF NOT EXISTS idx_cm_cirurgia_atendimento
  ON cm_cirurgia (atendimento_id);

-- Quantas glicemias capilares o prontuario registra em cada dia.
CREATE TABLE IF NOT EXISTS cm_glicemia_dia (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  atendimento_id  UUID NOT NULL REFERENCES cm_atendimento(id) ON DELETE CASCADE,
  data            DATE NOT NULL,
  quantidade      INTEGER NOT NULL CHECK (quantidade >= 0),
  UNIQUE (atendimento_id, data)
);

-- ---------- 5. A conta, os itens, o Guia e as observacoes ----------

-- Uma conta (ou parcial) de um atendimento, e uma linha da fila. A fila vive
-- aqui (ADR 0070, decisao 5): NA_FILA, claim atomico para PROCESSANDO com
-- `processando_desde`, e `tentativas` ate tres antes de ERRO. As colunas de
-- tokens e custo ficam vazias ate a IA chegar (PRD 2).
CREATE TABLE IF NOT EXISTS cm_conta (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  atendimento_id      UUID NOT NULL REFERENCES cm_atendimento(id),
  arquivo_id          UUID REFERENCES cm_arquivo(id),
  numero_conta        TEXT,
  parcial_ordem       INTEGER,
  periodo_inicio      DATE,
  periodo_fim         DATE,
  total_lancado       NUMERIC(14, 2),
  situacao            TEXT NOT NULL DEFAULT 'AGUARDANDO_ARQUIVO' CHECK (situacao IN (
    'AGUARDANDO_ARQUIVO', 'NA_FILA', 'PROCESSANDO', 'A_FAZER', 'EM_CORRECAO',
    'CONCLUIDA', 'CONCLUIDA_COM_PENDENCIA', 'RETORNO', 'ERRO'
  )),
  erro_motivo         TEXT,
  processando_desde   TIMESTAMPTZ,
  tentativas          INTEGER NOT NULL DEFAULT 0,
  parecer_parcial     BOOLEAN NOT NULL DEFAULT false,
  faltantes           JSONB,
  nota_bruta          NUMERIC(6, 2),
  nota_entrada        NUMERIC(6, 2),
  valor_apontado      NUMERIC(14, 2),
  valor_em_validacao  NUMERIC(14, 2),
  faturista_id        VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ordem_fila          BIGINT,
  enviada_em          TIMESTAMPTZ,
  pronta_em           TIMESTAMPTZ,
  aberta_em           TIMESTAMPTZ,
  concluida_em        TIMESTAMPTZ,
  memoria_versao_id   UUID REFERENCES cm_memoria_versao(id),
  modelo_ia           TEXT,
  tokens_entrada      INTEGER,
  tokens_saida        INTEGER,
  tokens_cache        INTEGER,
  custo_usd           NUMERIC(10, 4),
  criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_conta_faturista_situacao_ordem
  ON cm_conta (faturista_id, situacao, ordem_fila);

CREATE INDEX IF NOT EXISTS idx_cm_conta_atendimento
  ON cm_conta (atendimento_id);

-- Um item lido da conta do MV.
CREATE TABLE IF NOT EXISTS cm_conta_item (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id            UUID NOT NULL REFERENCES cm_conta(id) ON DELETE CASCADE,
  ordem               INTEGER,
  data                DATE,
  grupo_conta         TEXT,
  setor               TEXT,
  grupo_procedimento  TEXT,
  codigo              TEXT,
  descricao           TEXT,
  quantidade          NUMERIC(14, 4),
  unidade             TEXT,
  valor_unitario      NUMERIC(14, 4),
  valor_total         NUMERIC(14, 2),
  percentual          NUMERIC(7, 2),
  preco_tabela        NUMERIC(14, 4),
  situacao_preco      TEXT CHECK (situacao_preco IS NULL OR situacao_preco IN ('CONFERIDO', 'DIVERGENTE', 'NAO_CONFERIDO'))
);

CREATE INDEX IF NOT EXISTS idx_cm_conta_item_conta
  ON cm_conta_item (conta_id);

-- Uma linha do Guia: uma acao sobre um item da conta, com regra, evidencia,
-- nivel, causa-raiz e confianca. Reprocessar substitui as ABERTAS e preserva
-- as marcadas.
CREATE TABLE IF NOT EXISTS cm_guia_linha (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id            UUID NOT NULL REFERENCES cm_conta(id) ON DELETE CASCADE,
  ordem               INTEGER,
  acao                TEXT NOT NULL CHECK (acao IN ('INCLUIR', 'AJUSTAR_QUANTIDADE', 'RETIRAR', 'CORRIGIR_PRECO', 'VALIDAR')),
  data                DATE,
  data_fim            DATE,
  setor               TEXT,
  codigo              TEXT,
  descricao           TEXT,
  quantidade_lancada  NUMERIC(14, 4),
  quantidade_devida   NUMERIC(14, 4),
  preco_lancado       NUMERIC(14, 4),
  preco_tabela        NUMERIC(14, 4),
  valor_diferenca     NUMERIC(14, 2),
  regra_codigo        TEXT,
  motivo              TEXT,
  evidencia_pagina    INTEGER,
  evidencia_trecho    TEXT CHECK (evidencia_trecho IS NULL OR char_length(evidencia_trecho) <= 300),
  nivel_evidencia     TEXT CHECK (nivel_evidencia IS NULL OR nivel_evidencia IN ('REGISTRADO', 'PRESCRITO', 'PRESCRITO_SN', 'POR_REGRA')),
  causa_raiz          TEXT CHECK (causa_raiz IS NULL OR causa_raiz IN (
    'DISPENSACAO', 'REGRA_AUTOMATICA', 'CADASTRO_PRECO', 'REGISTRO_ASSISTENCIAL', 'LANCAMENTO_MANUAL'
  )),
  confianca           TEXT CHECK (confianca IS NULL OR confianca IN ('ALTA', 'MEDIA', 'BAIXA')),
  origem              TEXT NOT NULL DEFAULT 'CODIGO' CHECK (origem IN ('CODIGO', 'IA')),
  estado              TEXT NOT NULL DEFAULT 'ABERTA' CHECK (estado IN (
    'ABERTA', 'FEITO', 'NAO_PROCEDE', 'BLOQUEADO', 'EM_VALIDACAO', 'DECIDIDA'
  )),
  motivo_nao_procede  TEXT CHECK (motivo_nao_procede IS NULL OR motivo_nao_procede IN (
    'JA_ESTA_NA_CONTA', 'SEM_EVIDENCIA', 'REGRA_E_OUTRA', 'OUTRO'
  )),
  texto_nao_procede   TEXT,
  marcado_por         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  marcado_em          TIMESTAMPTZ,
  criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_guia_linha_conta
  ON cm_guia_linha (conta_id);

-- Observacao do time sobre uma conta: faturista e coordenadora nunca alteram
-- regra, mandam observacao, que cai na Validacao.
CREATE TABLE IF NOT EXISTS cm_observacao (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id   UUID NOT NULL REFERENCES cm_conta(id) ON DELETE CASCADE,
  autor_id   VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  texto      TEXT NOT NULL CHECK (btrim(texto) <> ''),
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_observacao_conta
  ON cm_observacao (conta_id);

-- RLS default-deny em todas: nenhuma policy de proposito.
ALTER TABLE cm_operadora ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_operadora_plano ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_memoria_versao ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_regra ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_tabela_preco ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_tabela_preco_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_operadora_tabela ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_setor ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_item_dicionario ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_envio ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_atendimento ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_arquivo ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_prescricao ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_prescricao_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_cirurgia ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_glicemia_dia ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_conta ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_conta_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_guia_linha ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_observacao ENABLE ROW LEVEL SECURITY;

-- ---------- 6. O sino ----------
-- O aviso de conta pronta (PRD #1113, Notificacao): tipo CONTAS_MEDICAS, com a
-- conta como referencia (`referencia_id` e TEXT desde a 060). O CHECK e
-- refeito inteiro, com os seis tipos que ja existem.
ALTER TABLE notificacoes DROP CONSTRAINT IF EXISTS notificacoes_tipo_check;
ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_tipo_check
  CHECK (tipo IN (
    'MENCAO',
    'STATUS_ALTERADO',
    'COMENTARIO',
    'PRAZO_PROXIMO',
    'RESPONSAVEL_ATRIBUIDO',
    'ACEITE_INTERNO',
    'CONTAS_MEDICAS'
  ));

-- ---------- 7. O bucket privado ----------
-- Molde do `anexos-ouvidoria` (066) e do `anexos-tecnologia` (115): sem
-- policy de leitura para `authenticated`. Prontuario e dado pessoal sensivel;
-- o unico caminho ate o arquivo e o backend com a service_role.
--
-- Teto de 100 MiB por arquivo (104857600 bytes), o limite por arquivo do PRD.
-- O DO UPDATE garante o teto e o fechamento mesmo se o bucket tiver nascido a
-- mao no Studio.
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('contas-medicas', 'contas-medicas', false, 104857600)
ON CONFLICT (id) DO UPDATE SET public = false, file_size_limit = 104857600;

DROP POLICY IF EXISTS "Authenticated Access contas-medicas" ON storage.objects;

-- ---------- 8. O Produto na aba Tecnologia ----------
-- Molde da 111: o modulo ganha Produto proprio, com texto no Kit de
-- conhecimento do Assistente de Tecnologia. ON CONFLICT cai no indice unico
-- de nome sem distinguir maiusculas. Sem dono: a tela cobra um.
INSERT INTO tecnologia_produtos (nome, ordem) VALUES
  ('Contas médicas', (SELECT COALESCE(MAX(ordem), 0) + 1 FROM tecnologia_produtos))
ON CONFLICT DO NOTHING;

INSERT INTO migracoes_aplicadas (numero) VALUES (116) ON CONFLICT (numero) DO NOTHING;
