# Contas médicas (HSM)

Confere a conta hospitalar de internação antes do envio à operadora: a faturista envia a conta e o prontuário completo exportados do MV, o módulo cruza os dois com a memória da operadora e devolve um Guia de ações. O que ela corrige vira indicador de onde a perda nasce. Terceiro contexto do repositório (ver [CONTEXT-MAP.md](../../CONTEXT-MAP.md)); nasceu da especificação do Diretor Executivo (v1.0 e adendos v1.1 a v1.3, outubro/2026) e do grilling de 12/10/2026 ([ADR 0070](../adr/0070-contas-medicas-aritmetica-no-codigo-ia-no-julgamento-memoria-no-banco.md)). Curado por humano daqui em diante.

**Nome do módulo:** Contas médicas. A palavra "auditoria" não aparece em tela, rota, texto, Manual nem nome de tabela deste módulo (decisão do diretor).

## Atendimento, conta e prontuário

**Atendimento**:
Número da internação no MV. É a identificação principal de tudo no módulo: a faturista nunca digita, o sistema lê dos PDFs e pareia por ele. Um Atendimento tem um Prontuário e uma ou mais Contas.
_Evitar_: internação (como identificador), número da conta (como identificador). **Homônimo**: "Dados do Atendimento" no contexto Reuniões é o módulo das tabelas que alimentam a Ana; não é este Atendimento.

**Conta**:
Fatura de um Atendimento, exportada do MV como PDF "Fatura Individual": cabeçalho (atendimento, conta, período, acomodação, plano) e itens com data, setor, código, quantidade, unitário e total. A leitura só é aceita quando a soma dos itens fecha com o total.
_Evitar_: fatura, guia (que é outra coisa aqui).

**Parcial**:
Conta que cobre só um período do Atendimento. Todas as Parciais usam o mesmo Prontuário; cada uma é uma linha da fila. Diária que começa no dia de divisa entre duas Parciais pertence a exatamente uma delas.

**Prontuário**:
PDF único "Impressão de Prontuário" do MV com todos os documentos clínicos do Atendimento, de preferência na impressão Completa. A capa declara os grupos impressos e a quantidade de cada um; o módulo confere capa contra corpo.
_Evitar_: PEP, evolução (que é um dos documentos, não o todo).

**Família de documento**:
Layout reconhecido por assinatura de texto dentro do Prontuário (capa, prescrição, evolução, anotação de enfermagem, balanço hídrico, resumo de alta, admissão de unidade, ficha anestésica, descrição cirúrgica, fisioterapia, guia TISS, anexo, digitalizado, não reconhecido). Cada Família tem o seu tratamento: estruturar por código, mandar o texto à IA, ou descartar.

**Parecer parcial**:
Marca do Guia quando o Prontuário não trouxe um grupo essencial que a capa declara, termina antes do fim do período da Conta, ou tem mais de 10% de páginas sem texto. O Guia sai mesmo assim, com a lista do que faltou.

**Operadora**:
Convênio com contrato próprio com o hospital (ASSIM, Unimed, Leve, Porto, Amil, Oplan, Klini). Reconhecida pelo nome do **Plano** impresso na Conta, por uma tabela de planos mantida pela gestão. Plano desconhecido: a Conta é recusada com o nome do plano, nunca analisada com regra de outra Operadora.
_Evitar_: convênio (no código), plano (como sinônimo de Operadora).

**Coluna de preço**:
Preço distinto por plano dentro da mesma Operadora (na ASSIM, Carioca e Comum). Nem toda Operadora tem; a Unimed tem coluna única.

## Memória da operadora

**Memória**:
Conjunto de parâmetros e Regras de uma Operadora, que mora no banco e é versionado a cada validação (3.1, 3.2). Entra por importação de um arquivo `MEMORIA-<SIGLA>-v<X.Y>.md` (cabeçalho YAML lido pelo código, tabelas de Regras lidas pela IA) e, depois, por tela. A Conta guarda a versão da Memória com que foi analisada. Nada de uma Operadora é usado na análise de outra.
_Evitar_: base de auditoria, configuração da operadora.

