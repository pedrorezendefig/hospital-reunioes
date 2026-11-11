# A aba Tecnologia

A aba Tecnologia é onde o diretor conta à Vitta (a empresa que cuida dos sistemas do hospital) um bug ou uma melhoria que quer nos sistemas. Antes isso era o WhatsApp, e o que se combinava lá se perdia. Aqui cada pedido vira uma Demanda, guardada com a conversa que a originou.

Só quem tem acesso de administrador do aplicativo enxerga a aba. Ela é uma tela só: a conversa com o **Assistente**, a IA que entende o pedido, com a lista dos seus pedidos ao lado.

## A conversa com o Assistente

Ao abrir a aba Tecnologia, você cai direto numa conversa com a IA. Ela pergunta se é um bug ou uma melhoria: bug é algo que não funciona como deveria, e melhoria é algo novo ou uma mudança no que já existe. Dá para clicar num dos dois botões ou escrever do seu jeito. Se você só descrever, a IA diz o que entendeu e pergunta se é isso antes de seguir.

Se for uma dúvida que o material da Vitta responde (como uma tela funciona, onde fica um botão), a IA responde ali mesmo e diz de onde tirou a resposta. Dúvida respondida não vira pedido para a Vitta.

Para responder e para perguntar, a IA consulta o que já existe na plataforma: como as telas funcionam de verdade e o que a Vitta já decidiu. Se o seu pedido esbarra em algo já decidido, ela avisa e explica em palavras simples, sem termos de programador. Ela só lê: nada que ela consulta muda o aplicativo.

No bug, a IA faz no máximo cinco perguntas, uma por vez: onde aconteceu, o que aconteceu, o que você esperava, como repetir e, se você tiver, o print da tela. Ela pula o que você já contou. O print vai pelo botão de anexo da conversa e fica guardado como anexo na hora em que você manda, sem nunca sair do aplicativo. O que você não respondeu aparece como "não informado".

Pelo mesmo botão de anexo entra um documento: um texto, um PDF, um arquivo do Word ou uma planilha do Excel, em qualquer ponto da conversa, no bug ou na melhoria. Na conversa aparece só o nome e o tamanho do arquivo, e a IA lê o documento inteiro antes de responder, sem perguntar o que ele já diz. Um documento com várias melhorias continua sendo um pedido só, que a Vitta divide em partes depois. Se ele mistura sistemas que não têm nada a ver um com o outro, a IA avisa e sugere uma conversa para cada assunto. Nas respostas seguintes, mesmo numa conversa retomada pela lista, a IA continua lendo o documento.

No fim, a IA mostra um resumo com o que você disse e com os critérios que dizem como se sabe que o bug foi resolvido. Se estiver certo, o botão **Criar o card** manda o bug para o desenvolvimento da Vitta, que começa a trabalhar nele sem ninguém precisar assumir antes. Se alguma coisa estiver errada, o botão **Não bateu** pede para você dizer o quê, a conversa continua e o resumo é refeito. Nada vai para a Vitta antes do clique em Criar o card.

Na melhoria, a conversa vira o Planejamento da Demanda ali mesmo, sem trocar de tela: a IA faz as perguntas que a Vitta faria, uma por vez. Cada pergunta traz uma ou duas frases de contexto, duas opções para clicar, com a recomendada em destaque, e um campo para responder do seu jeito, por texto ou por voz. A melhoria não tem limite de perguntas: a IA segue até não sobrar nada indefinido no seu pedido, e o botão **Fechar e resumir**, no alto da conversa, encerra a qualquer momento. Depois que a IA encerra, ou depois do resumo, o campo de texto continua aberto até o clique em Criar o card: você escreve e ela volta a perguntar. A melhoria ganha um título desde a primeira resposta da IA, e ele se ajusta enquanto a conversa avança.

O resumo da melhoria mostra as decisões que você tomou e o que ficou em aberto, que são os pontos que a IA não chegou a perguntar. O que você não decidiu nunca aparece como decisão. Os botões são os mesmos do bug: **Criar o card** manda o pedido completo para a Vitta, já com o que a IA viu no sistema sobre como fazer e como testar, e **Não bateu** volta à conversa para acertar o que estiver errado. A Vitta ainda planeja o resto da parte técnica antes de começar. Se você fechou antes da hora e sobrou algo em aberto, o resumo traz também o botão **Continuar respondendo**: a IA volta a perguntar, começando pelo primeiro ponto em aberto. Dá para clicar em Criar o card mesmo com algo em aberto.

