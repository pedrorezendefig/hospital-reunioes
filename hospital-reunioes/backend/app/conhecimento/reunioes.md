# Reuniões

O módulo de Reuniões é o que o aplicativo faz desde o começo: transforma uma reunião em ata, e a ata em tarefas com dono e prazo. É onde a diretoria registra o que foi decidido e acompanha o que ficou combinado.

Quem conduz uma reunião e responde pela ata é o facilitador, e é ele quem entra no aplicativo. Quem só foi citado numa reunião, ou ficou responsável por alguma coisa, não entra: recebe e-mail e links diretos para o que é dele.

## Os dois jeitos de montar a ata

**Por transcrição.** O facilitador traz o texto da reunião e a inteligência artificial monta a ata: tópicos, decisões e ações. Essa ata vira PDF e pode ir para assinatura digital.

**Ata guiada.** Para a reunião operacional que não teve transcrição, o facilitador monta a ata conversando numa tela própria, por escrito ou por voz: de um lado o chat, do outro a ata tomando forma, já com o visual da ata final. O agente pergunta o que falta, principalmente quem faz e até quando, e o facilitador pode apontar uma seção e corrigi-la pela conversa. Essa ata não gera PDF e não vai para assinatura.

Uma reunião tem no máximo uma ata, por um dos dois caminhos.

## Quem faz o quê, e até quando

Os nomes citados na reunião são casados com o cadastro de pessoas do hospital. Quem está no cadastro vira responsável de verdade e passa a ser cobrado; quem é de fora fica só como nome, sem cobrança. Quando o agente não tem certeza de quem é, ele pergunta.

Cada linha do quadro da ata é de um tipo: Ação, Rotina ou Processo. A Ação acontece uma vez e tem prazo. A Rotina se repete toda semana, quinzena ou mês e tem um responsável que executa; ela substitui o antigo "fluxo contínuo". O Processo diz como se faz dali para frente, sem executor e sem cobrança. A inteligência artificial sugere o tipo de cada linha, na ata por transcrição, na correção e na ata guiada, e o facilitador troca o tipo e a frequência na revisão da ata. A linha sem tipo vale como Ação, e é assim que as atas antigas continuam.

No envio, só a Ação vira pendência, com responsável e prazo, e desde o primeiro segundo ela é cobrada de verdade: aparece no painel, vence e atrasa. A linha de Rotina vira uma rotina, com o responsável e a frequência da linha, e o Processo fica guardado no quadro da ata. Antes de enviar, toda Rotina precisa de responsável e frequência: se faltar um dos dois, o aplicativo não envia e diz qual linha falta completar.

## Como a pendência anda

A pendência tem quatro estados: pendente, em progresso, concluída e cancelada. Atrasada não é um estado que alguém marca: é a pendência aberta (pendente ou em progresso) cujo prazo já passou, e o aplicativo mostra isso na hora, sem esperar rotina nenhuma. Ela continua atrasada, com o prazo que venceu, até ser repactuada ou concluída. O prazo de um dia só vence quando esse dia acaba, no horário de Brasília.

Toda mudança pede uma anotação, escrita por quem faz. As ações são iniciar, anotar, concluir, repactuar, cancelar e reabrir. Na tela da pendência, cada botão abre um campo de anotação, e nada é gravado com ele vazio. Repactuar e reabrir pedem também o prazo novo, que vale na hora.

Quem pode o quê:

- O responsável e o co-responsável iniciam, anotam, concluem e repactuam. Só o responsável contesta.
- O facilitador da reunião repactua, cancela e reabre, e responde à contestação, ajustando ou recusando.
- Quem administra o aplicativo faz tudo, menos contestar, e menos nas reuniões do Núcleo de Segurança do Paciente, que seguem a regra do Núcleo.
- Quem só participou da reunião não age na pendência dos outros.

Concluir já termina, sem validação de ninguém, e o aplicativo guarda o dia em que o responsável marcou. Repactuar antes do prazo vencer não conta como atraso; depois de vencer, conta, e a repactuação fica marcada para o ranking. A reabertura feita com o prazo já vencido também fica marcada. A pendência que já teve o prazo trocado aparece como repactuada enquanto estiver aberta e no prazo.

