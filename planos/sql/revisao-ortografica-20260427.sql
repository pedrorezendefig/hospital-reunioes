-- =================================================================
-- REVISÃO ORTOGRÁFICA EM MASSA — Hospital Reuniões
-- Gerado: 2026-04-27 17:28
-- Escopo: Camada 1 (texto plano)
--   - reunioes.{titulo, objetivo}
--   - pendencias.{descricao_acao, meta_entregavel, cargo}
--   - participantes.{cargo, nome_completo, setor}
-- Volume: 27 reuniões, ~140 pendências, 12 participantes (~180 UPDATEs)
-- Política: conservadora — só adiciona acentos/cedilha/til/crase/ordinais.
--          Nomes próprios e siglas passam intactos.
-- =================================================================

\set ON_ERROR_STOP on

BEGIN;

-- =================================================================
-- BACKUP — tabelas de rollback rápido
-- (drop manual após 30 dias: DROP TABLE *_backup_ortografia_20260427)
-- =================================================================

CREATE TABLE IF NOT EXISTS pendencias_backup_ortografia_20260427    AS TABLE pendencias;
CREATE TABLE IF NOT EXISTS participantes_backup_ortografia_20260427 AS TABLE participantes;
CREATE TABLE IF NOT EXISTS reunioes_backup_ortografia_20260427      AS TABLE reunioes;

-- =================================================================
-- REUNIÕES (27 ATAs migradas)
-- =================================================================

UPDATE reunioes SET
  objetivo = 'A reunião teve por objetivo revisar o cronograma de execução do cabeamento estruturado pela empresa Cyber, definir os setores prioritários para intervenção imediata e estabelecer logística de obras de forma a garantir que todos os setores críticos estejam operacionais em rede até a migração do sistema MV em 28 de março de 2026.'
WHERE id_reuniao = 'MIG_20260303_033813A9';

UPDATE reunioes SET
  titulo = 'Planejamento do remanejamento provisório do CTI 3',
  objetivo = 'Planejar o remanejamento provisório do CTI 3 para o setor 3A, com conclusão das intervenções de infraestrutura até 13/03/2026, viabilizando o início da reforma estrutural do CTI 3 em 16/03/2026.'
WHERE id_reuniao = 'MIG_20260310_0122323C';

UPDATE reunioes SET
  objetivo = 'Inaugurar o modelo de reuniões semanais de alinhamento operacional da manutenção, apresentar o formulário de atendimento de chamados e tratar as principais demandas de infraestrutura da semana.'
WHERE id_reuniao = 'MIG_20260310_0122339C';

UPDATE reunioes SET
  objetivo = 'Alinhar a distribuição das funções do setor de Credenciamento durante o período de licença maternidade da Coordenadora Camila, garantindo a continuidade das negociações com operadoras e o andamento do cadastro no sistema MV.'
WHERE id_reuniao = 'MIG_20260312_012233B1';

UPDATE reunioes SET
  objetivo = 'A reunião teve por objetivo realizar o seguimento (follow-up) das atribuições assumidas nas atas anteriores de cada diretoria, alinhar decisões operacionais urgentes relativas a infraestrutura, financeiro e gestão médica, e deliberar sobre pendências críticas — em especial a situação do QTA do gerador, a reforma do CTI e a estruturação do processo de recuperação judicial.'
WHERE id_reuniao = 'MIG_20260313_0122338A';

UPDATE reunioes SET
  objetivo = 'Realizar a segunda reunião semanal da equipe de manutenção, revisar o quadro de atribuições da semana anterior e definir as prioridades operacionais para a semana corrente.'
WHERE id_reuniao = 'MIG_20260316_0122337F';

UPDATE reunioes SET
  objetivo = 'Apresentar os indicadores de contas a receber por operadora de saúde, identificar valores em aberto, bloqueios judiciais e dificuldades de comunicação com convênios, e definir plano de ação para cobrança e melhoria do setor.'
WHERE id_reuniao = 'MIG_20260317_01223381';

UPDATE reunioes SET
  objetivo = 'Apresentar os indicadores de recurso de glosas por operadora, identificar os principais motivos de glosa, discutir dificuldades operacionais do setor e alinhar programa de educação continuada para redução de glosas evitáveis.'
WHERE id_reuniao = 'MIG_20260317_0122339E';

UPDATE reunioes SET
  titulo = 'Repasse Médico — Indicadores',
  objetivo = 'Apresentar os indicadores de repasse médico de 2025 e início de 2026, alinhar o modelo de trabalho e identificar dificuldades operacionais do setor, incluindo a integração com o sistema MV e as pendências com a Clin Carioca.'
WHERE id_reuniao = 'MIG_20260317_012233D8';

UPDATE reunioes SET
  titulo = 'Apresentação de Indicadores Financeiros',
  objetivo = 'Apresentar os indicadores financeiros referentes ao mês de janeiro de 2026, identificar as principais dificuldades operacionais da gerência financeira e alinhar melhorias no modelo de trabalho e relatórios.'
