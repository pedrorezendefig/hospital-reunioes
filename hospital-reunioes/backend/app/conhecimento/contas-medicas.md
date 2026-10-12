# Contas médicas

Contas médicas é o módulo que confere a conta hospitalar de internação antes de ela ir para a operadora. A faturista envia a conta e o prontuário completo exportados do MV; o módulo cruza os dois com a memória da operadora e devolve um Guia, a lista do que corrigir no MV, item por item. O que ela corrige vira indicador de onde a perda nasce: dispensação, regra automática, cadastro e preço, registro assistencial ou lançamento manual.

O módulo nasceu da especificação do Diretor Executivo e é entregue em três etapas. A primeira faz a conferência só por código, sem inteligência artificial: preço contra a tabela da operadora, diárias contadas pelas movimentações, prescrição contra o que foi lançado, item lançado sem registro no prontuário. A segunda traz a leitura do texto livre do prontuário por IA e o Painel com os indicadores. A terceira traz a gestão: memória editada pela tela, Validação, Conferência da coordenação, contratos e Habilitação.

Toda Demanda sobre uma tela de Contas médicas, uma conta mal lida, um preço ou uma diária que não bate pertence a este Produto.

## O que já está no ar

Por enquanto, a fundação do módulo, a carga das operadoras e o envio das contas:

- o item **Contas médicas** no menu lateral, que aparece só para quem tem perfil no módulo;
- a tela de contas, com o envio dos PDFs, o "Último envio" e a fila, descritos abaixo;
- os perfis e as permissões de cada um, já gravados no banco;
- o lugar seguro onde os PDFs ficam guardados por sete dias;
- a tela Operadoras, aberta a partir da tela de contas para quem tem a permissão de regra contratual e tabelas (gestão de contas médicas e as duas diretorias).

Na tela Operadoras, a gestão envia o arquivo de memória de cada convênio, o mesmo que o diretor monta, e a memória passa a valer sem programador no meio. A tela mostra a versão, quantas regras vigentes e pendentes entraram e os parâmetros lidos do cabeçalho; os números têm de bater com o arquivo. Mandar uma versão nova aposenta a anterior. Parâmetro do cabeçalho que o sistema ainda não usa fica guardado, e a memória em vigor pode ser baixada de volta inteira. Arquivo com um número no formato de CPF é recusado, porque memória não pode ter dado de paciente. Na mesma tela a gestão cadastra os nomes de plano como o MV imprime, cada um com a operadora e a coluna de preço, e os setores do MV com a acomodação de cada um.

Também na tela Operadoras entram as tabelas de preço de cada convênio. A gestão escolhe a operadora e a categoria (materiais, medicamentos, diárias e taxas ou pacotes), informa o início da vigência e, se houver, o fim, e envia a tabela de preço no arquivo de planilha separado por ponto e vírgula que o diretor entrega. O sistema reconhece sozinho o tipo da tabela pelas colunas da primeira linha e diz quantos itens entraram; arquivo com colunas que ele não conhece é recusado, e a mensagem lista as colunas esperadas. Uma versão nova não apaga a anterior: as duas ficam lado a lado, e a conta de um atendimento antigo usa a tabela que valia na data do atendimento. Para cada operadora, a tela mostra cada categoria com a tabela, a versão, a vigência e a situação (carregada ou não carregada). Honorário aparece sempre como não carregado, porque a tabela de honorários ainda não chegou; categorias que só a memória de uma operadora traz, como SADT e porte anestésico, aparecem do mesmo jeito. Preço que a memória da operadora dá como validado vale mais que a tabela.

Na mesma tela entra o dicionário de itens do hospital: o nome do produto na prescrição e na ficha anestésica, com os sinônimos, ligado ao código da conta (por exemplo, rocurônio e Esmeron caem no mesmo código). Termo que já existe é atualizado. Quando o nome não está no dicionário, o sistema tenta casar pela marca e pela concentração; só pela marca, o casamento sai com confiança média.

Na conferência, um preço que não pode ser comparado com a tabela sai como "Não conferido", e nunca como erro de preço: tabela não carregada para a categoria, nenhuma versão vigente na data do atendimento, preço zero na tabela, item que a tabela marca como pacote, código que aparece repetido na tabela sem a especialidade que desempata, e honorário.

A conta enviada já entra na fila, mas a análise dela (a leitura da conta inteira, a contagem de diárias e a conferência de preço) chega nas próximas entregas da primeira etapa. Até lá a conta fica Na fila. A tela do Guia já existe e é descrita abaixo; ela passa a ter linhas quando a análise entrar no ar.

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

## Quem vê

O módulo tem perfis próprios, separados dos de Reuniões, POPs e Ouvidoria. São seis: faturista, coordenadora de faturamento, gestão de contas médicas, diretoria médica, diretoria executiva e credenciamento. Quem não tem nenhum deles não vê o item no menu e não consegue abrir a tela. O Super admin do aplicativo entra, como nos outros módulos.

Cada perfil vem com um conjunto inicial de permissões, tirado da especificação do diretor:

- **Faturista**: envia e corrige contas, e vê só as próprias.
- **Coordenadora de faturamento**: o mesmo da faturista, mais o Painel completo e a Conferência da coordenação. Incluir regra operacional está desligado para ela, em avaliação pelo diretor.
- **Gestão de contas médicas**: tudo, menos habilitar pessoas.
- **Diretoria médica** e **Diretoria executiva**: tudo.
- **Credenciamento**: só os contratos e o aviso de reajuste.

Hoje o perfil de cada pessoa é gravado pela equipe de tecnologia, a partir do e-mail que o diretor informa. A tela de Habilitação, que liga e desliga cada permissão por perfil, chega na terceira etapa.

## Dado de paciente

O módulo não guarda nome completo, CPF, carteira nem data de nascimento de paciente em lugar nenhum. Da paciente ficam só um rótulo curto, como "Maria S.", e a idade em anos. Os PDFs da conta e do prontuário ficam num depósito privado, que só o aplicativo alcança, e são apagados sete dias depois do envio.

## O que costuma virar Demanda

- Uma pessoa que deveria ver Contas médicas no menu e não vê, ou o contrário (Defeito, ou Informação se for dúvida sobre o perfil).
- Pedido para dar ou trocar o perfil de alguém no módulo (Informação).
- Memória recusada na tela Operadoras, ou contagem de regras que não bate com o arquivo do diretor (Defeito, ou Informação se a recusa explica o motivo, como o CPF).
- Tabela de preço recusada, contagem de itens que não bate com o arquivo, ou preço "Não conferido" onde a tabela tem valor (Defeito, ou Informação se a recusa lista as colunas esperadas ou se o motivo é um dos casos de "Não conferido").
- Um botão do Guia que não marca, uma conta que não conclui ou uma nota que não bate com as linhas (Defeito).
- Dúvida sobre quando chega o envio de contas ou alguma das próximas entregas (Informação).
