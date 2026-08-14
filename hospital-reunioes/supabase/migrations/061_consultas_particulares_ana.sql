-- Migration 061: consultas particulares (Dados do Atendimento da Ana)
-- Issue #288, ADR 0031: primeira tabela dos dados que alimentam a Ana.
-- Colunas equivalentes ao export do NocoDB (sem remodelagem nesta passada).

CREATE TABLE IF NOT EXISTS consultas_particulares (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  especialidade TEXT NOT NULL UNIQUE,
  valor_rs NUMERIC(10, 2) NOT NULL,
  descricao_servico TEXT NOT NULL,
  diferencial_1 TEXT NOT NULL DEFAULT '',
  diferencial_2 TEXT NOT NULL DEFAULT '',
  diferencial_3 TEXT NOT NULL DEFAULT '',
  alta_demanda BOOLEAN NOT NULL DEFAULT FALSE,
  observacoes_ana TEXT NOT NULL DEFAULT '',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  ultima_atualizacao DATE NOT NULL DEFAULT CURRENT_DATE
);

COMMENT ON TABLE consultas_particulares IS
  'Precos e diferenciais das consultas particulares que a Ana informa (ADR 0031). Casa dos dados: este app; o NocoDB se aposenta.';
COMMENT ON COLUMN consultas_particulares.observacoes_ana IS
  'Instrucao de conversa para a Ana (combos, perguntas de direcionamento). Nao e exibida a pacientes como texto literal.';
COMMENT ON COLUMN consultas_particulares.ativo IS
  'Somente registros ativos saem na API da Ana. Desativar preserva o historico sem apagar.';

-- RLS default-deny (padrao da casa: 009/041/051/057/060). Backend usa service_role.
ALTER TABLE consultas_particulares ENABLE ROW LEVEL SECURITY;

-- Seed: import do export do NocoDB (gerado por app/scripts/import_consultas_particulares.py --sql
-- a partir de backend/tests/fixtures/export_nocodb_consultas_particulares.csv).
-- Idempotente: nao sobrescreve edicoes feitas depois no admin.
-- Tipografia sanitizada no parse (ADR 0013): travessao do dado fonte vira virgula.
INSERT INTO consultas_particulares (especialidade, valor_rs, descricao_servico, diferencial_1, diferencial_2, diferencial_3, alta_demanda, observacoes_ana, ativo, ultima_atualizacao)
VALUES
  ('Cardiologia', 380.00, 'Consulta com cardiologista adulto para avaliação clínica, prevenção e acompanhamento de doenças cardiovasculares.', 'Estrutura hospitalar completa com UTI e centro cirúrgico cardíaco no mesmo complexo', 'Equipe médica com formação e experiência em cardiologia de alta complexidade', 'Resultados de exames integrados, médico já acessa tudo na consulta', TRUE, 'Oferecer combo com Ecocardiograma ou Holter quando pertinente.', TRUE, '2026-03-10'),
  ('Pediatria', 320.00, 'Consulta pediátrica para crianças de 0 a 14 anos com médico especializado.', 'PS Pediátrico 24h no mesmo hospital, segurança em caso de urgência', 'Atendimento acolhedor, pensado para o conforto da criança e da família', 'Integração com exames e vacinas no mesmo complexo', TRUE, 'Oferecer combo Cardiopediatria + Ecocardiograma pediátrico quando pertinente.', TRUE, '2026-03-10'),
  ('Ortopedia', 350.00, 'Consulta com ortopedista para avaliação de ossos, articulações, coluna e medicina esportiva.', 'PS Ortopédico 24h, médico disponível para urgências imediatamente', 'Centro cirúrgico ortopédico completo para casos que evoluem para cirurgia', 'Reabilitação e fisioterapia disponíveis no mesmo complexo', FALSE, 'Perguntar se há queixa específica (joelho, coluna, ombro) para direcionar melhor.', TRUE, '2026-03-10'),
  ('Cirurgia Geral', 350.00, 'Consulta pré-operatória ou de avaliação com cirurgião geral.', 'Centro cirúrgico de alta complexidade com UTI pós-operatória integrada', 'Equipe treinada em cirurgia minimamente invasiva por videolaparoscopia', 'Acompanhamento pré e pós-operatório no mesmo hospital', FALSE, 'Para pacientes com interesse em cirurgia: consultar Aba 3, Cirurgias_Estimativas.', TRUE, '2026-03-10'),
  ('Ginecologia', 340.00, 'Consulta ginecológica para prevenção, saúde da mulher e acompanhamento clínico.', 'Estrutura hospitalar completa incluindo Maternidade integrada', 'Equipe feminina disponível, informar ao paciente se solicitar', 'Centro cirúrgico e internação disponíveis no mesmo complexo', FALSE, 'Mencionar Maternidade quando pertinente.', FALSE, '2026-03-10'),
  ('Obstetrícia', 360.00, 'Consulta de pré-natal e acompanhamento gestacional com obstetra.', 'Maternidade de alto risco integrada ao hospital, parto e emergência obstétrica no mesmo local', 'UTI Neonatal disponível, segurança completa para mãe e bebê', 'Pré-natal de alto risco com equipe multidisciplinar', TRUE, 'Mencionar Maternidade e UTI Neonatal. Enviar vídeo/material da Maternidade se disponível.', TRUE, '2026-03-10'),
  ('Neurologia', 380.00, 'Consulta neurológica para avaliação de cérebro, coluna vertebral e sistema nervoso.', 'Equipe neurológica com suporte de neuroimagem no mesmo complexo', 'Integração com tomografia e ressonância para diagnóstico ágil', 'UTI disponível para casos de maior complexidade neurológica', FALSE, 'Verificar disponibilidade do especialista antes de confirmar agendamento.', TRUE, '2026-03-10'),
  ('Urologia', 350.00, 'Consulta urológica para avaliação do sistema urinário e saúde masculina.', 'Centro cirúrgico completo para casos que evoluam para procedimento', 'Exames urológicos realizados no mesmo complexo hospitalar', 'Equipe com experiência em cirurgia minimamente invasiva urológica', FALSE, 'Oferecer exame de PSA quando pertinente para pacientes masculinos acima de 40 anos.', TRUE, '2026-03-10'),
  ('Oftalmologia', 320.00, 'Consulta oftalmológica para avaliação da saúde ocular e da visão.', 'Equipamentos de diagnóstico ocular de última geração disponíveis', 'Exames complementares como tonometria e mapeamento de retina no local', 'Laudos integrados ao prontuário eletrônico do hospital', FALSE, 'Verificar quais exames diagnósticos são realizados no local antes de confirmar.', TRUE, '2026-03-10'),
  ('Dermatologia', 320.00, 'Consulta dermatológica para pele, cabelo, unhas e tratamentos estéticos médicos.', 'Dermatoscopia digital disponível no mesmo local', 'Laudos integrados ao prontuário eletrônico do hospital', 'Possibilidade de biópsia e procedimentos menores na mesma consulta', FALSE, 'Mencionar dermatoscopia digital como diferencial diagnóstico.', TRUE, '2026-03-10')
ON CONFLICT (especialidade) DO NOTHING;
