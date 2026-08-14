-- Migration 062: exames, cirurgias e convênios (Dados do Atendimento da Ana)
-- Issue #289, ADR 0031: as três tabelas de valores restantes que alimentam a Ana.
-- Colunas equivalentes ao export do NocoDB (sem remodelagem nesta passada),
-- mesmo padrão da 061 (consultas particulares).

CREATE TABLE IF NOT EXISTS exames (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome_exame TEXT NOT NULL UNIQUE,
  tipo_exame TEXT NOT NULL,
  convenio_aceito BOOLEAN NOT NULL DEFAULT FALSE,
  valor_particular_rs NUMERIC(10, 2) NOT NULL,
  requer_pedido_medico BOOLEAN NOT NULL DEFAULT FALSE,
  preparo_necessario BOOLEAN NOT NULL DEFAULT FALSE,
  instrucoes_preparo_completas TEXT NOT NULL DEFAULT '',
  tempo_resultado TEXT NOT NULL DEFAULT '',
  local_realizacao TEXT NOT NULL DEFAULT '',
  diferencial_1 TEXT NOT NULL DEFAULT '',
  diferencial_2 TEXT NOT NULL DEFAULT '',
  observacoes_ana TEXT NOT NULL DEFAULT '',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_atualizacao DATE NOT NULL DEFAULT CURRENT_DATE
);

COMMENT ON TABLE exames IS
  'Exames com valores, preparo e local que a Ana informa (ADR 0031). Casa dos dados: este app; o NocoDB se aposenta.';
COMMENT ON COLUMN exames.observacoes_ana IS
  'Instrucao de conversa para a Ana. Nao e exibida a pacientes como texto literal.';
COMMENT ON COLUMN exames.ativo IS
  'Somente registros ativos saem na API da Ana. Desativar preserva o historico sem apagar.';

-- RLS default-deny (padrao da casa: 009/041/051/057/060/061). Backend usa service_role.
ALTER TABLE exames ENABLE ROW LEVEL SECURITY;

