-- =====================================================
-- Migration 137: nota do Google buscada toda semana (issue #1619, PRD #1527, ADR 0089)
-- =====================================================
-- Ate aqui o ouvidor lia a nota do Google na pagina e digitava no diario de
-- Nota externa (migration 082). Agora um job semanal, sem IA, le a nota e o
-- total de avaliacoes pela Places API (New) e grava no MESMO diario, com a
-- marca de leitura automatica. O Reclame Aqui continua digitado a mao.
--
-- Duas mudancas:
--
-- 1. O diario ganha o total de avaliacoes e a origem da linha. O total so
--    existe na leitura automatica (o ouvidor nunca digitou total), por isso e
--    nulo nas linhas antigas. A origem das linhas antigas e `manual`, e o
--    DEFAULT cobre o historico sem UPDATE.
--
-- 2. Nasce a configuracao da Ouvidoria: UMA linha, com o Place ID do hospital
--    e o link de avaliacao do Google. As fatias seguintes do PRD (Nucleo de
--    Seguranca do Paciente e convite ao Google) acrescentam colunas aqui. A
--    chave da API NAO mora aqui: e segredo de ambiente, criado na tela do
--    Coolify (`GOOGLE_PLACES_API_KEY`).
-- =====================================================

ALTER TABLE ouvidoria_nota_externa
  ADD COLUMN IF NOT EXISTS total_avaliacoes INTEGER CHECK (total_avaliacoes IS NULL OR total_avaliacoes >= 0),
  ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual', 'automatica'));

COMMENT ON COLUMN ouvidoria_nota_externa.total_avaliacoes IS
  'Total de avaliacoes do perfil no Google na hora da leitura. So a leitura automatica traz; nulo nas digitadas.';
COMMENT ON COLUMN ouvidoria_nota_externa.origem IS
  'manual (digitada pelo ouvidor) ou automatica (lida pelo job semanal da Places API, ADR 0089).';

-- A configuracao da Ouvidoria: uma linha so. A PK booleana com CHECK impede a
-- segunda linha, e quem le pega sempre `id = true`.
CREATE TABLE IF NOT EXISTS ouvidoria_config (
  id                 BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
  google_place_id    TEXT NOT NULL DEFAULT '',
  google_review_url  TEXT NOT NULL DEFAULT '',
  atualizada_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO ouvidoria_config (id, google_place_id, google_review_url)
VALUES (
  TRUE,
  'ChIJN5IUl-vfmwARsSET9nFjh70',
  'https://search.google.com/local/writereview?placeid=ChIJN5IUl-vfmwARsSET9nFjh70'
)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE ouvidoria_config IS
  'Configuracao da Ouvidoria, uma linha so: Place ID e link de avaliacao do Google (ADR 0089). Fatias seguintes acrescentam colunas.';

-- RLS default-deny (padrao da casa). Backend usa service_role; a anon_key do
-- bundle do frontend fica de fora.
ALTER TABLE ouvidoria_config ENABLE ROW LEVEL SECURITY;

INSERT INTO migracoes_aplicadas (numero) VALUES (137) ON CONFLICT (numero) DO NOTHING;
