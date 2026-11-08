-- =====================================================
-- Migration 126: Contas medicas, o schema do Auditor
-- (issue #1486, PRD #1484, ADR 0081)
-- =====================================================
-- A unica migration do PRD #1484. O que o Auditor, a Prova da regra, o
-- Faltou isto e a Validacao decidida precisam no banco nasce aqui, para as
-- fatias do PRD andarem sem pedir outra parada no Studio.
--
-- O que entra:
--   1. `cm_conversa` e `cm_conversa_mensagem`: a conversa com o Auditor, da
--      Operadora ou da Conta, e as mensagens dela. A mensagem que gerou uma
--      versao da Memoria aponta para ela. A conversa nao e memoria: nada
--      daqui entra no prompt do Passo A nem do Passo B (ADR 0081, decisao 3);
--   2. `cm_lote` e `cm_lote_item`: o lote de propostas do Auditor, ja
--      decididas, e cada item numerado (o N do "corrige o item N"). O lote
--      aplicado aponta para a versao da Memoria que gerou (uma por lote);
--   3. `cm_prova`: a Prova da regra, o que o Guia teria dito de diferente nas
--      ultimas Contas concluidas da Operadora, ligada ao item do lote;
--   4. `cm_faltou_isto`: o apontamento de omissao no Guia (Conta, dia, item,
--      pagina, texto, origem PESSOA ou AGENTE), a classificacao do Auditor
--      (REGRA, LEITURA ou DEFEITO) e o resultado (o item do lote com a
--      proposta de Regra, ou o numero da issue);
--   5. a recomendacao do Auditor em `cm_validacao_tema`: decisao, motivo e a
--      Prova, quando o Tema e de Regra;
--   6. os passos CONVERSA, PROVA e REVISOR no CHECK de `cm_chamada_ia.passo`,
--      para o custo das conversas, das provas e do segundo agente entrar na
--      semana do Painel.
--
-- So acrescenta: tabelas novas, colunas nulas e um CHECK mais largo. O
-- backend de antes segue funcionando entre a aplicacao e a subida.
--
-- RLS default-deny nas tabelas novas (padrao da casa): quem le e escreve e o
-- backend com a service_role. Nenhuma policy de proposito.
--
-- Tudo com IF NOT EXISTS / DROP antes de ADD / ON CONFLICT: rodar duas vezes
-- e inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. A conversa com o Auditor ----------
-- Duas conversas, cada uma com o seu contexto (ADR 0081, decisao 2): a da
-- Operadora (ensinar Regra, subir tabela e contrato, revisar pendentes) e a
-- da Conta, aberta do Guia. A da Conta guarda tambem a Operadora quando a
-- conta tem uma, para a tela filtrar sem passar pelo atendimento.
CREATE TABLE IF NOT EXISTS cm_conversa (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contexto      TEXT NOT NULL CHECK (contexto IN ('OPERADORA', 'CONTA')),
  operadora_id  UUID REFERENCES cm_operadora(id) ON DELETE CASCADE,
  conta_id      UUID REFERENCES cm_conta(id) ON DELETE CASCADE,
  criado_por    VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (contexto = 'OPERADORA' AND operadora_id IS NOT NULL AND conta_id IS NULL)
    OR (contexto = 'CONTA' AND conta_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_cm_conversa_operadora
  ON cm_conversa (operadora_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_cm_conversa_conta
  ON cm_conversa (conta_id);

COMMENT ON TABLE cm_conversa IS
  'Conversa com o Auditor de Contas medicas (ADR 0081): da Operadora (ensinar) ou da Conta (explicar um erro, aberta do Guia). Historico, nunca memoria: nao entra no prompt do Passo A nem do Passo B.';

-- Uma mensagem da conversa. PESSOA e quem escreveu (autor_id); AUDITOR e o
-- agente. A mensagem cujo lote foi aplicado aponta para a versao da Memoria
-- que ele gerou: e assim que se sabe depois quem ensinou cada Regra e por que.
CREATE TABLE IF NOT EXISTS cm_conversa_mensagem (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversa_id        UUID NOT NULL REFERENCES cm_conversa(id) ON DELETE CASCADE,
  autor              TEXT NOT NULL CHECK (autor IN ('PESSOA', 'AUDITOR')),
  autor_id           VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  texto              TEXT NOT NULL,
  anexo_nome         TEXT,
  memoria_versao_id  UUID REFERENCES cm_memoria_versao(id) ON DELETE SET NULL,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_conversa_mensagem_conversa
  ON cm_conversa_mensagem (conversa_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_cm_conversa_mensagem_versao
  ON cm_conversa_mensagem (memoria_versao_id) WHERE memoria_versao_id IS NOT NULL;

COMMENT ON TABLE cm_conversa_mensagem IS
  'Mensagem da conversa com o Auditor (ADR 0081). memoria_versao_id = a versao da Memoria que o lote desta mensagem gerou.';
COMMENT ON COLUMN cm_conversa_mensagem.anexo_nome IS
  'Nome do arquivo enviado com a mensagem (tabela, contrato). O arquivo em si nao fica aqui.';

-- ---------- 2. O lote de propostas ----------
-- O Auditor entrega as propostas em lote, ja decididas (decisao 1): quem
-- decide responde "ok" ou "corrige o item N". Aplicar gera UMA versao nova da
-- Memoria por lote. A fonte diz de onde o lote saiu: texto, tabela ou
-- contrato da conversa da Operadora, um Faltou isto, a fila de Validacao ou a
-- revisao das Regras pendentes.
CREATE TABLE IF NOT EXISTS cm_lote (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id       UUID REFERENCES cm_operadora(id) ON DELETE CASCADE,
  conversa_id        UUID REFERENCES cm_conversa(id) ON DELETE SET NULL,
  mensagem_id        UUID REFERENCES cm_conversa_mensagem(id) ON DELETE SET NULL,
  fonte              TEXT NOT NULL CHECK (fonte IN ('TEXTO', 'TABELA', 'CONTRATO', 'FALTOU_ISTO', 'VALIDACAO', 'PENDENTES')),
  estado             TEXT NOT NULL DEFAULT 'PROPOSTO' CHECK (estado IN ('PROPOSTO', 'APLICADO', 'DESCARTADO')),
  memoria_versao_id  UUID REFERENCES cm_memoria_versao(id) ON DELETE SET NULL,
  criado_por         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now(),
  aplicado_por       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  aplicado_em        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cm_lote_operadora
  ON cm_lote (operadora_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_cm_lote_conversa
  ON cm_lote (conversa_id);

COMMENT ON TABLE cm_lote IS
  'Lote de propostas do Auditor (ADR 0081, decisao 1). Nada vale sem o ok; aplicado, gera uma versao da Memoria (memoria_versao_id).';

-- Um item do lote, numerado a partir de 1. `proposta_json` traz o que o item
-- muda (a Regra no formato da Memoria, o parametro, a tabela ou o card), e
-- `conflitos_json` as Regras existentes com que ele conflita (decisao 8).
CREATE TABLE IF NOT EXISTS cm_lote_item (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lote_id         UUID NOT NULL REFERENCES cm_lote(id) ON DELETE CASCADE,
  numero          INTEGER NOT NULL CHECK (numero >= 1),
  tipo            TEXT NOT NULL CHECK (tipo IN ('REGRA_NOVA', 'REGRA_ALTERADA', 'TABELA', 'PARAMETRO', 'CARD_TECNOLOGIA')),
  regra_codigo    TEXT,
  proposta_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
  motivo          TEXT,
  conflitos_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
  estado          TEXT NOT NULL DEFAULT 'PROPOSTO' CHECK (estado IN ('PROPOSTO', 'APLICADO', 'DESCARTADO')),
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (lote_id, numero)
);

COMMENT ON TABLE cm_lote_item IS
  'Item do lote do Auditor, numerado no lote (o N do "corrige o item N").';

-- ---------- 3. A Prova da regra ----------
-- A Regra candidata refaz o Passo B nas ultimas Contas concluidas da
-- Operadora, a partir dos eventos guardados, sem mexer nelas (decisao 7).
-- `resultado_json` traz, por Conta, as Linhas que entrariam, sairiam ou
-- mudariam, com a Linha Feito que sumiria marcada; `mudaria = false` e o
-- "nao mudaria nada". `memoria_versao_id` e a versao vigente comparada.
CREATE TABLE IF NOT EXISTS cm_prova (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operadora_id       UUID NOT NULL REFERENCES cm_operadora(id) ON DELETE CASCADE,
  memoria_versao_id  UUID REFERENCES cm_memoria_versao(id) ON DELETE SET NULL,
  lote_item_id       UUID REFERENCES cm_lote_item(id) ON DELETE SET NULL,
  regra_codigo       TEXT,
  regra_texto        TEXT,
  contas             INTEGER NOT NULL DEFAULT 0 CHECK (contas >= 0),
  mudaria            BOOLEAN NOT NULL DEFAULT false,
  resultado_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
  criado_por         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_prova_operadora
  ON cm_prova (operadora_id, criado_em);

CREATE INDEX IF NOT EXISTS idx_cm_prova_lote_item
  ON cm_prova (lote_item_id) WHERE lote_item_id IS NOT NULL;

COMMENT ON TABLE cm_prova IS
  'Prova da regra (ADR 0081, decisao 7): o diff de Linhas por Conta nas ultimas Contas concluidas da Operadora. Nada e gravado nas Contas.';
COMMENT ON COLUMN cm_prova.contas IS
  'Quantas Contas concluidas a prova refez.';

-- ---------- 4. O Faltou isto ----------
-- Quem ve o Guia aponta, por dia, o item e a pagina que o modulo nao achou
-- (decisao 4). PESSOA traz `apontado_por`; AGENTE e o segundo agente
-- (decisao 14). O Auditor classifica e explica; REGRA vira item de lote,
-- LEITURA e DEFEITO viram issue no GitHub (o numero fica aqui). O texto e a
-- mensagem de quem apontou: o trecho do prontuario nunca entra aqui inteiro.
CREATE TABLE IF NOT EXISTS cm_faltou_isto (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id         UUID NOT NULL REFERENCES cm_conta(id) ON DELETE CASCADE,
  data             DATE NOT NULL,
  item             TEXT NOT NULL CHECK (btrim(item) <> ''),
  pagina           INTEGER CHECK (pagina IS NULL OR pagina >= 1),
  texto            TEXT,
  origem           TEXT NOT NULL CHECK (origem IN ('PESSOA', 'AGENTE')),
  apontado_por     VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  conversa_id      UUID REFERENCES cm_conversa(id) ON DELETE SET NULL,
  classificacao    TEXT CHECK (classificacao IS NULL OR classificacao IN ('REGRA', 'LEITURA', 'DEFEITO')),
  explicacao       TEXT,
  classificado_em  TIMESTAMPTZ,
  lote_item_id     UUID REFERENCES cm_lote_item(id) ON DELETE SET NULL,
  issue_numero     INTEGER CHECK (issue_numero IS NULL OR issue_numero >= 1),
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_faltou_isto_conta
  ON cm_faltou_isto (conta_id, data);

-- O Painel conta o Faltou isto por semana, por classificacao e por origem.
CREATE INDEX IF NOT EXISTS idx_cm_faltou_isto_criado_em
  ON cm_faltou_isto (criado_em);

CREATE INDEX IF NOT EXISTS idx_cm_faltou_isto_conversa
  ON cm_faltou_isto (conversa_id) WHERE conversa_id IS NOT NULL;

COMMENT ON TABLE cm_faltou_isto IS
  'Apontamento de omissao no Guia (ADR 0081, decisao 4): o item e a pagina que o modulo nao achou num dia da Conta, a classificacao do Auditor e o resultado (item de lote ou numero da issue).';
COMMENT ON COLUMN cm_faltou_isto.origem IS
  'PESSOA = alguem que ve o Guia apontou (apontado_por); AGENTE = o segundo agente, na releitura semanal.';
COMMENT ON COLUMN cm_faltou_isto.classificacao IS
  'Nula ate o Auditor classificar. REGRA = falta Regra; LEITURA = pagina nao lida, OCR ou folha digitalizada; DEFEITO = do codigo.';

-- ---------- 5. A recomendacao do Auditor no Tema de validacao ----------
-- A fila chega decidida (decisao 13): cada Tema traz a decisao que o Auditor
-- recomenda (o mesmo vocabulario de `decisao`), o motivo e a Prova quando o
-- Tema e de Regra. A decisao de quem aprova continua em `decisao`.
ALTER TABLE cm_validacao_tema
  ADD COLUMN IF NOT EXISTS recomendacao TEXT;
ALTER TABLE cm_validacao_tema
  ADD COLUMN IF NOT EXISTS recomendacao_motivo TEXT;
ALTER TABLE cm_validacao_tema
  ADD COLUMN IF NOT EXISTS recomendacao_prova_id UUID REFERENCES cm_prova(id) ON DELETE SET NULL;
ALTER TABLE cm_validacao_tema
  ADD COLUMN IF NOT EXISTS recomendado_em TIMESTAMPTZ;

COMMENT ON COLUMN cm_validacao_tema.recomendacao IS
  'A decisao que o Auditor recomenda para o Tema (ADR 0081, decisao 13). Nula = sem recomendacao ainda.';
COMMENT ON COLUMN cm_validacao_tema.recomendacao_prova_id IS
  'A Prova da regra que sustenta a recomendacao, quando o Tema e de Regra.';

-- ---------- 6. Os passos novos da chamada de IA ----------
-- CONVERSA = o Auditor nas duas conversas; PROVA = o Passo B refeito na
-- Prova da regra; REVISOR = o segundo agente (decisao 14). O CHECK e refeito
-- com os valores de antes, para o banco ter exatamente o que esta escrito.
ALTER TABLE cm_chamada_ia DROP CONSTRAINT IF EXISTS cm_chamada_ia_passo_check;
ALTER TABLE cm_chamada_ia
  ADD CONSTRAINT cm_chamada_ia_passo_check
  CHECK (passo IN ('A', 'B', 'DICIONARIO', 'OBSERVACAO', 'CONVERSA', 'PROVA', 'REVISOR'));

COMMENT ON COLUMN cm_chamada_ia.passo IS
  'A = eventos do prontuario; B = comparacao com a memoria; DICIONARIO e OBSERVACAO = a chamada curta; CONVERSA = o Auditor; PROVA = a Prova da regra; REVISOR = o segundo agente.';

-- RLS default-deny nas tabelas novas: nenhuma policy de proposito.
ALTER TABLE cm_conversa ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_conversa_mensagem ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_lote ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_lote_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_prova ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_faltou_isto ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (126) ON CONFLICT (numero) DO NOTHING;