Ao concluir, dá para anexar uma foto ou um PDF de até 10 MB, como prova da entrega. O anexo é opcional; a anotação continua obrigatória. Arquivo maior ou de outro tipo é recusado com a explicação na tela, e a tela lembra de não mandar foto com paciente nem documento interno sensível. O anexo aparece na linha da conclusão, no histórico, mas só o responsável, o facilitador da reunião e quem administra o aplicativo abrem o arquivo, por um link que vale poucos minutos. O co-responsável e quem vê a pendência por outro motivo enxergam que há anexo, sem abrir.

O histórico da pendência começa com o nascimento dela. Cada ação vira uma linha no histórico, com quem fez, quando e a anotação, e a tela mostra esse histórico em ordem. Ninguém edita nem apaga uma linha do histórico, nem quem administra o aplicativo: o próprio banco de dados recusa. Também não existe mais o "excluir pendência": o caminho é cancelar, com anotação. Título, meta, cargo e responsável ficam só para leitura na tela.

Excluir a reunião também não apaga as pendências dela. Reunião que já teve pendência não pode ser excluída, mesmo que todas estejam canceladas: ela segue com a ata e o histórico, e quem tenta desmarcar vê uma mensagem explicando por quê. O mesmo vale para desmarcar uma série recorrente em que alguma reunião já tem pendência. Reunião que nunca teve pendência continua podendo ser desmarcada, como antes.

Os lembretes da Agenda regulatória do Núcleo de Segurança do Paciente também são pendências e têm o mesmo histórico. Quando o resultado do evento é registrado na Agenda, o lembrete é concluído e o resultado que a Presidência escreve vira a anotação. Se a data do evento muda antes do resultado, o lembrete da data antiga é cancelado, e a anotação diz a data de antes e a nova. Esses lembretes continuam aparecendo só na Agenda regulatória, para quem é do Núcleo.

As pendências antigas que estavam atrasadas ou "a repactuar" (sem prazo) recuperaram o prazo que estava no quadro da ata. Onde o quadro não tinha o prazo, ficou valendo a data da última mudança, e o histórico dela mostra esse ajuste.

## A rotina e a verificação de cada ciclo

A rotina nasce no envio da ata e segue o calendário: a semana vai de segunda a domingo, a quinzena vai do dia 1 ao 15 e do 16 ao fim do mês, e o mês vai do dia 1 ao último dia. Ela começa no ciclo seguinte ao do envio, o primeiro inteiro: a ata enviada numa quinta só cobra a partir da segunda seguinte, e ninguém é cobrado por um ciclo pela metade.

A cada ciclo o responsável marca se fez ou não. Realizada é um clique; Não realizada pede uma anotação, e o aplicativo não grava sem ela. A verificação vale até o último dia do ciclo. O ciclo que terminou sem marcação fica atrasado e ainda pode ser marcado depois, mas a marcação fica registrada como atrasada. Nenhuma rotina de fundo cria a verificação: o ciclo existe pela data, e o registro só aparece quando alguém marca.

Quem marca é o responsável, no aplicativo. Para quem não entra no aplicativo, o facilitador da reunião marca por ele. O facilitador também pode encerrar a rotina a qualquer momento, com uma anotação: o ciclo em curso e os seguintes deixam de ser cobrados, e os que já tinham terminado sem marcação continuam lá para marcar. Quem administra o aplicativo faz o mesmo que o facilitador, menos nas reuniões do Núcleo de Segurança do Paciente, que seguem a regra do Núcleo.

A tela Rotinas, no menu de Reuniões, mostra as rotinas no nome da pessoa e as das reuniões que ela conduz, com os ciclos em aberto e as marcações feitas. A verificação do ciclo em aberto também aparece no Início do responsável, com o prazo no último dia do ciclo e o botão Realizada, que marca ali mesmo; o ciclo que fechou sem marcação aparece como prazo vencido.

## Contestar um item da ata

Quando um item da ata está errado (o prazo, o responsável ou o que foi combinado), o responsável por ele pode contestar. Só o responsável pelo item contesta, e só enquanto a ata está em assinatura. Na tela da pendência aparece o botão Contestar, que pede uma anotação explicando o que está errado. A contestação vale para aquele item: a pessoa contesta o item e assina a ata mesmo assim, porque a assinatura registra que ela leu o resto da ata.

Contestar não é jeito de adiar. O item contestado continua sendo cobrado, com o mesmo prazo, e conta atraso se o prazo vencer, até o facilitador responder.

A contestação aparece na hora no Início do facilitador da reunião, no grupo do que vence em até 48 horas, sem esperar a segunda-feira. Se ele não responde até o fim do dia seguinte, ela passa para o grupo do que já venceu. O facilitador, ou quem administra o aplicativo, abre a pendência e escolhe ajustar ou recusar, sempre com uma anotação:

- **Ajustar** aceita a contestação, e a anotação diz o que foi corrigido. Se o erro era o prazo, ele informa também o prazo novo, que vale na hora e não conta como repactuação. Se o erro era o responsável, ele escolhe a pessoa certa no cadastro: a pendência passa para o nome dela na hora, sai da lista de quem estava errado, e o histórico mostra quem era e quem passou a ser.
- **Recusar** mantém a pendência como está, e a anotação explica por quê.

O ajuste fica na pendência e no histórico, e a ata não volta para assinatura. Respondida a contestação, ela sai do Início do facilitador, e o responsável pode contestar de novo enquanto a ata estiver em assinatura.

## Assinar ou finalizar sem assinar

Depois de revisar a ata, o facilitador escolhe um de dois caminhos, e os dois são definitivos:

- **Enviar para assinatura.** As pendências nascem todas no momento do envio, sem esperar ninguém assinar, e a cobrança começa no mesmo dia. A ata vira PDF, gerado de novo nessa hora com o quadro de ações final, e segue para assinatura digital, na ClickSign, que é quem manda o e-mail para cada pessoa assinar. Daí em diante, a assinatura vale como ciência da ata.
- **Finalizar sem assinatura.** As pendências nascem na hora e a ata fica aprovada, sem passar pela assinatura.

Não existe "assinar depois": escolhido o caminho, ele vale.

Se o envio para a ClickSign falhar, a ata continua aguardando assinatura, as pendências continuam valendo, e na tela da reunião aparece o botão de reenviar. Reenviar não repete pendência nem cria um segundo envio para assinatura, e clicar duas vezes em enviar também não. Depois do envio, reprocessar e corrigir a ata ficam bloqueados, o quadro de ações inclusive: o que foi enviado é o que vale.

Quando a assinatura não se completa (alguém recusa, ou o processo é cancelado), quem ainda não assinou recebe um e-mail com link, lê a ata inteira e clica em "li e aceito". Esse aceite vale como ciência, igual à assinatura, e não cria pendência, porque elas já existem desde o envio. A reunião fecha quando todos deram ciência; a recusa sozinha não fecha a ata como assinada. O aceite não é assinatura digital: a formalidade continua sendo só do caminho da assinatura.

A coleta de assinaturas também tem prazo: são 30 dias. Vencido o prazo, a ata é finalizada com as assinaturas que tiver, e a tela mostra quantos de quantos assinaram.

Todo dia, às 5h30, o aplicativo confere as atas que aguardam assinatura e cria as pendências que faltarem, sem repetir nenhuma. Foi assim que as atas que já estavam em assinatura antes dessa regra ganharam as pendências delas.

## Quem vê cada pendência

Cada pessoa vê as pendências de que é responsável ou divide a responsabilidade, e todas as pendências das reuniões em que ela é o facilitador. Quem só participou de uma reunião não vê as pendências dos outros que saíram dela. Quem administra o aplicativo vê todas, menos as das reuniões do Núcleo de Segurança do Paciente, que seguem a regra do Núcleo. Isso vale para a lista e o quadro de pendências, os números do painel, a tela da pendência com os comentários e o que o Claude da diretoria consulta. Num comentário, só dá para mencionar quem vê a pendência. A Secretária não vê pendência nenhuma, como antes.

## O setor da reunião

Toda reunião marcada tem setor. Quem agenda, a Secretária inclusive, escolhe o setor numa lista com os setores ativos do hospital, e o aplicativo não deixa marcar a reunião sem ele. A reunião repetida pela recorrência leva o setor da reunião de origem.

As reuniões antigas, marcadas antes dessa regra, continuam valendo mesmo sem setor. Quem administra o aplicativo tem no Admin a tela Acertos de setor, que lista as reuniões e os responsáveis por pendência que estão sem setor e deixa escolher o setor de cada um. Preenchido o setor, o item sai da lista.

## As definições de processo do setor

No envio da ata, cada linha do tipo Processo entra na lista de definições de processo do setor da reunião, com o trecho da ata copiado: quem consulta lê a regra combinada sem abrir a ata, e a lista não muda se a ata for corrigida depois. A lista fica nas Reuniões, e não nos POPs, até o rascunho de POP chegar. Ela não tem responsável, prazo nem lembrete: o processo não vira tarefa cobrada, e o facilitador consulta a lista quando quiser, na tela Definições de processo, no menu de Reuniões.

