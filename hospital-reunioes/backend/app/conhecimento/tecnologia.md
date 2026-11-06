# A aba Tecnologia

A aba Tecnologia é onde o diretor conta à Vitta (a empresa que cuida dos sistemas do hospital) um bug ou uma melhoria que quer nos sistemas. Antes isso era o WhatsApp, e o que se combinava lá se perdia. Aqui cada pedido vira uma Demanda, guardada com a conversa que a originou.

Só quem tem acesso de administrador do aplicativo enxerga a aba. Ela é uma tela só: a conversa com o **Assistente**, a IA que entende o pedido, com a lista dos seus pedidos ao lado.

## A conversa com o Assistente

Ao abrir a aba Tecnologia, você cai direto numa conversa com a IA. Ela pergunta se é um bug ou uma melhoria: bug é algo que não funciona como deveria, e melhoria é algo novo ou uma mudança no que já existe. Dá para clicar num dos dois botões ou escrever do seu jeito. Se você só descrever, a IA diz o que entendeu e pergunta se é isso antes de seguir.

Se for uma dúvida que o material da Vitta responde (como uma tela funciona, onde fica um botão), a IA responde ali mesmo e diz de onde tirou a resposta. Dúvida respondida não vira pedido para a Vitta.

Para responder e para perguntar, a IA consulta o que já existe na plataforma: como as telas funcionam de verdade e o que a Vitta já decidiu. Se o seu pedido esbarra em algo já decidido, ela avisa e explica em palavras simples, sem termos de programador. Ela só lê: nada que ela consulta muda o aplicativo.

No bug, a IA faz no máximo cinco perguntas, uma por vez: onde aconteceu, o que aconteceu, o que você esperava, como repetir e, se você tiver, o print da tela. Ela pula o que você já contou. O print vai pelo botão de imagem da conversa e fica guardado como anexo na hora em que você manda, sem nunca sair do aplicativo. O que você não respondeu aparece como "não informado".

No fim, a IA mostra um resumo com o que você disse e com os critérios que dizem como se sabe que o bug foi resolvido. Se estiver certo, o botão **Criar o card** manda o bug para o desenvolvimento da Vitta, que começa a trabalhar nele sem ninguém precisar assumir antes. Se alguma coisa estiver errada, o botão **Não bateu** pede para você dizer o quê, a conversa continua e o resumo é refeito. Nada vai para a Vitta antes do clique em Criar o card.

Na melhoria, a conversa vira o Planejamento da Demanda ali mesmo, sem trocar de tela: a IA faz as perguntas que a Vitta faria, uma por vez. Cada pergunta traz uma ou duas frases de contexto, duas opções para clicar, com a recomendada em destaque, e um campo para responder do seu jeito, por texto ou por voz. A melhoria não tem limite de perguntas: a IA segue até não sobrar nada indefinido no seu pedido, e o botão **Fechar e resumir**, no alto da conversa, encerra a qualquer momento. Depois que a IA encerra, ou depois do resumo, o campo de texto continua aberto até o clique em Criar o card: você escreve e ela volta a perguntar.

O resumo da melhoria mostra as decisões que você tomou e o que ficou em aberto, que são os pontos que a IA não chegou a perguntar. O que você não decidiu nunca aparece como decisão. Os botões são os mesmos do bug: **Criar o card** manda o pedido completo para a Vitta, já com o que a IA viu no sistema sobre como fazer e como testar, e **Não bateu** volta à conversa para acertar o que estiver errado. A Vitta ainda planeja o resto da parte técnica antes de começar.

Antes do resumo, no bug e na melhoria, a IA confere os pedidos que já estão na fila da Vitta. Se houver um pedido aberto parecido, ela avisa com o título dele, para você ver se não é o mesmo antes de clicar em Criar o card.

Se a IA não conseguir responder, a tela avisa, a conversa continua como estava e o que você escreveu fica na caixa: é só mandar de novo.

O modelo de IA que está respondendo e quanto a conversa já custou em dólar aparecem no alto da conversa aberta, por exemplo "Opus 5.5 · US$ 1,84 até agora". O valor soma o que a IA fez naquela conversa (as perguntas, o resumo e a leitura do código) e muda a cada resposta. Aparece "custo não medido" em dois casos em que o sistema não tem como fazer a conta inteira: quando o modelo usado está sem preço cadastrado e quando a conversa tem print, porque a leitura do print ainda não fica registrada. Nesses casos ele avisa em vez de mostrar um valor menor que o de verdade. Enquanto a IA não respondeu nada, não aparece custo. O custo não está na lista ao lado, só na conversa aberta.