WHERE id_reuniao = 'MIG_20260317_012233DD';

UPDATE reunioes SET
  objetivo = 'Apresentar os indicadores operacionais e de custos do hospital, discutir as medidas necessárias em relação ao problema da dedetização, alinhar o modelo de trabalho das reuniões mensais e intermediárias e identificar gargalos operacionais da administração.'
WHERE id_reuniao = 'MIG_20260318_0122337C';

UPDATE reunioes SET
  titulo = 'Reunião Mensal de Gerência — DP e RH'
WHERE id_reuniao = 'MIG_20260318_012233F6';

UPDATE reunioes SET
  objetivo = 'Alinhar o desempenho operacional do Call Center e do setor de agendamento, apresentar indicadores de atendimento telefônico e marcação, identificar gargalos, e pactar ações de melhoria com foco em conversão e tecnologia.'
WHERE id_reuniao = 'MIG_20260319_01223280';

UPDATE reunioes SET
  objetivo = 'Avaliar o fluxo de internação e prorrogação, identificar gargalos na liberação de leitos e no processo de autorização com operadoras, e definir ações para melhoria da rotatividade e do faturamento.'
WHERE id_reuniao = 'MIG_20260320_01223329';

UPDATE reunioes SET
  objetivo = 'Avaliar o fluxo de atendimento e os indicadores das emergências e dos setores de imagem, identificar gargalos na jornada do paciente e pactar ações de melhoria para redução do tempo de espera e das evasões.'
WHERE id_reuniao = 'MIG_20260320_01354361';

UPDATE reunioes SET
  objetivo = 'Alinhar a gestão do Centro Médico, revisar indicadores de produção médica e agendamentos, discutir estratégias de recuperação da demanda e motivação da equipe, e definir ações para o projeto particular e retorno dos médicos.'
WHERE id_reuniao = 'MIG_20260323_01223266';

UPDATE reunioes SET
  titulo = 'Revisão do quadro de atribuições, quadros elétricos, CTI-3 (reforma), ar-condicionados, laje',
  objetivo = 'Revisar o quadro de atribuições da semana anterior, atualizar o status das obras e intervenções em curso e definir as prioridades operacionais de manutenção e infraestrutura para a semana.'
WHERE id_reuniao = 'MIG_20260323_01223393';

UPDATE reunioes SET
  objetivo = 'Alinhar a gestão operacional das equipes de apoio, maqueiros e controle de acesso, apresentar indicadores de produtividade e fluxo de pessoas, discutir dificuldades de gestão de equipe e definir ações de melhoria.'
WHERE id_reuniao = 'MIG_20260324_0122337B';

UPDATE reunioes SET
  objetivo = 'Alinhar o andamento do cadastro no sistema MV, discutir dificuldades de credenciamento com operadoras, planejar a transição para a licença maternidade e definir prioridades do setor.'
WHERE id_reuniao = 'MIG_20260326_01223393';

UPDATE reunioes SET
  objetivo = 'Alinhar a gestão do setor de compras, apresentar indicadores de redução de custos e desafios operacionais, e definir estratégias para melhoria do abastecimento, diversificação de fornecedores e contratação de assistente.'
WHERE id_reuniao = 'MIG_20260327_01223255';

UPDATE reunioes SET
  objetivo = 'Realizar o primeiro alinhamento com a Coordenação de Faturamento, identificar dificuldades operacionais críticas, discutir o impacto do novo sistema MV e definir ações para estabilização e melhoria do setor.'
WHERE id_reuniao = 'MIG_20260327_013543D2';

UPDATE reunioes SET
  titulo = 'Revisão do quadro de atribuições, elétrica do CTI, telhado CTI 3, farmácia antiga e pendências',
  objetivo = 'Revisar o quadro de atribuições da reunião anterior, verificar o status de execução de cada item, deliberar sobre encaminhamentos operacionais e tratar de novos temas relacionados a infraestrutura, manutenção predial e obras em andamento — com ênfase nas intervenções no CTI 3, na farmácia antiga e nos contratos de prestadores externos.'
WHERE id_reuniao = 'MIG_20260330_01223318';

UPDATE reunioes SET
  titulo = 'Reunião Intermediária de Acompanhamento da Gerência Financeira',
  objetivo = 'Promover o acompanhamento intermediário das pautas financeiras em andamento, revisar o status de compromissos assumidos na última reunião mensal, deliberar sobre ações urgentes nos setores Financeiro e de Compras, e alinhar encaminhamentos operacionais para a semana.'
WHERE id_reuniao = 'MIG_20260406_01223313';

UPDATE reunioes SET
  objetivo = 'Revisar o andamento das pendências registradas na última ata, acompanhar temas operacionais e de custos em aberto, deliberar sobre contratos, manutenções de equipamentos, conformidades regulatórias e ações de infraestrutura do hospital.'
