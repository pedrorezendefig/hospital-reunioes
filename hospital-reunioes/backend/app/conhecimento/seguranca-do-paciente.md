# Segurança do Paciente

Segurança do Paciente é o módulo em que o Núcleo de Segurança do Paciente funciona dentro do aplicativo. Ele nasceu da especificação da Diretoria Executiva e entra em quatro fases: a primeira cuida da constituição do Núcleo (membros, documentos, capacitações, agenda regulatória) e das reuniões; a segunda traz a notificação de incidente, a triagem e os prazos; a terceira, a investigação e o plano de ação; a quarta, a notificação externa, os indicadores, o relatório mensal e o dossiê de inspeção.

O Núcleo continua recebendo os casos da Ouvidoria como hoje. O módulo é outra coisa: é onde o Núcleo trabalha.

Toda Demanda sobre o item Segurança do Paciente do menu, sobre quem vê o quê no módulo ou sobre uma tela do Núcleo pertence a este Produto.

## O que já está no ar

A notificação de incidente:

- qualquer profissional notifica um incidente pelo celular ou pelo computador, sem login, em quatro telas curtas: o que aconteceu (com as próprias palavras, com o aviso de não escrever o nome do paciente e o campo opcional de leito ou atendimento), onde e quando (setor, data, que vem com hoje, turno e, se quiser, a hora aproximada), se o paciente foi atingido (não chegou, chegou sem dano, chegou com dano ou não sei; com dano ou não sei, pergunta se foi grave ou se houve morte; e, se quiser, se a família ou o paciente percebeu ou se há risco de reclamação) e a identificação. Quem notifica conta o que aconteceu e não classifica nada. Toda tela traz, no rodapé, "Notificar não gera punição" e, no topo, uma linha dizendo o que fazer ali;
- na primeira tela, quem notifica pode anexar até três fotos ou PDFs, somando menos de 9 MB. A foto grande é reduzida no próprio celular antes do envio. O quarto arquivo, o tipo que não é foto nem PDF e a soma acima do limite são recusados com a explicação na tela. Os arquivos ficam guardados em lugar fechado e só abrem para quem abre os casos do Núcleo, pelo próprio aplicativo; o super admin sem o Acesso pleno não abre. O nome original do arquivo não é guardado, e nenhum anexo vai para a inteligência artificial;
- há três portas para o mesmo formulário: o QR do Núcleo, o endereço da página (que a TI usa para criar o ícone nos computadores do hospital) e o botão **Notificar incidente**, dentro do grupo Segurança do Paciente do menu. Cada notificação guarda por qual porta chegou. Não há atalho no topo do aplicativo;
- o QR e o endereço ficam no item **Configuração**, dentro do módulo, na seção "QR e endereço da notificação", que só aparece para quem abre a Configuração: a Presidência e o Acesso pleno. O botão **Baixar o QR** baixa a imagem do QR, boa para o cartaz e para o papel de parede; o endereço completo da página aparece em texto, com o botão **Copiar**, para a TI criar o ícone nos computadores. A seção é só de leitura: não há nada para editar. O ícone nos computadores é criado pela TI do hospital, fora do aplicativo;
- pelo botão do módulo, a identificação já vem preenchida com o nome e o e-mail da conta, sem digitar;
- a identificação vem marcada como "Com o meu nome", com a explicação de que o nome aparece só para a Presidência do Núcleo e o Diretor Executivo. Quem escolhe "Sem me identificar" não deixa nome nem contato;
- ao enviar, a pessoa recebe o protocolo na tela, no formato NSP-2026-0001, numa sequência que recomeça a cada ano. Quem notificou sem se identificar recebe também um código de acompanhamento, mostrado uma vez só: o aplicativo não guarda o código, e ninguém consegue recuperá-lo depois. O aplicativo não guarda o endereço de internet nem nada que identifique o aparelho de quem notificou;
- na página de acompanhamento, a pessoa informa o protocolo e o código (se notificou sem se identificar) ou o protocolo e o e-mail ou telefone que deixou, e vê só o estado, em palavras simples: Recebida, Em análise ou Concluída. Dado errado recebe sempre a mesma resposta, sem dizer qual parte errou;
- o formulário sem login aceita até 30 envios por minuto e 300 por hora de uma mesma rede. A conta é pela rede, sem guardar o endereço, e os computadores e o Wi-Fi do hospital saem pela mesma rede; acima disso o envio é recusado com o pedido de tentar mais tarde, e quem tem login pode notificar pelo botão **Notificar incidente**, que conta por pessoa (5 por minuto, 20 por hora);
- o item **Notificações**, dentro do módulo, lista todos os casos, do mais novo ao mais antigo, para quem abre os casos: a Presidência, o Acesso pleno e o membro com o Termo assinado. O nome e o contato de quem notificou aparecem só para a Presidência e o Acesso pleno; o membro vê o caso sem saber quem notificou;
- no alto de **Notificações**, o **Registro rápido** serve para o incidente que o próprio Núcleo encontra: a Presidência e o membro com o Termo assinado lançam, numa tela só, o relato, o setor, a data e a origem (busca ativa, ronda, reunião rápida de segurança, auditoria ou outra). Quem registrou fica como autor, com o nome e o e-mail da conta, e a notificação recebe o protocolo e segue o mesmo caminho de qualquer outra. O membro sem o Termo e quem é de fora do Núcleo não registram por aqui; notificam pelo botão **Notificar incidente**;
- nenhuma notificação é apagada, por ninguém: a correção é feita por edição, e cada edição fica registrada com quem fez, quando, o valor anterior e o novo;
- quando quem notifica marca "grave ou houve morte", a Presidência do Núcleo, o suplente vigente, quem tem Acesso pleno e a Diretoria Executiva recebem um e-mail na hora, cada um com o próprio nome, a qualquer dia e horário, inclusive de madrugada e no fim de semana. O alerta sai antes de qualquer triagem e não depende do agente nem de IA. O assunto começa por "Caso grave ou com morte", com o protocolo e a data e a hora do recebimento; o e-mail traz o protocolo, o setor e o link para Notificações, e nunca o relato;
- na página inicial do módulo, quem abre os casos vê em destaque, no topo, os casos graves ou com morte que ainda esperam a triagem, com o protocolo, o setor e a hora do recebimento;
- quem notificou com o nome e deixou um e-mail recebe na hora a confirmação de recebimento, com o protocolo e o link da página de acompanhamento, o que cumpre o prazo de 24 horas do Regimento. Quem notificou sem se identificar, ou deixou só telefone, não recebe e-mail. A confirmação também não traz o relato;
- o caso que a Ouvidoria manda ao Núcleo vira uma notificação de origem Ouvidoria, na mesma fila das outras, no momento em que o ouvidor confirma o envio. Ela traz o relato integral, o que a Ouvidoria apurou, o setor e quando foi, e não traz o nome nem o contato de quem manifestou, nem para a Presidência. Confirmar de novo não cria outra. O caso mostra o selo **Veio da Ouvidoria** com o estado da manifestação numa palavra (Recebida, Em análise, Respondida ou Encerrada). O e-mail que a Ouvidoria manda ao Núcleo abre o caso dentro do módulo, com login, e abrir o caso já marca o recebido na Ouvidoria, com o nome de quem abriu. O Núcleo não mexe na manifestação: ela segue o curso dela na Ouvidoria. Os casos que a Ouvidoria mandou antes disso não foram trazidos para o módulo;
- logo depois do envio, o agente de triagem do Núcleo lê a notificação e prepara uma sugestão de classificação pela norma: natureza, grau de dano, categoria e incidente, se é evento que nunca deveria ocorrer, IRAS, risco de imagem, protocolo básico, canal, faixa, justificativa, confiança em palavras e alertas. Ele só sugere: quem decide é a Presidência. A sugestão fica guardada com a versão do prompt, a versão da base de conhecimento e o modelo usados. Quem notificou não espera por ela: o protocolo já saiu antes;
- o agente não recebe o nome nem o contato de quem notificou, o leito ou atendimento, nem os anexos. O relato vai com os nomes e números pessoais trocados por marcadores. Relato que traz instrução dirigida ao agente (por exemplo, "ignore as regras") é classificado pelos fatos e ganha um alerta;
- a resposta do agente passa pelas regras de coerência da norma (natureza com dano, faixa, revisão campo a campo e canal). Resposta fora das regras é pedida de novo uma vez; se vier errada outra vez, a notificação entra na fila marcada "classificar manualmente". O mesmo acontece quando o agente está desligado ou não responde e quando passa do limite de 100 leituras por dia, que é do Núcleo e não divide conta com a Ouvidoria. A notificação nunca fica retida;
- o agente nasce desligado, e toda notificação entra para classificar manualmente até a Vitta rodar o teste de aceite com os 144 casos da Diretoria (três vezes cada) e as metas baterem: nenhum caso das faixas A ou B rebaixado e todos os eventos que nunca deveriam ocorrer de confiança alta reconhecidos. Toda mudança no prompt ou na base repete o teste;
- quando o agente acha que falta uma informação, ele propõe até duas perguntas curtas a quem notificou. Elas aparecem na tela de confirmação, depois que a notificação já está registrada e o protocolo já saiu, e nunca seguram o envio. Quem notificou responde em poucas palavras ou aperta **Responder depois**, que leva à página de acompanhamento: lá, com o protocolo e o código (ou o e-mail ou telefone que deixou), vê as perguntas que ainda não respondeu e pode responder. Sem pergunta do agente (inclusive com o agente desligado), a confirmação não mostra nada disso. Cada pergunta se responde uma vez. A resposta fica guardada com a pergunta; enquanto a triagem não foi confirmada pela Presidência, ela faz o agente ler a notificação de novo, com a resposta, e preparar uma sugestão nova, que fica guardada ao lado da anterior. A nova leitura conta no limite de 100 leituras por dia; sem vaga no dia, a sugestão anterior continua valendo. Depois da confirmação, a resposta só fica guardada e não chama o agente. A resposta vai ao agente sem o nome e o contato de quem notificou.