-- Seed: import do export do NocoDB (gerado por app/scripts/import_tabelas_ana.py exames --sql
-- a partir de backend/tests/fixtures/export_nocodb_exames.csv).
-- Idempotente: nao sobrescreve edicoes feitas depois no admin.
-- Tipografia sanitizada no parse (ADR 0013): travessao do dado fonte vira virgula.
INSERT INTO exames (nome_exame, tipo_exame, convenio_aceito, valor_particular_rs, requer_pedido_medico, preparo_necessario, instrucoes_preparo_completas, tempo_resultado, local_realizacao, diferencial_1, diferencial_2, observacoes_ana, ativo, ultima_atualizacao)
VALUES
  ('Hemograma Completo', 'Laboratorial', TRUE, 45.00, TRUE, TRUE, 'Jejum de 4 horas. Água pode ser ingerida normalmente. Evitar atividade física intensa nas 24h anteriores.', '24 horas', 'Laboratório parceiro RIOLABOR', 'Coleta rápida e resultado em até 24h', 'Laudo acessível pelo portal do laboratório', 'Orientar acesso ao site do RIOLABOR para consulta do resultado.', TRUE, '2026-03-10'),
  ('Tomografia Computadorizada (TC)', 'Imagem', TRUE, 580.00, TRUE, TRUE, 'Preparo varia conforme região do corpo. Para TC de abdome: jejum de 4h. ATENÇÃO: TC com contraste iodado suspenso, confirmar modalidade disponível.', 'No ato / 48h', 'Hospital São Matheus, Imagem', 'Equipamento de última geração com alta resolução de imagem', 'Laudo por radiologista especializado integrado ao prontuário', 'ATENÇÃO: TC com contraste iodado suspenso. Informar ao paciente e confirmar modalidade disponível.', TRUE, '2026-03-10'),
  ('Ecocardiograma', 'Cardiológico', TRUE, 320.00, TRUE, FALSE, 'Não requer preparo especial. Usar roupas confortáveis.', 'No ato / 48h', 'Hospital São Matheus, Cardiologia', 'Exame realizado por cardiologista especializado em ecocardiografia', 'Resultado integrado ao prontuário para acompanhamento pelo médico assistente', 'Oferecer combo com consulta de Cardiologia quando pertinente.', TRUE, '2026-03-10'),
  ('Endoscopia Digestiva Alta', 'Endoscopia', TRUE, 480.00, TRUE, TRUE, 'Jejum absoluto de 8 horas (sólidos e líquidos). Medicamentos podem ser tomados com pequena quantidade de água, confirmar com médico.', 'No ato / 48h', 'Hospital São Matheus, Endoscopia', 'Equipe especializada em endoscopia digestiva de alta complexidade', 'Centro cirúrgico disponível no mesmo complexo para casos que evoluem para procedimento', 'Alertar sobre necessidade de acompanhante para sedação.', TRUE, '2026-03-10'),
  ('Colonoscopia', 'Endoscopia', TRUE, 580.00, TRUE, TRUE, 'Preparo intestinal completo obrigatório: dieta sem resíduos 2 dias antes + laxativo prescrito pelo médico. Jejum absoluto de 8h antes do exame.', 'No ato / 48h', 'Hospital São Matheus, Endoscopia', 'Procedimento realizado com sedação, conforto e segurança para o paciente', 'Centro cirúrgico e UTI disponíveis no mesmo complexo', 'Alertar sobre necessidade de acompanhante para sedação.', TRUE, '2026-03-10'),
  ('Eletrocardiograma (ECG)', 'Cardiológico', TRUE, 80.00, TRUE, FALSE, 'Não requer preparo especial. Usar roupas fáceis de remover na região do tórax. Evitar cremes ou óleos na pele.', 'No ato', 'Hospital São Matheus, Cardiologia', 'Resultado imediato integrado ao prontuário', 'Equipe treinada em cardiologia com suporte de especialista no mesmo complexo', 'Oferecer combo com consulta de Cardiologia quando pertinente.', TRUE, '2026-03-10'),
  ('Raio-X (RX)', 'Imagem', TRUE, 120.00, TRUE, FALSE, 'Preparo depende da região examinada. Geralmente sem preparo especial. Retirar acessórios metálicos e peças de roupa com metal antes do exame.', 'No ato / 24h', 'Hospital São Matheus, Imagem', 'Equipamento digital com alta resolução e menor exposição à radiação', 'Laudo por radiologista especializado integrado ao prontuário', 'Informar região do corpo a ser examinada para orientação correta.', TRUE, '2026-03-10'),
  ('Ultrassonografia Abdominal', 'Imagem', TRUE, 220.00, TRUE, TRUE, 'Jejum de 6 horas. Para ultrassom pélvico: bexiga cheia (ingerir 1 litro de água 1h antes sem urinar).', 'No ato / 48h', 'Hospital São Matheus, Imagem', 'Equipamento de última geração com transdutor de alta frequência', 'Laudo integrado ao prontuário eletrônico do hospital', 'Perguntar qual região será examinada para orientar preparo correto.', TRUE, '2026-03-10'),
  ('Holter 24h', 'Cardiológico', TRUE, 280.00, TRUE, FALSE, 'Não tomar banho no dia do exame. Evitar atividades que causem suor excessivo. Manter atividades normais para garantir registro real do ritmo cardíaco.', '48-72h após devolução', 'Hospital São Matheus, Cardiologia', 'Monitoramento contínuo de 24h para detecção de arritmias e alterações cardíacas', 'Laudo por cardiologista especializado integrado ao prontuário', 'Orientar paciente a anotar horários de sintomas durante o monitoramento.', TRUE, '2026-03-10'),
  ('MAPA 24h', 'Cardiológico', TRUE, 260.00, TRUE, FALSE, 'Manter atividades normais durante o período de monitoramento. Evitar exercícios que possam deslocar o aparelho. Manter braço parado nos momentos de medição automática.', '48h após devolução', 'Hospital São Matheus, Cardiologia', 'Monitoramento ambulatorial da pressão arterial durante 24h', 'Laudo integrado ao prontuário para acompanhamento pelo médico assistente', 'Orientar paciente a anotar atividades e sintomas durante o monitoramento.', TRUE, '2026-03-10')
ON CONFLICT (nome_exame) DO NOTHING;

CREATE TABLE IF NOT EXISTS cirurgias_estimativas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  procedimento TEXT NOT NULL UNIQUE,
  descricao_procedimento TEXT NOT NULL,
  honorarios_equipe_rs NUMERIC(10, 2) NOT NULL,
  valor_internacao_rs NUMERIC(10, 2) NOT NULL,
  estimativa_total_rs NUMERIC(10, 2) NOT NULL,
  o_que_inclui_honorarios TEXT NOT NULL DEFAULT '',
  o_que_inclui_internacao TEXT NOT NULL DEFAULT '',
  diferencial_1 TEXT NOT NULL DEFAULT '',
  diferencial_2 TEXT NOT NULL DEFAULT '',
  caveat_obrigatorio_ana TEXT NOT NULL,
  observacoes_ana TEXT NOT NULL DEFAULT '',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_atualizacao DATE NOT NULL DEFAULT CURRENT_DATE
);

