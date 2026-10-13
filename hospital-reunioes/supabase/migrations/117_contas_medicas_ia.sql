-- =====================================================
-- Migration 117: Contas medicas, a IA (issue #1130, PRD #1128)
-- =====================================================
-- A unica migration do PRD 2 de Contas medicas: o que a IA, o Painel, o
-- formulario em branco aprendido e o reenvio da conta corrigida precisam no
-- banco nasce aqui, para as fatias do PRD andarem em paralelo sem pedir outra
-- parada no Studio. A 118 (PRD #1129, Gestao) entra depois desta.
--
-- O que entra:
--   1. `cm_chamada_ia`: uma linha por chamada a IA, com modelo, tokens, custo,
--      duracao e tentativas. A soma vai para `cm_conta` (colunas da 116);
--   2. `cm_linha_formulario`: a linha de formulario em branco aprendida por
--      familia de documento, que sai do texto enviado a IA;
--   3. o CHECK do nivel de evidencia com `PRESCRITO_SN` (adendo v1.1);
--   4. `nota_saida` e `reenviada_em` na conta (reenvio da conta corrigida);
--   5. a proposta da IA no dicionario (`PROPOSTO`, origem `IA`);
--   6. o indice do Guia por causa-raiz e data, para o Painel.
--
-- Os itens 3 e 5 ja nasceram na 116. Os CHECKs sao refeitos aqui, com os
-- mesmos valores, para o banco ter exatamente o que esta escrito, mesmo que a
-- 116 tenha entrado no Studio com outra redacao.
--
-- RLS default-deny nas tabelas novas (padrao da casa): quem le e escreve e o
-- backend com a service_role. Nenhuma policy de proposito.
--
-- Tudo com IF NOT EXISTS / DROP antes de ADD / ON CONFLICT: rodar duas vezes
-- tem que ser inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. A chamada de IA ----------
-- Toda chamada do modulo a IA grava uma linha, inclusive a que falhou nas tres
-- tentativas: o provedor cobra a tentativa que voltou fora do formato. O texto
-- do prontuario nunca entra aqui, so os numeros. ON DELETE SET NULL: o custo
-- fica, mesmo que a conta saia.
CREATE TABLE IF NOT EXISTS cm_chamada_ia (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conta_id        UUID REFERENCES cm_conta(id) ON DELETE SET NULL,
  atendimento_id  UUID REFERENCES cm_atendimento(id) ON DELETE SET NULL,
  passo           TEXT NOT NULL CHECK (passo IN ('A', 'B', 'DICIONARIO', 'OBSERVACAO')),
  modelo          TEXT NOT NULL CHECK (btrim(modelo) <> ''),
  tokens_entrada  INTEGER NOT NULL DEFAULT 0 CHECK (tokens_entrada >= 0),
  tokens_saida    INTEGER NOT NULL DEFAULT 0 CHECK (tokens_saida >= 0),
  tokens_cache    INTEGER NOT NULL DEFAULT 0 CHECK (tokens_cache >= 0),
  custo_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (custo_usd >= 0),
  duracao_ms      INTEGER NOT NULL DEFAULT 0 CHECK (duracao_ms >= 0),
  tentativas      INTEGER NOT NULL DEFAULT 1 CHECK (tentativas BETWEEN 1 AND 3),
  sucesso         BOOLEAN NOT NULL DEFAULT true,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cm_chamada_ia_conta
  ON cm_chamada_ia (conta_id);

CREATE INDEX IF NOT EXISTS idx_cm_chamada_ia_criado_em
  ON cm_chamada_ia (criado_em);

COMMENT ON TABLE cm_chamada_ia IS
  'Uma chamada de Contas medicas a IA (issue #1130): modelo, tokens, custo em dolar, duracao e tentativas. A soma por conta vai para cm_conta. Nunca guarda texto de prontuario.';
COMMENT ON COLUMN cm_chamada_ia.passo IS
  'A = eventos do prontuario; B = comparacao com a memoria; DICIONARIO e OBSERVACAO = a chamada curta.';
COMMENT ON COLUMN cm_chamada_ia.tokens_cache IS
  'Tokens de entrada lidos do cache de prompt (cached_tokens do provedor).';
COMMENT ON COLUMN cm_chamada_ia.sucesso IS
  'false = a resposta nao veio no formato nas tres tentativas e a conta foi para ERRO.';

-- ---------- 2. A linha de formulario em branco ----------
-- A linha que se repete igual na maioria dos documentos de uma familia (o
-- formulario impresso, sem o que foi preenchido). A contagem acumula entre
-- todos os prontuarios processados; a linha aprendida sai do texto enviado a IA.
CREATE TABLE IF NOT EXISTS cm_linha_formulario (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  familia        TEXT NOT NULL CHECK (btrim(familia) <> ''),
  linha          TEXT NOT NULL,
  contagem       INTEGER NOT NULL DEFAULT 0 CHECK (contagem >= 0),
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (familia, linha)
);

COMMENT ON TABLE cm_linha_formulario IS
  'Linha de formulario em branco aprendida por familia de documento do prontuario (PRD #1128). Sai do texto enviado a IA.';

-- ---------- 3. O nivel de evidencia ----------
-- PRESCRITO_SN: prescricao "se necessario" sem nenhum registro de uso, incluida
-- sempre (adendo v1.1 da spec).
ALTER TABLE cm_guia_linha DROP CONSTRAINT IF EXISTS cm_guia_linha_nivel_evidencia_check;
ALTER TABLE cm_guia_linha
  ADD CONSTRAINT cm_guia_linha_nivel_evidencia_check
  CHECK (nivel_evidencia IS NULL OR nivel_evidencia IN ('REGISTRADO', 'PRESCRITO', 'PRESCRITO_SN', 'POR_REGRA'));

-- ---------- 4. O reenvio da conta corrigida ----------
-- A nota de saida e a nota da conta depois da correcao no MV, calculada no
-- reenvio. A de entrada continua em `nota_entrada`.
ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS nota_saida NUMERIC(6, 2);
ALTER TABLE cm_conta
  ADD COLUMN IF NOT EXISTS reenviada_em TIMESTAMPTZ;

COMMENT ON COLUMN cm_conta.nota_saida IS
  'Nota da conta depois da correcao, calculada no reenvio do PDF corrigido. Nulo = a conta nao foi reenviada.';
COMMENT ON COLUMN cm_conta.reenviada_em IS
  'Quando a conta corrigida foi reenviada.';

-- ---------- 5. A proposta da IA no dicionario ----------
-- Termo de medicamento sem par no dicionario vai uma vez a IA, e a proposta
-- entra como PROPOSTO, com origem IA, ate a gestao confirmar.
ALTER TABLE cm_item_dicionario DROP CONSTRAINT IF EXISTS cm_item_dicionario_origem_check;
ALTER TABLE cm_item_dicionario
  ADD CONSTRAINT cm_item_dicionario_origem_check
  CHECK (origem IN ('IA', 'GESTAO'));

ALTER TABLE cm_item_dicionario DROP CONSTRAINT IF EXISTS cm_item_dicionario_situacao_check;
ALTER TABLE cm_item_dicionario
  ADD CONSTRAINT cm_item_dicionario_situacao_check
  CHECK (situacao IN ('PROPOSTO', 'CONFIRMADO'));

-- ---------- 6. O indice do Painel ----------
-- O Painel soma o R$ apontado por causa-raiz e por semana.
CREATE INDEX IF NOT EXISTS idx_cm_guia_linha_causa_raiz_data
  ON cm_guia_linha (causa_raiz, data);

-- RLS default-deny nas tabelas novas: nenhuma policy de proposito.
ALTER TABLE cm_chamada_ia ENABLE ROW LEVEL SECURITY;
ALTER TABLE cm_linha_formulario ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (117) ON CONFLICT (numero) DO NOTHING;
