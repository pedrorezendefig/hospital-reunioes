# Base de conhecimento do agente do Núcleo de Segurança do Paciente (Anexo A)

**Hospital São Matheus · Plataforma de Gestão · Módulo Núcleo de Segurança do Paciente**
Versão 1.1 · 12/11/2026 · revisada contra o caderno ANVISA "Implantação do Núcleo de Segurança do Paciente em Serviços de Saúde" (Série nº 6, 3ª ed., 2025)

Este documento é o conhecimento de referência dos agentes de IA do módulo NSP. Ele é carregado junto com o prompt de cada agente. O que está aqui prevalece sobre o conhecimento geral do modelo.

---

### 1. HIERARQUIA DAS FONTES

Em qualquer conflito, a camada de cima prevalece.

| Camada | Fonte | Uso |
|---|---|---|
| **1. Norma brasileira** | RDC ANVISA nº 36/2013 · Portaria GM/MS nº 529/2013 (PNSP) · Portarias GM/MS nº 1.377/2013 e nº 2.095/2013 (protocolos básicos) · Nota Técnica GVIMS/GGTES/ANVISA nº 09/2025 · caderno ANVISA "Implantação do NSP em Serviços de Saúde" (Série nº 6, 3ª ed., 2025; orientação oficial, não normativa) | Definições, obrigações, prazos, lista de eventos que nunca deveriam ocorrer |
| **2. Referência técnica** | Classificação Internacional para a Segurança do Paciente da OMS (2009) · caderno ANVISA "Gestão de Riscos e Investigação de Eventos Adversos" (3ª ed., 2025) · Protocolo de Londres · política de evento sentinela da Joint Commission · hierarquia de efetividade de ações (IHI) | Tipos de incidente, grau de dano, método de investigação, força das ações |
| **3. Regras do Hospital São Matheus** | Regimento Interno do NSP · decisões da Diretoria Executiva registradas na especificação do módulo | Prazos internos, papéis, roteamento entre canais |

Regra geral: prazo interno pode ser mais rígido que o legal, nunca mais frouxo.

---

### 2. CONCEITOS

| Termo | Definição operacional |
|---|---|
| **Incidente** | Evento ou circunstância que resultou, ou poderia ter resultado, em dano desnecessário ao paciente |
| **Circunstância de risco** | Situação com potencial significativo de dano, sem que nenhum incidente tenha ocorrido. Ex.: desfibrilador sem bateria no teste |
| **Quase erro** (near miss) | Incidente que não chegou ao paciente, porque foi interceptado. Ex.: dose errada percebida na conferência |
| **Incidente sem dano** | Chegou ao paciente e não causou dano detectável. Ex.: comprimido do paciente vizinho, sem efeito |
| **Evento adverso** | Incidente que causou dano ao paciente |
| **Evento que nunca deveria ocorrer** (never event) | Evento da lista fechada da ANVISA (seção 5). Vale a lista, e não a gravidade aparente |
| **IRAS** | Infecção relacionada à assistência à saúde. Tem fluxo próprio de vigilância com a CCIH |
| **Queixa técnica** | Suspeita de defeito ou desvio de qualidade de produto (medicamento, material, equipamento) |

**Como decidir a natureza, em duas perguntas:**

1. Chegou ao paciente? Se não: havia um erro em curso que foi interceptado (quase erro) ou só uma condição perigosa (circunstância de risco)?
2. Se chegou: houve dano (evento adverso) ou não (incidente sem dano)?

**Correspondência com o NOTIVISA.** O sistema da ANVISA usa três tipos: near miss (não atingiu o paciente), incidente sem dano e incidente com dano (evento adverso). O quase erro corresponde ao near miss. A circunstância de risco é categoria interna do hospital: nenhum incidente ocorreu, então ela é tratada no Núcleo e não é notificada externamente.

---

### 3. GRAU DE DANO

Escala da OMS, usada pelo NOTIVISA. Os critérios abaixo seguem a redação do caderno da ANVISA (item 5.8.2).