Enquanto o organograma não chega, cuidam da lista os facilitadores das reuniões do setor: quem conduz alguma reunião de um setor vê a lista inteira daquele setor, e os outros setores não aparecem para ele. A reunião antiga, ainda sem setor, mostra os itens dela só para o próprio facilitador. Quem administra o aplicativo vê as listas de todos os setores, menos as das reuniões do Núcleo de Segurança do Paciente, que seguem a regra do Núcleo. A Secretária não vê a lista.

Um item repetido, ou que deixou de valer, sai da lista pelo botão Tirar da lista, que pede uma anotação dizendo por quê. Só tiram o facilitador da reunião de onde o item saiu e quem administra o aplicativo. O item retirado não aparece mais na lista, mas não se apaga: fica registrado com o dia, quem tirou e a anotação.

## As reuniões do Núcleo de Segurança do Paciente

As reuniões do Núcleo de Segurança do Paciente ficam no módulo Segurança do Paciente, no item Reuniões, e não são marcadas pela tela de Reuniões. São de quatro tipos: ordinária mensal, análise de evento, apresentação à Diretoria e reunião rápida de segurança. Depois de criada, a reunião do Núcleo segue o mesmo caminho das outras até a ata. A reunião rápida de segurança é só um registro de três linhas, sem transcrição nem ata.

Só quem é do Núcleo vê essas reuniões. Para quem é de fora, elas não aparecem na lista de reuniões, no calendário, nas pendências, nos números do painel, no sino nem no que o Claude da diretoria consulta. Isso vale também para quem administra o aplicativo.

## O Início

O Início é a tela de cada pessoa, com o que ela tem para entregar. É o primeiro item do menu para todos, menos a Secretária, que continua com a tela dela e não vê pendência. Depois de entrar com a senha, todo mundo cai no Início, inclusive quem só usa Ouvidoria, POPs, o Núcleo ou Contas médicas; quem chegou ao login por um link (o de um caso da Ouvidoria, por exemplo) volta para esse link. A Secretária cai na tela de agendamento dela, e abrir o endereço do Início a leva de volta para lá. O logo do menu também leva ao Início. A antiga capa do aplicativo, com dois botões, não existe mais: o endereço principal leva ao Início quem já entrou e ao login quem não entrou. O painel de Reuniões continua no menu, no mesmo endereço.

No topo, uma frase escrita pelo próprio aplicativo, a partir dos números e sem inteligência artificial, diz quantos prazos venceram e há quantos dias o mais antigo espera. Quem não tem nada vencido lê que está em dia e qual é o próximo prazo. Enquanto houver prazo vencido, o topo fica numa faixa azul-marinho escura, e o vermelho aparece só no texto.

Nada na tela pisca. O título da aba do navegador mostra o número de prazos vencidos, e só "Início" quando não há nenhum. Os prazos vencidos entram uma vez, quando a tela abre; para quem pediu ao sistema menos movimento, nada se move. Os três números do topo levam à parte correspondente da lista. Ao passar o mouse numa linha, ou chegar nela pelo teclado, a linha ganha um fundo suave, o botão fica preenchido e aparece uma linha com o andamento e o dia em que o item abriu; no celular essa linha fica sempre à vista. No celular a tela fica em uma coluna, e o Início é o primeiro item da barra de baixo. Com leitor de tela, a frase do topo é anunciada quando chega e cada botão diz o que abre.

Embaixo vem a lista, do prazo mais vencido para o mais distante, em três partes: passou do prazo, vence em até 48 horas e próximos 7 dias. O prazo de um dia só vence quando esse dia acaba, no horário de Brasília. O atraso é contado pela data: a pendência aberta com o prazo vencido está atrasada.

Nesta primeira versão a lista traz as pendências abertas em que a pessoa é responsável ou divide a responsabilidade, inclusive o lembrete da Agenda regulatória do Núcleo, que antes não aparecia na lista de ninguém. Cada linha mostra os dias de atraso ou a data, de onde a pendência veio e um botão: a pendência de reunião abre no quadro de pendências já destacada, e o lembrete do Núcleo abre a Agenda regulatória. Se uma parte da tela não carregar, ela mostra um aviso só daquela parte e o resto continua. O caso da Ouvidoria que espera a resposta do setor também aparece, para o titular, o substituto e o gestor do setor, e quem tem o perfil da Ouvidoria vê uma linha à parte com o tamanho da fila (o texto do módulo Ouvidoria explica). POPs, o Núcleo e Contas médicas entram no Início nas próximas etapas.