A fundação do módulo:

- o item **Segurança do Paciente** no menu lateral, com a página inicial do módulo (o item Visão geral, para não se confundir com o Início de cada pessoa), as Reuniões e o grupo Núcleo (Membros, Documentos, Capacitações e Agenda regulatória). Cada tela abre com uma linha dizendo o que fazer ali;
- os itens Auditorias de adesão, Gestão de riscos e Comissões, que aparecem no menu desabilitados, com o selo "Em breve" e uma explicação do que vão fazer;
- o Núcleo criado como o primeiro colegiado do hospital, ainda sem nenhum membro: a composição é cadastrada pela tela;
- a tela **Membros**, com uma linha por membro (papel, área, conselho e registro, vigência, estado e situação do Termo). A Presidência e o Acesso pleno cadastram, editam, renovam a vigência, mudam o papel e encerram a participação. Os demais que abrem a tela só leem;
- o cadastro de pessoas com conselho profissional, número de registro e UF;
- o Acesso pleno ao NSP, marcado no cadastro da pessoa pela área administrativa.

O Termo de Adesão:

- ao cadastrar um membro, o aplicativo gera um documento só, com o Termo de Adesão preenchido (nome, cargo, setor, conselho, número do registro e UF, papel e vigência) e, no fim, o texto inteiro do Regimento vigente. O documento vai por e-mail para a assinatura eletrônica, com um signatário só: o próprio membro. Sem Regimento publicado em Documentos, o cadastro fica feito, o membro fica em Cadastrado e a tela avisa para publicar o Regimento;
- quando o membro assina, ele fica Ativo sozinho, sem ninguém mexer, e o Termo assinado entra em Documentos como o Termo daquele membro e daquela vigência;
- renovar a vigência ou mudar o papel de um membro gera um Termo novo, com a vigência e o papel de agora e o Regimento vigente, e o manda para assinatura. Quem já tinha o Termo assinado continua no estado em que estava até assinar o novo, seguindo as datas da vigência e a carência. Cada Termo assinado entra em Documentos, um por membro e por vigência;
- na seção de cada membro com Termo à espera da assinatura, inclusive o Termo novo de quem já tinha assinado, a Presidência e o Acesso pleno têm três botões: **Reconsultar status da assinatura** (para quando a assinatura foi feita e o aplicativo não ficou sabendo), **Reenviar o Termo** (cancela o link anterior e manda um documento novo, com outro número) e **Liberar sem assinatura** (exige justificativa, que fica registrada com quem liberou e quando). A Diretoria não usa esses botões;
- quem está no Núcleo e ainda não assinou vê, nas telas bloqueadas, a faixa "Assine o Termo de Adesão para liberar este acesso", com o botão que abre o documento pendente.