| Grau | Critério | Exemplos |
|---|---|---|
| **Nenhum** | Paciente assintomático ou sem sintoma detectado, sem necessidade de tratamento | Dose atrasada sem repercussão |
| **Leve** | Sintomas leves, perda de função ou danos mínimos ou moderados de curta duração; sem intervenção ou com intervenção mínima (observação extra, investigação, revisão de tratamento ou tratamento leve) | Urticária tratada com anti-histamínico; corte suturado; flebite |
| **Moderado** | Paciente sintomático que exige intervenção (procedimento suplementar, terapêutica adicional), com aumento da internação, ou com danos permanentes ou de longo prazo | Transfusão por sangramento; novo dreno; antibiótico venoso com reinternação |
| **Grave** | Paciente sintomático que exige intervenção para salvar a vida ou intervenção clínica ou cirúrgica de grande porte, com diminuição da expectativa de vida, grande dano ou perda de função, permanente ou de longo prazo | Reintubação; reoperação; transferência ao CTI por instabilidade; fratura de fêmur |
| **Óbito** | O evento adverso causou ou acelerou a morte do paciente | Parada após dose excessiva de opioide |

**Regras de aplicação:**

1. **Na dúvida entre dois graus, classificar no mais alto.** O erro inaceitável é rebaixar um caso grave.
2. Coerência obrigatória: circunstância de risco, quase erro e incidente sem dano têm dano "nenhum"; evento adverso tem dano de leve a óbito.
3. Linguagem atenuada não reduz o grau. "Deu um probleminha, mas já está tudo bem" seguido de "tomou duas bolsas de sangue" é dano moderado.
4. Se a opção marcada pelo notificante divergir do relato, vale o mais grave dos dois, e a divergência é sinalizada.
5. Óbito citado no relato sempre vai à revisão campo a campo, mesmo que pareça decorrer da doença de base. Decidir se o óbito foi causado pelo incidente é tarefa humana.

---

### 4. TIPO DE INCIDENTE: CATEGORIA E INCIDENTE

Dois níveis. O detalhe fino permanece no relato.

| Código | Categoria | Incidentes |
|---|---|---|
| **IDP** | Identificação do paciente | Sem pulseira ou pulseira errada · homônimos sem alerta · procedimento, exame ou documento no paciente errado · amostra mal identificada |
| **MED** | Medicamentos e soluções | Prescrição · dispensação · preparo · administração (paciente, medicamento, dose, via, horário ou velocidade errados) · omissão ou atraso · alergia conhecida ignorada · extravasamento · armazenamento e medicamentos de alta vigilância |
| **SAN** | Sangue e hemocomponentes | Transfusão no paciente errado ou incompatível · falha de checagem · tempo ou conservação inadequados · reação transfusional |
| **CIR** | Cirurgia e anestesia | Local, lado, paciente ou procedimento errado · retenção de corpo estranho · falha na lista de verificação · intercorrência anestésica · queimadura por bisturi elétrico |
| **PRO** | Processo clínico e cuidado | Atraso ou falha de diagnóstico ou tratamento · deterioração clínica não reconhecida · falha de monitoramento · cuidado omitido · contenção inadequada · falha na classificação de risco |
| **QUE** | Quedas | Do leito · da maca ou cadeira · no banheiro · ao deambular · durante transporte |
| **LPP** | Lesão por pressão e pele | Lesão por pressão (com estágio) · falha de prevenção · lesão por adesivo ou dispositivo |
| **DIS** | Dispositivos invasivos | Perda acidental de cateter, sonda, dreno ou tubo · extubação não planejada · flebite · obstrução · conexão errada |
| **INF** | Infecção | IRAS (corrente sanguínea, sítio cirúrgico, pneumonia, urinária) · falha de higiene das mãos · falha de precaução ou isolamento · surto |
| **EXA** | Exames e diagnóstico | Resultado crítico não comunicado · amostra perdida, trocada ou sem identificação · exame errado ou no lado errado · laudo atrasado |
| **EQP** | Equipamentos e materiais | Falha ou indisponibilidade de equipamento · alarme inoperante · defeito de material |
| **GAS** | Oxigênio e gases medicinais | Gás errado · contaminação · falta ou interrupção · falha de rede |
| **NUT** | Dieta e nutrição | Dieta errada ou alergia alimentar · quebra de jejum · tempo de infusão · broncoaspiração |
| **COM** | Comunicação e documentação | Passagem de plantão · registro em prontuário errado · consentimento ausente · ordem verbal mal entendida |
| **ACE** | Acesso, transferência e alta | Evasão ou fuga · alta a pessoa não autorizada · atraso de transferência · transporte inseguro · documento de alta errado |
| **CMP** | Comportamento | Autolesão ou tentativa de suicídio · agressão por paciente · conduta de profissional (ver roteamento) |
| **EST** | Estrutura e ambiente | Energia elétrica · incêndio · piso, mobiliário e instalações · choque elétrico |
| **MAT** | Materno-infantil | Intercorrência de parto · queda de recém-nascido · troca de bebês · identificação do binômio |
| **OUT** | Outros | Usar só quando nenhuma categoria servir, com justificativa |

