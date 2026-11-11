# A aba Tecnologia

A aba Tecnologia é onde o diretor conta à Vitta (a empresa que cuida dos sistemas do hospital) um bug ou uma melhoria que quer nos sistemas. Antes isso era o WhatsApp, e o que se combinava lá se perdia. Aqui cada pedido vira uma Demanda, guardada com a conversa que a originou.

Só quem tem acesso de administrador do aplicativo enxerga a aba. Ela tem duas abas no alto: **Conversas**, a conversa com o **Assistente**, a IA que entende o pedido, com a lista dos seus pedidos ao lado, e **Entregas**, o que já foi entregue.

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

Se o card não chegar à Vitta depois do clique em Criar o card, o pedido fica marcado com **Envio falhou** na lista ao lado. Você não precisa refazer nada do que disse: a conversa e o resumo continuam guardados, e o botão **Reenviar**, na conversa aberta, tenta de novo. O sistema não reenvia sozinho, para não criar o mesmo card duas vezes. A Vitta também vê o pedido marcado e pode reenviar por você.

O modelo de IA que está respondendo e quanto a conversa já custou em dólar aparecem no alto da conversa aberta, por exemplo "Opus 5.5 · US$ 1,84 até agora". O valor soma o que a IA fez naquela conversa (as perguntas, o resumo e a leitura do código) e muda a cada resposta. Aparece "custo não medido" em dois casos em que o sistema não tem como fazer a conta inteira: quando o modelo usado está sem preço cadastrado e quando a conversa tem print, porque a leitura do print ainda não fica registrada. Nesses casos ele avisa em vez de mostrar um valor menor que o de verdade. Documento não deixa o custo sem medida: ele é lido sem IA, e as respostas que o levam à IA entram na conta como as outras. Enquanto a IA não respondeu nada, não aparece custo. O custo não está na lista ao lado, só na conversa aberta.

A conversa fica guardada. Ao lado dela fica a lista de tudo o que você já pediu, do mais recente para o mais antigo, com o título e a Etapa de cada pedido. Ao lado da Etapa, o selo **Bug** ou **Melhoria** diz o que o pedido é. Uma conversa que ficou no meio aparece como Registrada: clique nela e você continua de onde parou. Num pedido que já foi para a Vitta, o clique abre o documento do pedido, com O que muda, que é o que a entrega acrescenta para você, e a conversa embaixo; enquanto a Vitta não escreve esse texto, aparece "Descrição em preparação". O botão **Nova conversa**, no alto da lista, começa um pedido do zero. No alto da lista há uma busca pelo título, que acha o pedido sem diferenciar maiúscula e acento, e filtros em forma de botão: **Bug** ou **Melhoria**, a Etapa e a Origem (**Pedido do diretor** ou **Vitta**). Os filtros combinam entre si e com a busca, por exemplo só as melhorias que já estão Em produção; clicar de novo num filtro marcado o desliga. Ao abrir um pedido, a lista recolhe para a conversa ocupar a tela, e o botão Voltar às conversas a traz de volta. No celular a lista abre primeiro, e o mesmo botão leva de volta a ela.

## O que é uma Demanda

Uma Demanda é um pedido sobre um dos sistemas: um bug ou uma melhoria. Ela nasce na primeira resposta da conversa com o Assistente e guarda o que você disse, os prints e os documentos que você mandou e, depois do clique em Criar o card, a ligação com o trabalho de desenvolvimento.

Quase sempre quem abre um pedido é você. A exceção são os cards que a Vitta abre pelo desenvolvimento, sem passar pela conversa: uma melhoria ou um bug do aplicativo que ela mesma decidiu fazer. Eles também viram Demanda e aparecem na sua lista, marcados como **Vitta**, com a Etapa, o documento e a Conversa da Demanda, sem conversa com a IA. Os ajustes internos da Vitta, que não mudam nada no aplicativo que você usa (as ferramentas e a documentação dela), não aparecem. Dentro de cada pedido, a Vitta responde e pergunta pela Conversa da Demanda. Quando a Vitta precisa de uma decisão, de um dado ou de um acesso do hospital que não nasce de um pedido seu, ela pede pelo WhatsApp.

Não chame de pendência, tarefa nem chamado. Pendência é outra coisa no aplicativo: é o compromisso operacional que sai de uma reunião do hospital, e mora em outro lugar.

## A Conversa da Demanda

Cada pedido tem, além da conversa com a IA, a **Conversa da Demanda**: um espaço para você e as pessoas da Vitta que desenvolvem trocarem mensagens sobre aquele pedido. Serve para tirar uma dúvida e ser respondido ali mesmo. Ela fica separada da conversa com a IA, numa área própria embaixo dela, e a IA não lê nem responde ali.

