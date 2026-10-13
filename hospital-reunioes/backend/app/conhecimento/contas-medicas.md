# Contas médicas

Contas médicas é o módulo que confere a conta hospitalar de internação antes de ela ir para a operadora. A faturista envia a conta e o prontuário completo exportados do MV; o módulo cruza os dois com a memória da operadora e devolve um Guia, a lista do que corrigir no MV, item por item. O que ela corrige vira indicador de onde a perda nasce: dispensação, regra automática, cadastro e preço, registro assistencial ou lançamento manual.

O módulo nasceu da especificação do Diretor Executivo e é entregue em três etapas. A primeira faz a conferência só por código, sem inteligência artificial: preço contra a tabela da operadora, diárias contadas pelas movimentações, prescrição contra o que foi lançado, item lançado sem registro no prontuário. A segunda traz a leitura do texto livre do prontuário por IA e o Painel com os indicadores. A terceira traz a gestão: memória editada pela tela, Validação, Conferência da coordenação, contratos e Habilitação.

Toda Demanda sobre uma tela de Contas médicas, uma conta mal lida, um preço ou uma diária que não bate pertence a este Produto.

## O que já está no ar

A primeira etapa inteira: a fundação do módulo, a carga das operadoras, o envio das contas, a análise e o Guia:

- o item **Contas médicas** no menu lateral, que aparece só para quem tem perfil no módulo;
- a tela de contas, com o envio dos PDFs, o "Último envio" e a fila, descritos abaixo;
- a análise da conta, que roda sozinha em segundo plano e avisa no sino quando o Guia fica pronto;
- os perfis e as permissões de cada um, já gravados no banco;
- o lugar seguro onde os PDFs ficam guardados por sete dias;
- a tela Operadoras, aberta a partir da tela de contas para quem tem a permissão de regra contratual e tabelas (gestão de contas médicas e as duas diretorias);
- a tela Memória da operadora, aberta pela operadora na tela Operadoras, descrita abaixo;
- a tela de Habilitação, aberta a partir da tela de contas para quem tem a permissão de habilitar pessoas (as duas diretorias), descrita em "Quem vê";
- o Painel, aberto a partir da tela de contas, descrito em "O Painel".

Na tela Operadoras, a gestão envia o arquivo de memória de cada convênio, o mesmo que o diretor monta, e a memória passa a valer sem programador no meio. A tela mostra a versão, quantas regras vigentes e pendentes entraram e os parâmetros lidos do cabeçalho; os números têm de bater com o arquivo. Mandar uma versão nova aposenta a anterior. Parâmetro do cabeçalho que o sistema ainda não usa fica guardado, e a memória em vigor pode ser baixada de volta inteira. Arquivo com um número no formato de CPF é recusado, porque memória não pode ter dado de paciente. Na mesma tela a gestão cadastra os nomes de plano como o MV imprime, cada um com a operadora e a coluna de preço, e os setores do MV com a acomodação de cada um.

Também na tela Operadoras entram as tabelas de preço de cada convênio. A gestão escolhe a operadora e a categoria (materiais, medicamentos, diárias e taxas ou pacotes), informa o início da vigência e, se houver, o fim, e envia a tabela de preço no arquivo de planilha separado por ponto e vírgula que o diretor entrega. O sistema reconhece sozinho o tipo da tabela pelas colunas da primeira linha e diz quantos itens entraram; arquivo com colunas que ele não conhece é recusado, e a mensagem lista as colunas esperadas. Uma versão nova não apaga a anterior: as duas ficam lado a lado, e a conta de um atendimento antigo usa a tabela que valia na data do atendimento. Para cada operadora, a tela mostra cada categoria com a tabela, a versão, a vigência e a situação (carregada ou não carregada). Honorário aparece sempre como não carregado, porque a tabela de honorários ainda não chegou; categorias que só a memória de uma operadora traz, como SADT e porte anestésico, aparecem do mesmo jeito. Preço que a memória da operadora dá como validado vale mais que a tabela.