Quando o caso tocar duas categorias, escolher a da **falha de origem** e citar a outra na justificativa.

---

### 5. EVENTOS QUE NUNCA DEVERIAM OCORRER (LISTA ANVISA 2025)

Lista fechada do NOTIVISA, módulo Assistência à Saúde, conforme a NT nº 09/2025. **Conferir em toda notificação, qualquer que seja a gravidade aparente.**

| Nº | Evento |
|---|---|
| 1 | Alta ou liberação de paciente incapaz de tomar decisões para pessoa não autorizada |
| 2 | Contaminação na administração de oxigênio ou gases medicinais |
| 3 | Desaparecimento do corpo de recém-nascido que foi a óbito |
| 4 | Exodontia de dente errado |
| 5 | Gás errado na administração de oxigênio ou gases medicinais |
| 6 | Inseminação artificial ou fertilização in vitro com esperma ou óvulo errado |
| 7 | Lesão grave associada a queda do paciente durante o atendimento |
| 8 | Lesão por pressão estágio 3 |
| 9 | Lesão por pressão estágio 4 |
| 10 | Lesão por pressão não classificável |
| 11 | Óbito associado a queda do paciente durante o atendimento |
| 12 | Óbito intraoperatório ou imediatamente após cirurgia ou procedimento em paciente ASA 1 |
| 13 | Óbito ou lesão grave associados a fuga do paciente |
| 14 | Óbito ou lesão grave associados a choque elétrico durante a assistência |
| 15 | Óbito ou lesão grave de paciente ou colaborador por objeto metálico em área de ressonância magnética |
| 16 | Óbito ou lesão grave associados a contenção física ou grades da cama |
| 17 | Óbito ou lesão grave associados a queimadura de qualquer fonte durante a assistência |
| 18 | Óbito ou lesão grave por perda irrecuperável de amostra biológica insubstituível |
| 19 | Óbito ou lesão grave de recém-nascido no trabalho de parto ou parto em gestação de baixo risco |
| 20 | Óbito ou lesão grave por falha no acompanhamento ou na comunicação de resultado de exame laboratorial ou de patologia clínica |
| 21 | Óbito ou lesão grave por falha no acompanhamento ou na comunicação de resultado de exame radiológico |
| 22 | Óbito ou lesão materna grave no trabalho de parto ou parto em gestação de baixo risco |
| 23 | Procedimento cirúrgico em local errado |
| 24 | Procedimento cirúrgico no lado errado do corpo |
| 25 | Procedimento cirúrgico no paciente errado |
| 26 | Queda de recém-nascido durante o parto |
| 27 | Cirurgia errada em um paciente |
| 28 | Retenção não intencional de corpo estranho após cirurgia |
| 29 | Suicídio, tentativa de suicídio ou dano autoinfligido com lesão grave durante a assistência |
| 30 | Troca de bebês |

**Atenção a três grupos que enganam:**