No resumo, no bug e na melhoria, antes do Criar o card, aparece a pergunta **Quem cuida disto?**, com as pessoas da Vitta que desenvolvem: Pedro Rezende, Pedro Rib e Lucas Sampaio. Quem você escolher passa a cuidar do pedido, e o card cai na fila dessa pessoa. Escolher é opcional: sem escolha, o card vai para o Pedro Rezende, que repassa a quem for cuidar. O nome de quem cuida aparece em cada pedido da sua lista.

Antes do resumo, no bug e na melhoria, a IA confere os pedidos que já estão na fila da Vitta. Se houver um pedido aberto parecido, ela avisa com o título dele, para você ver se não é o mesmo antes de clicar em Criar o card.

Se a IA não conseguir responder, a tela avisa, a conversa continua como estava e o que você escreveu fica na caixa: é só mandar de novo.

O modelo de IA que está respondendo e quanto a conversa já custou em dólar aparecem no alto da conversa aberta, por exemplo "Opus 5.5 · US$ 1,84 até agora". O valor soma o que a IA fez naquela conversa (as perguntas, o resumo e a leitura do código) e muda a cada resposta. Aparece "custo não medido" em dois casos em que o sistema não tem como fazer a conta inteira: quando o modelo usado está sem preço cadastrado e quando a conversa tem print, porque a leitura do print ainda não fica registrada. Nesses casos ele avisa em vez de mostrar um valor menor que o de verdade. Documento não deixa o custo sem medida: ele é lido sem IA, e as respostas que o levam à IA entram na conta como as outras. Enquanto a IA não respondeu nada, não aparece custo. O custo não está na lista ao lado, só na conversa aberta.

A conversa fica guardada. Ao lado dela fica a lista de tudo o que você já pediu, do mais recente para o mais antigo, com o título e a Etapa de cada pedido. Ao lado da Etapa, o selo **Bug** ou **Melhoria** diz o que o pedido é. Uma conversa que ficou no meio aparece como Registrada: clique nela e você continua de onde parou. Num pedido que já foi para a Vitta, o clique mostra a conversa e O que muda, que é o que a entrega acrescenta para você; enquanto a Vitta não escreve esse texto, aparece "Descrição em preparação". O botão **Nova conversa**, no alto da lista, começa um pedido do zero. No celular a lista abre primeiro, e o botão Voltar às conversas leva de volta a ela.

## O que é uma Demanda

Uma Demanda é um pedido sobre um dos sistemas: um bug ou uma melhoria. Ela nasce na primeira resposta da conversa com o Assistente e guarda o que você disse, os prints e os documentos que você mandou e, depois do clique em Criar o card, a ligação com o trabalho de desenvolvimento.

Quem abre um pedido é sempre você. Dentro dele, a Vitta responde e pergunta pela Conversa da Demanda. Quando a Vitta precisa de uma decisão, de um dado ou de um acesso do hospital que não nasce de um pedido seu, ela pede pelo WhatsApp.

Não chame de pendência, tarefa nem chamado. Pendência é outra coisa no aplicativo: é o compromisso operacional que sai de uma reunião do hospital, e mora em outro lugar.

## A Conversa da Demanda

Cada pedido tem, além da conversa com a IA, a **Conversa da Demanda**: um espaço para você e as pessoas da Vitta que desenvolvem trocarem mensagens sobre aquele pedido. Serve para tirar uma dúvida e ser respondido ali mesmo. Ela fica separada da conversa com a IA, numa área própria embaixo dela, e a IA não lê nem responde ali.

Escreve e lê na Conversa quem vê o pedido: você, que pediu, e o Desenvolvedor. Outra pessoa da diretoria não vê, nem abrindo pelo endereço.

Para chamar alguém, escreva @ e escolha o nome na lista que aparece, como nos comentários de uma pendência. A lista traz só quem vê o pedido. Quem você marcou é avisado no sino. Sem marcar ninguém, a sua mensagem avisa o Responsável, a pessoa da Vitta que cuida do pedido; enquanto o pedido não virou card ainda não há Responsável, então marque alguém para ser lido. Quando é alguém da Vitta que escreve sem marcar ninguém, a mensagem avisa você. Ninguém é avisado da própria mensagem. O clique no aviso do sino abre o pedido na aba Tecnologia.

O que se escreve na Conversa fica só dentro do aplicativo e nunca vai para o material público do desenvolvimento.

## Os anexos da Demanda

Os anexos são prints de tela e documentos guardados junto da Demanda, para quem vai resolver ver o que você viu e ler o que você escreveu. Entram:

