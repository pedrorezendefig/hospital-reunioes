# A aba Tecnologia

A aba Tecnologia é onde o hospital e a Vitta (a empresa que cuida dos sistemas do hospital) conversam sobre os sistemas. Antes ela era o WhatsApp, e o que se combinava lá se perdia. Aqui cada assunto vira uma Demanda, com um lugar fixo para ficar até alguém resolver.

Só quem tem acesso de administrador do aplicativo enxerga a aba. Os dois lados usam a mesma tela: o hospital pede para a Vitta, e a Vitta também pede para o hospital.

A aba tem duas abas no alto: o **Quadro**, onde o trabalho do dia anda, e o **Painel**, onde se lê o que está com você, o que a Vitta está entregando e o que já fechou.

## O que é uma Demanda

Uma Demanda é um pedido sobre um dos sistemas. Ela vai nos dois sentidos: o diretor pede à Vitta (um ajuste, uma dúvida, um estudo) e a Vitta pede ao diretor (uma decisão, um dado, um acesso).

Toda Demanda tem título, Tipo, Produto, prioridade, descrição e, quando existe de verdade, um prazo. A descrição é texto livre, sem limite de tamanho. Ela também pode levar prints da tela, que são os anexos da Demanda.

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

Produto é cada coisa que a Vitta mantém para o hospital: Ana (o WhatsApp), Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site, Infra e Central de Comando (o painel dos números do Site e do Instagram, só para Super admin). Cada Produto tem um dono do lado da Vitta.

Toda Demanda pertence a um Produto. É o Produto que decide quem responde por ela.

A lista de Produtos tem tela própria: o botão da engrenagem, ao lado de **Nova Demanda** no alto do Quadro, abre a tela **Produtos**. Lá dá para criar um Produto, renomear, trocar o dono e desativar. Desativar não apaga nada: as Demandas daquele Produto continuam onde estão, ele só sai da lista de escolha.

## O que acontece depois de criar

A Demanda nasce na raia **Nova**, já atribuída ao dono do Produto escolhido. Quem virou responsável recebe um e-mail avisando.

Além do estado, a Demanda tem um responsável (uma pessoa), uma prioridade (Baixa, Normal ou Alta) e um prazo opcional. Sem prazo, o card não atrasa: ele só envelhece, e a idade em dias fica vermelha a partir de 14 dias.

Dentro do card existe a **Conversa**: um fio de respostas, onde a decisão evolui. Dá para mencionar alguém com arroba, e essa pessoa recebe um e-mail. O responsável também recebe e-mail quando alguém responde.

## O Quadro

O Quadro é a primeira aba. Ele mostra só as três raias vivas, uma ao lado da outra:

- **Nova**: acabou de ser aberta, ninguém pegou ainda.
- **Em andamento**: alguém está tocando o assunto.
- **Aguardando**: a bola está com o hospital, ou com alguém de fora, ou com quem pediu conferindo uma entrega. É a única raia em que a vez não é da Vitta, e o responsável diz com quem está.

A Demanda termina de dois jeitos: **Concluída** (o assunto acabou) ou **Cancelada** (o assunto não vai acontecer). Esses dois não são raias: são os botões **Concluir** e **Cancelar**, dentro do card aberto, em **Mover**. A Demanda encerrada sai do Quadro e passa a morar no Histórico do Painel.

O card fechado é curto: o símbolo do Tipo, o título e, embaixo, o Produto e o responsável. O resto só aparece quando é exceção: o selo da Etapa quando a Demanda está ligada ao desenvolvimento, a prioridade só quando é Alta, e a idade só quando já está vermelha ou com o prazo vencido. Para ver tudo, clique no card. Arrastar o card de uma raia para outra continua valendo, e dá no mesmo que usar Mover.

## O Painel

O Painel é a segunda aba, só de leitura. É o lugar para responder "o que está comigo?", "o que está com o hospital?" e "o que a Vitta está fazendo?" sem abrir card nenhum.

No topo ficam quatro números, os mesmos para quem estiver olhando:

- **Abertas**: as Demandas em Nova, Em andamento ou Aguardando.
- **Com o hospital**: as que estão em Aguardando, a raia em que a vez não é da Vitta.
- **Em desenvolvimento**: as abertas que a Vitta já planejou ou está construindo.
- **Entregues em 30 dias**: as que chegaram a Entregue ou Em produção no último mês, mesmo que já tenham sido concluídas.

