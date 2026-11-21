# Canal de Conduta

Canal de Conduta é o módulo em que quem trabalha no hospital, com qualquer vínculo, relata conduta grave de forma anônima, e em que o Comitê de Conduta apura o caso até a medida. Ele tem dois lados: o público, sem login, onde a pessoa relata e acompanha pelo protocolo e pelo código, e o do Comitê, onde os casos são lidos e apurados.

Hoje o relato de conduta de colaborador chega pela Ouvidoria, junto das manifestações de pacientes. O Canal separa esses casos, com anonimato real e prova que aguente uma medida disciplinar ou um processo.

Toda Demanda sobre o relato de conduta, sobre o Comitê de Conduta, sobre quem lê um caso ou sobre o sigilo do Canal pertence a este Produto.

## O que já está no ar

A base do sigilo e a tela Membros do Comitê:

- o Comitê de Conduta criado como o segundo colegiado do hospital, ao lado do Núcleo de Segurança do Paciente. Ele nasceu sem nenhum membro: os membros entram só pela tela Membros, nunca direto na base;
- o conteúdo de cada caso guardado cifrado. Quem abre a base de dados direto vê o relato embaralhado, e não o texto. Ficam legíveis só o que a lista e o prazo precisam: a rota, a etapa, a categoria e as datas;
- o protocolo do caso é sorteado, sem ordem e sem contagem, para não revelar quantos casos existem. A numeração da Ouvidoria continua a mesma;
- o código de acompanhamento é mostrado uma vez só a quem relatou, e o aplicativo guarda apenas uma marca dele, que não permite recuperar o código;
- a lista dos casos e a abertura de um caso, para quem está designado. Cada abertura fica registrada com quem abriu, quando e o quê;
- o canal está fechado: a página pública responde como se não existisse, até a abertura;
- a tela Configurações, só da coordenação do Comitê, com os contatos e os textos que o canal mostra (veja abaixo).

As telas do Comitê, em Comitê de Conduta:

- MINHA VEZ, a tela inicial: só o que depende da pessoa naquele momento, do prazo que vence antes ao que vence depois. Cada linha mostra o protocolo, a etapa, o que falta fazer e o prazo ("Faltam 12 dias"). Vazia, diz "Nada depende de você agora.";
- Casos: todos os casos a que a pessoa tem acesso, com filtro por situação (em triagem, em andamento, encerrado) e por rito. As duas listas não mostram nome nem trecho de relato;
- a tela do caso: o trilho do rito no topo (Triagem, Apuração, Voto, Ata, Medida, Acompanhamento), o prazo sempre visível, a triagem, o relato original e a caixa "O QUE FAZER AGORA", com uma frase, um botão e o "Como fazer" em três linhas que abrem ao toque. Quando o botão está bloqueado, a caixa diz o motivo numa linha, como "Só a coordenação confirma a triagem." ou "Falta o segundo leitor conferir a triagem.".

A triagem e os ritos:

- a triagem é manual: a coordenação diz se o caso é do canal (dentro, fora ou misto), a categoria (A a F), o rito e, quando parte do assunto é de fora, para onde ele vai (Departamento Pessoal, Ouvidoria, Núcleo de Segurança do Paciente ou a liderança);
- o segundo leitor vê a mesma fila e confere cada triagem, ou contesta com o motivo em uma linha e a triagem que defende. A contestação vai à decisão dos três membros votantes, e vale o que dois deles escolherem;
- os ritos desta fase são Encaminhamento (5 dias úteis, sem contar feriado cadastrado), Rápido (20 dias corridos) e Completo (30 dias corridos). O prazo conta do dia em que o relato foi enviado, nunca da triagem;
- prazo vencido fica registrado para sempre: nenhum perfil apaga o registro, e prorrogar depois não o tira;
- o rito Completo prorroga uma única vez, por mais 30 dias, com justificativa escrita, que fica guardada cifrada;
- no Encaminhamento (assunto fora do canal), depois da conferência do segundo leitor, a coordenação confirma a resposta padrão num clique e o caso encerra como "Encaminhado". A resposta diz ao relator que o assunto não é tratado no canal, para onde ele deve ir e que assédio, ameaça ou retaliação viram um novo relato.