| Grupo | Itens | Por que engana |
|---|---|---|
| Valem **sem dano grave** | 1, 2, 5, 8, 9, 10, 23, 24, 25, 26, 27, 28, 30 e a tentativa de suicídio do item 29 | O evento entra na lista mesmo que o paciente esteja bem. Uma lesão por pressão estágio 3 já é evento que nunca deveria ocorrer |
| Exigem **óbito ou lesão grave** | 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22 | Sem óbito ou lesão grave, o evento não entra na lista. Ex.: queimadura leve não é o item 17 |
| Fronteira duvidosa | Qualquer um | Marcar como "possível", explicar a dúvida e deixar a decisão à coordenação |

---

### 6. MARCADORES

| Marcador | Quando marcar |
|---|---|
| **Evento que nunca deveria ocorrer** | Corresponde a um item da seção 5. Informar o número |
| **IRAS** | Infecção associada à assistência, confirmada ou suspeita. Não marcar para falha de higiene das mãos sem infecção |
| **Risco de imagem** | O notificante relatou que paciente ou família percebeu e reclamou, ou mencionou advogado, imprensa ou redes sociais; ou o próprio fato tem exposição pública evidente (óbito em sala de espera, paciente incapaz encontrado na rua) |
| **Protocolo básico relacionado** | Identificação do paciente · higiene das mãos · cirurgia segura · medicamentos · quedas · lesão por pressão |

---

### 7. PRIORIDADE E PRAZOS

#### 7.1 Faixa de tratamento

| Faixa | Critério | Revisão pela coordenação |
|---|---|---|
| **A** | Óbito, ou evento que nunca deveria ocorrer (qualquer dano) | Campo a campo |
| **B** | Dano grave | Campo a campo |
| **C** | Dano moderado | Confirmação simples |
| **D** | Dano leve, ou incidente sem dano | Confirmação simples; pode ir em lote |
| **E** | Quase erro ou circunstância de risco | Confirmação simples; pode ir em lote |

#### 7.2 Matriz de prioridade

Gravidade (catastrófico, grave, moderado, leve) por frequência (frequente, ocasional, incomum, remoto).

| | Catastrófico | Grave | Moderado | Leve |
|---|---|---|---|---|
| **Frequente** | Alta | Alta | Moderada | Baixa |
| **Ocasional** | Alta | Moderada | Baixa | Baixa |
| **Incomum** | Alta | Moderada | Baixa | Baixa |
| **Remoto** | Alta | Moderada | Baixa | Baixa |

A frequência é calculada pelo sistema, pela contagem de ocorrências do mesmo incidente no mesmo setor. O agente não a estima.

#### 7.3 Prazos legais

| Situação | Prazo | Fonte |
|---|---|---|
| Óbito por evento adverso: notificação ao NOTIVISA | 72 horas do ocorrido | RDC 36/2013, art. 10 |
| Evento que nunca deveria ocorrer: notificação | Mesmo procedimento do óbito. O módulo trata como 72 horas | Caderno ANVISA nº 6, item 5.5 |
| Óbito e evento que nunca deveria ocorrer: 10 etapas preenchidas, com o plano de ação anexado | 60 dias corridos da notificação | NT 09/2025; caderno nº 6, item 5.5 |
| Demais incidentes e eventos adversos | Até o 15º dia útil do mês seguinte | NT 09/2025 |
| Erros de medicação | Notificados pelo NSP no sistema VigiMed, com os mesmos prazos | Caderno nº 6, itens 5.2 e 5.5; NT conjunta GGTES/GGMON nº 02/2015 |
| Mês sem evento adverso detectado | Arquivar internamente o registro de ausência. Não há notificação negativa | Caderno nº 6, item 2.6 |

**O que notificar.** A obrigação expressa da RDC 36/2013 alcança os eventos adversos. A orientação da ANVISA (NT 09/2025 e caderno nº 6, item 5.1) é notificar todos os incidentes relacionados à assistência, incluindo quase erro e incidente sem dano.

**Envio.** Cada notificação é enviada individualmente no portal. A alteração em lote descrita na NT 09/2025 é função da vigilância sanitária, não do serviço de saúde.

**Sistema de destino.** Categoria MED: VigiMed. Demais categorias: NOTIVISA, módulo Assistência à Saúde. IRAS e resistência microbiana: formulários próprios, pela CCIH. Sangue, produtos e equipamentos têm também fluxos próprios de hemovigilância e tecnovigilância, a confirmar com a Farmácia e a Agência Transfusional.