COMMENT ON TABLE cirurgias_estimativas IS
  'Estimativas de cirurgias que a Ana informa (ADR 0031). Valores sao estimativas gerais, nunca orcamento final.';
COMMENT ON COLUMN cirurgias_estimativas.caveat_obrigatorio_ana IS
  'Texto que a Ana DEVE incluir sempre que informar a estimativa: valor final so apos avaliacao medica.';
COMMENT ON COLUMN cirurgias_estimativas.ativo IS
  'Somente registros ativos saem na API da Ana. Desativar preserva o historico sem apagar.';

ALTER TABLE cirurgias_estimativas ENABLE ROW LEVEL SECURITY;

-- Seed: import do export do NocoDB (gerado por app/scripts/import_tabelas_ana.py cirurgias_estimativas --sql
-- a partir de backend/tests/fixtures/export_nocodb_cirurgias_estimativas.csv).
INSERT INTO cirurgias_estimativas (procedimento, descricao_procedimento, honorarios_equipe_rs, valor_internacao_rs, estimativa_total_rs, o_que_inclui_honorarios, o_que_inclui_internacao, diferencial_1, diferencial_2, caveat_obrigatorio_ana, observacoes_ana, ativo, ultima_atualizacao)
VALUES
  ('Colecistectomia Videolaparoscópica', 'Cirurgia de retirada da vesícula biliar por técnica minimamente invasiva (videolaparoscopia), com 3 a 4 pequenas incisões.', 6000.00, 3000.00, 9000.00, 'Cirurgião principal, 2 auxiliares, instrumentador e anestesista', 'Centro cirúrgico, diária de internação hospitalar, materiais cirúrgicos e medicamentos durante internação', 'Técnica minimamente invasiva, menos dor, recuperação mais rápida e alta em 24 a 48h', 'Centro cirúrgico completo com UTI integrada, segurança em todo o processo', 'Esta é uma estimativa geral. O valor final é definido após avaliação médica individual e pode variar conforme materiais utilizados, tempo de internação e intercorrências. Nossa equipe elabora um orçamento personalizado após a consulta.', 'Após informar estimativa, sempre oferecer conexão com equipe para orçamento formal.', TRUE, '2026-03-10'),
  ('Apendicectomia Videolaparoscópica', 'Cirurgia de retirada do apêndice por videolaparoscopia, indicada em casos de apendicite aguda ou crônica.', 5500.00, 2800.00, 8300.00, 'Cirurgião, auxiliares, instrumentador, anestesista', 'Centro cirúrgico, internação, materiais e medicamentos', 'Cirurgia minimamente invasiva, recuperação acelerada e menor risco de infecção', 'Equipe de plantão disponível para urgências, incluindo apendicite aguda', 'Esta é uma estimativa geral. O valor final é definido após avaliação médica individual e pode variar conforme materiais utilizados, tempo de internação e intercorrências. Nossa equipe elabora um orçamento personalizado após a consulta.', 'Após informar estimativa, sempre oferecer conexão com equipe para orçamento formal.', TRUE, '2026-03-10'),
  ('Herniorrafia (Hérnia Inguinal)', 'Cirurgia de correção de hérnia inguinal, umbilical ou incisional com uso de tela cirúrgica.', 5000.00, 2500.00, 7500.00, 'Cirurgião, auxiliar, instrumentador, anestesista', 'Centro cirúrgico, internação, tela cirúrgica e materiais', 'Técnica com tela cirúrgica de baixo índice de recidiva', 'Centro cirúrgico completo e UTI disponíveis no mesmo complexo', 'Esta é uma estimativa geral. O valor final é definido após avaliação médica individual e pode variar conforme materiais utilizados, tempo de internação e intercorrências. Nossa equipe elabora um orçamento personalizado após a consulta.', 'Após informar estimativa, sempre oferecer conexão com equipe para orçamento formal.', TRUE, '2026-03-10')
ON CONFLICT (procedimento) DO NOTHING;

CREATE TABLE IF NOT EXISTS convenios_especialidade (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  convenio TEXT NOT NULL,
  especialidade TEXT NOT NULL,
  cobre BOOLEAN NOT NULL,
  observacao TEXT NOT NULL DEFAULT '',
  -- O export do NocoDB nao tem coluna Ativo: tudo entra ativo e o admin desativa depois
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_atualizacao DATE NOT NULL DEFAULT CURRENT_DATE,
  UNIQUE (convenio, especialidade)
);

