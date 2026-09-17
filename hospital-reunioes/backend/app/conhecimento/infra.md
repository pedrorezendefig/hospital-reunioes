# Infra

Infra é tudo que faz os sistemas ficarem de pé: os servidores onde o aplicativo roda, o banco onde os dados moram, os endereços na internet e os e-mails que o sistema envia. Ninguém do hospital abre uma tela de Infra; o sinal de que ela está bem é o resto funcionando.

Ela é um Produto da aba Tecnologia para que problema de disponibilidade, de acesso e de endereço tenha onde ser registrado, em vez de virar Demanda do módulo que por acaso estava aberto na hora.

## Onde as coisas rodam

O aplicativo do hospital roda num servidor alugado, com um painel que a Vitta usa para subir versão nova, ver o que está no ar e reiniciar quando precisa.

O banco de dados e o login dos usuários rodam no mesmo servidor, instalados e mantidos pela Vitta, e não contratados como serviço pronto de um fornecedor. A escolha foi deliberada, por causa do tipo de dado que o hospital guarda, e ela tem um preço: cópia de segurança, atualização e monitoramento são responsabilidade da Vitta, sem contrato de terceiro por trás para acionar.

## O que depende de empresa de fora

Algumas partes dependem de fornecedores, e isso importa quando alguma coisa para:

- **Assinatura digital** das atas e dos POPs, na ClickSign.
- **Envio de e-mail.** Todo e-mail do sistema sai por um serviço de entrega de terceiros, com servidores fora do Brasil. Vale inclusive para os e-mails da Ouvidoria, e o que viaja neles é uma lista fechada de informações, decidida uma vez: no caso comum estão nela o resumo, o relato integral e o nome de quem manifestou; em caso anônimo ou sigiloso sai só a nota da ouvidoria.
- **Agenda online**, do lado da Ana e também do aplicativo: é dela que vem o espelho da agenda na tela de Dados do Atendimento.
- **Inteligência artificial.** Um serviço único de fora está atrás de tudo que o aplicativo escreve ou entende com inteligência artificial: a ata por transcrição, a conversa da ata guiada, o ditado por voz que vira texto, a elaboração do POP e o assistente desta aba. Quando ele para, essas funções param. O relatório da Ouvidoria é o caso à parte: os números são medidos pelo aplicativo e saem do mesmo jeito, e o que depende dele ali é só a seção de sugestões de ação corretiva da edição mensal, que sai com um aviso no lugar quando ela não vem. Fora essa lista, nenhuma parte do aplicativo depende dele.

O hospital não opera servidor de e-mail próprio, e não há intenção de operar.

## Subir uma versão nova

Uma mudança aprovada vira uma versão nova, que a Vitta sobe. Enquanto sobe, a aplicação reinicia: quem estiver com a tela aberta pode precisar recarregar a página, e nada do que já foi salvo se perde.

Endereço novo na internet e mudança de configuração sensível são ato humano, feitos à mão e conferidos, e não sobem junto com a versão.

## O que ela não faz

- Não é uma tela: não existe painel de Infra dentro do aplicativo para o hospital olhar.
- Não tem contrato de disponibilidade de terceiro por trás do banco. Quem responde é a Vitta.
- Não guarda conteúdo de paciente fora do que os módulos já guardam.

## O que costuma virar Demanda

- Aplicativo fora do ar, lento ou reiniciando sozinho (Defeito).
- E-mail do sistema que não chegou (Defeito; ajuda dizer para qual endereço, e quando era para ter chegado).
- Endereço novo, ambiente novo, acesso novo para alguém de fora (Novo).
- Dúvida sobre onde os dados moram, sobre cópia de segurança ou sobre privacidade (Informação ou Consultoria).