#### 7.4 As 10 etapas do NOTIVISA

Obrigatórias para todas as notificações: 1) tipo de incidente; 2) consequências para o paciente; 3) características do paciente; 4) características do incidente. Obrigatórias também em óbito e evento que nunca deveria ocorrer: 5) fatores contribuintes; 6) consequências organizacionais; 7) detecção; 8) fatores atenuantes do dano; 9) ações de melhoria; 10) ações para reduzir o risco.

O módulo deve colher, durante a investigação, a informação que alimenta as etapas 5 a 10, para que o texto do NOTIVISA saia pronto.

---

### 8. ROTEAMENTO ENTRE CANAIS

| Situação | Destino |
|---|---|
| Incidente relacionado à assistência ao paciente | **NSP** |
| Reclamação de atendimento, conforto, espera, alimentação, cobrança | **Ouvidoria** |
| Reclamação que também descreve falha de cuidado com risco ao paciente | **NSP e Ouvidoria** |
| Assédio, desrespeito, discriminação, fraude, conflito de interesse | **Canal de Conduta** |
| Conduta com risco direto ao paciente (trabalhar sob efeito de substância, falsificar registro, omitir evento grave) | **NSP e Canal de Conduta** |
| Acidente ou risco que atinge o trabalhador | **Segurança do Trabalho** |
| Agressão de paciente a profissional | **NSP e Segurança do Trabalho** |
| Defeito de produto sem paciente envolvido | **Queixa técnica** (Farmácia ou Engenharia Clínica) |
| Falha de equipamento ou material que atingiu ou ameaçou paciente | **NSP e queixa técnica** |
| Assunto trabalhista ou administrativo (salário, escala, benefício) | **Fora de escopo**: orientar a procurar o setor competente, sem abrir caso |

Ao encaminhar, o agente explica o motivo em uma frase. O encaminhamento só acontece depois da confirmação humana.

---

### 9. HIERARQUIA DE EFETIVIDADE DAS AÇÕES

| Nível | O que é | Exemplos |
|---|---|---|
| **Forte** | Muda o sistema de modo que o erro fique impossível ou muito difícil, sem depender de atenção individual | Conector incompatível; retirar concentrado de potássio dos postos; bloqueio em sistema; mudança física; padronizar um único modelo de equipamento |
| **Intermediária** | Reduz a chance do erro, mas depende de execução | Dupla checagem; lista de verificação; alerta em sistema; redundância; redução de distrações; ajuste de dimensionamento |
| **Fraca** | Atua sobre o comportamento sem mudar o processo | Treinamento; comunicado; cartaz; nova norma escrita; "reforçar orientação" |

Regras: a partir de dano moderado, pelo menos uma ação proposta deve ser forte ou intermediária. Ação dirigida a uma pessoa (reorientar, treinar individualmente) não entra no plano de melhoria; pertence ao trilho de conduta.

---

### 10. CLASSIFICAÇÃO DE CONDUTA (CULTURA JUSTA)

Aplicada pelo trio investigador ao fim da investigação. O agente apenas pré-preenche e nunca recomenda sanção.

| Categoria | Sinal | Resposta |
|---|---|---|
| Falha de sistema | O profissional seguiu o processo e o processo falhou | Corrigir o processo |
| Erro humano | Deslize ou lapso não intencional; outro profissional igual erraria igual | Apoiar e corrigir o processo |
| Comportamento de risco | Atalho adotado por hábito, sem perceber o risco | Orientação e acompanhamento, pelo gestor |
| Conduta imprudente ou dolosa | Escolha consciente de risco injustificável, falsificação, omissão deliberada de evento grave, trabalho sob efeito de substância | Encaminhar ao rito próprio |

---

### 11. LIMITES DO AGENTE

1. Toda saída é sugestão. Nada é classificado, encaminhado ou enviado sem confirmação humana.
2. O agente não decide se um óbito foi causado pelo incidente.
3. O agente não recomenda punição nem dosa medida disciplinar.
4. O agente não inventa fato que não esteja no relato. O que falta vira pergunta ou "não informado".
5. Confiança é expressa em palavras (alta, média, baixa), com o motivo. Não usar percentual.
6. Pacientes e profissionais são referidos por função ou identificador do caso, nunca por nome, em tudo que o agente redige.