WHERE id_reuniao = 'MIG_20260407_01223381';

UPDATE reunioes SET
  objetivo = 'Apresentar aos encarregados de Higienização e Hotelaria o novo modelo de reuniões, coletar percepções da equipe sobre as mudanças organizacionais em curso e alinhar os encaminhamentos para a próxima reunião mensal.'
WHERE id_reuniao = 'MIG_20260410_0122331C';

UPDATE reunioes SET
  titulo = 'Acompanhamento Operacional da Coordenação de Apoio e Maqueiros',
  objetivo = 'Realizar acompanhamento intermediário da Coordenação de Apoio, abordando a alocação e proatividade dos maqueiros, treinamentos, controle de acesso e melhorias no fluxo de atendimento ao paciente.'
WHERE id_reuniao = 'MIG_20260410_01223387';

UPDATE reunioes SET
  titulo = 'Revisão de pendências e alinhamento operacional da Coordenação de Emergência e Imagens',
  objetivo = 'Revisar as pendências registradas na última reunião mensal relativas à Coordenação de Emergência e Imagens, verificar o andamento das ações em curso e alinhar os pontos que serão apresentados na próxima reunião mensal de 24 de abril de 2026.'
WHERE id_reuniao = 'MIG_20260413_01223366';

-- =================================================================
-- PENDÊNCIAS (~140 ações com correção)
-- =================================================================

-- ATA MIG_20260303_033813A9 (TI/Infra)
UPDATE pendencias SET descricao_acao='Conclusão dos serviços de rede no PSI (Pediatria)', meta_entregavel='PSI 100% concluído', cargo='Técnico Sênior' WHERE id_acao='A003';
UPDATE pendencias SET descricao_acao='Execução de infraestrutura de rede no CTI 3 (janela de obras civis)', cargo='Técnico Sênior' WHERE id_acao='A004';
UPDATE pendencias SET descricao_acao='Execução do cabeamento no corredor do PSA (noturno, após 20h)', meta_entregavel='Espinha dorsal do PSA concluída', cargo='Técnico Sênior' WHERE id_acao='A005';
UPDATE pendencias SET descricao_acao='Execução do cabeamento nos consultórios do PSA', cargo='Técnico Sênior' WHERE id_acao='A006';
UPDATE pendencias SET descricao_acao='Reunião de alinhamento da 2ª etapa do Centro Cirúrgico', meta_entregavel='2ª etapa planejada e aprovada' WHERE id_acao='A007';
UPDATE pendencias SET descricao_acao='Designar coordenador responsável por validar paralisações durante obras', meta_entregavel='Responsável nomeado e comunicado à Cyber' WHERE id_acao='A008';

-- ATA MIG_20260310_0122323C (CTI 3 provisório)
UPDATE pendencias SET descricao_acao='Realizar pente fino quarto a quarto nos setores 3B, 2A e 2B; reportar quartos não aptos', meta_entregavel='Relatório com quartos não aptos entregue à equipe de infraestrutura' WHERE id_acao='A009';
UPDATE pendencias SET descricao_acao='Remanejar material do Arsenal da LAC para berçário e quartos 301 a 304' WHERE id_acao='A010';
UPDATE pendencias SET meta_entregavel='Camas entregues à USP-MED com OS registrada' WHERE id_acao='A012';
UPDATE pendencias SET descricao_acao='Levar pauta de aquisição de novas camas com rebaixamento ao Diretor Executivo Felipe Malafaia' WHERE id_acao='A013';
UPDATE pendencias SET descricao_acao='Instalar porta de entrada do CTI provisório com dimensão para passagem de cama', meta_entregavel='Porta instalada e testada antes da migração dos pacientes' WHERE id_acao='A014';
UPDATE pendencias SET descricao_acao='Confirmar disponibilidade da equipe para horas extras no sábado 14/03' WHERE id_acao='A015';
UPDATE pendencias SET descricao_acao='Verificar funcionamento dos ar-condicionados nos quartos do CTI provisório e priorizar chamados do 3A', meta_entregavel='Ar-condicionados dos quartos do CTI provisório em pleno funcionamento' WHERE id_acao='A016';
UPDATE pendencias SET descricao_acao='Providenciar reparo da maçaneta do quarto 316 (3B — área do Dr. Felipe Malafaia)', meta_entregavel='Maçaneta do 316 reparada e quarto liberado para uso' WHERE id_acao='A017';

-- ATA MIG_20260319_01223280 (Call Center)
UPDATE pendencias SET descricao_acao='Popular o sistema Global Health com agendas fictícias (consultas e exames) para teste do agente de IA' WHERE id_acao='A018';
UPDATE pendencias SET descricao_acao='Separar relatórios de agendamento entre consultas e exames', meta_entregavel='Relatório segmentado apresentado' WHERE id_acao='A019';
UPDATE pendencias SET descricao_acao='Verificar custo do serviço de confirmação por SMS junto ao financeiro' WHERE id_acao='A020';
UPDATE pendencias SET descricao_acao='Elaborar documentação de rotina de trabalho dos colaboradores do Call Center' WHERE id_acao='A021';
UPDATE pendencias SET descricao_acao='Consultar jurídico sobre viabilidade de modelo híbrido de jornada', meta_entregavel='Parecer jurídico formal' WHERE id_acao='A022';