**Regra**:
Linha da Memória com identificador (`ASSIM-DIA-01`), seção (PRI, PRC, DIA, PAC, TAX, CC, HON, INS, MED), texto, tipo (**Contratual**: preço, diária, deflator, pacote, tabela; **Operacional**: quantidade, padrão de lançamento, orientação), origem e **Status** Vigente ou Pendente. Prática validada ganha do contrato; o que o contrato diz fica registrado na frase, para sustentar recurso de glosa.

**Regra pendente**:
Regra sem validação da diretoria ou da gestão de contas médicas. Nunca gera ordem para a faturista: gera a ação Validar.

**Diretriz geral HSM**:
Decisão do hospital sobre como ler o prontuário e montar a conta (identificar pelo Atendimento, prescrição plena, "se necessário" sempre incluído, regras de diária e de acomodação contratada). Entra Vigente em toda Operadora nova, copiada com o identificador dela.

**Regra técnica HSM**:
Regra do hospital que não depende de contrato (farmacotécnica, protocolo de diluição, fotossensíveis). Copiada para a Operadora nova como Pendente; vira Vigente quando validada para aquela Operadora.

**Tabela de preço**:
Arquivo de preços de uma categoria (material, medicamento, diária e taxa, pacote, honorário) com versão e vigência. Cada Operadora aponta, por categoria, para uma Tabela e uma **regra de preço** (coluna, PMC, preço de fábrica mais percentual, LPM). Tabela não carregada não trava a análise: o preço sai como Não conferido.

**Dicionário de itens**:
Tabela do hospital (não da Operadora) que liga os nomes do mesmo produto na Conta, na prescrição e na ficha anestésica ao código da Conta. Termo sem par vai uma vez à IA, a gestão confirma, e da segunda conta em diante é código.

**Setor**:
Nome do setor como o MV imprime, ligado a uma acomodação (CTI, enfermaria, apartamento, isolamento, centro cirúrgico, hospital-dia, pediatria, UTI pediátrica, UTI neonatal). Setor desconhecido não chuta: gera Validar na diária.
_Evitar_: confundir com o Setor dos POPs ou o setor das Reuniões (entidades de outros contextos).

## Motor de análise

**Motor**:
A sequência que vai do PDF ao Guia. Princípio que não muda: **o que é aritmética, contagem ou busca exata é do código; a IA entra onde só lendo texto livre se sabe o que aconteceu, e onde a Regra exige julgamento.** Preço, diária, teto, nota e indicador nunca saem da IA.

**Leitura por código**:
Extração do texto por página, divisão em Famílias, campos (atendimento, data, hora, setor), prescrição em itens consolidados por dia, balanço hídrico estruturado, contagem de glicemias, descrição cirúrgica e ficha anestésica, e desidentificação. Reduz o Prontuário em cerca de 94% antes de qualquer chamada de IA.

**Conferência por código**:
Comparação determinística que gera Linha do Guia sem IA: preço contra Tabela, Diária contra lançadas, prescrição contra Conta, item lançado sem registro no Prontuário, ficha anestésica contra Conta, gás do centro cirúrgico, procedimento do cabeçalho contra descrição cirúrgica, exame solicitado contra lançado, glicemia contra fita e lanceta. A IA recebe a lista para não repetir.

**Diária**:
Unidade de cobrança da acomodação, contada pelo código a partir das movimentações (internação, transferência de setor, alta, óbito, transferência de hospital) e dos parâmetros da Memória (vencimento às 10h, limite da madrugada às 5h, sempre integral, extra na origem conforme a Operadora). Transferência de setor sem hora exata vira uma **janela**: toda antes ou toda depois do vencimento aplica a regra; janela que atravessa o vencimento gera Validar. Acomodação cobrada é a contratada, mesmo que o MV mostre outra.

**Passo A**:
Chamada de IA que lê o texto livre do Prontuário (evoluções, anotações, formulários) e devolve eventos com página e trecho literal: movimentações, terapias, procedimentos, cirurgias. Não recebe a Conta nem a Tabela. Uma vez por Atendimento; o resultado serve a todas as Parciais.

**Passo B**:
Chamada de IA que compara os eventos com a Conta aplicando a Memória inteira e devolve Linhas com Regra, motivo e evidência. Não devolve valor em reais e não trata de preço nem de quantidade de diárias.