- print de tela em .png, .jpg, .jpeg ou .webp, de até 3,75 MB;
- documento em .md ou .txt, de até 5 MB, e em .pdf ou .docx (Word), de até 15 MB. O texto do documento pode ter até 100 mil caracteres; acima disso a tela pede para dividir o arquivo em partes;
- planilha em .csv, de até 5 MB, e em .xlsx (Excel), de até 15 MB. A planilha conta como documento: a IA lê todas as abas, cada uma com o nome dela, até o mesmo limite de 100 mil caracteres. Planilha maior que isso a tela pede para dividir.

São até 10 anexos por Demanda, somando prints e documentos. O PDF que é foto de papel, sem texto para ler, não entra como documento: mande as páginas como print. O arquivo .doc antigo também não entra; salve como .docx ou PDF. A planilha no formato antigo (.xls) não entra; salve como .xlsx no Excel e mande de novo. A tela recusa o arquivo fora da lista ou grande demais antes de enviar, com a frase que diz o que fazer.

O anexo entra pelo botão de anexo da conversa com o Assistente e vira anexo da Demanda na hora em que você manda. Se algum não entrar, a tela avisa, e é só mandar de novo na conversa.

Os anexos ficam só dentro do aplicativo. Eles nunca vão para o material público do desenvolvimento, porque um print ou um documento do hospital pode ter nome de paciente ou de colaborador: o pedido diz só quantos há, por exemplo "Anexos: 2 imagens e 1 documento na Demanda", e quem desenvolve busca os arquivos pelo aplicativo.

Os arquivos são apagados 30 dias depois de a entrega ficar **Em produção**, o que dá tempo de conferir a correção com o print na mão. Se a entrega fica **Não será feita**, eles são apagados logo, em até uma hora. Fica o registro de que existiram (o nome, quem mandou e quando), marcado como apagado. O texto que a IA leu de um documento continua na conversa.

## Quem vê

Na lista ao lado da conversa, cada diretor vê só as suas conversas. Outra pessoa da diretoria não vê os seus pedidos, nem abrindo pelo endereço. Em cada pedido que já virou card aparece o **Responsável**, a pessoa da Vitta que cuida dele, na lista e no pedido aberto. Quando a Vitta passa o pedido para outra pessoa, o nome muda sozinho na sua tela; você não precisa fazer nada, e no aplicativo não há como trocar quem cuida.

Quem desenvolve na Vitta é o **Desenvolvedor**: um administrador do aplicativo que tem o login do GitHub no cadastro. Ele vê as Demandas de todos. A lista dele abre em **Para mim**, os pedidos de que ele é o Responsável, e tem também **Minhas**, os pedidos que ele mesmo fez, e **Todas**, com o nome de quem pediu em cada linha. Ao abrir o pedido de outra pessoa, ele lê a conversa inteira com a IA (as perguntas e as respostas) e abre os prints e os documentos, sem poder responder no lugar de quem pediu. Ele vê também o número e o link do card no desenvolvimento, que para você não aparecem.

## A Etapa

Quando o pedido vira trabalho de desenvolvimento, ele ganha uma **Etapa**, que conta em que pé está a entrega, em palavras de quem pediu:

- **Registrada**: a conversa ainda não virou card.
- **Em análise**: a Vitta está entendendo o que precisa ser feito.
- **Planejada**: já se sabe o que fazer, o trabalho está na fila.
- **Em desenvolvimento**: está sendo feito agora.
- **Entregue**: está pronto, mas ainda não chegou ao aplicativo que você usa.
- **Em produção**: já está no ar, e dá para usar. A lista diz desde qual versão do aplicativo.
- **Não será feita**: decidiu-se não fazer.

A Etapa nunca é digitada à mão: ela é lida do planejamento da Vitta e aparece sozinha na lista. Quando a entrega tem partes, a lista mostra quantas já foram entregues. Assim que a Vitta começa a construir, a Etapa passa sozinha para Em desenvolvimento, e quando a versão nova do aplicativo sobe, passa para Em produção.

Ao abrir um pedido que já foi para a Vitta, aparece também **O que muda**: o que aquela entrega acrescenta, em linguagem de quem usa. Esse texto vem do planejamento da Vitta, ou das suas decisões quando a melhoria foi planejada com a IA, e não se edita no aplicativo.

## O Planejamento da Demanda

O Planejamento da Demanda é o caminho da melhoria na conversa com o Assistente: transforma o pedido de uma coisa nova, ou de uma mudança, num plano que a Vitta consegue construir. A IA faz as perguntas que a Vitta faria, uma por vez, e quem decide é você. Ele começa quando você escolhe melhoria na conversa.

A IA parte do que você já contou e não pergunta de novo. Cada pergunta traz uma ou duas frases de contexto, duas opções para clicar, com a recomendada em destaque, e um campo para responder do seu jeito, por texto ou por voz. O planejamento não tem limite de perguntas: a IA só encerra quando não falta nada do seu pedido, e o botão **Fechar e resumir** encerra a conversa a qualquer momento. Mesmo depois que a IA encerra, ou depois do resumo, o campo de texto continua aberto até o clique em Criar o card: você escreve e ela volta a perguntar.