-- ATA MIG_20260323_01223266 (Centro Médico)
UPDATE pendencias SET descricao_acao='Agendar reunião de integração com Dra. Carol sobre responsabilidade técnica do Centro Médico', meta_entregavel='Reunião realizada' WHERE id_acao='A023';
UPDATE pendencias SET descricao_acao='Discutir com Dr. Felipe a possibilidade do Dr. André realizar consultas de coluna sem cirurgia', meta_entregavel='Definição documentada e comunicada' WHERE id_acao='A024';
UPDATE pendencias SET descricao_acao='Conduzir formalização da responsabilidade técnica da Dra. Carol junto ao CREMERJ', meta_entregavel='Registro no CREMERJ concluído' WHERE id_acao='A025';
UPDATE pendencias SET descricao_acao='Apresentar comparativo mensal de evolução de consultas', meta_entregavel='Relatório com comparativo mensal' WHERE id_acao='A026';
UPDATE pendencias SET descricao_acao='Iniciar implantação do projeto de consultas particulares' WHERE id_acao='A027';
UPDATE pendencias SET descricao_acao='Verificar situação do atendimento Unimed no Centro Médico com Dr. Felipe', meta_entregavel='Decisão documentada' WHERE id_acao='A029';

-- ATA MIG_20260327_01223255 (Compras)
UPDATE pendencias SET descricao_acao='Criar formulário Google Forms para padronização de requisições de compras', meta_entregavel='Formulário em uso por todos os setores' WHERE id_acao='A030';
UPDATE pendencias SET descricao_acao='Elaborar lista de fornecedores estratégicos e alternativas para dependências críticas' WHERE id_acao='A031';
UPDATE pendencias SET descricao_acao='Verificar com Lucas sistema de compras integrado ao MV e possibilidade de integração do Bionexo', meta_entregavel='Resposta técnica documentada' WHERE id_acao='A033';
UPDATE pendencias SET descricao_acao='Elaborar proposta de metas de redução de custos e modelo de premiação', meta_entregavel='Proposta apresentada à direção' WHERE id_acao='A034';
UPDATE pendencias SET meta_entregavel='Relatório de viabilidade apresentado' WHERE id_acao='A035';

-- ATA MIG_20260317_01223381 (Contas a Receber)
UPDATE pendencias SET descricao_acao='Enviar por e-mail listagem de operadoras com maior dificuldade de comunicação em bloqueios' WHERE id_acao='A036';
UPDATE pendencias SET descricao_acao='Cobrar jurídico a identificar processos de bloqueio e informar setores afetados', meta_entregavel='Jurídico informando bloqueios por operadora com número de processo e valor' WHERE id_acao='A037';
UPDATE pendencias SET descricao_acao='Padronizar planilha de indicadores de CAR (operadoras x períodos)' WHERE id_acao='A038';
UPDATE pendencias SET descricao_acao='Montar plano de ação 30/60/90 dias para dificuldades do setor de CAR', meta_entregavel='Plano de ação enviado por e-mail a Josiane e Denize' WHERE id_acao='A039';
UPDATE pendencias SET descricao_acao='Discutir com Dr. Blanco a negociação Unimed Rio e Unimed Pad / contato FGV', meta_entregavel='Contato FGV estabelecido e caminho de negociação definido' WHERE id_acao='A040';
UPDATE pendencias SET descricao_acao='Formalizar dificuldades do MV para apresentação ao Dr. Felipe Malafaia', meta_entregavel='Levantamento formal das dificuldades entregue para reunião com diretor' WHERE id_acao='A041';

-- ATA MIG_20260324_0122337B (Apoio/Maqueiros)
UPDATE pendencias SET descricao_acao='Realizar reunião com maqueiros sobre proatividade e atitude de serviço', meta_entregavel='Relato na próxima reunião intermediária' WHERE id_acao='A042';
UPDATE pendencias SET descricao_acao='Alinhar fluxo previsível de solicitações de transporte para exames com equipe da recepção' WHERE id_acao='A043';
UPDATE pendencias SET descricao_acao='Verificar campos necessários para QR Code de reclamações', meta_entregavel='Campos definidos para implantação' WHERE id_acao='A047';
UPDATE pendencias SET descricao_acao='Orientar colaboradores sobre uso exclusivo do vestiário para pertences pessoais', meta_entregavel='Instrução disseminada à equipe' WHERE id_acao='A048';