Cada operadora da tela Operadoras abre a sua **Memória da operadora**. No topo ficam a versão em vigor, a data dela, o contrato e o último aditivo, a situação e quantas regras estão pendentes. As regras vêm em abas (Todas, Diárias, Pacotes, Taxas e aluguéis, Insumos por tempo, Medicamentos, Honorários e Pendentes), cada uma com a origem, quem validou e a data. Quem tem a permissão edita a regra pela tela, no botão Editar, e decide a regra pendente no botão Decidir, que a torna vigente com o nome de quem decidiu e a data. Toda mudança gera uma versão nova da memória: a anterior deixa de valer, mas fica no histórico de versões, com o que mudou, quem mudou, quando e o texto anterior, e a conta analisada antes continua ligada à versão com que foi analisada. Regra operacional pede a permissão de incluir regra operacional; regra de preço, diária, pacote ou tabela pede a de regra contratual e tabelas. Quando a regra veio do modelo do hospital, a edição oferece "aplicar a todas as operadoras que têm esta regra", e cada operadora com a mesma regra ganha a sua versão nova. O botão Exportar baixa a memória em vigor no formato do arquivo do diretor, gerada a partir do que está no sistema; o arquivo pode ser enviado de volta sem perder regra nem parâmetro do cabeçalho.

A tela Operadoras abre com o mapa: uma linha por operadora, com a situação, a versão da memória e, em cada categoria, a tabela e a versão em uso. Logo abaixo fica a biblioteca de tabelas, com todas as versões de cada categoria e a marca da que está em uso hoje. O botão "Nova versão" de uma categoria abre o envio de tabela já com a operadora e a categoria escolhidas; a versão anterior fica guardada, e a nova passa a valer a partir do início da vigência dela.

Na mesma tela entra o dicionário de itens do hospital: o nome do produto na prescrição e na ficha anestésica, com os sinônimos, ligado ao código da conta (por exemplo, rocurônio e Esmeron caem no mesmo código). Termo que já existe é atualizado. Quando o nome não está no dicionário, o sistema tenta casar pela marca e pela concentração; só pela marca, o casamento sai com confiança média.

Na conferência, um preço que não pode ser comparado com a tabela sai como "Não conferido", e nunca como erro de preço: tabela não carregada para a categoria, nenhuma versão vigente na data do atendimento, preço zero na tabela, item que a tabela marca como pacote, código que aparece repetido na tabela sem a especialidade que desempata, e honorário.

## O envio e a fila

Na tela de contas, a faturista arrasta os PDFs exportados do MV para a área de envio, ou clica em "Selecionar arquivos", vários de uma vez: a conta e o prontuário completo de cada atendimento. Ela não digita nem renomeia nada. O app lê dentro de cada PDF se ele é conta ou prontuário, pelo conteúdo da primeira página e não pelo nome do arquivo, e lê o número do atendimento. É por esse número que a conta e o prontuário se encontram. Um atendimento pode ter várias contas (as parciais), e todas usam o mesmo prontuário.

Cada envio aceita até 10 atendimentos e 30 arquivos, e cada arquivo pode ter até 100 MB. O que passa disso é recusado com uma frase que diz o limite, e o resto do envio segue. A conta de um plano que ainda não está cadastrado na tela Operadoras é recusada na hora, com o nome do plano: "Plano ASSIM BÁSICO ainda não configurado". A gestão cadastra o plano e a faturista envia a conta de novo. Os outros atendimentos do mesmo envio seguem normalmente.

Assim que o envio termina, aparece o **Último envio**, uma linha por atendimento, dizendo o que chegou: "31302, conta e prontuário", "31310, 2 parciais e prontuário", "31318, falta o prontuário" ou "31320, falta a conta". Logo abaixo ficam as recusas, cada uma com o arquivo e o motivo.

Se o prontuário do atendimento já foi enviado nos últimos sete dias, a conta nova é pareada com ele e não é preciso mandar o prontuário de novo. Quando o período da conta passa da última data desse prontuário, o Último envio avisa para mandar o prontuário atualizado. Enviar de novo a mesma conta do mesmo atendimento não cria outra: a conta volta para a fila e é analisada outra vez.

A fila mostra as contas em ordem de envio e, dentro do envio, na ordem dos arquivos. Nunca é reordenada por valor. Cada conta aparece pelo número do atendimento, com o número da conta ao lado, e com a situação:

- **Falta o prontuário** ou **Falta a conta**: o par ainda não chegou;
- **Na fila**: esperando a análise;
- **Pronta em instantes**: a análise está rodando;
- **A fazer**: o Guia está pronto, com a nota, o R$ a ajustar e quantos itens já foram feitos ("0 de 9");
- **Em correção**: o Guia já foi aberto, com o botão "Continuar";
- **Erro**: a análise não conseguiu ler um dos arquivos, com o motivo em uma frase e o botão "Enviar de novo".

A aba **Concluídas** guarda as contas já concluídas, as mais recentes primeiro, com a contagem de pendências de quem concluiu com pendência. A faturista vê só as próprias contas, na fila e nas Concluídas; quem tem o Painel completo vê as de todas.

## A análise

Assim que a conta e o prontuário do atendimento estão no sistema, a análise começa sozinha, em segundo plano: a faturista não precisa esperar na tela nem atualizar a página. O app lê a conta inteira e o prontuário, conta as diárias pelas movimentações, confere preço, prescrição, ficha anestésica e o que foi lançado sem registro, e monta o Guia. Ele analisa até duas contas ao mesmo tempo e continua respondendo enquanto lê um prontuário grande; as outras esperam a vez na fila, na ordem de envio.

O prontuário é lido uma vez por atendimento e serve a todas as parciais: a segunda parcial do mesmo atendimento não espera a leitura de novo. Quando o atendimento recebe um prontuário mais novo, ele substitui o anterior.

Quando as contas de um envio terminam, a faturista recebe um aviso no sino, como "2 contas prontas". Clicar no aviso abre a fila de contas, onde cada uma aparece como A fazer.

Enviar de novo uma conta que já tinha Guia refaz a análise: as linhas que a faturista já marcou (Feito, Não procede ou Bloqueado) ficam como estão, e as que estavam sem marcação são trocadas pelas da análise nova.

Se o app reiniciar no meio de uma análise, a conta volta sozinha para a fila. Depois de três tentativas sem terminar, ela fica em Erro, com o botão "Enviar de novo". Leitura que não fecha também vira Erro na hora, com o motivo em uma frase:

- "Este PDF não tem texto. Exporte de novo pelo MV": o PDF veio como imagem;
- "Não consegui ler a conta inteira": a soma dos itens lidos não bateu com o total da conta;
- "Prontuário com arquivo incompleto": o rodapé indica mais páginas do que vieram no arquivo.

O tempo de cada etapa da análise fica guardado, para medir a meta de uma conta de cinco dias pronta em até cinco minutos.

## A inteligência artificial

A segunda etapa trouxe a inteligência artificial para a análise. Ela tem duas tarefas. A primeira lê o texto livre do prontuário (evoluções, anotações, prescrições, descrição cirúrgica) e lista o que aconteceu com o paciente, dia a dia, com a página e o trecho que provam cada fato. A segunda compara esses fatos com a conta e com a memória da operadora e propõe as linhas do Guia (incluir, ajustar quantidade, retirar ou validar), cada uma com a regra da memória que a sustenta. Preço, contagem de diárias e as contas da nota continuam com o código: a IA não devolve valor em reais.

A leitura do prontuário pela IA acontece uma vez por atendimento e serve a todas as parciais e ao reenvio. Ela recebe só o texto que o código não leu sozinho, junto com o que ele já leu (prescrições, balanço, glicemias e as linhas que as conferências já puseram no Guia), para não refazer. Prontuário grande demais para uma leitura só é lido em partes, por períodos de dias, e o fato repetido entre duas partes conta uma vez. O trecho que a IA cita é conferido na página: quando não está lá nem na página vizinha, o fato fica marcado para conferir, com confiança baixa. Internação, alta e setor de cada dia valem como o código leu; quando a IA leu diferente, a diferença aparece no parecer parcial do Guia, junto com os documentos esperados que faltam e as observações da IA (uma evolução ilegível, por exemplo).

O texto do prontuário vai à IA sem o nome da paciente, e o provedor não guarda nada do que recebe nem usa o texto para treinar modelo. A resposta tem um formato combinado; fora dele, é recusada e pedida de novo, até três vezes, com uma espera maior a cada vez. Depois disso a conta fica em Erro com "Tente de novo em alguns minutos" e o botão "Enviar de novo".

O custo de cada chamada fica gravado: quantos tokens entraram e saíram, quantos vieram do cache e quanto custou, em dólar, e cada conta guarda a soma das chamadas dela, inclusive as de uma nova análise. O modelo de inteligência artificial de cada tarefa é trocado numa configuração do servidor, sem programador.