Escreve e lê na Conversa quem vê o pedido: você, que pediu, e o Desenvolvedor. Outra pessoa da diretoria não vê, nem abrindo pelo endereço. No card que a Vitta abriu, a Conversa fica aberta a toda a diretoria, como o próprio card.

Para chamar alguém, escreva @ e escolha o nome na lista que aparece, como nos comentários de uma pendência. A lista traz só quem vê o pedido. Quem você marcou é avisado no sino. Sem marcar ninguém, a sua mensagem avisa o Responsável, a pessoa da Vitta que cuida do pedido; enquanto o pedido não virou card ainda não há Responsável, então marque alguém para ser lido. Quando é alguém da Vitta que escreve sem marcar ninguém, a mensagem avisa você. Ninguém é avisado da própria mensagem. Todo aviso chega também por e-mail, com o nome do pedido e de quem escreveu, para você não precisar estar com o aplicativo aberto. O clique no aviso do sino abre o pedido na aba Tecnologia, e o link do e-mail abre o pedido no mesmo lugar.

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

Na lista ao lado da conversa, cada diretor vê as próprias conversas e todos os cards que a Vitta abriu pelo desenvolvimento. Cada pedido traz o selo da **Origem**: **Pedido do diretor**, quando nasceu da conversa com a IA, ou **Vitta**, quando a Vitta o abriu. Outra pessoa da diretoria não vê os seus pedidos, nem abrindo pelo endereço. Em cada pedido que já virou card aparece o **Responsável**, a pessoa da Vitta que cuida dele, na lista e no pedido aberto. Quando a Vitta passa o pedido para outra pessoa, o nome muda sozinho na sua tela; você não precisa fazer nada, e no aplicativo não há como trocar quem cuida.

Quem desenvolve na Vitta é o **Desenvolvedor**: um administrador do aplicativo que tem o login do GitHub no cadastro. Ele vê as Demandas de todos. A lista dele abre em **Para mim**, os pedidos de que ele é o Responsável, e tem também **Minhas**, os pedidos que ele mesmo fez, e **Todas**, com o nome de quem pediu em cada linha. Ao abrir o pedido de outra pessoa, ele lê a conversa inteira com a IA (as perguntas e as respostas) e abre os prints e os documentos, sem poder responder no lugar de quem pediu. Ele vê também o número e o link do card no desenvolvimento, que para você não aparecem. Num pedido em **Envio falhou**, ele vê o motivo da falha, que para você não aparece, e tem o filtro **Envio falhou**, com só os pedidos nesse estado. Ele tem também o filtro **Responsável**, com um botão para cada pessoa da Vitta. Os filtros dele combinam com os de todo mundo e com Para mim, Minhas e Todas, por exemplo os bugs Em análise de que ele cuida. **Para mim**, Minhas, Todas, Responsável e Envio falhou só aparecem para o Desenvolvedor: a lista do diretor tem a busca, Bug ou Melhoria e a Etapa.

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

Ao abrir um pedido que já foi para a Vitta, ele aparece como um documento curto, em quatro partes:

- **Em uma frase**: o que muda, numa frase só.
- **O que muda**: o que aquela entrega acrescenta, em linguagem de quem usa, em até cinco tópicos. Se houver mais, o botão **Ver tudo** mostra os outros.
- **Partes**: quando a entrega é feita em partes, cada uma mostra em que pé está e quando ficou pronta.
- **Datas**: quando o pedido foi criado, quando foi entregue e quando entrou em produção.

Esse texto vem do planejamento da Vitta, ou das suas decisões quando a melhoria foi planejada com a IA, e não se edita no aplicativo. Enquanto a Vitta não escreve o resumo, o documento mostra "Descrição em preparação".

## As Entregas

A aba **Entregas**, ao lado de Conversas, mostra o que já foi entregue: quantos pedidos ficaram prontos por semana ou por mês, e a lista deles, do mais recente para o mais antigo. A semana começa na segunda-feira, e o dia conta pelo horário do hospital. Cada pedido conta uma vez, mesmo quando foi feito em partes.

Em cada linha aparecem o título, a data de entrega (o dia em que o pedido ficou pronto), a data em que entrou em produção, quando já entrou, e o Responsável, a pessoa da Vitta que cuidou dele. Clicar num pedido abre o mesmo Documento do card da conversa, com as partes e as datas de cada uma.

No alto há os filtros: o período (de um dia até outro), **Bug** ou **Melhoria**, a Origem (**Pedido do diretor** ou **Vitta**) e o Responsável. Eles combinam entre si, por exemplo as melhorias da Vitta que ficaram prontas em outubro, e a contagem por semana ou por mês acompanha os filtros. Ali entram os mesmos pedidos que você vê na lista das conversas: os seus e os que a Vitta abriu. Pedido apagado e pedido que ainda não foi entregue não aparecem.

