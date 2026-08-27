-- =====================================================
-- Migration 080: registro dos relatorios da Ouvidoria (issue #345, PRD #319)
-- =====================================================
-- O relatorio quinzenal nasce de um job diario das 07h, que entrega a edicao
-- da quinzena assim que ela fecha (dias 1 e 16) e, se o container estiver fora
-- do ar naquela hora, no primeiro dia seguinte em que conseguir. Vai por email
-- a Diretoria Executiva em PDF e fica registrado aqui.
--
-- A coluna que carrega o peso e `dados`: a resposta INTEIRA de
-- `ouvidoria_metricas.metricas_do_periodo`, congelada no instante em que o
-- relatorio foi gerado. Ela existe por dois motivos:
--
--   1. Reenvio fiel. O ouvidor reenvia o relatorio JA GERADO, e o PDF do
--      reenvio precisa trazer os mesmos numeros do original. Regerar as
--      metricas na hora do reenvio devolveria outro retrato.
--   2. `pendencias_por_area` e fila VIVA: ela responde "o que esta pendente
--      agora", sem recorte de data. Sem congelar, um relatorio de julho
--      reenviado em setembro carregaria a fila de setembro embaixo do titulo
--      de julho. Com o congelamento, o que foi medido em julho continua sendo
--      o que o PDF mostra, e `medido_em` diz de quando e aquela fila.
--
-- Nada aqui identifica manifestacao: `dados` e o objeto agregado do modulo de
-- metricas, que nao carrega protocolo em campo nenhum, de proposito (RN-40,
-- ADR 0034 decisao 8). O unico nome proprio e o do responsavel de cada setor.
-- =====================================================

CREATE TABLE IF NOT EXISTS ouvidoria_relatorios (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Por enquanto so o quinzenal. O mensal (fatia I5) entra na mesma tabela.
  tipo            TEXT NOT NULL CHECK (tipo IN ('quinzenal', 'mensal')),

  -- A identidade da edicao: tipo mais periodo. E o que faz o job ser
  -- idempotente, e o UNIQUE e o que garante isso quando duas rodadas se
  -- cruzarem.
  competencia     TEXT NOT NULL,

  periodo_inicio  DATE NOT NULL,
  periodo_fim     DATE NOT NULL,
  CONSTRAINT ouvidoria_relatorios_periodo_check CHECK (periodo_fim >= periodo_inicio),

  -- O instante da medicao, no relogio da aplicacao. E o carimbo que data a
  -- fila viva de `pendencias_por_area` (issue #399).
  medido_em       TIMESTAMPTZ NOT NULL,

  -- A resposta congelada do modulo de metricas.
  dados           JSONB NOT NULL,

  gerado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- NULL enquanto o email nao saiu. E esta coluna que impede o segundo envio.
  -- Ela guarda a PRIMEIRA entrega e nunca e reescrita: e ela que responde
  -- "esta edicao saiu?".
  enviado_em      TIMESTAMPTZ,

  -- Quem recebeu, ACUMULADO: a lista da primeira entrega mais quem recebeu em
  -- cada reenvio, sem nunca encolher. Numa distribuicao de dado da Ouvidoria
  -- para fora do sistema, quem recebeu e a evidencia que nao pode ser
  -- reescrita: se o reenvio sobrescrevesse, os destinatarios da primeira
  -- entrega sumiriam do historico como se nunca tivessem recebido.
  destinatarios   TEXT[] NOT NULL DEFAULT '{}',

  -- Quando o PDF foi reemitido pela ultima vez, e quantas vezes ao todo. Sem
  -- isso, um documento arquivado nao diz quando nem quantas vezes saiu de novo.
  reenviado_em    TIMESTAMPTZ,
  reenvios        INTEGER NOT NULL DEFAULT 0,

  -- Por que a ULTIMA tentativa de entrega nao saiu, ou o que faltou nela
  -- (entrega parcial escreve aqui quem ficou de fora, mesmo com `enviado_em`
  -- preenchido). NULL significa que a ultima tentativa entregou a TODOS os
  -- destinatarios. Lido junto com `enviado_em`, `reenviado_em` e `reenvios`,
  -- ele diz sem ambiguidade em que pe esta a edicao.
  --
  -- A trilha permanente de quem pediu REENVIO MANUAL, quando e com que
  -- resultado vive em `audit_log`. O caminho automatico (job) nao entra la:
  -- ele deixa rastro no log da aplicacao e nestas colunas, e so.
  ultimo_erro     TEXT
);

-- As colunas que nasceram depois da primeira versao deste arquivo. Elas
-- precisam do ALTER: `CREATE TABLE IF NOT EXISTS` nao acrescenta coluna a uma
-- tabela que ja existe, e sairia daqui em silencio, sem erro nenhum. Quem
-- tivesse aplicado a versao anterior (no Studio de dev ou no Supabase local)
-- ficaria com a tabela velha e veria a listagem quebrar no SELECT e o reenvio
-- quebrar no UPDATE.
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS reenviado_em TIMESTAMPTZ;
ALTER TABLE ouvidoria_relatorios ADD COLUMN IF NOT EXISTS reenvios INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_relatorios_competencia
  ON ouvidoria_relatorios(competencia);

-- A fila da recuperacao: as edicoes que foram geradas e nao sairam. O job
-- diario varre por aqui antes de gerar a do dia, para uma quinzena que falhou
-- no envio nao ficar parada esperando alguem abrir a listagem.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_relatorios_nao_enviados
  ON ouvidoria_relatorios(periodo_fim DESC)
  WHERE enviado_em IS NULL;

-- A listagem do ouvidor: do mais recente para o mais antigo.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_relatorios_periodo
  ON ouvidoria_relatorios(periodo_fim DESC);

COMMENT ON TABLE ouvidoria_relatorios IS
  'Relatorios da Ouvidoria gerados e enviados por email. Guarda os numeros congelados no instante da geracao, para o reenvio mostrar o mesmo retrato (issue #345).';
COMMENT ON COLUMN ouvidoria_relatorios.competencia IS
  'Identidade da edicao (tipo + periodo). UNIQUE: e o que impede a mesma quinzena de ser registrada duas vezes.';
COMMENT ON COLUMN ouvidoria_relatorios.dados IS
  'Resposta congelada de ouvidoria_metricas.metricas_do_periodo. Nao carrega protocolo de manifestacao nenhuma.';
COMMENT ON COLUMN ouvidoria_relatorios.medido_em IS
  'Instante da medicao. Data a fila viva de pendencias_por_area, que nao tem recorte de periodo.';
COMMENT ON COLUMN ouvidoria_relatorios.enviado_em IS
  'Quando o email com o PDF saiu pela PRIMEIRA vez. NULL = ainda nao saiu; e a guarda de envio unico do job. O reenvio nao reescreve.';
COMMENT ON COLUMN ouvidoria_relatorios.destinatarios IS
  'Quem recebeu, acumulado entre a primeira entrega e os reenvios. Nunca encolhe.';
COMMENT ON COLUMN ouvidoria_relatorios.reenvios IS
  'Quantas vezes o PDF foi reemitido com sucesso depois da primeira entrega.';
COMMENT ON COLUMN ouvidoria_relatorios.ultimo_erro IS
  'Motivo de a ultima tentativa de entrega nao ter saido, ou quem ficou de fora numa entrega parcial. NULL = a ultima tentativa entregou a todos.';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/068/069/073).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_relatorios ENABLE ROW LEVEL SECURITY;