Quem tem a permissão de regra contratual e tabelas vê no Guia o botão "Reanalisar", nas contas A fazer e Em correção. A conta volta para a fila e é analisada de novo, com a memória e as tabelas de agora; as linhas que a faturista já marcou ficam como estão, e as sem marcação são trocadas pelas da análise nova.

## O Guia

O Guia é a tela de uma conta com a lista do que corrigir no MV. Foi feito para caber em meia tela, ao lado do MV, e vira lista em telas estreitas.

No topo ficam o número do atendimento, o rótulo da paciente, a conta, a operadora, a coluna de preço, o período da parcial e a situação. Quando o prontuário veio incompleto, aparece a faixa "PARECER PARCIAL" com a lista do que faltou. Logo abaixo, três números: a **Nota de entrada** (de 0 a 100, quanto a conta estava certa antes da correção), o **R$ a ajustar** (com quantos itens e quanto mais está em validação) e os **Itens feitos** (quantos a faturista já marcou, de quantos).

As linhas vêm agrupadas por dia e setor, como "03/10 · CTI". Cada linha começa pelo verbo (Incluir, Ajustar quantidade, Corrigir preço, Retirar ou Validar) e traz a quantidade, o período, o valor com sinal e o código, que copia com um clique. "Ver evidência" abre a página do prontuário e o trecho que sustenta a linha. A etiqueta cinza "Não conferido" marca o valor que não pôde ser conferido contra a tabela da operadora: ele fica fora da nota e do R$ a ajustar.

Em cada linha, três botões:

- **Feito**: a faturista corrigiu no MV. Um clique, e a linha recolhe em verde.
- **Não procede**: a linha está errada. Pede um de quatro motivos (já está na conta, sem evidência no prontuário, a regra é outra, outro); o texto é opcional, menos em "outro". Vai para a gestão como observação.
- **Bloqueado**: o MV não deixou lançar, por falta de cadastro ou de preço. Um clique.

Enquanto a conta não foi concluída, toda marcação tem "Desfazer". "Marcar o dia como feito" marca de uma vez as linhas abertas do grupo. A linha Validar não tem botão: o item já foi para a validação da gestão, e a faturista não precisa decidir.

No rodapé ficam a observação opcional para a gestão e o botão "Concluir e abrir a próxima", sempre habilitado. Com item sem marcação, o app pergunta "Concluir assim mesmo?". Concluir abre a próxima conta A fazer da faturista, na ordem de envio. A conta fica Concluída quando tudo foi resolvido, ou Concluída com pendência quando sobrou linha sem marcação, bloqueada ou em validação. Na conclusão a nota de entrada é refeita sem as linhas Não procede; a nota original fica guardada.

Abrir o Guia pela primeira vez muda a conta de A fazer para Em correção. A faturista só abre as próprias contas; quem tem o Painel completo abre a de qualquer uma.

## O Painel

O Painel mostra à diretoria onde a perda da conta nasce. Ele abre a partir da tela de contas, pelo botão Painel. Os números são das contas concluídas, por semana de segunda a domingo, contada pelo dia em que a faturista concluiu a conta. A conta concluída e enviada de novo sai do Painel até ser concluída outra vez. No topo ficam três filtros: a semana, a operadora e o tipo de conta (Parcial, quando o atendimento tem mais de uma conta, ou Única).

Quatro cartões no topo:

- **Nota média de entrada** da semana, com a da semana anterior ao lado. Sobe quando a ponta registra e dispensa melhor.
- **Contas concluídas** na semana.
- **R$ apontado**, com quanto disso já foi incluído no MV (as linhas Feito).
- **Não procede**: quantas linhas a faturista marcou como Não procede, de quantas apontadas, sem as de validação. Mede o acerto da IA e da memória.

E seis blocos:

- a nota média por semana, nas oito semanas até a escolhida;
- o R$ apontado por causa-raiz (dispensação, regra automática, cadastro e preço, registro assistencial, lançamento manual), com o percentual de cada uma: diz quem corrige;
- os dez itens que mais faltam: os códigos com mais contas com linha Incluir, com o número de contas e o R$. É a fila de parametrização para a consultoria do MV;
- a produção de cada faturista: contas, contas com pendência, R$ incluído, taxa de Não procede e, em segundo plano, o R$ retirado;
- o R$ incluído por nível de evidência (Registrado, Prescrito, Prescrito SN, Por regra), por semana, em barras: mostra quanto do valor incluído depende só de prescrição;
- o custo de inteligência artificial da semana e o custo médio por conta, em dólar.