-- ATA MIG_20260318_0122337C (Coordenação Operacional/Custos)
UPDATE pendencias SET cargo='Responsável pelo Setor de Custos' WHERE id_acao='A051';
UPDATE pendencias SET descricao_acao='Levantar motivos das altas tardias e apresentar na próxima reunião', meta_entregavel='Relatório com motivos e horários das altas' WHERE id_acao='A053';
UPDATE pendencias SET meta_entregavel='Definição documentada do projeto' WHERE id_acao='A054';
UPDATE pendencias SET meta_entregavel='Estudo com base em dados de CC, internações e altas' WHERE id_acao='A057';
UPDATE pendencias SET descricao_acao='Avaliar criação de QR Code para feedbacks no posto de apoio' WHERE id_acao='A058';
UPDATE pendencias SET descricao_acao='Completar estudo de viabilidade lavanderia com todos os parâmetros de custo', meta_entregavel='Estudo completo com comparativo de quilos, descartáveis e enxoval próprio' WHERE id_acao='A059';
UPDATE pendencias SET descricao_acao='Elaborar plano de ação 30/60/90 dias com dificuldades e melhorias operacionais', meta_entregavel='Plano de ação enviado por e-mail a Josiane Alves' WHERE id_acao='A060';
UPDATE pendencias SET descricao_acao='Formalizar encaminhamentos sobre o problema de dedetização', meta_entregavel='Relatório de medidas tomadas e responsáveis definidos' WHERE id_acao='A061';
UPDATE pendencias SET descricao_acao='Revisar gestão de suprimentos por Curva ABC após migração para o MV' WHERE id_acao='A062';

-- ATA MIG_20260312_012233B1 (Credenciamento — Transição)
UPDATE pendencias SET descricao_acao='Incluir Coordenadora em cópia em todas as comunicações com operadoras', meta_entregavel='Fluxo de cópia em vigor' WHERE id_acao='A068';
UPDATE pendencias SET descricao_acao='Elaborar proposta base de valores mínimos para negociações', meta_entregavel='Proposta apresentada à direção' WHERE id_acao='A069';
UPDATE pendencias SET descricao_acao='Verificar com Flavia cobrança de material e medicamento em retornos Klini' WHERE id_acao='A070';
UPDATE pendencias SET descricao_acao='Marcar reunião com Paulo Seixas (Klini) para aditivo e tratativa dos retornos', meta_entregavel='Reunião realizada e encaminhamentos registrados' WHERE id_acao='A071';
UPDATE pendencias SET descricao_acao='Verificar com Simone comunicação sobre casos de morte cefálica/transplante' WHERE id_acao='A072';
UPDATE pendencias SET descricao_acao='Encaminhar novos assuntos de operadoras para Iratiana com Camila em cópia', meta_entregavel='Transição iniciada' WHERE id_acao='A073';

-- ATA MIG_20260320_01354361 (Emergência/Imagens)
UPDATE pendencias SET descricao_acao='Regularizar faturamento de laudos de imagens atrasados (última subida: 08/04/2026) e comunicar data prevista a Adriana Araújo (Faturamento)' WHERE id_acao='A074';

-- ATA MIG_20260317_012233DD (Indicadores Financeiros)
UPDATE pendencias SET descricao_acao='Elaborar comparativo lavanderia TimeClean x São Geraldo com custo total e quilos por troca', meta_entregavel='Estudo de viabilidade completo com todos os parâmetros de custo comparados' WHERE id_acao='A077';
UPDATE pendencias SET meta_entregavel='Relatório comparativo com redução de custo pós-revisão da rede de gases' WHERE id_acao='A078';
UPDATE pendencias SET descricao_acao='Sinalizar ao Lucas (TI/MV) necessidades específicas de relatórios financeiros', meta_entregavel='Layout de relatórios financeiros implementado no MV' WHERE id_acao='A079';
UPDATE pendencias SET descricao_acao='Montar plano de ação 30/60/90 dias para dificuldades operacionais da gerência', meta_entregavel='Plano de ação enviado por e-mail a Josiane Alves' WHERE id_acao='A080';

-- ATA MIG_20260318_012233F6 (DP/RH)
UPDATE pendencias SET descricao_acao='Ressuscitar e-mail jurídico sobre plano de saúde de afastados pelo INSS e encaminhar ao Dr. Eduardo com questionamentos', meta_entregavel='E-mail enviado ao jurídico com posicionamento formal' WHERE id_acao='A082';
UPDATE pendencias SET descricao_acao='Desenhar planos de contingência de RH para setores críticos (Laboratório e Higienização como prioridade)', meta_entregavel='Planos documentados e apresentados na reunião mensal' WHERE id_acao='A083';
UPDATE pendencias SET descricao_acao='Aprofundar estudo de viabilidade de terceirização da Higienização com cálculo de horas efetivas trabalhadas' WHERE id_acao='A084';
UPDATE pendencias SET descricao_acao='Avaliar situação da funcionária Sonia (central telefônica) quanto a risco de doença ocupacional e definir encaminhamento', meta_entregavel='Decisão formalizada: desligamento ou remanejamento de setor' WHERE id_acao='A085';
UPDATE pendencias SET meta_entregavel='Pendências' WHERE id_acao='A086';
UPDATE pendencias SET descricao_acao='Agendar e realizar reunião sobre exames admissionais, demissionais e periódicos (MedSol)', meta_entregavel='Reunião realizada e pendências MedSol encaminhadas' WHERE id_acao='A087';

