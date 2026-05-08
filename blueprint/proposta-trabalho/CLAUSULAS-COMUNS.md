# Cláusulas · Proposta PJ Flowtech Soluções × Hospital São Mateus

> Espelho textual das cláusulas que aparecem no `proposta.html`. Serve como referência para o advogado redigir o contrato real após acordo verbal.

**Partes:**
- **Contratada:** Flowtech Soluções LTDA (CNPJ em abertura), com sede no Rio de Janeiro/RJ
- **Contratante:** Hospital São Mateus (Bangu, Rio de Janeiro/RJ)
- **Modalidade:** prestação de serviços PJ-PJ
- **Vigência:** 12 meses a partir da assinatura, com renovação por acordo expresso entre as partes (sem renovação automática)
- **Foro:** comarca do Rio de Janeiro/RJ

---

## 1. Saída livre

Qualquer das partes poderá encerrar a relação contratual mediante aviso por escrito de **15 (quinze) dias**, sem incidência de multa rescisória ou ônus adicional.

A simetria desta cláusula estende-se a eventual prestador subcontratado pela Contratada sob o seu CNPJ. Ou seja, o vínculo entre a Contratada e o subcontratado também poderá ser encerrado pelas mesmas regras, sem que isso afete a continuidade ou os termos vigentes entre Contratada e Contratante.

A janela de quinze dias destina-se especificamente a:

- Passagem de credenciais, acessos a infraestrutura e repositórios
- Atualização do runbook operacional
- Fechamento de pendências críticas em produção
- Repasse de status atualizado de projetos em andamento

Ao fim da janela, todos os acessos da Contratada à infraestrutura do Hospital são revogados imediatamente.

## 2. Condicionamento da rampa

A remuneração mensal segue estrutura escalonada por entrega, conforme detalhado no Anexo I (rampa de remuneração). Cada degrau da rampa será destravado mediante a **conclusão das entregas planejadas** para o ciclo de referência, pactuadas em ATA na reunião mensal anterior.

A validação ocorre em **reunião mensal com a Diretoria do Hospital São Mateus**, com registro em ATA. Caso o critério não seja atendido, o degrau correspondente é suspenso até a reunião subsequente, sem prejuízo do fixo vigente.

A não progressão da rampa não constitui inadimplemento contratual nem motivo para rescisão por qualquer das partes.

## 3. Propriedade intelectual

**Pertence ao Hospital São Mateus**, em caráter exclusivo e definitivo:

- Código-fonte específico desenvolvido sob encomenda
- Bases de dados operacionais e dados de paciente
- Modelos de IA treinados especificamente sobre os dados do Hospital
- Documentações operacionais (runbook, manuais, procedimentos internos)
- Configurações de infraestrutura específicas do ambiente do Hospital

**Permanece com a Flowtech Soluções LTDA**, podendo ser reaproveitado em outros projetos, sem reuso de dados sensíveis do Hospital:

- Templates genéricos de aplicações
- Padrões de automação reutilizáveis
- Skills, agentes e prompts próprios da Contratada
- Know-how técnico, metodologias e frameworks de trabalho
- Bibliotecas e utilitários genéricos não específicos ao domínio hospitalar

O acesso da Contratada aos repositórios privados do Hospital se dá via convite GitHub (ou plataforma equivalente), sem transferência de propriedade ou licenciamento exclusivo.

## 4. Confidencialidade e LGPD

Dados de paciente, prontuários, registros médicos e quaisquer informações sensíveis processadas no ambiente do Hospital São Mateus **nunca deixam o ambiente controlado pelo Hospital** (VPS própria, banco self-hosted, sistemas internos). A Contratada compromete-se a não exportar, copiar ou processar tais dados em ambientes externos sob qualquer hipótese.

A operação é coberta por **termo de confidencialidade dedicado** (NDA) entre as partes, a ser assinado em conjunto com este contrato. O termo cobre informações de paciente, dados financeiros, estratégia institucional e qualquer informação não pública à qual a Contratada tenha acesso por força do contrato.

Em caso de **incidente de segurança** (acesso não autorizado, vazamento de dados, falha em controle de acesso), a Contratada compromete-se a:

- Acionar plano de resposta a incidente em até **1 (uma) hora** após a detecção
- Comunicar formalmente a Diretoria do Hospital em até **2 (duas) horas** após a detecção
- Apoiar a investigação técnica e a remediação até a resolução plena
- Documentar o incidente em relatório formal arquivado por ambas as partes

A Contratada cumpre a Lei Geral de Proteção de Dados (LGPD) na qualidade de operadora dos dados, sob orientação do Hospital São Mateus na qualidade de controlador.

---

## Anexo I · Rampa de remuneração (referência rápida)

| Marco | Pedro | Lucas | Claude Code Max | Servidor (daily backup) | **Total mensal** |
|---|---|---|---|---|---|
| Início (presença, alinhamento, setup) | R$ 6.000 | 0 | + R$ 2.200 | + R$ 200 | **R$ 8.400** |
| Hospital Reuniões em produção | R$ 7.000 | R$ 1.000 | + R$ 2.200 | + R$ 200 | **R$ 10.400** |
| Site institucional no ar | R$ 7.500 | R$ 1.500 | + R$ 2.200 | + R$ 200 | **R$ 11.400** |
| Ana WhatsApp + integração MV | R$ 10.000 | R$ 4.000 | + R$ 2.200 | + R$ 200 | **R$ 16.400** |
| Retell.AI (futuro · referência) | R$ 13.000 | R$ 7.000 | + R$ 2.200 | + R$ 200 | **~ R$ 22.400** |

**Claude Code Max** representa o plano de assinatura da ferramenta de IA usada por Pedro e Lucas no trabalho operacional (R$ 1.100 cada por mês, totalizando R$ 2.200 mensais). **Servidor** representa a hospedagem das aplicações em produção com daily backup automatizado (R$ 200 mensais). Ambos os componentes permeiam todos os degraus desde o Início e são parte permanente do fixo.

**Retell.AI** é fase futura, não cravada. O salto de +R$ 3.000 cada (Pedro e Lucas) é referência. O pagamento pode ser proporcional à redução de custo gerada pela substituição das telefonistas, e parte da compensação pode ser posterior ao go-live. Discussão segue aberta entre as partes; só entra em vigor após acordo expresso e plano técnico assinado.

Durante toda a vigência, em paralelo aos degraus da rampa, o relacionamento contempla: reuniões de levantamento de requisitos, estudo de novas frentes (fluxos n8n, automações em Claude Code, refinamentos), discussão de valor agregado e custo de cada nova implementação antes da execução.

**NF única** emitida mensalmente pela Flowtech Soluções LTDA contra o Hospital São Mateus, totalizando o valor agregado do mês. A distribuição interna entre os sócios da Contratada é matéria interna e não afeta a relação contratual com o Contratante.