A conversa fica guardada. Ao lado dela fica a lista de tudo o que você já pediu, do mais recente para o mais antigo, com o título e a Etapa de cada pedido. Uma conversa que ficou no meio aparece como Registrada: clique nela e você continua de onde parou. Num pedido que já foi para a Vitta, o clique mostra a conversa e O que muda, que é o que a entrega acrescenta para você; enquanto a Vitta não escreve esse texto, aparece "Descrição em preparação". O botão **Nova conversa**, no alto da lista, começa um pedido do zero. No celular a lista abre primeiro, e o botão Voltar às conversas leva de volta a ela.

## O que é uma Demanda

Uma Demanda é um pedido sobre um dos sistemas: um bug ou uma melhoria. Ela nasce na primeira resposta da conversa com o Assistente e guarda o que você disse, os prints que você mandou e, depois do clique em Criar o card, a ligação com o trabalho de desenvolvimento.

A aba vai num sentido só: você conta à Vitta. Quando é a Vitta que precisa de uma decisão, de um dado ou de um acesso do hospital, ela pede pelo WhatsApp.

Não chame de pendência, tarefa nem chamado. Pendência é outra coisa no aplicativo: é o compromisso operacional que sai de uma reunião do hospital, e mora em outro lugar.

## Os anexos da Demanda

Os anexos são prints de tela guardados junto da Demanda, para quem vai resolver ver o que você viu. Aceita imagem PNG, JPG ou WEBP, de até 5 MB cada, e até 10 imagens por Demanda.

O print entra pelo botão de imagem da conversa com o Assistente e vira anexo na hora em que você manda. Se algum não entrar, a tela avisa, e é só mandar de novo na conversa.

Os prints ficam só dentro do aplicativo. Eles nunca vão para o material público do desenvolvimento, porque um print do hospital pode ter nome de paciente ou de colaborador; quem desenvolve busca as imagens pelo aplicativo.

As imagens são apagadas 30 dias depois de a entrega ficar **Em produção**, o que dá tempo de conferir a correção com o print na mão. Se a entrega fica **Não será feita**, elas são apagadas logo, em até uma hora. Fica o registro de que existiram (o nome, quem mandou e quando), marcado como apagado.

## Quem vê

Cada pessoa vê, na lista ao lado da conversa, os pedidos que ela fez. Quem desenvolve vê o pedido pelo material de desenvolvimento, sem os prints, que ficam no aplicativo.

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

No fim, a IA mostra um resumo com as decisões que você tomou e a lista do que ficou em aberto, que são os pontos que ela não chegou a perguntar. O que você não decidiu nunca aparece como decisão. Se alguma coisa não bater, o **Não bateu** pede para você dizer o quê, a conversa continua de onde parou e o resumo é refeito.

Se o resumo estiver certo, o **Criar o card** manda o plano para o desenvolvimento da Vitta com as suas decisões e com o que ficou em aberto, que a Vitta pergunta depois. A Demanda fica ligada ao desenvolvimento, passa para a Etapa **Em análise** e, na lista, mostra **O que muda** com o que você decidiu. Do lado da Vitta, o plano chega primeiro ao Pedro, que distribui o trabalho.

A IA cuida das decisões de negócio: o problema, quem usa, as regras e o que fica de fora. As decisões técnicas ficam com a Vitta, depois do sim. Quando o pedido esbarra numa regra da casa, a IA avisa e diz de onde tirou, citando a parte "O que já foi decidido" do texto daquele sistema.

## O que já foi decidido

- A aba mora dentro do aplicativo e só quem é Super admin a vê.
- A aba é uma tela só, a conversa com o Assistente, que pergunta se é bug ou melhoria e confirma antes de seguir.
- A aba vai num sentido só, do diretor para a Vitta, e os pedidos da Vitta ao hospital voltaram para o WhatsApp.
- No bug, a IA faz no máximo cinco perguntas, e o pedido só vai para a Vitta no clique em Criar o card.
- O bug que sai do Criar o card vai direto para o desenvolvimento, sem ninguém da Vitta precisar assumir antes.
- Na melhoria, a IA não tem limite de perguntas e só encerra quando nada fica em aberto, e a melhoria que sai do Criar o card ainda passa pelo planejamento técnico da Vitta antes de começar.
- A conversa com o Assistente fica guardada na Demanda e se retoma pela lista ao lado.
- O modelo de IA e o custo da conversa em dólar aparecem só no alto da conversa aberta, nunca na lista, e quando o custo não dá para calcular a tela diz "custo não medido".
- A lista ao lado da conversa mostra os pedidos de quem está olhando, e a Etapa de cada um vem do desenvolvimento, sem ninguém escrever à mão.
- Uma Demanda se liga a um trabalho de desenvolvimento só, e a Etapa é lida de lá, nunca digitada.
- O texto que sai da Demanda para o material público do desenvolvimento passa por uma peneira que esconde CPF, telefone, nome e outros dados pessoais.
- Os prints ficam só dentro do aplicativo e são apagados 30 dias depois de Em produção, ou logo quando a entrega fica Não será feita.
- No planejamento, a IA cuida só das decisões de negócio, e as decisões técnicas continuam com a Vitta.