Embaixo vêm três blocos, que abrem e fecham com um clique no título:

- **Com você**: as Demandas abertas de que você é o responsável e as em que mencionaram você e você ainda não respondeu. Cada linha diz o motivo: "Você é o responsável", "Mencionaram você" ou, quando a entrega volta para você conferir, "Entregue, confira e conclua". Vazio é boa notícia: a tela diz "Nada esperando por você agora".
- **Entregas**: as Demandas abertas ligadas ao desenvolvimento, uma linha cada, com a Etapa e as partes, a da última mudança primeiro. É onde se vê o que a Vitta está fazendo.
- **Histórico**: as Demandas Concluídas e Canceladas, com quem fechou e quando, e uma busca por título, descrição ou texto da Conversa.

Clicar numa linha abre o mesmo card do Quadro. O Painel não tem número por pessoa nem ranking de ninguém.

## Os anexos da Demanda

Os anexos são prints de tela guardados junto da Demanda, para quem vai resolver ver o que a pessoa viu. Aceita imagem PNG, JPG ou WEBP, de até 5 MB cada, e até 10 imagens por Demanda.

Dá para anexar por três caminhos:

- **No formulário**, pelo botão **Anexar prints (até 10)**.
- **No assistente**, mandando o print na conversa: se você clicar em **Criar Demanda**, o print vira anexo. Se não clicar, ele some com a conversa.
- **Na Conversa** do card, pelo botão de imagem ao lado de **Responder**: a imagem entra junto da resposta.

Os anexos aparecem no card aberto, em **Imagens**, com quem anexou e quando. Clicar na miniatura abre a imagem em tamanho real.

Os prints ficam só dentro do aplicativo. Eles nunca vão para o material público do desenvolvimento, porque um print do hospital pode ter nome de paciente ou de colaborador; quem desenvolve busca as imagens pelo aplicativo.

Quando a Demanda é Concluída ou Cancelada, as imagens são apagadas. Fica no card o registro de que existiram (o nome, quem anexou e quando), marcado como apagado. Por isso, enquanto a entrega está sendo conferida, a Demanda continua aberta e o print continua lá.

## Quem vê

Todo mundo que tem acesso à aba vê todas as Demandas, dos dois lados. Não existe Demanda privada nem escondida: o Quadro é compartilhado de propósito, para ninguém precisar perguntar em que pé está.

## A Etapa

Quando uma Demanda vira trabalho de desenvolvimento, ela ganha uma **Etapa**, que conta em que pé está a entrega, em palavras de quem pediu:

- **Registrada**: o pedido está anotado, a entrega ainda não começou.
- **Em análise**: a Vitta está entendendo o que precisa ser feito.
- **Planejada**: já se sabe o que fazer, o trabalho está na fila.
- **Em desenvolvimento**: está sendo feito agora.
- **Entregue**: está pronto, mas ainda não chegou ao aplicativo que você usa.
- **Em produção**: já está no ar, e dá para usar. O selo diz desde qual versão do aplicativo.
- **Não será feita**: decidiu-se não fazer.

A Etapa nunca é digitada à mão: ela é lida do planejamento da Vitta e aparece sozinha no card. Quando a entrega tem partes, o card mostra quantas já foram entregues. Assim que a Vitta começa a construir, a Etapa passa sozinha para Em desenvolvimento.

A Etapa é um eixo diferente do estado. O estado diz de quem é a vez na conversa; a Etapa diz o que o desenvolvimento já fez. Só uma Etapa mexe no estado: quando a entrega fica **Em produção**, a Demanda volta para quem pediu, em Aguardando, com um e-mail, para a pessoa conferir no aplicativo e então concluir. Na Conversa aparece a linha "Em produção na" seguida da versão. Entre Entregue e Em produção costuma passar pouco tempo, mas ninguém confere o que ainda não subiu, e por isso a devolução espera o Em produção.

Quando o assunto foi resolvido sem mexer no aplicativo (uma decisão, uma consultoria), não há o que subir: a Demanda volta para quem pediu já em Entregue.

No card também aparece **O que muda**: o que aquela entrega acrescenta, em linguagem de quem usa. Esse texto vem do planejamento da Vitta e não é escrito no aplicativo.