Além das pendências, a ata que falta assinar aparece no Início de cada signatário, num grupo sem prazo, no fim da lista, com há quantos dias ela espera. O botão abre a reunião, e a ata sai da lista assim que a pessoa assina ou dá o "li e aceito". A ata em validação aparece só para o facilitador da reunião: até o terceiro dia ela fica no grupo sem prazo, e a partir do quarto dia, como prazo vencido, passa para "passou do prazo". O que está sem prazo não entra na conta da frase do topo. Ao lado da lista fica o trilho, com as próximas reuniões da pessoa, como facilitador ou participante, com dia, hora e o link para a reunião, e a reunião cancelada não aparece. As reuniões do Núcleo só aparecem, na lista e no trilho, para quem o Núcleo deixa ver.

Quem acompanha outras pessoas vê, abaixo da lista, o bloco Quem responde a você. Enquanto o organograma não chega, vale o vínculo: quem administra o aplicativo vê todas as pessoas com pendência aberta, e o facilitador vê os responsáveis das pendências das reuniões que conduziu, contando só as pendências dessas reuniões. Quem não é nenhum dos dois não vê o bloco. Cada linha mostra o nome, o cargo, os prazos vencidos agora, os itens em aberto e o último acesso ao Início ("hoje", "há tantos dias" ou "nunca entrou"), e quem tem mais prazos vencidos vem primeiro. Clicar na linha, ou apertar Enter nela, abre ali mesmo, só para leitura, o que venceu e não foi entregue, com há quantos dias. O último acesso de uma pessoa só aparece para quem vê alguma pendência dela, e as pendências do Núcleo ficam de fora para quem o Núcleo não deixa ver, inclusive quem administra o aplicativo. Se esse bloco não carregar, o resto do Início continua. No celular a tabela rola de lado dentro do próprio bloco.

## O painel de Reuniões

O painel de Reuniões mostra, em cards, os números de quem está olhando, contados pelo servidor sobre todas as pendências e reuniões do hospital, sem corte de quantidade. Quem é responsável conta as pendências de que é responsável ou divide a responsabilidade. O facilitador conta também as reuniões que conduz e as pendências delas. Quem administra o aplicativo conta o hospital inteiro, menos as reuniões do Núcleo de Segurança do Paciente que o Núcleo não deixa ver. A Secretária não vê o painel e não recebe número de pendência.

Os cards são a conformidade (a parte das pendências abertas que está no prazo), as que vencem em até 3 dias, as atas paradas há mais de 3 dias e as atas que aguardam assinatura. Os filtros de setor, responsável e prazo valem para os números das pendências e para os gráficos; nos cards de atas, vale só o de setor. Os dois cards de atas abrem a lista das atas que contaram. Na lista das que aguardam assinatura, o facilitador da reunião e quem administra o aplicativo veem quem ainda falta assinar e o botão Cobrar, que manda de novo o pedido de assinatura da ClickSign só para quem não assinou. Na ata que passou para a coleta interna de aceites, o Cobrar avisa que o envio na ClickSign já foi encerrado.

Abaixo dos gráficos, o painel mostra o gráfico de atrasos por setor e o ranking dos responsáveis dos últimos 90 dias, com o hospital inteiro na conta, menos as reuniões do Núcleo que o Núcleo não deixa ver. Os dois aparecem só para quem administra o aplicativo e para quem facilitou ao menos uma reunião; quem é só responsável não vê ranking. Os filtros do painel não mudam o ranking. Cada atraso conta no setor do responsável pela pendência, e o responsável sem setor aparece em Sem Setor. Contam como atraso a pendência aberta com o prazo vencido hoje e, nos últimos 90 dias (hoje e os 89 dias antes, no horário de Brasília), a repactuação feita depois de o prazo vencer e a conclusão depois do prazo; a repactuação feita antes de o prazo vencer não pesa. A conclusão só é medida se aconteceu depois que o histórico da pendência passou a guardar a data. As reaberturas de entrega concluída, nos mesmos 90 dias, aparecem ao lado dos atrasos. A pendência cancelada não entra em nenhuma dessas contas.

O painel não tem alerta de prazo nem lista do que depende de cada um: isso fica no Início, e o painel tem um link para lá.

## O calendário