A aba é só para acompanhar: nada se move por ali. Ninguém muda a Etapa nem o Responsável pelas Entregas.

## Apagar um pedido

Um pedido que não vale mais pode sair da lista pelo botão **Apagar**, no alto do pedido aberto. O aplicativo pede confirmação antes de apagar, e depois não dá para desfazer.

Só dá para apagar enquanto ninguém começou a fazer o pedido. A conversa que ainda não virou card, a Registrada, quem apaga é quem escreveu. Depois do Criar o card, com o pedido Em análise ou Planejada, só o Desenvolvedor apaga: se quiser tirar um pedido seu nessa fase, peça na Conversa da Demanda. De Em desenvolvimento em diante, o aplicativo não deixa apagar. O botão só aparece para quem pode usar.

O pedido apagado some da lista junto com a conversa com a IA, a Conversa da Demanda e os anexos. No desenvolvimento da Vitta o card não some: ele fecha como não planejado, com um comentário dizendo que foi apagado no aplicativo, e o histórico das decisões fica guardado lá. Se o desenvolvimento não responder na hora, nada é apagado e a tela pede para tentar de novo.

## O Planejamento da Demanda

O Planejamento da Demanda é o caminho da melhoria na conversa com o Assistente: transforma o pedido de uma coisa nova, ou de uma mudança, num plano que a Vitta consegue construir. A IA faz as perguntas que a Vitta faria, uma por vez, e quem decide é você. Ele começa quando você escolhe melhoria na conversa.

A IA parte do que você já contou e não pergunta de novo. Cada pergunta traz uma ou duas frases de contexto, duas opções para clicar, com a recomendada em destaque, e um campo para responder do seu jeito, por texto ou por voz. O planejamento não tem limite de perguntas: a IA só encerra quando não falta nada do seu pedido, e o botão **Fechar e resumir** encerra a conversa a qualquer momento. Mesmo depois que a IA encerra, ou depois do resumo, o campo de texto continua aberto até o clique em Criar o card: você escreve e ela volta a perguntar.

A conversa fica guardada na Demanda, e a lista ao lado do chat a traz de volta.

Enquanto você responde, o documento do pedido se monta ao lado da conversa. A cada resposta, a IA reescreve o que já se sabe: uma frase e no máximo cinco tópicos curtos, só com o que você disse ou escolheu. É o mesmo documento que o pedido mostra depois de criado, em **Em uma frase** e **O que muda**. No bug não há documento ao lado: a IA segue as cinco perguntas e mostra o resumo no fim.

No fim, a IA mostra um resumo com as decisões que você tomou e a lista do que ficou em aberto, que são os pontos que ela não chegou a perguntar. O que você não decidiu nunca aparece como decisão. Se alguma coisa não bater, o **Não bateu** pede para você dizer o quê, a conversa continua de onde parou e o resumo é refeito. Quando sobra algo em aberto, o botão **Continuar respondendo** aparece embaixo da lista e faz a IA voltar às perguntas por esses pontos, um de cada vez. Com nada em aberto, o botão não aparece.

Se o resumo estiver certo, o **Criar o card** manda o plano para o desenvolvimento da Vitta com as suas decisões e com o que ficou em aberto, que a Vitta pergunta depois. A Demanda fica ligada ao desenvolvimento, passa para a Etapa **Em análise** e, na lista, mostra **O que muda** com o que você decidiu. Do lado da Vitta, o plano chega a quem você escolheu em Quem cuida disto?, ou ao Pedro Rezende quando ninguém foi escolhido.

A IA cuida das decisões de negócio: o problema, quem usa, as regras e o que fica de fora. As decisões técnicas ficam com a Vitta, depois do sim. Quando o pedido esbarra numa regra da casa, a IA avisa e diz de onde tirou, citando a parte "O que já foi decidido" do texto daquele sistema.

## Revisar com o código de hoje

Um pedido feito há tempo pode ser revisto pelo botão **Revisar com o código de hoje**, no alto do pedido aberto. Ele aparece num pedido de melhoria que já virou card, com a Etapa Em análise ou Planejada, enquanto nenhuma parte está em desenvolvimento. Só quem pediu e o Desenvolvedor veem o botão.

Antes de começar, o aplicativo mostra quanto a revisão deve custar, numa faixa em dólar, e a IA só começa depois que você confirma. Sem a confirmação nada é cobrado.

A revisão continua a mesma conversa de antes. A IA lê o pedido como está hoje no desenvolvimento, os comentários da Vitta nele, o que subiu no aplicativo desde a data do card e o próprio sistema, e abre o **Retrato de hoje** em três partes:

- **Já existe**: o que o sistema já faz do seu pedido, com a versão do aplicativo em que entrou.
- **Mudou desde o card**: o que se combinou depois e o que subiu e mexe no pedido.
- **Continua em aberto**: o que ainda falta.

Para cada item de Já existe a IA pergunta "isso atende?". Ele só sai do pedido se você disser que atende; se não atende, continua no pedido. Depois ela pergunta só o que falta, sem limite de perguntas. O Desenvolvedor também pode responder, e cada resposta mostra o nome de quem respondeu.

## O que já foi decidido

- A aba mora dentro do aplicativo e só quem é Super admin a vê.
- A aba tem Conversas, a conversa com o Assistente, que pergunta se é bug ou melhoria e confirma antes de seguir, e Entregas, que conta o que foi entregue por semana e por mês e não move nada.
- O pedido nasce da conversa do diretor ou de um card do aplicativo que a Vitta abre pelo desenvolvimento, que aparece na lista com o selo Vitta, sem conversa com a IA; os ajustes internos da Vitta não aparecem, e os pedidos da Vitta ao hospital continuam no WhatsApp.
- Cada pedido tem a Conversa da Demanda, entre quem pediu e a Vitta, separada da conversa com a IA e guardada só dentro do aplicativo.
- Na Conversa da Demanda, quem é marcado pelo nome é avisado no sino e por e-mail, e sem marcação a mensagem de quem pediu avisa o Responsável e a da Vitta avisa quem pediu.
- No bug, a IA faz no máximo cinco perguntas, e o pedido só vai para a Vitta no clique em Criar o card.
- O bug que sai do Criar o card vai direto para o desenvolvimento, sem ninguém da Vitta precisar assumir antes.
- O card que não chega à Vitta fica marcado como Envio falhou e se resolve com Reenviar, pelo diretor ou pela Vitta; o sistema nunca reenvia sozinho.
- Antes do Criar o card, o diretor escolhe em Quem cuida disto? a pessoa da Vitta que vai cuidar do pedido; a escolha é opcional e, sem ela, o card vai para o Pedro Rezende.
- Depois do Criar o card, quem troca o Responsável é a Vitta, no desenvolvimento, e a tela acompanha; o aplicativo não troca o Responsável.
- Na melhoria, a IA não tem limite de perguntas e só encerra quando nada fica em aberto, e a melhoria que sai do Criar o card ainda passa pelo planejamento técnico da Vitta antes de começar.
- A conversa com o Assistente fica guardada na Demanda e se retoma pela lista ao lado.
- Na melhoria, o documento do pedido se monta ao lado da conversa, com uma frase e no máximo cinco tópicos, e é ele que vai para o card; no bug não há documento ao lado.
- O modelo de IA e o custo da conversa em dólar aparecem só no alto da conversa aberta, nunca na lista, e quando o custo não dá para calcular a tela diz "custo não medido".
- A lista ao lado da conversa mostra os pedidos de quem está olhando, e a Etapa de cada um vem do desenvolvimento, sem ninguém escrever à mão.
- A lista tem busca pelo título e filtros que combinam (Bug ou Melhoria, Etapa, Origem, e para o Desenvolvedor também Responsável, Envio falhou e Para mim), e recolhe quando um pedido está aberto.
- O Desenvolvedor, administrador com login do GitHub no cadastro, vê as Demandas de todos, com a conversa inteira e os anexos; o diretor vê as suas e os cards da Vitta, sem número nem link do card.
- Uma Demanda se liga a um trabalho de desenvolvimento só, e a Etapa é lida de lá, nunca digitada.
- Um pedido de melhoria Em análise ou Planejada se revisa com o código de hoje, pelo autor ou pelo Desenvolvedor, com o custo mostrado antes e a confirmação, e o que já existe só sai do pedido com o sim de quem pediu.
- Um pedido se apaga só até Planejada, com confirmação, pela mão de quem escreveu a conversa que não virou card ou do Desenvolvedor no card criado, e no desenvolvimento o card fecha como não planejado e nunca é apagado.
- O texto que sai da Demanda para o material público do desenvolvimento passa por uma peneira que esconde CPF, telefone, nome e outros dados pessoais.
- Os prints e os documentos ficam só dentro do aplicativo e são apagados 30 dias depois de Em produção, ou logo quando a entrega fica Não será feita.
- Um documento anexado é um pedido só, mesmo com várias melhorias dentro, e a IA lê o texto inteiro, sem resumir antes.
- No planejamento, a IA cuida só das decisões de negócio, e as decisões técnicas continuam com a Vitta.
- Títulos, botões e abas aparecem em caixa alta só na tela, e o título de cada Demanda aparece como foi escrito.
- Dentro da aba, a conversa e o texto dos resumos ficam com maiúscula e minúscula, e só os subtítulos do resumo ficam em caixa alta.