A conversa fica guardada na Demanda, e a lista ao lado do chat a traz de volta.

No fim, a IA mostra um resumo com as decisões que você tomou e a lista do que ficou em aberto, que são os pontos que ela não chegou a perguntar. O que você não decidiu nunca aparece como decisão. Se alguma coisa não bater, o **Não bateu** pede para você dizer o quê, a conversa continua de onde parou e o resumo é refeito. Quando sobra algo em aberto, o botão **Continuar respondendo** aparece embaixo da lista e faz a IA voltar às perguntas por esses pontos, um de cada vez. Com nada em aberto, o botão não aparece.

Se o resumo estiver certo, o **Criar o card** manda o plano para o desenvolvimento da Vitta com as suas decisões e com o que ficou em aberto, que a Vitta pergunta depois. A Demanda fica ligada ao desenvolvimento, passa para a Etapa **Em análise** e, na lista, mostra **O que muda** com o que você decidiu. Do lado da Vitta, o plano chega a quem você escolheu em Quem cuida disto?, ou ao Pedro Rezende quando ninguém foi escolhido.

A IA cuida das decisões de negócio: o problema, quem usa, as regras e o que fica de fora. As decisões técnicas ficam com a Vitta, depois do sim. Quando o pedido esbarra numa regra da casa, a IA avisa e diz de onde tirou, citando a parte "O que já foi decidido" do texto daquele sistema.

## O que já foi decidido

- A aba mora dentro do aplicativo e só quem é Super admin a vê.
- A aba é uma tela só, a conversa com o Assistente, que pergunta se é bug ou melhoria e confirma antes de seguir.
- Quem abre o pedido é sempre o diretor, e os pedidos da Vitta ao hospital que não nascem de um pedido dele continuam no WhatsApp.
- Cada pedido tem a Conversa da Demanda, entre quem pediu e a Vitta, separada da conversa com a IA e guardada só dentro do aplicativo.
- Na Conversa da Demanda, quem é marcado pelo nome é avisado no sino, e sem marcação a mensagem de quem pediu avisa o Responsável e a da Vitta avisa quem pediu.
- No bug, a IA faz no máximo cinco perguntas, e o pedido só vai para a Vitta no clique em Criar o card.
- O bug que sai do Criar o card vai direto para o desenvolvimento, sem ninguém da Vitta precisar assumir antes.
- Antes do Criar o card, o diretor escolhe em Quem cuida disto? a pessoa da Vitta que vai cuidar do pedido; a escolha é opcional e, sem ela, o card vai para o Pedro Rezende.
- Depois do Criar o card, quem troca o Responsável é a Vitta, no desenvolvimento, e a tela acompanha; o aplicativo não troca o Responsável.
- Na melhoria, a IA não tem limite de perguntas e só encerra quando nada fica em aberto, e a melhoria que sai do Criar o card ainda passa pelo planejamento técnico da Vitta antes de começar.
- A conversa com o Assistente fica guardada na Demanda e se retoma pela lista ao lado.
- O modelo de IA e o custo da conversa em dólar aparecem só no alto da conversa aberta, nunca na lista, e quando o custo não dá para calcular a tela diz "custo não medido".
- A lista ao lado da conversa mostra os pedidos de quem está olhando, e a Etapa de cada um vem do desenvolvimento, sem ninguém escrever à mão.
- O Desenvolvedor, administrador com login do GitHub no cadastro, vê as Demandas de todos, com a conversa inteira e os anexos; o diretor vê só as suas, sem número nem link do card.
- Uma Demanda se liga a um trabalho de desenvolvimento só, e a Etapa é lida de lá, nunca digitada.
- O texto que sai da Demanda para o material público do desenvolvimento passa por uma peneira que esconde CPF, telefone, nome e outros dados pessoais.
- Os prints e os documentos ficam só dentro do aplicativo e são apagados 30 dias depois de Em produção, ou logo quando a entrega fica Não será feita.
- Um documento anexado é um pedido só, mesmo com várias melhorias dentro, e a IA lê o texto inteiro, sem resumir antes.
- No planejamento, a IA cuida só das decisões de negócio, e as decisões técnicas continuam com a Vitta.
- Títulos, botões e abas aparecem em caixa alta só na tela, e o título de cada Demanda aparece como foi escrito.
- Dentro da aba, a conversa e o texto dos resumos ficam com maiúscula e minúscula, e só os subtítulos do resumo ficam em caixa alta.