-- ATA MIG_20260410_0122331C (Higienização/Hotelaria)
UPDATE pendencias SET descricao_acao='Reunir com Uliandra e Ronildo para alinhar proposta de redimensionamento do quadro de higienização', meta_entregavel='Proposta consolidada para apresentação' WHERE id_acao='A090';
UPDATE pendencias SET descricao_acao='Levantar com Levi dos Santos o status das contratações pendentes', meta_entregavel='Relatório de' WHERE id_acao='A091';
UPDATE pendencias SET cargo='Encarregado de Higienização e Hotelaria', descricao_acao='Garantir participação de todos os colaboradores em todos os treinamentos por setor' WHERE id_acao='A092';
UPDATE pendencias SET cargo='Encarregado de Higienização e Hotelaria', descricao_acao='Garantir participação de todos os colaboradores em todos os treinamentos por setor' WHERE id_acao='A093';

-- ATA MIG_20260318_0122337C (cont.) — gases medicinais
UPDATE pendencias SET descricao_acao='Apresentar custo de gases medicinais (jan-mar) e impacto das revisões de válvulas', meta_entregavel='Relatório comparativo jan-mar apresentado na reunião mensal' WHERE id_acao='A094';

-- ATA MIG_20260320_01223329 (Internação/Prorrogação)
UPDATE pendencias SET descricao_acao='Convocar reunião intersetorial para definir fluxo de liberação de leitos' WHERE id_acao='A095';
UPDATE pendencias SET cargo='Coordenadora de Recepção — Internação e Prorrogação', descricao_acao='Elaborar POP completo de internação incluindo pré-internação' WHERE id_acao='A096';
UPDATE pendencias SET descricao_acao='Agendar reunião com Dr. Blanco ou Dr. Felipe para renegociar pacotes OPME', meta_entregavel='Reunião realizada; proposta de renegociação encaminhada' WHERE id_acao='A097';
UPDATE pendencias SET cargo='Coordenadora de Recepção — Internação e Prorrogação', descricao_acao='Trazer motivos das transferências por operadora na próxima reunião', meta_entregavel='Relatório de transferências com motivos' WHERE id_acao='A098';
UPDATE pendencias SET cargo='Coordenadora de Recepção — Internação e Prorrogação', descricao_acao='Elaborar cronograma de treinamento de educação continuada com Flavia' WHERE id_acao='A099';
UPDATE pendencias SET descricao_acao='Definir política de cobertura de extras com atrativo para colaboradores', meta_entregavel='Política documentada e comunicada' WHERE id_acao='A100';

-- ATA MIG_20260323_01223393 (Manutenção semanal)
UPDATE pendencias SET descricao_acao='Verificar disponibilidade de impressora no hospital para equipe de manutenção (ou levantar custo de aquisição)', meta_entregavel='Decisão tomada sobre remanejamento ou compra; equipe com impressora operacional' WHERE id_acao='A102';
UPDATE pendencias SET descricao_acao='Encaminhar tema do piso do centro cirúrgico para reunião da tarde com a Diretora Médica', meta_entregavel='Diagnóstico e plano de ação para reparo do piso definidos na reunião' WHERE id_acao='A103';
UPDATE pendencias SET descricao_acao='Reforçar com toda a equipe técnica as regras de conduta: uniforme, isolamento de área, limpeza e registro fotográfico', meta_entregavel='Regras comunicadas; equipe ciente de que reincidências geram advertência formal' WHERE id_acao='A104';
UPDATE pendencias SET descricao_acao='Verificar com Dra. Carol a quantidade necessária de tomadas por leito (2A, 2B, 3B)', meta_entregavel='Quantitativo definido e repassado à equipe de elétrica para execução' WHERE id_acao='A105';
UPDATE pendencias SET meta_entregavel='Comunicação feita ao setor de internação sobre disponibilidade dos leitos' WHERE id_acao='A106';
UPDATE pendencias SET descricao_acao='Instalar maçaneta na porta do CTI provisório', meta_entregavel='Maçaneta instalada para fechamento da porta' WHERE id_acao='A107';
UPDATE pendencias SET meta_entregavel='Organização dos reparos das telhas que causam infiltração' WHERE id_acao='A109';
UPDATE pendencias SET descricao_acao='Alinhar com Nayane a previsão de mobiliário danificado ou faltante nos quartos do 3A', meta_entregavel='Relação de mobiliário levantada e encaminhada para providências' WHERE id_acao='A110';
UPDATE pendencias SET descricao_acao='Iniciar checklist e recuperação dos quartos 310 e 312 (andar 300) — pintura, elétrica e ajustes', meta_entregavel='Quartos 310 e 312 prontos para ocupação' WHERE id_acao='A111';
UPDATE pendencias SET descricao_acao='Realizar demolição parcial no CTI-3 (remoção de materiais, forro e trecho de parede)', meta_entregavel='Área esvaziada e demolição concluída sem danos à rede de gás' WHERE id_acao='A112';
UPDATE pendencias SET descricao_acao='Instalar telhado na área de armazenamento de papelões', meta_entregavel='Área coberta e protegida' WHERE id_acao='A113';
UPDATE pendencias SET descricao_acao='Realizar limpeza e remoção de vegetação na área do gerador no estacionamento', meta_entregavel='Área do gerador limpa e desobstruída' WHERE id_acao='A114';
UPDATE pendencias SET descricao_acao='Remanejar mobiliário do consultório da sala 303 para o CTI-2', meta_entregavel='Sala 303 desocupada e mobiliário no CTI-2' WHERE id_acao='A115';