## As configurações e os textos

A coordenação do Comitê edita, na tela Configurações:

- o contato do DP, mostrado a quem procura o canal por salário, contracheque ou escala;
- a orientação do NSP, mostrada quando o assunto é segurança do paciente;
- os três avisos do primeiro passo do relato;
- os textos da página "Como este canal protege você", bloco a bloco;
- o texto de consentimento lido no início de cada depoimento gravado;
- o local padrão de guarda dos envelopes com os originais em papel.

Cada vez que alguém salva um item, nasce uma versão nova, com quem salvou e quando. A anterior continua lá e pode ser consultada na mesma tela. Nenhum perfil apaga ou troca uma versão, e a própria base de dados recusa essa alteração. As páginas públicas mostram sempre a versão mais recente e sabem dizer qual versão mostraram, para ficar guardado o texto que cada pessoa leu ao relatar.

Quem não é da coordenação do Comitê, o super admin inclusive, não abre a tela. Item que ninguém salvou ainda aparece como "Ainda não preenchido".

Não existe e-mail do DP nas configurações: o encaminhamento ao DP não sai por e-mail, e a página só mostra o contato dele.

## O Código de Conduta

A coordenação do Comitê publica o Código de Conduta em PDF, e só ela. Cada publicação vira uma versão nova, com quem publicou, quando e a data em que passa a valer. A data de vigência pode ser hoje ou depois, nunca antes de hoje nem antes da vigência da última versão: assim nenhuma publicação muda o Código que valia num dia que já passou.

Nenhuma versão é apagada ou trocada, e a própria base de dados recusa essa alteração. A coordenação lista todas as versões e baixa qualquer uma delas.

Dada uma data, o aplicativo diz qual versão valia naquele dia: a de vigência mais recente até a data. Se duas versões começam no mesmo dia, vale a publicada depois. É por ela que cada punição cita o item do Código que valia na data do fato.

A versão vigente tem um endereço público estável, sem login, que a página do canal usa quando abrir. O endereço é sempre o mesmo, de uma versão para a outra, e mostra o PDF da versão que vale hoje. Versão com vigência futura só aparece nele a partir do dia dela. Com o canal fechado, o endereço responde como se não existisse.

## A tela Membros

A tela Membros diz quem compõe o Comitê e até quando. Cada linha mostra a pessoa, a cadeira, se ela é diretor, a vigência e a situação: vigente, a começar, vencida ou encerrada. Escolhendo uma data passada, a tela mostra a composição daquele dia.

- As cadeiras são quatro: coordenação, membro, membro e segundo leitor, e suplente. O segundo leitor vê a mesma fila da coordenação.
- Cada membro tem a marcação de que é ou não diretor, que a Rota Especial usa depois.
- O mandato é de dois anos: sem data de fim, a vigência vai até a véspera do mesmo dia, dois anos depois.
- Veem a tela os membros do Comitê e quem tem o perfil de cadastro de membros.
- Só quem tem o perfil de cadastro de membros inclui e encerra a participação de um membro ou suplente. O super admin sem esse perfil não cadastra. O perfil fica no cadastro da pessoa, na área de administração.
- Quem tem só o perfil de cadastro não vê a lista de casos nem abre caso nenhum.
- Encerrar não apaga: a participação fica na lista como encerrada, para a composição das datas em que valia.
- Toda inclusão ou saída de membro, e todo perfil de cadastro dado ou tirado, avisa os membros vigentes do Comitê no sino do aplicativo e por e-mail. O e-mail diz só que houve mudança, sem nomes e sem nada de caso, e leva à tela Membros.
- Cada uma dessas mudanças fica no registro do Comitê, com quem fez e quando, e o registro não se altera nem se apaga.

## Quem vê

Ninguém vê um caso por ter um cargo. Vê quem está designado naquele caso:

- a coordenação, o segundo leitor e os membros do Comitê, com a participação em dia e o Termo assinado, veem os casos da fila comum;
- o suplente vê só o caso para o qual foi convocado;
- o apurador, o membro da CIPA e o grupo da Rota Especial veem só o caso que receberam, depois do termo assinado;
- quem é citado no relato como envolvido nunca vê o caso, em nenhum perfil, e quem se declarou impedido perde o acesso àquele caso;
- o super admin e a equipe técnica não abrem conteúdo de caso pelo aplicativo;
- quem está no Comitê e ainda não assinou o Termo não abre caso.

Quem não tem acesso recebe a mesma recusa, exista o caso ou não.

## O sigilo

- Se a chave da cifra não estiver configurada no servidor, o módulo recusa gravar e ler caso, e o resto do aplicativo funciona normalmente. A verificação de saúde do sistema diz se a chave está lá, sem mostrar a chave.
- Se o registro da abertura não puder ser gravado, o caso não abre.
- O registro dos acessos é uma corrente: cada linha carrega a marca da anterior, e nenhuma pode ser alterada nem apagada. Uma linha trocada ou apagada por quem mexer direto na base aparece na conferência.
- O registro de funcionamento do servidor não guarda o endereço de quem usa o Canal.
- Os arquivos do caso ficam numa área própria, cifrados, e só saem pelo aplicativo, depois de conferido o acesso.
- A cifra protege as cópias de segurança e quem consulta a base de dados. Quem opera o servidor ainda alcança a chave, e por isso o canal só abre com o aditivo de sigilo assinado.

## O que ele ainda não faz

O formulário público de relato, as páginas públicas que vão mostrar os textos das configurações, a página de acompanhamento, a sugestão do agente na triagem, a Rota Especial, as perguntas ao relator, os depoimentos, o voto, a ata, o dossiê e o Termo de Confidencialidade e Posse do membro chegam nas próximas entregas. Na apuração, o botão "ADICIONAR PESSOA A OUVIR" aparece bloqueado até os depoimentos chegarem. O item Comitê de Conduta do menu lateral abre a tela Membros; MINHA VEZ, Casos e Configurações abrem pelo endereço do Comitê de Conduta. Por enquanto ninguém relata pelo Canal: os relatos continuam chegando pela Ouvidoria.

## O que já foi decidido

- O canal só abre quando a primeira fase inteira estiver pronta, com o aditivo de sigilo assinado, o layout aprovado e o teste de anonimato feito por quem não desenvolveu.
- O super admin não lê caso, e o único super admin com papel no Canal só cadastra membros, a pedido do Comitê, e só com o perfil de cadastro de membros.
- Toda mudança na composição do Comitê é vista por todos os membros, para aparecer uma mudança que o Comitê não pediu.
- Os casos de conduta que já estão na Ouvidoria terminam lá; só os novos vão ao Canal.
- O protocolo é sorteado, para não contar os casos nem deixar buraco na fila quando um caso vai para a Rota Especial.
- Nada do Canal guarda o endereço, o aparelho ou a localização de quem relata.

## O que costuma virar Demanda

- Um membro do Comitê que não abre caso: costuma ser o Termo ainda não assinado ou a participação fora da vigência.
- O super admin que não consegue incluir membro: falta o perfil de cadastro de membros no cadastro dele.
- Pedido para o super admin ler um caso: não é atendido, por decisão da Diretoria.
- A página pública que não abre: o canal ainda está fechado.
- Pedido para apagar um registro de acesso: não existe; o registro não se apaga.
- Pedido para tirar o prazo vencido de um caso: não existe; o vencido fica registrado mesmo depois da prorrogação.
- Pedido para prorrogar de novo um caso do rito Completo, ou prorrogar um caso do rito Rápido: o rito Completo prorroga uma vez só, e os outros não prorrogam.
- A coordenação que não consegue encerrar um Encaminhamento: costuma faltar a conferência do segundo leitor.
- Pedido para apagar ou corrigir uma versão antiga de um texto: não existe; salva-se uma versão nova, e a antiga fica.
- Pedido para publicar o Código de Conduta com vigência numa data passada: não existe; a versão nova vale de hoje ou de uma data futura, e a que valia antes continua valendo para os dias que já passaram.
- Pedido de um item novo nas configurações: entra por Demanda, porque a lista de itens é fixa.
