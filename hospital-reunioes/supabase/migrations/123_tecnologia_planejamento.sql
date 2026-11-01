-- =====================================================
-- Migration 123: Planejamento da Demanda (issue #1345, PRD #1344, ADR 0075)
-- =====================================================
-- A unica migration do PRD #1344. Duas tabelas entram:
--
--   1. `tecnologia_planejamentos`: a conversa do planejamento, uma por
--      Demanda, que fica guardada para o diretor retomar de onde parou
--      (ADR 0075, decisao 3) e some quando a Demanda chega a Concluida ou
--      Cancelada, pelo mesmo gancho dos Anexos (ADR 0069, decisao 3);
--   2. `tecnologia_chamadas_ia`: uma linha por chamada da aba Tecnologia a IA,
--      no molde de `cm_chamada_ia` (migration 117): modelo, tokens, custo em
--      dolar, duracao e sucesso (ADR 0075, decisao 7).
--
-- O estado e o resumo ja nascem com o que as fatias seguintes do PRD usam
-- (Fechar e resumir, o "nao" e o "sim", issues #1347 e #1349), para elas nao
-- pedirem outra parada no Studio. Nesta fatia so `em_andamento` e
-- `encerrado` sao gravados, e o resumo fica nulo.
--
-- RLS default-deny nas duas (padrao da casa): quem le e escreve e o backend
-- com a service_role. Nenhuma policy de proposito.
--
-- Tudo com IF NOT EXISTS / ON CONFLICT: rodar duas vezes tem que ser
-- inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. O planejamento da Demanda ----------
-- `mensagens` e a conversa inteira, na ordem: cada pergunta da IA (contexto,
-- as duas opcoes e a recomendada), cada resposta do diretor (a opcao clicada
-- ou o texto livre) e o "encerrou". `decisoes` e o painel "O que ja
-- decidimos", uma frase por decisao, na ordem em que fecharam.
--
-- `modelo` e o modelo que conduziu a conversa (LLM_MODEL_PLANEJAMENTO): se a
-- variavel mudar no meio de um planejamento, fica dito com qual ele comecou.
--
-- ON DELETE CASCADE: a conversa nao tem sentido sem a Demanda. Na pratica a
-- Demanda nao se apaga (ADR 0050, decisao 11); quem apaga o planejamento e o
-- encerramento da Demanda.
CREATE TABLE IF NOT EXISTS tecnologia_planejamentos (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  demanda_id     UUID NOT NULL UNIQUE REFERENCES tecnologia_demandas(id) ON DELETE CASCADE,
  estado         TEXT NOT NULL DEFAULT 'em_andamento'
                 CHECK (estado IN ('em_andamento', 'encerrado', 'resumido', 'enviado')),
  mensagens      JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(mensagens) = 'array'),
  decisoes       JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(decisoes) = 'array'),
  resumo         JSONB,
  modelo         TEXT NOT NULL CHECK (btrim(modelo) <> ''),
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE tecnologia_planejamentos IS
  'Planejamento da Demanda (ADR 0075): a conversa em que a IA faz as perguntas de negocio ao diretor, uma por Demanda. Some quando a Demanda e Concluida ou Cancelada.';
COMMENT ON COLUMN tecnologia_planejamentos.estado IS
  'em_andamento = a IA ainda pergunta; encerrado = a IA disse que tem o bastante ou bateu o teto de 12 perguntas; resumido e enviado = as fatias do resumo e do sim (#1347, #1349).';
COMMENT ON COLUMN tecnologia_planejamentos.mensagens IS
  'A conversa, na ordem: perguntas da IA (contexto, opcoes A e B, recomendada), respostas do diretor (opcao ou texto livre) e o encerrou.';
COMMENT ON COLUMN tecnologia_planejamentos.decisoes IS
  'O painel "O que ja decidimos": uma frase por decisao fechada, na ordem.';
COMMENT ON COLUMN tecnologia_planejamentos.resumo IS
  'O resumo do Fechar e resumir (#1347). Guarda so o ultimo. Nulo = ainda nao resumido.';

-- ---------- 2. A chamada de IA da Tecnologia ----------
-- Toda chamada grava uma linha, inclusive a que falhou: o provedor cobra a
-- resposta que voltou fora do formato. O texto da conversa nunca entra aqui,
-- so os numeros. ON DELETE SET NULL: o custo fica, mesmo que a Demanda saia.
CREATE TABLE IF NOT EXISTS tecnologia_chamadas_ia (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  demanda_id      UUID REFERENCES tecnologia_demandas(id) ON DELETE SET NULL,
  passo           TEXT NOT NULL CHECK (passo IN ('pergunta', 'resumo')),
  modelo          TEXT NOT NULL CHECK (btrim(modelo) <> ''),
  tokens_entrada  INTEGER NOT NULL DEFAULT 0 CHECK (tokens_entrada >= 0),
  tokens_saida    INTEGER NOT NULL DEFAULT 0 CHECK (tokens_saida >= 0),
  tokens_cache    INTEGER NOT NULL DEFAULT 0 CHECK (tokens_cache >= 0),
  custo_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (custo_usd >= 0),
  duracao_ms      INTEGER NOT NULL DEFAULT 0 CHECK (duracao_ms >= 0),
  sucesso         BOOLEAN NOT NULL DEFAULT true,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tecnologia_chamadas_ia_demanda
  ON tecnologia_chamadas_ia (demanda_id);

CREATE INDEX IF NOT EXISTS idx_tecnologia_chamadas_ia_criado_em
  ON tecnologia_chamadas_ia (criado_em);

COMMENT ON TABLE tecnologia_chamadas_ia IS
  'Uma chamada da aba Tecnologia a IA (ADR 0075, decisao 7): modelo, tokens, custo em dolar, duracao e sucesso. Nunca guarda o texto da conversa e nunca aparece na tela do diretor.';
COMMENT ON COLUMN tecnologia_chamadas_ia.passo IS
  'pergunta = um turno do planejamento; resumo = o Fechar e resumir (#1347).';
COMMENT ON COLUMN tecnologia_chamadas_ia.tokens_entrada IS
  'Tudo que entrou: sem cache, lido do cache e escrito no cache.';
COMMENT ON COLUMN tecnologia_chamadas_ia.tokens_cache IS
  'Tokens de entrada lidos do cache de prompt (cache_read_input_tokens). E por ele que se confere o acerto do cache do bloco fixo.';
COMMENT ON COLUMN tecnologia_chamadas_ia.sucesso IS
  'false = o provedor falhou ou a resposta nao validou contra o esquema; a conversa ficou como estava.';

-- RLS default-deny nas tabelas novas: nenhuma policy de proposito.
ALTER TABLE tecnologia_planejamentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE tecnologia_chamadas_ia ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (123) ON CONFLICT (numero) DO NOTHING;