**Evidência**:
Página do PDF original e trecho literal de até 300 caracteres que sustentam uma Linha. O código confere que o trecho existe na página citada; sem conferência, a Linha ganha a etiqueta "conferir evidência". Nível: **Registrado** (uso escrito), **Prescrito** (prescrição de horário fixo sem checagem), **Prescrito SN** ("se necessário" sem registro), **Por regra** (por tempo ou teto).

**Desidentificação**:
Remoção, antes de qualquer envio à IA e de qualquer gravação em banco, do nome do paciente, nome da mãe, CPF (inclusive do médico na assinatura), RG, CNS, carteira, data de nascimento, endereço e telefone. No banco ficam só o **rótulo** ("Maria S.") e a idade em anos. Teste automático em toda conta: os valores da capa não aparecem no texto de saída.

**Nota de entrada**:
`100 × (1 − R$ apontado ÷ R$ devido)`, mínimo 0, calculada quando o Guia fica pronto. R$ apontado é a soma dos valores absolutos das Linhas, sem Validar nem Não conferido. Recalculada na conclusão sem as Linhas Não procede (`nota_entrada`; a original fica em `nota_bruta`).

## Guia e trabalho da faturista

**Guia**:
Lista de Linhas que o módulo entrega para uma Conta, agrupada por dia e setor, com três números no topo: Nota de entrada, R$ a ajustar, Itens feitos. Funciona a 720 px, ao lado do MV. Vai direto para a faturista, sem validador humano antes.
_Evitar_: parecer, relatório, auditoria.

**Linha**:
Uma ação sobre um item da Conta, com verbo na frente: **Incluir**, **Ajustar quantidade**, **Retirar**, **Corrigir preço** (só o código gera) ou **Validar**. Item diário repetido vira uma Linha só, com data e data fim. Toda Linha tem origem (código ou IA), Regra, Evidência, causa-raiz e confiança.

**Estado da Linha**:
Aberta → **Feito** (conta para a produção), **Não procede** (com motivo: já está na conta, sem evidência no prontuário, a regra é outra, outro; vai para a Validação), **Bloqueado** (o MV não deixou lançar; vai para a fila do cadastro), **Em validação** (ação Validar, sem botão para a faturista), **Decidida** (pelo validador). Desfazer existe enquanto a Conta não foi concluída.

**Situação da Conta**:
Aguardando arquivo → Em análise (na fila ou processando) → A fazer (Guia pronto) → Em correção → Concluída ou Concluída com pendência; mais **Retorno** (a Validação decidiu uma Linha de Conta já concluída) e **Erro** (leitura impossível, com motivo em uma frase e "Enviar de novo").

**Causa-raiz**:
Onde o problema nasce e quem corrige: **Dispensação** (farmácia e enfermagem), **Regra automática** (TI e consultoria MV), **Cadastro e preço** (credenciamento e cadastro), **Registro assistencial** (enfermagem e corpo clínico), **Lançamento manual** (faturamento). A IA propõe; o código sobrepõe nos casos óbvios (toda Linha de diária, de preço e Bloqueado).

**Validação**:
Fila da diretoria e da gestão de contas médicas: Regras pendentes agrupadas por Regra, Bloqueados agrupados por código, observações do time. Decidir uma Regra gera versão nova da Memória e devolve as Linhas afetadas; Conta já concluída volta à faturista em Retorno só com essas Linhas.

**Conferência da coordenação**:
Segunda checagem que só a coordenadora de faturamento vê: cenários cadastrados pela gestão (procedimento que dispara → insumos a conferir) geram **lembretes** por Conta. A faturista não sabe que existem; o Guia, a nota e a produção dela não mudam.

**Tema de validação**:
Cartão da Validação: uma Regra pendente, um código Bloqueado, uma observação do time ou um termo proposto para o Dicionário, com as Linhas de todas as Contas que esperam a mesma decisão. É por tema, nunca por Conta.

**Cenário**:
Situação cadastrada pela gestão para a Conferência da coordenação: o procedimento que dispara (texto livre) e os insumos a conferir (código e quantidade). Pode valer para uma Operadora ou para todas.

**Lembrete**:
O que a Conferência da coordenação gera quando um Cenário ocorreu no Atendimento e falta insumo na Conta: insumos que faltam, valor pela Tabela, Evidência. Estados: aberto, Incluído, Não se aplica.

