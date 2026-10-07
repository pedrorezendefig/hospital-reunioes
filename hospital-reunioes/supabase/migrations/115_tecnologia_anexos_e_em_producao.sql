-- =====================================================
-- Migration 115: Anexo da Demanda e a Etapa Em producao
-- (issue #1057, PRD #1056, ADR 0069)
-- =====================================================
-- A fundacao do PRD #1056 numa migration so: a migration e aplicada a mao no
-- Studio, e uma por fatia multiplicaria a parada humana por tres.
--
-- Quatro coisas entram:
--   1. a tabela de Anexos da Demanda (metadados aqui, binario no storage);
--   2. o bucket privado `anexos-tecnologia`;
--   3. o valor `em_producao` no CHECK da Etapa;
--   4. duas colunas na Demanda: a versao em que ela subiu e a data em que a
--      Etapa chegou a Entregue ou Em producao.
--
-- Nada aqui e alimentado ainda: as fatias seguintes gravam os anexos, a
-- versao e a data. Por isso tudo nasce nulo ou vazio, e o que ja existe em
-- producao continua exatamente como esta.
--
-- Tudo com IF NOT EXISTS / DROP antes de CREATE / ON CONFLICT: rodar duas
-- vezes tem que ser inofensivo.
-- =====================================================

-- ---------- 1. Anexo da Demanda ----------
-- Uma imagem (print de tela) guardada junto da Demanda, ate dez por Demanda
-- (ADR 0069, decisao 1). Vive so no app e nunca vai para o GitHub: o
-- repositorio e publico e print do hospital e dado pessoal.
--
-- O binario e apagado quando a Demanda chega a Concluida ou Cancelada
-- (decisao 3), e a linha FICA, com `apagado_em` preenchido: a Conversa mostra
-- que o anexo existiu (nome, quem, quando) e nao pode quebrar.
CREATE TABLE IF NOT EXISTS tecnologia_anexos (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  demanda_id     UUID NOT NULL REFERENCES tecnologia_demandas(id) ON DELETE RESTRICT,
  -- A posicao da imagem na Demanda, de 1 a 10: o teto de dez da ADR 0069 vive
  -- tambem aqui, como na Ouvidoria, para contornar a API nao contornar o teto.
  ordem          INTEGER NOT NULL CHECK (ordem BETWEEN 1 AND 10),
  storage_path   TEXT NOT NULL CHECK (btrim(storage_path) <> ''),
  nome_original  TEXT NOT NULL CHECK (btrim(nome_original) <> ''),
  -- Os formatos e o teto de 5 MB sao os do Assistente de Tecnologia
  -- (`assistente_tecnologia.py`): a regra da imagem e uma so no modulo.
  content_type   TEXT NOT NULL CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
  tamanho_bytes  BIGINT NOT NULL CHECK (tamanho_bytes > 0 AND tamanho_bytes <= 5242880),
  anexado_por    VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  conversa_id    UUID REFERENCES tecnologia_conversas(id) ON DELETE RESTRICT,
  apagado_em     TIMESTAMPTZ,
  UNIQUE (demanda_id, ordem)
);

CREATE INDEX IF NOT EXISTS idx_tecnologia_anexos_conversa
  ON tecnologia_anexos(conversa_id)
  WHERE conversa_id IS NOT NULL;

COMMENT ON TABLE tecnologia_anexos IS
  'Anexo da Demanda (ADR 0069): print de tela guardado junto da Demanda, ate dez. Metadados aqui, binario no bucket privado anexos-tecnologia. Nunca vai para o GitHub.';
COMMENT ON COLUMN tecnologia_anexos.ordem IS
  'Posicao da imagem na Demanda, de 1 a 10. A rota de automacao devolve as imagens nesta ordem.';
COMMENT ON COLUMN tecnologia_anexos.storage_path IS
  'Caminho no bucket privado. Nome sorteado, como na Ouvidoria: o nome original pode carregar dado pessoal e nao entra em caminho. Continua preenchido depois do apagamento, como registro.';
COMMENT ON COLUMN tecnologia_anexos.nome_original IS
  'O nome do arquivo como chegou. E o que a tela e o "Copiar para IA" mostram.';
COMMENT ON COLUMN tecnologia_anexos.anexado_por IS
  'Quem anexou. ON DELETE SET NULL porque a pessoa pode sair, e o registro continua.';
COMMENT ON COLUMN tecnologia_anexos.conversa_id IS
  'A resposta da Conversa que trouxe a imagem. Nulo quando ela veio pelo formulario ou pelo Assistente.';
COMMENT ON COLUMN tecnologia_anexos.apagado_em IS
  'Quando o binario saiu do bucket (Demanda Concluida ou Cancelada, ADR 0069, decisao 3). Nulo = imagem ainda guardada.';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/066/102): quem le e
-- escreve e o backend com a service_role. Nenhuma policy de proposito.
ALTER TABLE tecnologia_anexos ENABLE ROW LEVEL SECURITY;

-- ---------- 2. O bucket privado ----------
-- Molde do `anexos-ouvidoria` (migration 066): sem policy de leitura para
-- `authenticated`. O unico caminho ate a imagem e a URL assinada que o backend
-- emite depois de conferir o acesso a aba Tecnologia.
INSERT INTO storage.buckets (id, name, public)
VALUES ('anexos-tecnologia', 'anexos-tecnologia', false)
ON CONFLICT (id) DO NOTHING;

-- Idempotente: se alguem criou a mao no Studio uma policy aberta para este
-- bucket, ela sai aqui. Nenhuma e criada no lugar.
DROP POLICY IF EXISTS "Authenticated Access anexos-tecnologia" ON storage.objects;

-- ---------- 3. A setima Etapa ----------
-- Em producao e a subida que levou o fechamento da issue ao ar (ADR 0069,
-- decisao 4). O CHECK e a mesma lista fechada do servico puro que a calcula
-- (`tecnologia_vinculo.ETAPAS`); o teste amarra as duas pontas.
ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_etapa_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_etapa_check
  CHECK (etapa IN ('registrada', 'em_analise', 'planejada', 'em_desenvolvimento', 'entregue', 'em_producao', 'nao_sera_feita'));

-- ---------- 4. A versao e a data da entrega ----------
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS versao_em_producao TEXT;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS entregue_em TIMESTAMPTZ;

COMMENT ON COLUMN tecnologia_demandas.versao_em_producao IS
  'A versao do app em que a Demanda subiu ("v0.165.0"), gravada pelo webhook de deploy que a Action pos-merge chama (ADR 0069, decisao 4). Com ela e a issue fechada como concluida, a Etapa e Em producao. Nulo = ainda nao subiu.';
COMMENT ON COLUMN tecnologia_demandas.entregue_em IS
  'Quando a Etapa chegou a Entregue ou Em producao. O Painel conta "entregues nos ultimos 30 dias" por ela. Nulo = ainda nao entregue.';

INSERT INTO migracoes_aplicadas (numero) VALUES (115) ON CONFLICT (numero) DO NOTHING;