-- ATA MIG_20260330_01223318 (Manutenção - revisão)
UPDATE pendencias SET descricao_acao='Enviar ata com quadro de atribuições à equipe' WHERE id_acao='A116';
UPDATE pendencias SET descricao_acao='Confirmar necessidades do quarto 212 com Dra. Carol (bancada, acabamentos, destinação do espaço)', meta_entregavel='Lista de necessidades recebida e encaminhada à equipe' WHERE id_acao='A117';
UPDATE pendencias SET descricao_acao='Encaminhar questão trabalhista (ex-funcionário Vicente, R$ 219 mil) ao jurídico', meta_entregavel='Jurídico acionado e providências registradas' WHERE id_acao='A118';
UPDATE pendencias SET descricao_acao='Solicitar orçamento de empresas para reforma dos frigobares', meta_entregavel='3 orçamentos recebidos e avaliados' WHERE id_acao='A119';
UPDATE pendencias SET descricao_acao='Realizar serviço de acabamento do rack de TI (juntas com tela, massa e pintura borrachada) com Sergio', meta_entregavel='Acabamento concluído em horário de menor circulação' WHERE id_acao='A121';
UPDATE pendencias SET descricao_acao='Agendar reunião com RH para tratar questão trabalhista dos ex-funcionários Renato e Vicente', meta_entregavel='Reunião realizada; encaminhamentos definidos' WHERE id_acao='A122';

-- ATA MIG_20260317_0122339E (Glosas)
UPDATE pendencias SET descricao_acao='Elaborar programa de educação continuada para faturamento, recepção e credenciamento', meta_entregavel='Programa estruturado com datas, público-alvo e conteúdo apresentado à diretoria' WHERE id_acao='A123';
UPDATE pendencias SET descricao_acao='Verificar viabilidade de campo de matrícula obrigatório no MV', meta_entregavel='Campo obrigatório implementado no MV para redução de erros de matrícula' WHERE id_acao='A124';
UPDATE pendencias SET descricao_acao='Formalizar comunicação entre credenciamento, faturamento e recurso de glosas', meta_entregavel='Fluxo de comunicação documentado e comunicado a todos os setores envolvidos' WHERE id_acao='A126';

-- ATA MIG_20260317_012233D8 (Repasse Médico)
UPDATE pendencias SET descricao_acao='Elaborar plano de ação 30/60/90 dias com dificuldades do setor, incluindo Clin Carioca', meta_entregavel='Plano de ação enviado por e-mail e apresentado na reunião mensal' WHERE id_acao='A129';
UPDATE pendencias SET descricao_acao='Elaborar fluxo completo de trabalho de repasse médico' WHERE id_acao='A130';
UPDATE pendencias SET descricao_acao='Elaborar proposta de padronização de critérios e datas de pagamento médico', meta_entregavel='Proposta com impacto de fluxo de caixa apresentada à diretoria' WHERE id_acao='A131';
UPDATE pendencias SET descricao_acao='Formalizar e assinar POP de repasse médico após revisão final' WHERE id_acao='A132';
UPDATE pendencias SET descricao_acao='Revisão do POP de Repasse Médico com inclusão de planilha de regras de repasse como anexo' WHERE id_acao='A133';
UPDATE pendencias SET descricao_acao='Cobrar retorno da proposta Santander (Rangel, AMA e JB) por e-mail caso não haja resposta até sexta' WHERE id_acao='A134';

-- ATA MIG_20260406_01223313 (Gerência Financeira intermediária)
UPDATE pendencias SET descricao_acao='Contatar consultores externos de MV para suporte prático na implantação' WHERE id_acao='A142';