Os avisos por e-mail:

- todo dia de manhã o aplicativo manda os avisos do Núcleo, um e-mail com o nome de cada pessoa, sem nada do conteúdo do Núcleo. O assunto diz o que fazer e traz a data por extenso, como 16/11/2026. No fim de semana e no feriado, o aviso espera o próximo dia útil e sai às 8h;
- Termo de Adesão: quando o documento é gerado, o membro recebe o aviso para assinar. Sem assinatura, ele recebe de novo com 3 e 7 dias, e com 14 dias o aviso vai para ele e para a Presidência. Assinado ou liberado sem assinatura, os avisos param. Reenviar o Termo recomeça a contagem pelo documento novo;
- vigência: 60 e 30 dias antes do fim, o membro e a Presidência recebem o aviso para renovar. Renovada a vigência, os avisos recomeçam pelo fim novo;
- fim da carência sem renovação: a Presidência e a Diretoria Executiva recebem o aviso para recompor o Núcleo;
- cada aviso sai uma vez só para cada pessoa. Se o aplicativo ficou fora do ar uns dias, sai só o aviso mais recente que ficou para trás (o de 7 dias, e não o de 3 e o de 7 juntos). Todo e-mail do Núcleo fica registrado antes de sair. Se o provedor de e-mail falha, o aplicativo tenta de novo depois de 5 e de 15 minutos; na terceira falha, o e-mail fica marcado como falha e o admin técnico do aplicativo é avisado. A pessoa sem e-mail no cadastro fica registrada como falha. Nenhuma falha impede os outros avisos do dia;
- participação encerrada não recebe aviso.