Quem tem o Painel completo (coordenadora de faturamento, gestão de contas médicas e as duas diretorias) vê tudo. A faturista vê só a própria linha de produção, e mais nenhum bloco.

## Quem vê

O módulo tem perfis próprios, separados dos de Reuniões, POPs e Ouvidoria. São seis: faturista, coordenadora de faturamento, gestão de contas médicas, diretoria médica, diretoria executiva e credenciamento. Quem não tem nenhum deles não vê o item no menu e não consegue abrir a tela. O Super admin do aplicativo entra, como nos outros módulos.

Cada perfil vem com um conjunto inicial de permissões, tirado da especificação do diretor:

- **Faturista**: envia e corrige contas, e vê só as próprias.
- **Coordenadora de faturamento**: o mesmo da faturista, mais o Painel completo e a Conferência da coordenação. Incluir regra operacional está desligado para ela, em avaliação pelo diretor.
- **Gestão de contas médicas**: tudo, menos habilitar pessoas.
- **Diretoria médica** e **Diretoria executiva**: tudo.
- **Credenciamento**: só os contratos e o aviso de reajuste.

Esse conjunto não é fixo. A diretoria muda tudo pela tela de **Habilitação**, sem programador no meio: os perfis ficam nas linhas e as permissões nas colunas, e cada célula liga ou desliga com um clique. Na mesma tela, a busca acha a pessoa pelo nome, e ali se dá, troca ou tira o perfil dela. A mudança vale na hora: quem ganha um perfil passa a ver o item no menu, e quem perde uma permissão deixa de abrir a tela dela já no clique seguinte. Toda mudança fica registrada com quem mudou, quando, como estava antes e como ficou.

## Dado de paciente

O módulo não guarda nome completo, CPF, carteira nem data de nascimento de paciente em lugar nenhum. Da paciente ficam só um rótulo curto, como "Maria S.", e a idade em anos. Os PDFs da conta e do prontuário ficam num depósito privado, que só o aplicativo alcança, e são apagados sete dias depois do envio.

## O que costuma virar Demanda

- Uma pessoa que deveria ver Contas médicas no menu e não vê, ou o contrário (Defeito, ou Informação se for dúvida sobre o perfil).
- Pedido para dar ou trocar o perfil de alguém no módulo (Informação: quem faz é a diretoria, na tela de Habilitação).
- Uma permissão desligada na Habilitação que continua valendo, ou ligada que não abre a tela (Defeito).
- Memória recusada na tela Operadoras, ou contagem de regras que não bate com o arquivo do diretor (Defeito, ou Informação se a recusa explica o motivo, como o CPF).
- Uma regra editada ou decidida que não gera versão nova, o botão Editar ou Decidir que some para quem tem a permissão, ou a memória exportada que não volta igual quando enviada de novo (Defeito).
- Tabela de preço recusada, contagem de itens que não bate com o arquivo, ou preço "Não conferido" onde a tabela tem valor (Defeito, ou Informação se a recusa lista as colunas esperadas ou se o motivo é um dos casos de "Não conferido").
- Um botão do Guia que não marca, uma conta que não conclui ou uma nota que não bate com as linhas (Defeito).
- Uma conta que não sai de Na fila ou de "Pronta em instantes", um Erro com motivo que não bate com o PDF, ou o aviso de contas prontas que não chega ao sino (Defeito, ou Informação se o motivo do Erro explica, como o PDF sem texto).
- Uma conta que volta para Erro com "Tente de novo em alguns minutos" mesmo depois de enviada de novo, ou o botão "Reanalisar" que não aparece para a gestão (Defeito).
- Um número do Painel que não bate com as contas da semana, ou a faturista que vê a produção de outra pessoa (Defeito, ou Informação se a dúvida é sobre a semana de segunda a domingo ou sobre o que entra em cada número).
- Dúvida sobre quando chega o envio de contas ou alguma das próximas entregas (Informação).