-- ATA MIG_20260327_013543D2 (Faturamento)
UPDATE pendencias SET descricao_acao='Elaborar proposta de modelo de premiação para a equipe de faturamento', meta_entregavel='Proposta apresentada à direção' WHERE id_acao='A143';
UPDATE pendencias SET descricao_acao='Incluir Flavia (Glosas) nos treinamentos de preenchimento de guias para emergência e internação', meta_entregavel='Treinamento realizado com emergência e internação' WHERE id_acao='A144';
UPDATE pendencias SET descricao_acao='Alinhar com Dr. Felipe desligamento dos colaboradores de baixa produção', meta_entregavel='Definição documentada' WHERE id_acao='A145';
UPDATE pendencias SET descricao_acao='Assumir gradualmente comunicação de reajustes de operadoras vinda do Credenciamento' WHERE id_acao='A146';

-- ATA MIG_20260413_01223366 (Emergência/Imagens - revisão)
UPDATE pendencias SET descricao_acao='Conversar com Dra. Carol e Simone sobre redução do tempo de espera médica e laboratorial', meta_entregavel='Solução prática apresentada na reunião' WHERE id_acao='A147';
UPDATE pendencias SET descricao_acao='Criar indicador manual de evasão de pacientes (convênio, data, volume)', meta_entregavel='Planilha de evasão em uso' WHERE id_acao='A149';
UPDATE pendencias SET descricao_acao='Avaliar criação de status de abandono no sistema junto ao Lucas', meta_entregavel='Resposta técnica do TI' WHERE id_acao='A150';

-- =================================================================
-- PARTICIPANTES (12 correções globais)
-- =================================================================

UPDATE participantes SET nome_completo='João Diretor Administrativo' WHERE id='P045';
UPDATE participantes SET cargo='Diretor de Operações' WHERE id IN ('P047','P049','P051');
UPDATE participantes SET cargo='Técnico Sênior' WHERE id IN ('P048','P050','P052');
UPDATE participantes SET cargo='Técnico de Segurança do Trabalho' WHERE id='P053';
UPDATE participantes SET cargo='Coordenadora de Recepção / Internação' WHERE id='P055';
UPDATE participantes SET setor='Hospital São Matheus' WHERE id='P057';
UPDATE participantes SET cargo='Encarregado de Higienização e Hotelaria' WHERE id IN ('P065','P066');

-- =================================================================
-- VALIDAÇÃO INLINE — falha aborta tudo
-- =================================================================

DO $$
DECLARE
  v_pend_susp INT;
  v_part_susp INT;
  v_reun_susp INT;
BEGIN
  -- Quantos restos suspeitos sobraram (palavras claramente sem acento)?
  SELECT COUNT(*) INTO v_pend_susp FROM pendencias
   WHERE descricao_acao ~ '\m(execucao|conclusao|reuniao|reunioes|gestao|coordenacao|integracao|formalizacao|implantacao|aquisicao|definicao|reducao|migracao|atribuicoes|paralisacoes|comunicacao|operacao|operacoes|criticos|necessarios|necessaria|previsao|relatorio|relatorios|proximo|proxima|periodo|periodos|orcamento|orcamentos|servico|servicos|publico)\M';

  SELECT COUNT(*) INTO v_part_susp FROM participantes
   WHERE cargo ~ '\m(Tecnico|Senior|Operacoes|Higienizacao|Recepcao|Internacao|Seguranca|Responsavel)\M';

  SELECT COUNT(*) INTO v_reun_susp FROM reunioes
   WHERE status_ata='MIGRADA' AND (
     COALESCE(objetivo,'') ~ '\m(execucao|conclusao|reuniao|reunioes|gestao|coordenacao|integracao|implantacao|reducao|migracao|atribuicoes|comunicacao|operacao|criticos|necessarios|periodo|orcamento|servico|publico)\M'
     OR COALESCE(titulo,'') ~ '\m(Reuniao|Coordenacao|Apresentacao|Revisao|Gerencia|Medico|Provisorio)\M'
   );

  RAISE NOTICE 'Pendências com palavras suspeitas remanescentes: %', v_pend_susp;
  RAISE NOTICE 'Participantes com cargo suspeito remanescente: %', v_part_susp;
  RAISE NOTICE 'Reuniões com texto suspeito remanescente: %', v_reun_susp;

  IF v_pend_susp > 5 OR v_part_susp > 0 OR v_reun_susp > 0 THEN
    RAISE EXCEPTION 'Validação falhou: pendências=%, participantes=%, reuniões=% — abortando transação', v_pend_susp, v_part_susp, v_reun_susp;
  END IF;
END $$;

COMMIT;

-- =================================================================
-- ROLLBACK (caso alguma mudança seja indesejada após COMMIT):
-- =================================================================
-- BEGIN;
--   DELETE FROM pendencias;     INSERT INTO pendencias    SELECT * FROM pendencias_backup_ortografia_20260427;
--   DELETE FROM participantes;  INSERT INTO participantes SELECT * FROM participantes_backup_ortografia_20260427;
--   DELETE FROM reunioes;       INSERT INTO reunioes      SELECT * FROM reunioes_backup_ortografia_20260427;
-- COMMIT;