A tela Núcleo, Documentos:

- guarda o ato de designação, o Regimento, o Plano de Segurança do Paciente, o Termo, as atas e outros documentos do Núcleo, cada um com as suas versões;
- cada tipo tem uma única versão vigente, marcada na tela. As versões anteriores ficam na lista, embaixo da vigente, e continuam abrindo;
- o texto do Regimento fica guardado no aplicativo e é lido na própria tela, assim como o do Plano quando ele foi publicado com texto. Membro com o Termo assinado, Presidência e Acesso pleno leem;
- quem publica uma versão nova é a Presidência ou o Acesso pleno. A versão publicada passa a ser a vigente e a anterior vai para a lista;
- ao publicar uma revisão do Regimento, a Presidência escolhe se ela é material (muda o conteúdo) ou só de redação, e a escolha fica gravada e aparece na tela;
- publicar pelo botão Publicar não passa por assinatura;
- publicar uma revisão material do Regimento gera um Termo novo, já com o texto revisado, para todos os membros em Ativo, A vencer e Em carência, e o manda para assinatura. A revisão só de redação não gera Termo nem pede assinatura de ninguém;
- o ato de designação, o Regimento e o Plano de Segurança do Paciente também podem sair pelo botão **Enviar para assinatura**, no mesmo formulário. O ato de designação é assinado pela Diretoria Executiva (quem tem o Acesso pleno ao NSP); o Regimento e o Plano, pela Diretoria Executiva e pela Presidência do Núcleo. Cada pessoa recebe o documento por e-mail. Sem Presidência vigente, sem Diretoria Executiva cadastrada ou com alguém sem e-mail, nada é criado e a tela diz o que falta;
- a versão enviada aparece em Aguardando assinatura, com o nome de quem assina, quem já assinou e quando. Ela só vira a vigente quando todos assinam; até lá a anterior continua valendo, e o Termo de Adesão de quem for cadastrado sai com o Regimento que ainda vale;
- quando a última assinatura chega, a versão vira a vigente sozinha e o arquivo assinado fica guardado nela, com o selo Assinado. Membro com o Termo assinado, Presidência e Acesso pleno abrem o arquivo pelo botão **Baixar o arquivo assinado**;
- a revisão material do Regimento enviada para assinatura também gera o Termo novo, já com o texto revisado, para todos os membros em Ativo, A vencer e Em carência, uma vez só, quando a última assinatura chega e ela vira a vigente. Enquanto ela espera assinatura, ninguém fica com Termo pendente por causa dela;
- na versão que espera assinatura, a Presidência e o Acesso pleno têm os botões **Reconsultar status da assinatura** (para quando alguém assinou e o aplicativo não ficou sabendo) e **Reenviar para assinatura** (cancela o link anterior e manda outro). Mandar outra versão do mesmo tipo para assinatura cancela a que esperava.

As reuniões do Núcleo:

- o item **Reuniões** mostra o calendário das reuniões do Núcleo, mês a mês. Quem tem o Termo assinado clica na reunião e abre a ata; quem ainda não assinou vê a data, o tipo e o título, e não abre;
- a Presidência cria a reunião ali mesmo, à mão, num dos quatro tipos do Núcleo: ordinária mensal, análise de evento, apresentação à Diretoria e reunião rápida de segurança. A ordinária, a de análise de evento e a de apresentação à Diretoria seguem o caminho de sempre: transcrição, revisão e ata;
- a reunião rápida de segurança não tem transcrição, ata nem assinatura, e não conta quórum. Ao escolher esse tipo, a Presidência preenche a data, o setor, quem participou e um texto de até três linhas. A reunião aparece na lista com o tipo marcado e o setor no lugar do título. Quem tem o Termo assinado lê o texto e os participantes ali mesmo, na lista, sem abrir outra tela; quem ainda não assinou vê só a data, o tipo e o setor. Ela também não tem pauta, convocação nem presença;
- a Presidência gera o **calendário do ano** de uma vez: as doze reuniões ordinárias, uma por mês, no dia do mês e na hora que ela escolhe. Dia que cai em fim de semana ou feriado cadastrado vai para o próximo dia útil do mesmo mês. Pedir de novo no mesmo ano não duplica: o mês que já tem ordinária fica como está;
- a **pauta** da ordinária aparece 5 dias úteis antes da reunião, contando os feriados cadastrados, montada pelo aplicativo: as pendências da ordinária anterior, com a situação de hoje de cada uma, e os eventos da Agenda regulatória previstos até um mês depois da reunião. Os blocos de indicadores, casos, planos de ação vencidos e alertas sanitários aparecem como "sem dados nesta fase". Nos outros tipos de reunião, a pauta aparece desde a criação. A Presidência muda, tira e inclui itens e blocos enquanto a reunião está programada; quem tem o Termo assinado lê;
- a Presidência **convoca** em um clique: sai um e-mail nominal para cada membro Ativo, A vencer ou Em carência, com o dia da semana, a data e a hora, e o link para o módulo, sem o conteúdo da pauta. O aplicativo grava quem foi convocado e mostra a lista junto da pauta. A ordinária precisa ser convocada até o 5º dia útil antes da reunião; os outros tipos, até 24 horas antes. Fora desse prazo o aplicativo recusa e diz por quê. Cada reunião é convocada uma vez. A convocação sai na hora do clique, mesmo à noite; se o provedor de e-mail falha, o aplicativo tenta de novo sozinho e a lista passa a mostrar o e-mail como enviado quando ele sai;
- na reunião programada, a Presidência abre a **Presença** na própria lista e marca cada pessoa como presente, ausente, ausente justificado ou convidado. Convidado é quem não é do Núcleo e foi chamado para a reunião. O botão Presença só aparece para a Presidência e o Acesso pleno: os outros membros não veem a presença na tela;
- o aplicativo calcula o quórum: metade de quem conta para quórum no dia da reunião, arredondada para cima, com a Presidência ou o suplente presente. Conta para quórum quem estava Ativo, A vencer ou Em carência naquele dia. Com cinco membros, são três presentes. Convidado e ausente justificado não somam;
- sem quórum, a Presidência escolhe a nova data e a reunião fica como não instalada, não aceita transcrição nem ata, e a reunião reagendada nasce ligada à original, com o mesmo tipo e título. A situação "Não instalada" aparece na lista do Núcleo e na legenda do calendário;
- a **ata do Núcleo** tem os dez blocos do Regimento: identificação; presenças e quórum; situação das pendências da reunião anterior; indicadores; casos analisados; deliberações; plano de ação; alertas sanitários; próxima reunião; assinaturas. A IA escreve a minuta só quando a Presidência importa a transcrição na tela da reunião, e nenhuma rotina automática chama a IA. A tela da reunião do Núcleo mostra a ata nos dez blocos, no lugar das seções da ata comum;
- identificação, presenças e quórum, pendências da reunião anterior e indicadores vêm do aplicativo, e não da transcrição: o que a IA escrever sobre eles é descartado, e a tela marca esses blocos como "do sistema". Indicadores e casos aparecem como "Sem dados nesta fase.". As assinaturas listam os presentes;
- a ata não traz nome de paciente nem de profissional envolvido em caso, nem travessão. Se a minuta trouxer nome de membro fora da lista de presença, o aplicativo pede outra uma vez; se a segunda vier igual, a tela avisa e abre os blocos em branco para a Presidência redigir;
- na reunião de apresentação à Diretoria, a ata é a resumida: os mesmos dez blocos, com no máximo três itens em cada bloco escrito pela IA;
- quem importa a transcrição, revisa e valida a ata do Núcleo é a Presidência, o suplente em exercício (o suplente presente numa reunião em que a Presidência não estava) e o Acesso pleno: só para eles a tela mostra os botões Revisar e Validar a ata. Os outros membros leem a ata e veem "A Presidência revisa e valida esta ata.". Na reunião do Núcleo não aparecem os botões da ata comum (enviar para assinatura, finalizar sem assinatura, pedir correção);
- cada deliberação precisa de responsável e prazo para a ata ser validada. Ao validar, cada deliberação vira uma pendência da reunião, com o responsável e o prazo, e a ata fica marcada como validada;
- a ata validada vai por e-mail para a assinatura eletrônica de quem estava presente, e só deles: ausentes, ausentes com justificativa e convidados não assinam. O documento é a própria ata nos dez blocos. Se a assinatura eletrônica não responder na hora, a ata fica validada, a tela mostra o aviso e o aplicativo tenta de novo na manhã seguinte;
- a ata encerra sozinha 5 dias úteis depois do envio, contando os feriados cadastrados, com as assinaturas que tiver; se todos assinam antes, ela encerra na manhã seguinte. Ao encerrar, quem estava presente e não assinou fica registrado no bloco Assinaturas da própria ata, ao lado de quem assinou, e a reunião fica como assinada;
- se um presente recusa a assinatura ou o envio é cancelado no painel da assinatura eletrônica, a ata não encerra sozinha e a tela mostra o aviso. Para destravar, a Presidência usa **Reenviar para assinatura**, na tela da reunião: sai um envio novo para todos os presentes, e o prazo de 5 dias úteis recomeça a contar do reenvio. Quem já tinha assinado o envio cancelado assina de novo, porque o envio cancelado não vale como ata assinada;
- a ata encerrada entra em Documentos como ata, com o número seguinte das atas do Núcleo, e o arquivo assinado abre pelo botão **Baixar a ata assinada**, na tela da reunião. Só quem abre as atas do Núcleo baixa: o membro com o Termo assinado, a Presidência e o Acesso pleno. O super admin sem o Acesso pleno não baixa;
- a transcrição importada é apagada 30 dias corridos depois da ata assinada, por uma rotina diária. Isso vale só para as reuniões do Núcleo: a transcrição das outras reuniões do hospital fica como sempre ficou. A ata assinada é o registro que fica;
- a reunião do Núcleo some de todo o resto do aplicativo para quem não é do Núcleo: da lista de reuniões, do calendário geral, das pendências, dos números do painel, do sino e do que o Claude da diretoria consulta. Isso vale também para o super admin.