No calendário de Reuniões, na visão do mês e na da semana, as reuniões de cada dia aparecem na ordem da hora de início, e a mais cedo vem primeiro. No mês, o dia mostra as três primeiras e um "mais" para abrir as outras. O título que não cabe no bloco aparece inteiro quando se passa o mouse sobre a reunião.

Na tela da reunião, o botão Excluir, que apagava a reunião em qualquer status e só quem administra o aplicativo via, saiu. Fica o Desmarcar, que vale para a reunião programada ou parada no erro e sem pendência.

## O que ele não faz

- Não grava a reunião: o aplicativo não capta o que se fala na sala. O áudio que ele recebe é o ditado, quando o facilitador prefere falar a digitar na ata guiada: esse áudio sobe, é transcrito ali mesmo e descartado. Áudio nenhum fica guardado.
- Não gera PDF da ata guiada, e não a manda para assinatura.
- Não desfaz uma ata finalizada pelo caminho normal: quem administra o aplicativo consegue corrigir uma ata já finalizada, com motivo obrigatório e registro de quem fez, e isso é exceção pedida caso a caso, não botão de uso corrente. Apagar a reunião, nem ele consegue.

## O que já foi decidido

- Uma reunião tem no máximo uma ata, feita por transcrição ou pela ata guiada.
- A ata guiada não gera PDF e não vai para assinatura.
- Depois de revisar a ata, o facilitador escolhe entre enviar para assinatura e finalizar sem assinatura, e a escolha é definitiva.
- No caminho da assinatura, todas as pendências nascem no envio da ata, e a assinatura e o "li e aceito" valem como ciência.
- A coleta de assinaturas dura até 30 dias, e depois disso a ata fecha com as assinaturas que tiver.
- A inteligência artificial pergunta quando não tem certeza de quem é o responsável, e quem liga a ação a uma pessoa do cadastro é o aplicativo.
- Quem é de fora do cadastro fica na ata só como nome, sem cobrança.
- A lista de participantes da ata é proposta pela inteligência artificial uma vez só, e daí em diante só o facilitador mexe nela.
- O aplicativo não grava a reunião, e o áudio do ditado é descartado assim que vira texto.
- As notas avulsas e a importação de atas antigas foram retiradas do aplicativo.
- O papel interno de cada facilitador é uma etiqueta da administração, e a própria pessoa não vê o dela.
- Os títulos e subtítulos do PDF da ata saem em caixa alta, inclusive os tópicos escritos pela inteligência artificial, e o resto do texto continua com maiúscula e minúscula.
- As reuniões do Núcleo de Segurança do Paciente ficam no módulo Segurança do Paciente e não aparecem para quem não é do Núcleo, nem para quem administra o aplicativo.
- Cada pessoa vê as pendências dela e as das reuniões que facilita, quem só participou da reunião não vê as dos outros, e quem administra o aplicativo vê todas, fora as do Núcleo.
- No calendário, as reuniões de cada dia seguem a hora de início, da mais cedo para a mais tarde.
- Nada apaga pendência: reunião que já teve pendência, mesmo toda cancelada, não se exclui.
- Toda reunião nova tem setor, e quem administra o aplicativo preenche o setor que falta nas reuniões antigas e nos responsáveis.
- A linha de Processo entra, no envio, na lista de definições de processo do setor da reunião, com o trecho da ata copiado; cuidam dela os facilitadores das reuniões do setor, quem administra o aplicativo vê todas, a Secretária não vê, e tirar um item pede anotação e cabe ao facilitador da reunião de origem e a quem administra o aplicativo.
- Cada linha da ata é Ação, Rotina ou Processo, e só a Ação vira pendência; a linha sem tipo vale como Ação, e toda Rotina precisa de responsável e frequência antes do envio.
- A rotina segue o calendário (semana, quinzena de 1 a 15 e de 16 ao fim do mês, ou mês), começa no primeiro ciclo inteiro depois do envio, e cada ciclo é marcado como Realizada, com um clique, ou Não realizada, com anotação; o facilitador marca por quem não entra no aplicativo e encerra a rotina com anotação.

## O que costuma virar Demanda

- Ata saindo com erro de conteúdo, ou perdendo uma decisão que foi tomada (Defeito).
- Nome citado que casou com a pessoa errada, ou não casou com ninguém (Defeito).
- Campo novo na ata, ou mudança no texto do e-mail de cobrança (Ajuste).
- Mudança em quem assina, ou na ordem das assinaturas (Decisão).
