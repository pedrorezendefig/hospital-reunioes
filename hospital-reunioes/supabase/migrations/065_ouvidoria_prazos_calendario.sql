-- =====================================================
-- Migration 065: motor de prazos em calendario util (issue #322, ADR 0034 decisao 6)
-- =====================================================
-- Prazo hardcoded foi rejeitado no ADR 0034: a tabela do diretor ainda muda em
-- 28/08/2026 (RN-21). Ela vive em banco, editavel pela diretoria executiva,
-- com historico de quem mudou o que.
--
-- O calculo em si nao vive aqui: e funcao pura em app/services/ouvidoria_prazos.py,
-- que recebe o prazo e os feriados desta migration e devolve o vencimento. O
-- banco guarda os parametros e o vencimento ja calculado; nao recalcula nada.
-- =====================================================

-- 1. Tabela de prazos por gravidade e marco (RN-21). Uma linha por celula da
--    tabela da spec: a diretoria edita celula a celula, e o historico fica no
--    mesmo grao.
--    valor NULL = sem prazo (critico nao tem prazo conclusivo fixo; baixo nao
--    passa pela area). valor 0 = imediato.
CREATE TABLE IF NOT EXISTS ouvidoria_prazos (
  gravidade     TEXT NOT NULL CHECK (gravidade IN ('critico', 'alto', 'medio', 'baixo')),
  marco         TEXT NOT NULL CHECK (marco IN ('triagem', 'area_resposta', 'conclusiva')),
  valor         INTEGER CHECK (valor IS NULL OR valor >= 0),
  unidade       TEXT NOT NULL CHECK (unidade IN ('horas_uteis', 'dias_uteis')),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (gravidade, marco)
);

COMMENT ON TABLE ouvidoria_prazos IS
  'Tabela de prazos por gravidade (RN-21, ADR 0034 decisao 6). Editavel pela diretoria executiva; nunca hardcoded, porque os valores ainda mudam com as coordenacoes.';
COMMENT ON COLUMN ouvidoria_prazos.marco IS
  'Trecho medido: triagem (T0 ate T1, ouvidoria), area_resposta (T1 ate T2, setor), conclusiva (T0 ate T3, ouvidoria).';
COMMENT ON COLUMN ouvidoria_prazos.valor IS
  'NULL significa sem prazo para essa celula (critico nao tem conclusiva fixa; baixo nao vai a area). Zero significa imediato.';

-- Valores da especificacao da Diretoria de 19/08/2026, secao 7.2, como seed.
-- "Acusar recebimento" fica de fora: e prazo em calendario corrido e pertence
-- ao catalogo de notificacoes, nao ao calendario util deste motor.
INSERT INTO ouvidoria_prazos (gravidade, marco, valor, unidade) VALUES
  ('critico', 'triagem',       0,    'horas_uteis'),
  ('critico', 'area_resposta', 4,    'horas_uteis'),
  ('critico', 'conclusiva',    NULL, 'dias_uteis'),
  ('alto',    'triagem',       4,    'horas_uteis'),
  ('alto',    'area_resposta', 2,    'dias_uteis'),
  ('alto',    'conclusiva',    5,    'dias_uteis'),
  ('medio',   'triagem',       1,    'dias_uteis'),
  ('medio',   'area_resposta', 4,    'dias_uteis'),
  ('medio',   'conclusiva',    7,    'dias_uteis'),
  ('baixo',   'triagem',       1,    'dias_uteis'),
  ('baixo',   'area_resposta', NULL, 'dias_uteis'),
  ('baixo',   'conclusiva',    2,    'dias_uteis')
ON CONFLICT (gravidade, marco) DO NOTHING;

-- 2. Historico de alteracao (RN-21): quem mudou, quando, de que para que.
--    Append-only, como a trilha de movimentos: o registro de quem mexeu no
--    prazo nao pode ser reescrito depois.
CREATE TABLE IF NOT EXISTS ouvidoria_prazos_historico (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gravidade        TEXT NOT NULL,
  marco            TEXT NOT NULL,
  valor_anterior   INTEGER,
  unidade_anterior TEXT,
  valor_novo       INTEGER,
  unidade_nova     TEXT NOT NULL,
  -- Sem FK de propósito: numa tabela append-only, qualquer acao de FK que
  -- mexa na linha (ON DELETE SET NULL) e um UPDATE, e a trigger abaixo recusa
  -- UPDATE. Com FK, apagar quem ja editou um prazo falharia com "movimento e
  -- imutavel" em vez de anonimizar. O dado durável aqui e o autor_nome.
  autor_id         VARCHAR(10),
  autor_nome       TEXT NOT NULL,
  ocorrido_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_prazos_historico_celula
  ON ouvidoria_prazos_historico(gravidade, marco, ocorrido_em DESC);

COMMENT ON TABLE ouvidoria_prazos_historico IS
  'Historico de alteracao da tabela de prazos (RN-21). Append-only: UPDATE e DELETE bloqueados por trigger.';
COMMENT ON COLUMN ouvidoria_prazos_historico.autor_nome IS
  'Nome no momento do ato: o historico nao muda se a pessoa for renomeada ou removida depois.';

-- Reaproveita a funcao de bloqueio da migration 064 (mesma regra, mesma razao).
DROP TRIGGER IF EXISTS trg_ouvidoria_prazos_historico_sem_update ON ouvidoria_prazos_historico;
CREATE TRIGGER trg_ouvidoria_prazos_historico_sem_update
  BEFORE UPDATE ON ouvidoria_prazos_historico
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

DROP TRIGGER IF EXISTS trg_ouvidoria_prazos_historico_sem_delete ON ouvidoria_prazos_historico;
CREATE TRIGGER trg_ouvidoria_prazos_historico_sem_delete
  BEFORE DELETE ON ouvidoria_prazos_historico
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

-- 3. Feriados administraveis (RN-22): nacionais, estaduais do RJ e municipais
--    do Rio. Sem eles o motor contaria 20 de novembro como dia util.
CREATE TABLE IF NOT EXISTS ouvidoria_feriados (
  data        DATE PRIMARY KEY,
  nome        TEXT NOT NULL CHECK (btrim(nome) <> ''),
  abrangencia TEXT NOT NULL CHECK (abrangencia IN ('nacional', 'estadual_rj', 'municipal_rio'))
);

COMMENT ON TABLE ouvidoria_feriados IS
  'Feriados que saem do calendario util da Ouvidoria (RN-22). Data como chave: o mesmo dia nao entra duas vezes com abrangencias diferentes.';

-- Seed de 2026 e 2027 (as datas moveis seguem a Pascoa: 05/04/2026 e 28/03/2027).
-- Feriado seguinte entra pela tela, sem migration.
INSERT INTO ouvidoria_feriados (data, nome, abrangencia) VALUES
  ('2026-01-01', 'Confraternizacao Universal',      'nacional'),
  ('2026-01-20', 'Sao Sebastiao',                   'municipal_rio'),
  ('2026-02-16', 'Carnaval',                        'municipal_rio'),
  ('2026-02-17', 'Carnaval',                        'municipal_rio'),
  ('2026-03-01', 'Aniversario da cidade do Rio',    'municipal_rio'),
  ('2026-04-03', 'Sexta-feira Santa',               'nacional'),
  ('2026-04-21', 'Tiradentes',                      'nacional'),
  ('2026-04-23', 'Sao Jorge',                       'estadual_rj'),
  ('2026-05-01', 'Dia do Trabalho',                 'nacional'),
  ('2026-06-04', 'Corpus Christi',                  'municipal_rio'),
  ('2026-09-07', 'Independencia do Brasil',         'nacional'),
  ('2026-10-12', 'Nossa Senhora Aparecida',         'nacional'),
  ('2026-11-02', 'Finados',                         'nacional'),
  ('2026-11-15', 'Proclamacao da Republica',        'nacional'),
  ('2026-11-20', 'Consciencia Negra',               'nacional'),
  ('2026-12-25', 'Natal',                           'nacional'),
  ('2027-01-01', 'Confraternizacao Universal',      'nacional'),
  ('2027-01-20', 'Sao Sebastiao',                   'municipal_rio'),
  ('2027-02-08', 'Carnaval',                        'municipal_rio'),
  ('2027-02-09', 'Carnaval',                        'municipal_rio'),
  ('2027-03-01', 'Aniversario da cidade do Rio',    'municipal_rio'),
  ('2027-03-26', 'Sexta-feira Santa',               'nacional'),
  ('2027-04-21', 'Tiradentes',                      'nacional'),
  ('2027-04-23', 'Sao Jorge',                       'estadual_rj'),
  ('2027-05-01', 'Dia do Trabalho',                 'nacional'),
  ('2027-05-27', 'Corpus Christi',                  'municipal_rio'),
  ('2027-09-07', 'Independencia do Brasil',         'nacional'),
  ('2027-10-12', 'Nossa Senhora Aparecida',         'nacional'),
  ('2027-11-02', 'Finados',                         'nacional'),
  ('2027-11-15', 'Proclamacao da Republica',        'nacional'),
  ('2027-11-20', 'Consciencia Negra',               'nacional'),
  ('2027-12-25', 'Natal',                           'nacional')
ON CONFLICT (data) DO NOTHING;

-- 4. A gravidade validada pelo ouvidor e o vencimento ja calculado.
--    O vencimento e PERSISTIDO, nao derivado: editar a tabela de prazos vale
--    para validacao nova, e caso ja despachado mantem o prazo que o setor
--    recebeu por email (criterio de aceite da #322).
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS gravidade     TEXT,
  ADD COLUMN IF NOT EXISTS prazo_area_em TIMESTAMPTZ;

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_gravidade_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_gravidade_check
  CHECK (gravidade IS NULL OR gravidade IN ('critico', 'alto', 'medio', 'baixo'));

COMMENT ON COLUMN ouvidoria_protocolos.gravidade IS
  'Gravidade validada pelo ouvidor (ADR 0034, decisao 10). NULL enquanto o caso nao foi classificado; a sugestao da Ana vive em classificacao_ia e nunca vem para ca sozinha.';
COMMENT ON COLUMN ouvidoria_protocolos.prazo_area_em IS
  'Vencimento do prazo da area, em UTC, calculado pelo motor no momento do acionamento. Congelado: mudanca posterior na tabela de prazos nao o recalcula.';

CREATE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_prazo_area
  ON ouvidoria_protocolos(prazo_area_em) WHERE prazo_area_em IS NOT NULL;

-- 5. RLS default-deny nas tabelas novas (padrao da casa: 009/041/051/063/064).
--    Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_prazos ENABLE ROW LEVEL SECURITY;
ALTER TABLE ouvidoria_prazos_historico ENABLE ROW LEVEL SECURITY;
ALTER TABLE ouvidoria_feriados ENABLE ROW LEVEL SECURITY;