A Agenda regulatória do Núcleo:

- a lista única das obrigações que se repetem (notificação externa do mês, fechamento mensal, reunião ordinária, avaliações nacionais, avaliação da cultura de segurança, revisão do PSP e do Regimento, vencimento de vigência dos membros, recalibração do agente), cada uma com periodicidade, próxima data, link e quantos dias antes lembrar. A lista nasce com os eventos da especificação e com as datas em branco, para a Presidência marcar;
- a Presidência inclui, edita e desativa os eventos. Quem está no Núcleo, mesmo sem o Termo assinado, e a Diretoria só leem;
- quando a próxima data entra na antecedência, o aplicativo cria uma pendência para a Presidência, uma só por data. O lembrete não sai por e-mail: aparece no cartão do evento, na tela Agenda regulatória, com o número da pendência e o prazo. Ele não entra na tela Pendências, porque é assunto do Núcleo. Se a Presidência muda a data antes de registrar o resultado, o lembrete da data antiga é cancelado e um novo nasce para a data nova;
- depois de cumprir, a Presidência registra o resultado e a data em que fez. O resultado fica no histórico do evento, o lembrete é concluído e a próxima data é calculada pela periodicidade (mensal, anual ou a cada dois anos). Evento avulso fica sem próxima data até alguém marcar.

A tela Núcleo, Capacitações:

- mostra cada capacitação com título, data, carga horária, instrutor, público (membros do Núcleo ou profissionais), os temas tratados e a lista de participantes, com quem já confirmou a presença e quando;
- a Presidência e o Acesso pleno registram a capacitação pelo botão Registrar capacitação, escolhendo os temas tratados e os participantes. Os demais que abrem a tela só leem;
- quem está na lista de uma capacitação vê o botão **Confirmar minha presença** no cartão dela e confirma com um toque. O aplicativo grava a data e a hora. Ninguém confirma pelo outro, nem a Presidência;
- a seção Temas mínimos por membro mostra, para cada membro com participação vigente, quantos temas mínimos já cobriu e quais. Conta só a capacitação com presença confirmada: estar na lista sem confirmar não cobre o tema;
- a lista de temas mínimos fica no fim da tela. A Presidência e o Acesso pleno incluem, renomeiam e desativam os temas. A lista vem com os 17 temas mínimos do caderno nº 6 da ANVISA. Tema desativado sai da cobertura e da escolha no cadastro, mas continua aparecendo nas capacitações antigas.

O Núcleo no Início:

- quem é do Núcleo vê no Início, a tela de cada pessoa, o que o Núcleo espera dela: o Termo de Adesão que falta assinar, o ato de designação, o Regimento ou o Plano que espera a assinatura dela e a capacitação em que falta confirmar a presença, a partir do dia da capacitação;
- o item do Termo tem o botão Abrir o Termo de Adesão, que leva à tela Documentos, onde a faixa abre o documento pendente. O Termo sai do Início quando é assinado ou liberado sem assinatura, e o documento sai quando a pessoa assina;
- esses itens não têm prazo no Núcleo: ficam no grupo Sem prazo, no fim da lista, com há quantos dias esperam, e não contam como prazo vencido;
- a presença se confirma no próprio Início, pelo botão **Confirmar presença**, sem abrir outra tela: a linha sai e a frase e os números do topo se refazem;
- cada item só aparece para quem abriria a tela dele no módulo. Quem está no Núcleo sem o Termo assinado vê só o Termo; quem é de fora do Núcleo não vê nada do Núcleo, nem estando na lista de uma capacitação; o super admin sem o Acesso pleno também não vê nada do Núcleo no Início;
- os casos e a notificação ao Notivisa entram no Início quando as próximas fases do Núcleo forem ao ar.

## Quem vê

O item Segurança do Paciente aparece para todo usuário logado, com o botão Notificar incidente, inclusive para quem só tem papel nas Reuniões e para o super admin. As telas do Núcleo aparecem para quem tem participação vigente no Núcleo, para quem tem o Acesso pleno ao NSP e para a Diretoria. Os demais veem só o botão Notificar incidente.

Dentro do módulo, cada pessoa vê conforme o papel:

- **Acesso pleno ao NSP**: tudo, inclusive a configuração. É do Diretor Executivo;
- **Presidência do Núcleo**, com o Termo de Adesão assinado: tudo do módulo;
- **Membro do Núcleo** (ou suplente), com o Termo assinado: painel, calendário, agenda, membros, documentos, capacitações, reuniões e casos, sem a identidade de quem notificou;
- **quem está no Núcleo e ainda não assinou o Termo**: só painel, calendário e agenda;
- **Diretoria**: painel, calendário, agenda e a composição do Núcleo;
- **super admin do aplicativo**: só a configuração técnica do módulo, sem nenhum conteúdo.

Participação vencida, ou que ainda não começou, não dá acesso.

## Membros e estados

O estado de cada membro é calculado pelas datas e pela assinatura, e ninguém o edita à mão:

- **Cadastrado**: a participação existe e o Termo ainda não foi gerado;
- **Documento gerado** e **Aguardando assinatura**: o Termo saiu e espera a assinatura;
- **Ativo**: Termo assinado e vigência em dia;
- **A vencer**: faltam 60 dias ou menos para o fim da vigência;
- **Em carência**: até 30 dias depois do fim da vigência, para dar tempo de renovar;
- **Vencido**: passou a carência;
- **Encerrado**: a Presidência encerrou a participação.

Membro nunca é apagado. Encerrar termina a vigência no dia escolhido e a participação vai para o histórico, recolhido no fim da tela. Escolhendo uma data, a tela mostra quem compunha o Núcleo naquele dia, inclusive quem já saiu. Toda mudança (cadastro, edição, renovação, mudança de papel, encerramento) fica registrada com quem fez, quando, o valor anterior e o novo, e aparece na seção de cada membro. Uma pessoa tem uma participação aberta por vez: para voltar depois de encerrada, ela é cadastrada de novo.

## O que ele ainda não faz

Nas Capacitações, o profissional de fora do Núcleo que está na lista ainda não abre o módulo, então não confirma a presença por enquanto; a capacitação registrada também não se edita depois de salva. Nas reuniões, a ata própria do Núcleo também chega depois: por enquanto a ata segue o modelo das outras reuniões, e a pauta ainda não traz indicadores, casos, planos vencidos nem alertas, que dependem das próximas fases. Na notificação de incidente, ainda não chegaram a tela de triagem (a sugestão do agente já fica guardada, mas ainda não aparece na tela para a Presidência), os prazos e o encaminhamento a outro canal: a notificação fica registrada como Recebida até essas partes entrarem. As notificações criadas a partir da reunião rápida chegam na segunda fase. Os casos que a Ouvidoria manda ao Núcleo também chegam depois.

## O que já foi decidido

