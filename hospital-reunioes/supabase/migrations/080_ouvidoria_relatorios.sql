-- =====================================================
-- Migration 080: registro dos relatorios da Ouvidoria (issue #345, PRD #319)
-- =====================================================
-- O relatorio quinzenal nasce de um job agendado (dias 1 e 16, 07h), vai por
-- email a Diretoria Executiva em PDF e fica registrado aqui.
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
  enviado_em      TIMESTAMPTZ,

  -- Quem recebeu, como estava a Diretoria Executiva no dia do envio.
  destinatarios   TEXT[] NOT NULL DEFAULT '{}',

  -- O ultimo motivo de o envio nao ter saido, para o ouvidor saber o que
  -- aconteceu antes de reenviar.
  ultimo_erro     TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_relatorios_competencia
  ON ouvidoria_relatorios(competencia);

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
  'Quando o email com o PDF saiu. NULL = ainda nao saiu; e a guarda de envio unico do job.';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/068/069/073).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_relatorios ENABLE ROW LEVEL SECURITY;
