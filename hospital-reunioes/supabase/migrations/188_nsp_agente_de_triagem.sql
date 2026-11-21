-- =====================================================
-- Migration 188: o agente de triagem do Núcleo
-- (issue #1990, PRD #1979, ADR 0095 decisões 5, 7 e 8; ADR 0107 decisões 9 e 11)
-- =====================================================
-- O que entra:
--   1. a configuração do agente: as 19 categorias de incidente e os 30
--      eventos que nunca deveriam ocorrer (lista ANVISA 2025), como estão na
--      base de conhecimento (Anexo A). O validador do app tem as mesmas
--      listas, e o teste confere que as três dizem a mesma coisa;
--   2. a triagem: uma linha por rodada do agente (e, na tela de triagem, uma
--      pela decisão da pessoa), com os campos do formato de saída do Anexo B
--      e as versões do prompt, da base e do modelo. A versão da linha sai do
--      banco, em sequência por notificação;
--   3. a notificação ganha a marca "classificar manualmente", com o motivo:
--      agente fora, teto do dia ou duas saídas inválidas. A marca é edição da
--      notificação e entra na trilha da migration 174;
--   4. a cota diária do agente do Núcleo, à parte da cota da Ouvidoria
--      (migration 143): `nsp_agente_reservar_chamada` soma uma chamada ao dia
--      corrente (fuso do hospital) só se ainda houver vaga, num comando só.
--
-- Nenhuma pessoa entra por aqui. RLS ligado e sem política nas tabelas novas:
-- só o backend, com a service_role, lê e grava; a função da cota só pode ser
-- chamada pela service_role. Rodar duas vezes é inofensivo. Aplicar à mão no
-- Studio.
-- =====================================================

BEGIN;

-- ---------- 1. A configuração do agente ----------
CREATE TABLE IF NOT EXISTS nsp_categorias (
  codigo      TEXT PRIMARY KEY CHECK (codigo ~ '^[A-Z]{3}$'),
  nome        TEXT NOT NULL,
  incidentes  TEXT NOT NULL,
  ordem       SMALLINT NOT NULL UNIQUE
);

COMMENT ON TABLE nsp_categorias IS
  'As 19 categorias de incidente da base de conhecimento do agente do Núcleo (Anexo A, seção 4). Issue #1990.';

ALTER TABLE nsp_categorias ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS nsp_eventos_que_nunca_deveriam_ocorrer (
  item                        SMALLINT PRIMARY KEY CHECK (item BETWEEN 1 AND 30),
  evento                      TEXT NOT NULL,
  exige_obito_ou_lesao_grave  BOOLEAN NOT NULL
);

COMMENT ON TABLE nsp_eventos_que_nunca_deveriam_ocorrer IS
  'A lista ANVISA 2025 dos 30 eventos que nunca deveriam ocorrer (Anexo A, seção 5). Issue #1990.';
COMMENT ON COLUMN nsp_eventos_que_nunca_deveriam_ocorrer.exige_obito_ou_lesao_grave IS
  'Verdadeiro nos itens que só entram na lista com óbito ou lesão grave (7 e 11 a 22).';

ALTER TABLE nsp_eventos_que_nunca_deveriam_ocorrer ENABLE ROW LEVEL SECURITY;

INSERT INTO nsp_categorias (codigo, nome, incidentes, ordem) VALUES
  ('IDP', 'Identificação do paciente', 'Sem pulseira ou pulseira errada · homônimos sem alerta · procedimento, exame ou documento no paciente errado · amostra mal identificada', 1),
  ('MED', 'Medicamentos e soluções', 'Prescrição · dispensação · preparo · administração (paciente, medicamento, dose, via, horário ou velocidade errados) · omissão ou atraso · alergia conhecida ignorada · extravasamento · armazenamento e medicamentos de alta vigilância', 2),
  ('SAN', 'Sangue e hemocomponentes', 'Transfusão no paciente errado ou incompatível · falha de checagem · tempo ou conservação inadequados · reação transfusional', 3),
  ('CIR', 'Cirurgia e anestesia', 'Local, lado, paciente ou procedimento errado · retenção de corpo estranho · falha na lista de verificação · intercorrência anestésica · queimadura por bisturi elétrico', 4),
  ('PRO', 'Processo clínico e cuidado', 'Atraso ou falha de diagnóstico ou tratamento · deterioração clínica não reconhecida · falha de monitoramento · cuidado omitido · contenção inadequada · falha na classificação de risco', 5),
  ('QUE', 'Quedas', 'Do leito · da maca ou cadeira · no banheiro · ao deambular · durante transporte', 6),
  ('LPP', 'Lesão por pressão e pele', 'Lesão por pressão (com estágio) · falha de prevenção · lesão por adesivo ou dispositivo', 7),
  ('DIS', 'Dispositivos invasivos', 'Perda acidental de cateter, sonda, dreno ou tubo · extubação não planejada · flebite · obstrução · conexão errada', 8),
  ('INF', 'Infecção', 'IRAS (corrente sanguínea, sítio cirúrgico, pneumonia, urinária) · falha de higiene das mãos · falha de precaução ou isolamento · surto', 9),
  ('EXA', 'Exames e diagnóstico', 'Resultado crítico não comunicado · amostra perdida, trocada ou sem identificação · exame errado ou no lado errado · laudo atrasado', 10),
  ('EQP', 'Equipamentos e materiais', 'Falha ou indisponibilidade de equipamento · alarme inoperante · defeito de material', 11),
  ('GAS', 'Oxigênio e gases medicinais', 'Gás errado · contaminação · falta ou interrupção · falha de rede', 12),
  ('NUT', 'Dieta e nutrição', 'Dieta errada ou alergia alimentar · quebra de jejum · tempo de infusão · broncoaspiração', 13),
  ('COM', 'Comunicação e documentação', 'Passagem de plantão · registro em prontuário errado · consentimento ausente · ordem verbal mal entendida', 14),
  ('ACE', 'Acesso, transferência e alta', 'Evasão ou fuga · alta a pessoa não autorizada · atraso de transferência · transporte inseguro · documento de alta errado', 15),
  ('CMP', 'Comportamento', 'Autolesão ou tentativa de suicídio · agressão por paciente · conduta de profissional (ver roteamento)', 16),
  ('EST', 'Estrutura e ambiente', 'Energia elétrica · incêndio · piso, mobiliário e instalações · choque elétrico', 17),
  ('MAT', 'Materno-infantil', 'Intercorrência de parto · queda de recém-nascido · troca de bebês · identificação do binômio', 18),
  ('OUT', 'Outros', 'Usar só quando nenhuma categoria servir, com justificativa', 19)
ON CONFLICT (codigo) DO UPDATE SET nome = EXCLUDED.nome, incidentes = EXCLUDED.incidentes, ordem = EXCLUDED.ordem;

INSERT INTO nsp_eventos_que_nunca_deveriam_ocorrer (item, evento, exige_obito_ou_lesao_grave) VALUES
  (1, 'Alta ou liberação de paciente incapaz de tomar decisões para pessoa não autorizada', false),
  (2, 'Contaminação na administração de oxigênio ou gases medicinais', false),
  (3, 'Desaparecimento do corpo de recém-nascido que foi a óbito', false),
  (4, 'Exodontia de dente errado', false),
  (5, 'Gás errado na administração de oxigênio ou gases medicinais', false),
  (6, 'Inseminação artificial ou fertilização in vitro com esperma ou óvulo errado', false),
  (7, 'Lesão grave associada a queda do paciente durante o atendimento', true),
  (8, 'Lesão por pressão estágio 3', false),
  (9, 'Lesão por pressão estágio 4', false),
  (10, 'Lesão por pressão não classificável', false),
  (11, 'Óbito associado a queda do paciente durante o atendimento', true),
  (12, 'Óbito intraoperatório ou imediatamente após cirurgia ou procedimento em paciente ASA 1', true),
  (13, 'Óbito ou lesão grave associados a fuga do paciente', true),
  (14, 'Óbito ou lesão grave associados a choque elétrico durante a assistência', true),
  (15, 'Óbito ou lesão grave de paciente ou colaborador por objeto metálico em área de ressonância magnética', true),
  (16, 'Óbito ou lesão grave associados a contenção física ou grades da cama', true),
  (17, 'Óbito ou lesão grave associados a queimadura de qualquer fonte durante a assistência', true),
  (18, 'Óbito ou lesão grave por perda irrecuperável de amostra biológica insubstituível', true),
  (19, 'Óbito ou lesão grave de recém-nascido no trabalho de parto ou parto em gestação de baixo risco', true),
  (20, 'Óbito ou lesão grave por falha no acompanhamento ou na comunicação de resultado de exame laboratorial ou de patologia clínica', true),
  (21, 'Óbito ou lesão grave por falha no acompanhamento ou na comunicação de resultado de exame radiológico', true),
  (22, 'Óbito ou lesão materna grave no trabalho de parto ou parto em gestação de baixo risco', true),
  (23, 'Procedimento cirúrgico em local errado', false),
  (24, 'Procedimento cirúrgico no lado errado do corpo', false),
  (25, 'Procedimento cirúrgico no paciente errado', false),
  (26, 'Queda de recém-nascido durante o parto', false),
  (27, 'Cirurgia errada em um paciente', false),
  (28, 'Retenção não intencional de corpo estranho após cirurgia', false),
  (29, 'Suicídio, tentativa de suicídio ou dano autoinfligido com lesão grave durante a assistência', false),
  (30, 'Troca de bebês', false)
ON CONFLICT (item) DO UPDATE SET evento = EXCLUDED.evento, exige_obito_ou_lesao_grave = EXCLUDED.exige_obito_ou_lesao_grave;

-- ---------- 2. A triagem ----------
CREATE TABLE IF NOT EXISTS nsp_triagens (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notificacao_id            UUID NOT NULL REFERENCES nsp_notificacoes(id) ON DELETE RESTRICT,
  versao                    INTEGER NOT NULL CHECK (versao > 0),
  autor_tipo                TEXT NOT NULL CHECK (autor_tipo IN ('agente', 'pessoa')),
  assunto                   TEXT NOT NULL CHECK (char_length(assunto) <= 300),
  natureza                  TEXT NOT NULL CHECK (natureza IN ('circunstancia_de_risco', 'quase_erro', 'incidente_sem_dano', 'evento_adverso', 'nao_e_do_nsp', 'indeterminada')),
  grau_de_dano              TEXT NOT NULL CHECK (grau_de_dano IN ('nenhum', 'leve', 'moderado', 'grave', 'obito', 'nao_se_aplica')),
  categoria                 TEXT NOT NULL REFERENCES nsp_categorias(codigo) ON DELETE RESTRICT,
  incidente                 TEXT,
  evento_situacao           TEXT NOT NULL CHECK (evento_situacao IN ('sim', 'possivel', 'nao')),
  evento_item               SMALLINT REFERENCES nsp_eventos_que_nunca_deveriam_ocorrer(item) ON DELETE RESTRICT,
  evento_motivo             TEXT,
  iras                      BOOLEAN NOT NULL,
  risco_de_imagem           BOOLEAN NOT NULL,
  protocolo_basico          TEXT NOT NULL CHECK (protocolo_basico IN ('identificacao', 'higiene_das_maos', 'cirurgia_segura', 'medicamentos', 'quedas', 'lesao_por_pressao', 'nenhum')),
  canais                    TEXT[] NOT NULL CHECK (cardinality(canais) > 0 AND canais <@ ARRAY['NSP', 'OUV', 'COND', 'SST', 'QT', 'FORA']),
  motivo_do_encaminhamento  TEXT,
  faixa                     TEXT NOT NULL CHECK (faixa IN ('A', 'B', 'C', 'D', 'E', 'nao_se_aplica')),
  revisao                   TEXT NOT NULL CHECK (revisao IN ('campo_a_campo', 'confirmacao_simples')),
  justificativa             TEXT,
  confianca                 TEXT CHECK (confianca IN ('alta', 'media', 'baixa')),
  motivo_da_confianca       TEXT,
  alertas                   TEXT[] NOT NULL DEFAULT '{}',
  perguntas_ao_notificante  TEXT[] NOT NULL DEFAULT '{}' CHECK (cardinality(perguntas_ao_notificante) <= 2),
  prompt_versao             TEXT,
  base_versao               TEXT,
  modelo                    TEXT,
  tentativas                SMALLINT CHECK (tentativas BETWEEN 1 AND 2),
  criado_em                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (notificacao_id, versao),
  CHECK ((evento_situacao = 'nao') = (evento_item IS NULL)),
  CHECK (autor_tipo <> 'agente' OR (prompt_versao IS NOT NULL AND base_versao IS NOT NULL AND modelo IS NOT NULL AND tentativas IS NOT NULL))
);

COMMENT ON TABLE nsp_triagens IS
  'A triagem da notificação do Núcleo: uma linha por rodada do agente e uma pela decisão da pessoa, com as versões do prompt, da base e do modelo. Issue #1990.';
COMMENT ON COLUMN nsp_triagens.versao IS
  'A ordem da linha na notificação (1, 2, 3...). Sai do trigger no insert.';
COMMENT ON COLUMN nsp_triagens.tentativas IS
  'Na linha do agente: 1, ou 2 quando a primeira saída falhou na validação e foi refeita.';

CREATE INDEX IF NOT EXISTS idx_nsp_triagens_notificacao ON nsp_triagens (notificacao_id, versao DESC);
CREATE INDEX IF NOT EXISTS idx_nsp_triagens_categoria ON nsp_triagens (categoria);
CREATE INDEX IF NOT EXISTS idx_nsp_triagens_evento_item ON nsp_triagens (evento_item);

ALTER TABLE nsp_triagens ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION nsp_triagem_versao() RETURNS TRIGGER AS $$
BEGIN
  -- Duas rodadas da mesma notificação ao mesmo tempo esperam uma pela outra.
  PERFORM pg_advisory_xact_lock(hashtext('nsp_triagens:' || NEW.notificacao_id::text));
  SELECT coalesce(max(versao), 0) + 1 INTO NEW.versao
    FROM nsp_triagens WHERE notificacao_id = NEW.notificacao_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

DROP TRIGGER IF EXISTS trg_nsp_triagem_versao ON nsp_triagens;
CREATE TRIGGER trg_nsp_triagem_versao
  BEFORE INSERT ON nsp_triagens
  FOR EACH ROW EXECUTE FUNCTION nsp_triagem_versao();

-- ---------- 3. A marca "classificar manualmente" ----------
ALTER TABLE nsp_notificacoes
  ADD COLUMN IF NOT EXISTS classificar_manualmente BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE nsp_notificacoes
  ADD COLUMN IF NOT EXISTS motivo_classificar_manualmente TEXT
    CHECK (motivo_classificar_manualmente IN ('agente_fora', 'teto', 'validacao'));

ALTER TABLE nsp_notificacoes DROP CONSTRAINT IF EXISTS nsp_notificacoes_classificar_manualmente_motivo;
ALTER TABLE nsp_notificacoes
  ADD CONSTRAINT nsp_notificacoes_classificar_manualmente_motivo
  CHECK (classificar_manualmente = (motivo_classificar_manualmente IS NOT NULL));

COMMENT ON COLUMN nsp_notificacoes.classificar_manualmente IS
  'Verdadeiro quando o agente de triagem não deixou sugestão: a coordenação classifica do zero. Issue #1990.';
COMMENT ON COLUMN nsp_notificacoes.motivo_classificar_manualmente IS
  'agente_fora (desligado, sem chave ou sem resposta), teto (cota do dia) ou validacao (duas saídas inválidas).';

-- ---------- 4. A cota diária do agente do Núcleo ----------
CREATE TABLE IF NOT EXISTS nsp_agente_cota (
  dia       DATE PRIMARY KEY,
  chamadas  INTEGER NOT NULL DEFAULT 0 CHECK (chamadas >= 0)
);

ALTER TABLE nsp_agente_cota ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE nsp_agente_cota IS
  'Quantas chamadas o agente de triagem do Núcleo fez em cada dia, à parte da Ouvidoria (ADR 0107, decisão 11). Só o backend lê e escreve.';

CREATE OR REPLACE FUNCTION nsp_agente_reservar_chamada(p_teto INTEGER)
RETURNS TABLE (reservada BOOLEAN)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_dia DATE := (now() AT TIME ZONE 'America/Sao_Paulo')::date;
BEGIN
  INSERT INTO nsp_agente_cota AS cota (dia, chamadas)
  VALUES (v_dia, 1)
  ON CONFLICT (dia) DO UPDATE
    SET chamadas = cota.chamadas + 1
    WHERE cota.chamadas < p_teto;
  -- FOUND é falso quando o WHERE do ON CONFLICT barrou a soma: o teto do dia.
  reservada := FOUND AND p_teto > 0;
  RETURN NEXT;
END;
$$;

REVOKE EXECUTE ON FUNCTION nsp_agente_reservar_chamada(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION nsp_agente_reservar_chamada(INTEGER) TO service_role;

COMMENT ON FUNCTION nsp_agente_reservar_chamada(INTEGER) IS
  'Reserva uma chamada do agente de triagem do Núcleo no dia corrente, se a cota do dia ainda tem vaga. Devolve reservada = false no teto.';

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (188) ON CONFLICT (numero) DO NOTHING;
