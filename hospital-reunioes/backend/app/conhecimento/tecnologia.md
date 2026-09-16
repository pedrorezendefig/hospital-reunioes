# A aba Tecnologia

A aba Tecnologia é onde o hospital e a Vitta (a empresa que cuida dos sistemas do hospital) conversam sobre os sistemas. Antes ela era o WhatsApp, e o que se combinava lá se perdia. Aqui cada assunto vira uma Demanda, com um lugar fixo para ficar até alguém resolver.

Só quem tem acesso de administrador do aplicativo enxerga a aba. Os dois lados usam a mesma tela: o hospital pede para a Vitta, e a Vitta também pede para o hospital.

## O que é uma Demanda

Uma Demanda é um pedido sobre um dos sistemas. Ela vai nos dois sentidos: o diretor pede à Vitta (um ajuste, uma dúvida, um estudo) e a Vitta pede ao diretor (uma decisão, um dado, um acesso).

Toda Demanda tem título, Tipo, Produto, prioridade, descrição e, quando existe de verdade, um prazo. A descrição é texto livre, sem limite de tamanho.

Não chame de pendência, tarefa nem chamado. Pendência é outra coisa no aplicativo: é o compromisso operacional que sai de uma reunião do hospital, e mora em outro lugar.

## Os sete Tipos

A lista de Tipos é fechada. São sete:

- **Decisão**: a Vitta precisa que o hospital escolha uma coisa. Exemplo: "a Vitta quer saber se o relatório da Ouvidoria sai mensal ou trimestral".
- **Informação**: a Vitta precisa de um dado do hospital. Exemplo: "a Vitta pede a lista atualizada de setores para cadastrar na Ouvidoria".
- **Terceiro**: o assunto depende de alguém de fora do hospital e da Vitta, como a Global Health, o analista de TI do hospital ou a MV. Exemplo: "o relatório novo depende de a Global Health liberar um acesso".
- **Ajuste**: o hospital quer mudar algo que já existe. Exemplo: "a tela de Demandas devia mostrar quem é o responsável antes da prioridade".
- **Novo**: o hospital quer algo que ainda não existe. Exemplo: "queria um aviso por e-mail quando a Ouvidoria encerrar um caso".
- **Defeito**: algo está quebrado, ou funciona diferente do que deveria. Exemplo: "o botão de salvar o POP não faz nada".
- **Consultoria**: o hospital quer uma opinião ou um estudo da Vitta, sem que isso vire código agora. Exemplo: "vale a pena trocar o provedor de e-mail?".

O Tipo não diz de quem é a vez de responder. Isso é o estado e o responsável.

## Os Produtos

Produto é cada coisa que a Vitta mantém para o hospital: Ana (o WhatsApp), Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site e Infra. Cada Produto tem um dono do lado da Vitta.

Toda Demanda pertence a um Produto. É o Produto que decide quem responde por ela.

## O que acontece depois de criar

A Demanda nasce na coluna **Nova**, já atribuída ao dono do Produto escolhido. Quem virou responsável recebe um e-mail avisando.

A partir daí ela anda por um quadro de cinco colunas:

- **Nova**: acabou de ser aberta, ninguém pegou ainda.
- **Em andamento**: alguém está tocando o assunto.
- **Aguardando**: a bola está com o outro lado, ou com alguém de fora.
- **Concluída**: o assunto acabou.
- **Cancelada**: o assunto não vai acontecer.

Além do estado, a Demanda tem um responsável (uma pessoa), uma prioridade (Baixa, Normal ou Alta) e um prazo opcional. Sem prazo, o card não atrasa: ele só envelhece, e a idade em dias aparece no card.

Dentro do card existe a **Conversa**: um fio de respostas, onde a decisão evolui. Dá para mencionar alguém com arroba, e essa pessoa recebe um e-mail. O responsável também recebe e-mail quando alguém responde.

## Quem vê

Todo mundo que tem acesso à aba vê todas as Demandas, dos dois lados. Não existe Demanda privada nem escondida: o quadro é compartilhado de propósito, para ninguém precisar perguntar em que pé está.

## A Etapa

Quando uma Demanda vira trabalho de desenvolvimento, ela ganha uma **Etapa**, que conta em que pé está a entrega, em palavras de quem pediu:

- **Registrada**: o pedido está anotado, a entrega ainda não começou.
- **Em análise**: a Vitta está entendendo o que precisa ser feito.
- **Planejada**: já se sabe o que fazer, o trabalho está na fila.
- **Em desenvolvimento**: está sendo feito agora.
- **Entregue**: está pronto e no ar.
- **Não será feita**: decidiu-se não fazer.

A Etapa nunca é digitada à mão: ela é lida do planejamento da Vitta e aparece sozinha no card. Quando a entrega tem partes, o card mostra quantas já foram entregues.

A Etapa é um eixo diferente do estado. O estado diz de quem é a vez na conversa; a Etapa diz o que o desenvolvimento já fez. Só uma Etapa mexe no estado: quando a entrega fica **Entregue**, a Demanda volta para quem pediu, em Aguardando, para a pessoa conferir e então concluir.

No card também aparece **O que muda**: o que aquela entrega acrescenta, em linguagem de quem usa. Esse texto vem do planejamento da Vitta e não é escrito no aplicativo.