**Nota de saída**:
Nota recalculada sobre a Conta reenviada depois da correção no MV, só com as Linhas Feito que continuam na conta. O reenvio é opcional; sem ele a Conta vale igual para a Produção da faturista.

**Reanalisar**:
Reprocessar uma Conta A fazer ou Em correção com o modelo ou a Memória atuais, preservando as Linhas já marcadas. Aparece como "Reanalisar com a regra nova" depois de ensinar uma Regra.

**Produção da faturista**:
Contas concluídas, R$ incluído (diferenças positivas das Linhas Feito), R$ retirado (glosa evitada, em segundo plano) e taxa de Não procede (Linhas Não procede ÷ Linhas apontadas, sem Validar).

## Pessoas e papéis de acesso

Eixo próprio `perfil_contas_medicas` em `participantes`, ortogonal aos eixos de Reuniões, POPs e Ouvidoria. O perfil é um conjunto inicial de **permissões** (enviar e corrigir contas, decidir na validação, incluir regra operacional, regra contratual e tabelas, contratos e avisos, painel completo, habilitar pessoas, conferência da coordenação); a tela de Habilitação liga e desliga cada uma por perfil. Quem não tem a permissão não vê o item no menu, e rota e API recusam (403).

**Faturista**: envia e analisa Contas. A Fila é comum: a conta livre ganha dona quando uma faturista abre o Guia dela (puxa a conta), e a dona pode devolver à fila a conta Em correção. Vê a Fila, as que puxou ("Minhas"), os próprios envios e, no Painel, só a produção das contas que concluiu (ADR 0073).
**Apoio ao faturamento**: só envia Contas e acompanha os próprios envios até a conta ficar pronta; não analisa. Nome de tela a confirmar com o diretor (ADR 0073).
**Coordenadora de faturamento**: faturista mais Painel completo e Conferência da coordenação.
**Responsável por gestão de contas médicas**: tudo menos habilitar pessoas.
**Diretoria médica** e **Diretoria executiva**: tudo.
**Credenciamento**: só vê Contratos e recebe o aviso de reajuste.

## Ambiguidades resolvidas

- **Atendimento** (este contexto) ≠ **Dados do Atendimento** (Reuniões / Ana). Homônimos, conceitos distintos.
- **Setor** (este contexto: nome no MV → acomodação) ≠ Setor dos POPs ≠ setor das Reuniões. Sem FK entre eles.
- **Guia** é a lista de ações da faturista. A "guia" da Conta do MV (campo `Guia:` do cabeçalho, autorização da operadora) chama-se **guia de autorização** quando precisar ser citada.
- **Conferência** é sempre por código. O que a IA faz chama-se Passo A e Passo B, nunca conferência.
- **Validar** (ação da Linha, para a diretoria) ≠ validar a leitura (teste de soma da Conta). O segundo chama-se **conferência da leitura**.

## Diálogo de exemplo

**Dev:** A faturista arrastou a conta 48811 e o prontuário do atendimento 31245. O que acontece?
**Especialista:** O sistema pareia pelo Atendimento, lê o Plano na Conta e acha a Operadora. Se o plano não estiver cadastrado, recusa na hora e diz o nome do plano. Se achou, a Conta entra na fila.
**Dev:** E a IA lê o prontuário inteiro?
**Especialista:** Não. O código separa as Famílias, estrutura prescrição e balanço, conta glicemia, desidentifica, e manda à IA só o texto livre, uns 6% do arquivo. A diária, o preço e a prescrição contra a Conta o código confere sozinho antes da IA.
**Dev:** Achou pantoprazol prescrito em 6 dias e lançado em 3. Isso é Linha de quem?
**Especialista:** Do código: Incluir, 3 a mais, Regra de prescrição plena, Evidência Prescrito, causa-raiz Dispensação. A IA recebe essa Linha na lista para não repetir.
**Dev:** E se a regra que sustenta a Linha for Pendente?
**Especialista:** Então a ação é Validar, a faturista só vê "o item já foi para a validação", e a Linha aparece na fila da diretoria agrupada pela Regra. Pendente nunca vira ordem.
**Dev:** A faturista marcou Não procede. A conta fecha?
**Especialista:** Fecha. Concluir é sempre possível; o Não procede vai para a Validação como observação e a nota de entrada é recalculada sem ele. O que não muda é a nota bruta, que fica guardada.