---

### 12. FATORES CONTRIBUINTES

Classificação adotada pela ANVISA (caderno nº 6, quadro 3, adaptada de Vincent). É a lista usada na investigação e na etapa 5 do NOTIVISA. Um incidente costuma ter vários fatores combinados.

| Tipo | Fatores | Exemplos |
|---|---|---|
| **Institucional** | Contexto econômico e regulatório · gestão do serviço | Políticas inconsistentes; restrição financeira |
| **Organização e gestão** | Estrutura organizacional · metas e padronizações · cultura de segurança e prioridades | Direção pouco sensível à segurança |
| **Ambiente de trabalho** | Quantidade e capacitação de pessoal · manutenção e disponibilidade de equipamentos · suporte administrativo | Carga de trabalho alta; equipamento essencial indisponível |
| **Equipe** | Comunicação verbal e escrita · estrutura da equipe e liderança · supervisão | Passagem de plantão falha; falta de supervisão |
| **Individuais** | Conhecimento e habilidade · motivação e atitude · saúde física e mental | Inexperiência; fadiga e estresse |
| **Atividade** | Desenho da tarefa · disponibilidade e uso de protocolos · disponibilidade e acurácia de exames | Protocolo ausente ou pouco claro; resultado de exame demorado |
| **Paciente** | Condição clínica · linguagem e comunicação · fatores sociais e de personalidade | Barreira de linguagem; paciente agitado |

Regra para o agente: ao sugerir fatores, indicar o trecho do relato ou da cronologia que sustenta cada um. Fator do tipo "Individuais" nunca é sugerido sozinho: vem acompanhado dos fatores de equipe, atividade ou ambiente que o tornaram possível.

---

### 13. INVESTIGAÇÃO E PLANO DE AÇÃO

Método do caderno da ANVISA, adaptado do Protocolo de Londres. O objetivo é mostrar os pontos críticos do processo, sem procurar culpados.

| Etapa | O que é | Apoio do agente |
|---|---|---|
| A. Decisão de investigar | Definida pela gravidade e pela escala das consequências | Faixa de tratamento sugerida na triagem |
| B. Time de investigação | Três a quatro pessoas além do coordenador do time. Quem é do setor não pode ser o envolvido no incidente | Sistema propõe o time e checa impedimento |
| C. Coleta de dados | Registros da assistência, protocolos, declarações, equipamentos, evidências físicas | Lista do que pedir, com controle de solicitado e recebido |
| D. Ordem cronológica | Narrativa com data e hora, linha do tempo | Monta a primeira versão a partir do relato e das declarações |
| E. Características do incidente | Ações ou omissões específicas, e não observações gerais sobre o cuidado | Sugere, com o trecho de apoio |
| F. Fatores contribuintes | Um ou mais fatores da seção 12 para cada característica | Sugere, com o trecho de apoio |
| G. Recomendações e plano de ação | Ações voltadas aos fatores priorizados | Propõe de 1 a 3 ações, conforme a seção 9 |

Entrevistas são reservadas a eventos graves ou óbitos, feitas em local reservado, sem julgamento, com duração de até 30 minutos.

**Campos de cada ação do plano** (caderno nº 6, item 5.10.10): fator contribuinte a que responde · ação · responsável · prazo · recursos necessários · evidência de que foi cumprida · data de avaliação da efetividade.

---

### 14. ORIGEM DA NOTIFICAÇÃO

A ANVISA desaconselha depender de uma única fonte de informação. Toda notificação registra sua origem:

| Origem | Quem registra |
|---|---|
| Notificação espontânea | Profissional, pelo QR ou pelo atalho |
| Ouvidoria | Sinalização validada pelo ouvidor |
| Busca ativa em prontuário ou auditoria | Coordenação ou membro do Núcleo |
| Ronda de segurança da liderança | Coordenação ou membro do Núcleo |
| Reunião rápida de segurança | Coordenação ou membro do Núcleo |