- O super admin do aplicativo não abre conteúdo do Núcleo e só chega à configuração técnica.
- Quem vê tudo é o Acesso pleno ao NSP, uma permissão dada pelo nome ao Diretor Executivo.
- A proteção é do aplicativo, e a Diretoria sabe que quem opera o banco de dados diretamente consegue ler.
- Presidência, suplente e membro vêm da participação vigente no Núcleo, com início e fim, e não de um perfil marcado à mão.
- Quem está no Núcleo sem o Termo de Adesão assinado vê só painel, calendário e agenda, até assinar.
- A reunião do Núcleo é vista por quem é do Núcleo, e não por quem foi incluído na lista de participantes: quem é de fora não a vê nem estando na lista, e o membro a vê mesmo sem estar.
- A reunião do Núcleo não aparece em nenhuma tela de quem é de fora, inclusive do super admin.
- Os dados dos membros não entram no aplicativo por carga automática: a composição é cadastrada pela tela, depois da entrega.
- Auditorias de adesão, Gestão de riscos e Comissões ficam no menu com o selo "Em breve", desabilitados, para quem usa já saber o que vem.
- Os títulos das telas do módulo ficam em caixa alta, na identidade do hospital.
- Nenhum documento do Núcleo é apagado nem editado: a correção é uma versão nova, e a anterior fica na lista com quem publicou e quando.
- O texto do Regimento entra pela tela, nunca por carga automática.
- A versão do ato de designação, do Regimento ou do Plano enviada para assinatura só vale depois que todos os signatários assinam.
- Revisão só de redação do Regimento não pede nova assinatura do Termo de Adesão; revisão material pede, de todos os membros em Ativo, A vencer e Em carência, quando passa a valer: pelo botão Publicar, na hora; pela assinatura, quando a última assinatura chega.
- O lembrete de cada obrigação é uma pendência da Presidência no aplicativo, e não um e-mail, criada por uma rotina diária que não usa inteligência artificial.
- A pauta é montada pelo aplicativo, sem inteligência artificial.
- A convocação vai só para quem conta para quórum, os membros Ativo, A vencer e Em carência.
- Os avisos do Termo e da vigência saem por uma rotina diária que não usa inteligência artificial, e cada aviso sai uma vez só.

## O que costuma virar Demanda

- Uma pessoa do Núcleo que não vê o item no menu: costuma ser participação com a vigência vencida ou ainda não cadastrada.
- Pedido para apagar um membro cadastrado por engano: não existe exclusão. A Presidência encerra a participação, que fica no histórico.
- Um diretor que pede para ver um caso: depende da fase e da faixa do caso, e o Acesso pleno é só do Diretor Executivo.
- Pedido para o super admin ler uma ata ou um caso do Núcleo: não é atendido, por decisão da Diretoria.
- Pedido da transcrição ou da gravação de uma reunião do Núcleo com a ata assinada há mais de 30 dias: ela já foi apagada, e o registro é a ata assinada, em Documentos.
- Um presente que não recebeu o e-mail para assinar a ata: costuma ser e-mail errado no cadastro. A ata encerra mesmo assim no 5º dia útil, e ele fica registrado como quem não assinou.
- Pedido para apagar um documento publicado errado: não existe; a Presidência publica uma versão nova corrigida, que passa a ser a vigente.
- Um membro que não abre a tela Documentos: costuma ser o Termo de Adesão ainda não assinado.
- Um Regimento ou Plano assinado por todos que continua em Aguardando assinatura: a Presidência usa Reconsultar status da assinatura na versão.
- Um membro que diz ter assinado e continua em Aguardando assinatura: a Presidência usa Reconsultar status da assinatura na seção dele.
- Um membro que não recebeu o e-mail para assinar: costuma ser e-mail errado no cadastro; corrigido o e-mail, a Presidência usa Reenviar o Termo.
- Uma reunião do Núcleo que alguém de fora diz não achar na lista de reuniões: é o sigilo funcionando, e a reunião está no módulo Segurança do Paciente.
- Pedido de ata ou de assinatura de uma reunião rápida de segurança: ela não tem ata. O registro é o texto de três linhas, que aparece na lista de reuniões do módulo.
- Um lembrete da agenda que não apareceu: costuma ser evento sem próxima data, evento desativado ou o Núcleo sem Presidência vigente.
- Um membro que diz não ter recebido a convocação: costuma ser Termo não assinado, vigência vencida ou cadastro sem e-mail.
- Um membro que diz não ter recebido o aviso do Termo ou da vigência: costuma ser cadastro sem e-mail, participação encerrada ou Termo já assinado.
- A Presidência que não consegue convocar a ordinária: passou do 5º dia útil antes da reunião, e o aplicativo diz qual era o último dia.
- Um membro que fez a capacitação e o tema não aparece como coberto: costuma ser que ele não confirmou a presença, ou que o tema foi desativado na lista.
- Pedido para a Presidência confirmar a presença de alguém: não existe; cada participante confirma a própria.
