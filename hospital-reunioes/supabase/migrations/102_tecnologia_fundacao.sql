-- =====================================================
-- Migration 102: fundacao da aba Tecnologia
-- (issue #636, PRD #634, ADR 0050)
-- =====================================================
-- A conversa entre o hospital e a Vitta sobre as aplicacoes sai do WhatsApp e
-- vira a aba Tecnologia da area admin. Tres tabelas novas, todas com prefixo
-- `tecnologia_`: Produto, Demanda e Conversa.
--
-- As tres nascem AQUI, no formato final da PRD, embora esta fatia so use o
-- Produto. As fatias seguintes (issues #637 a #642) montam Demanda e Conversa
-- em cima destas colunas e nao abrem migration nova: a migration e aplicada a
-- mao no Studio, e uma por fatia multiplicaria o passo humano por seis.
--
-- Nenhuma referencia a `pendencias`, `atas` ou `reunioes`: Demanda e assunto
-- de tecnologia entre fornecedor e cliente, Pendencia e compromisso
-- operacional do hospital (ADR 0050). Nenhum relatorio de Pendencia le estas
-- tabelas.
--
-- RLS ligado e SEM policy nas tres (default-deny da casa, padrao das 009, 041,
-- 051, 063 e 064): quem le e escreve e o backend com a service_role, e o gate
-- de papel (`require_super_admin`) vive na rota. A anon_key que vai no bundle
-- do frontend fica de fora.
--
-- Sem RPC: as transicoes de estado da Demanda sao simples o bastante para o
-- backend garantir em codigo (PRD #634). Nada a revogar de anon nem de
-- authenticated no schema public, entao as regras das migrations 095 e 097 nao
-- tem o que morder aqui.
-- =====================================================

-- ---------- Carimbo de atualizacao ----------
-- Funcao propria em vez da `update_updated_at()` da casa porque as tabelas de
-- Tecnologia usam `atualizado_em` (o nome da PRD), e a funcao antiga escreve
-- em `updated_at`.
CREATE OR REPLACE FUNCTION tecnologia_atualizado_em() RETURNS TRIGGER AS $$
BEGIN
  NEW.atualizado_em = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------- 1. Produto ----------
-- Cada coisa que a Vitta mantem para o hospital, com um dono do lado da Vitta.
-- Desativar nao apaga: a linha continua, e as Demandas dela seguem inteiras
-- (ADR 0050, decisao 4).
CREATE TABLE IF NOT EXISTS tecnologia_produtos (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome          TEXT NOT NULL,
  ativo         BOOLEAN NOT NULL DEFAULT true,
  dono_id       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ordem         INTEGER NOT NULL DEFAULT 0,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Nome unico sem distinguir maiusculas, no molde do `tipos_reuniao_nome_lower_idx`
-- da migration 027: "Ana" e "ANA" sao o mesmo Produto.
CREATE UNIQUE INDEX IF NOT EXISTS tecnologia_produtos_nome_lower_idx
  ON tecnologia_produtos ((lower(nome)));

DROP TRIGGER IF EXISTS trg_tecnologia_produtos_atualizado_em ON tecnologia_produtos;
CREATE TRIGGER trg_tecnologia_produtos_atualizado_em
  BEFORE UPDATE ON tecnologia_produtos
  FOR EACH ROW EXECUTE FUNCTION tecnologia_atualizado_em();

COMMENT ON TABLE tecnologia_produtos IS
  'Cada coisa que a Vitta mantem para o hospital (ADR 0050, decisao 4). Toda Demanda pertence a um Produto e nasce atribuida ao dono dele.';
COMMENT ON COLUMN tecnologia_produtos.dono_id IS
  'Quem responde pelo Produto do lado da Vitta. Produto ativo sem dono e recusado pela API (422): sem dono, a Demanda nasceria sem ninguem. ON DELETE SET NULL porque a pessoa pode sair, e ai a tela cobra um dono novo.';
COMMENT ON COLUMN tecnologia_produtos.ativo IS
  'Desativar tira o Produto da lista de escolha, nao apaga nem esconde o que ja existe (ADR 0050, decisao 11: nada se apaga).';
COMMENT ON COLUMN tecnologia_produtos.ordem IS
  'Ordem de exibicao na tela. Empate cai no nome.';

-- ---------- 2. Demanda ----------
-- Um pedido entre o hospital e a Vitta. Nada se apaga: a saida e `cancelada`
-- (ADR 0050, decisao 11).
CREATE TABLE IF NOT EXISTS tecnologia_demandas (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  titulo         TEXT NOT NULL,
  descricao      TEXT,
  tipo           TEXT NOT NULL,
  produto_id     UUID NOT NULL REFERENCES tecnologia_produtos(id) ON DELETE RESTRICT,
  estado         TEXT NOT NULL DEFAULT 'nova',
  responsavel_id VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  autor_id       VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  prioridade     TEXT NOT NULL DEFAULT 'normal',
  prazo          DATE,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  concluida_em   TIMESTAMPTZ,
  concluida_por  VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  cancelada_em   TIMESTAMPTZ,
  cancelada_por  VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL
);

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_tipo_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_tipo_check
  CHECK (tipo IN ('decisao', 'informacao', 'terceiro', 'ajuste', 'novo', 'defeito', 'consultoria'));

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_estado_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_estado_check
  CHECK (estado IN ('nova', 'em_andamento', 'aguardando', 'concluida', 'cancelada'));

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_prioridade_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_prioridade_check
  CHECK (prioridade IN ('baixa', 'normal', 'alta'));

-- Os tres eixos por onde a tela varre: a coluna do Quadro, a aba "Minha vez" e
-- o filtro por Produto (PRD #634).
CREATE INDEX IF NOT EXISTS idx_tecnologia_demandas_estado
  ON tecnologia_demandas(estado);
CREATE INDEX IF NOT EXISTS idx_tecnologia_demandas_responsavel
  ON tecnologia_demandas(responsavel_id);
CREATE INDEX IF NOT EXISTS idx_tecnologia_demandas_produto
  ON tecnologia_demandas(produto_id);

DROP TRIGGER IF EXISTS trg_tecnologia_demandas_atualizado_em ON tecnologia_demandas;
CREATE TRIGGER trg_tecnologia_demandas_atualizado_em
  BEFORE UPDATE ON tecnologia_demandas
  FOR EACH ROW EXECUTE FUNCTION tecnologia_atualizado_em();

COMMENT ON TABLE tecnologia_demandas IS
  'Um pedido entre o hospital e a Vitta sobre as aplicacoes (ADR 0050). Nada a ver com `pendencias`: nenhum relatorio, painel ou email de Pendencia le esta tabela.';
COMMENT ON COLUMN tecnologia_demandas.tipo IS
  'Lista fechada de sete (ADR 0050, decisao 3): decisao, informacao, terceiro, ajuste, novo, defeito, consultoria. Em minusculas e sem acento.';
COMMENT ON COLUMN tecnologia_demandas.estado IS
  'Coluna do Kanban (ADR 0050, decisao 5). Nasce em `nova`. A saida e `cancelada`, nunca DELETE.';
COMMENT ON COLUMN tecnologia_demandas.produto_id IS
  'ON DELETE RESTRICT: Produto com Demanda nao e apagado, e desativado.';
COMMENT ON COLUMN tecnologia_demandas.concluida_em IS
  'Carimbo de quando a Demanda foi concluida. Reabrir volta a NULL, junto com `concluida_por`.';
COMMENT ON COLUMN tecnologia_demandas.cancelada_em IS
  'Carimbo de quando a Demanda foi cancelada. Reabrir volta a NULL, junto com `cancelada_por`.';

-- ---------- 3. Conversa ----------
-- O fio dentro do card: resposta de gente e linha automatica de movimento, na
-- mesma tabela e na mesma ordem cronologica (ADR 0050, decisao 6).
CREATE TABLE IF NOT EXISTS tecnologia_conversas (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  demanda_id       UUID NOT NULL REFERENCES tecnologia_demandas(id) ON DELETE RESTRICT,
  autor_id         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  linha            TEXT NOT NULL DEFAULT 'resposta',
  texto            TEXT NOT NULL,
  mencoes          VARCHAR(10)[] NOT NULL DEFAULT '{}',
  movimento_campo  TEXT,
  movimento_de     TEXT,
  movimento_para   TEXT,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  editado_em       TIMESTAMPTZ
);

ALTER TABLE tecnologia_conversas DROP CONSTRAINT IF EXISTS tecnologia_conversas_linha_check;
ALTER TABLE tecnologia_conversas
  ADD CONSTRAINT tecnologia_conversas_linha_check
  CHECK (linha IN ('resposta', 'movimento'));

ALTER TABLE tecnologia_conversas DROP CONSTRAINT IF EXISTS tecnologia_conversas_movimento_campo_check;
ALTER TABLE tecnologia_conversas
  ADD CONSTRAINT tecnologia_conversas_movimento_campo_check
  CHECK (movimento_campo IS NULL OR movimento_campo IN ('estado', 'responsavel'));

CREATE INDEX IF NOT EXISTS idx_tecnologia_conversas_demanda
  ON tecnologia_conversas(demanda_id, criado_em);

COMMENT ON TABLE tecnologia_conversas IS
  'O fio de respostas dentro do card da Demanda (ADR 0050, decisao 6), misturado com as linhas automaticas de movimento na mesma ordem cronologica.';
COMMENT ON COLUMN tecnologia_conversas.autor_id IS
  'NULL na linha automatica de movimento gravada pelo sistema. Resposta de gente sempre tem autor.';
COMMENT ON COLUMN tecnologia_conversas.movimento_campo IS
  'O que mudou na linha de movimento: `estado` ou `responsavel`. O de/para fica em `movimento_de` e `movimento_para`; o texto legivel e montado pelo backend na hora de gravar.';
COMMENT ON COLUMN tecnologia_conversas.editado_em IS
  'Quando o autor corrigiu a propria resposta (janela de 10 minutos). Linha de movimento nunca e editavel.';

-- ---------- 4. RLS default-deny ----------
-- Ligado e sem policy nenhuma nas tres: so a service_role passa.
ALTER TABLE tecnologia_produtos ENABLE ROW LEVEL SECURITY;
ALTER TABLE tecnologia_demandas ENABLE ROW LEVEL SECURITY;
ALTER TABLE tecnologia_conversas ENABLE ROW LEVEL SECURITY;

-- ---------- 5. Seed dos sete Produtos ----------
-- Sem dono de proposito: o dono e definido na tela antes do primeiro uso, e a
-- API recusa criar Demanda em Produto sem dono. `ON CONFLICT DO NOTHING`
-- deixa a migration idempotente e nao mexe em quem ja renomeou algum.
INSERT INTO tecnologia_produtos (nome, ordem) VALUES
  ('Ana',                  1),
  ('Integração Ana x MV',  2),
  ('Reuniões',             3),
  ('Ouvidoria',            4),
  ('POPs',                 5),
  ('Site',                 6),
  ('Infra',                7)
ON CONFLICT DO NOTHING;