COMMENT ON TABLE convenios_especialidade IS
  'Cobertura de convenios por especialidade que a Ana informa (ADR 0031). Cobertura de referencia, nao substitui autorizacao do plano.';
COMMENT ON COLUMN convenios_especialidade.ativo IS
  'Somente registros ativos saem na API da Ana. Desativar preserva o historico sem apagar.';

ALTER TABLE convenios_especialidade ENABLE ROW LEVEL SECURITY;

-- Seed: import do export do NocoDB (gerado por app/scripts/import_tabelas_ana.py convenios_especialidade --sql
-- a partir de backend/tests/fixtures/export_nocodb_convenios_especialidade.csv).
INSERT INTO convenios_especialidade (convenio, especialidade, cobre, observacao, ativo, ultima_atualizacao)
VALUES
  ('Bradesco Saúde', 'Cardiologia', TRUE, 'Cobre consultas e principais exames cardiológicos. Verificar procedimentos cirúrgicos individualmente.', TRUE, '2026-03-10'),
  ('Bradesco Saúde', 'Pediatria', TRUE, 'Cobre consultas pediátricas. Vacinas e procedimentos específicos sujeitos a verificação.', TRUE, '2026-03-10'),
  ('Bradesco Saúde', 'Ortopedia', TRUE, 'Cobre consultas e cirurgias ortopédicas de médio porte. Verificar cirurgias de alta complexidade.', TRUE, '2026-03-10'),
  ('Bradesco Saúde', 'Ginecologia', TRUE, 'Cobre consultas ginecológicas e preventivo. Procedimentos cirúrgicos sujeitos a autorização prévia.', TRUE, '2026-03-10'),
  ('Bradesco Saúde', 'Obstetrícia', TRUE, 'Cobre pré-natal e parto. Verificar cobertura para alto risco.', TRUE, '2026-03-10'),
  ('SulAmérica', 'Cardiologia', TRUE, 'Cobre consultas e exames cardiológicos. Cirurgias sujeitas a autorização prévia.', TRUE, '2026-03-10'),
  ('SulAmérica', 'Pediatria', TRUE, 'Cobre consultas pediátricas. Verificar exames específicos.', TRUE, '2026-03-10'),
  ('SulAmérica', 'Cirurgia Geral', TRUE, 'Cobre cirurgias gerais. Verificar complexidade e solicitar autorização prévia.', TRUE, '2026-03-10'),
  ('SulAmérica', 'Neurologia', TRUE, 'Cobre consultas neurológicas. Exames de imagem sujeitos a autorização.', TRUE, '2026-03-10'),
  ('Unimed', 'Cardiologia', TRUE, 'Cobre consultas, exames e cirurgias cardiológicas. Verificar plano específico.', TRUE, '2026-03-10'),
  ('Unimed', 'Pediatria', TRUE, 'Cobre consultas e exames pediátricos.', TRUE, '2026-03-10'),
  ('Unimed', 'Ortopedia', TRUE, 'Cobre consultas e cirurgias ortopédicas. Materiais especiais sujeitos a verificação.', TRUE, '2026-03-10'),
  ('Unimed', 'Ginecologia', TRUE, 'Cobre consultas e procedimentos ginecológicos. Verificar plano.', TRUE, '2026-03-10'),
  ('Unimed', 'Obstetrícia', TRUE, 'Cobre pré-natal e parto. Verificar cobertura para alto risco.', TRUE, '2026-03-10'),
  ('Amil', 'Cardiologia', TRUE, 'Cobre consultas e exames cardiológicos. Cirurgias sujeitas a autorização.', TRUE, '2026-03-10'),
  ('Amil', 'Cirurgia Geral', TRUE, 'Cobre cirurgias gerais. Procedimentos de alta complexidade sujeitos a autorização.', TRUE, '2026-03-10'),
  ('Amil', 'Neurologia', TRUE, 'Cobre consultas. Exames de alta complexidade sujeitos a autorização.', TRUE, '2026-03-10'),
  ('Golden Cross', 'Cardiologia', TRUE, 'Cobre consultas. Verificar cobertura de exames e cirurgias.', TRUE, '2026-03-10'),
  ('Golden Cross', 'Pediatria', TRUE, 'Cobre consultas pediátricas.', TRUE, '2026-03-10'),
  ('Particular (sem convênio)', 'Todas as especialidades', TRUE, 'Pagamento à vista ou parcelado. Verificar formas de pagamento aceitas.', TRUE, '2026-03-10')
ON CONFLICT (convenio, especialidade) DO NOTHING;
