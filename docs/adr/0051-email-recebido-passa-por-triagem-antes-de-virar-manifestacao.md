---
status: accepted
amends: 0039
---

# E-mail recebido em ouvidoria@ passa por triagem antes de virar manifestação

Decisão do Pedro (09/set/2026, grilling a partir de duas dúvidas do diretor; PRD #646). O e-mail que chega em `ouvidoria@hospitalsaomatheus.com.br` passa a entrar no app, mas **não como canal aberto**: cai numa [Triagem de e-mail], onde o ouvidor decide se vira manifestação, se junta a um caso que já existe ou se é descartado. O transporte é uma cópia por regra de roteamento do Google Workspace para um subdomínio de recebimento do Resend, o mesmo processador que já entrega os e-mails do app.

## Contexto

- Hoje o canal `email` é registro manual: o ouvidor lê a caixa no Gmail e digita o caso. Nenhum ADR, issue ou nota de deploy tratava de e-mail de entrada. O diretor perguntou se a caixa já estava integrada e se dava para integrar.
- O formulário público e o QR (Canal aberto, ADR 0036) criam o caso direto, "em classificação", sem tipo e sigiloso por padrão (ADR 0037). Isso funciona porque o formulário tem honeypot, rate limit e campos definidos: quem chega ali quis manifestar.
- E-mail não tem nada disso. A mesma caixa recebe spam, newsletter, resposta de área, e-mail interno e a segunda mensagem de quem já tem protocolo. E manifestação, uma vez criada, **não se apaga** (ADR 0047): o que entrar errado fica na estatística para sempre.
- O ADR 0039 registrou que todo e-mail do módulo **sai** pelo Resend, fora do Brasil, e fechou campo a campo o que atravessa a fronteira. Ele não previa e-mail **entrando** pelo mesmo processador.
- Pesquisa em fonte primária (09/09/2026, docs do Resend e do Google Workspace): o Resend recebe e-mail por domínio inteiro via MX, e recomenda subdomínio; a Gmail API exige projeto no Google Cloud, delegação por super admin e renovação da escuta a cada 7 dias; IMAP exige senha de app que morre na troca de senha. O Google Workspace tem regra de roteamento pelo admin que copia o que chega num endereço para outro, sem verificação e sem depender do usuário da caixa.

## Decisões

1. **E-mail recebido não é Canal aberto. Passa pela Triagem de e-mail.** Cada e-mail vira um item de triagem que só o Perfil da Ouvidoria vê. O ouvidor tem três ações: virar manifestação, juntar a um caso existente, descartar. Nenhum e-mail vira caso sem esse ato. O motivo é o ADR 0047: o filtro tem de vir antes do que não se apaga.
2. **Virar manifestação abre o registro manual que já existe, pré-preenchido.** Canal `email`, T0 igual à data do e-mail (não a do clique, como já vale para telefone), nome e contato do remetente, corpo como relato, anexos do e-mail como anexos do caso. O ouvidor escolhe o tipo e salva: o caso nasce classificado, como o telefone hoje. Não se cria um segundo caminho de criação.
3. **Nada responde na chegada.** O único e-mail que o manifestante recebe é o acuse de recebimento do ADR 0042, que sai quando o e-mail vira caso, com protocolo. Resposta automática na chegada responderia a spam e a robô, abriria loop de auto-resposta e mandaria dois e-mails para a mesma pessoa. A contrapartida é operacional: a triagem tem de ser diária, e o e-mail novo acende o ponto de novidade da fila.
4. **Juntar a um caso existente grava Movimento, não estado.** A resposta ao acuse e a segunda mensagem sobre o mesmo protocolo são o gesto mais comum de quem reclama por e-mail. Juntar põe texto e anexos na trilha do caso, sem mudar estado nem prazo. Se o assunto traz o protocolo, o app sugere o caso; a escolha é do ouvidor.
5. **Descartado guarda só o cabeçalho.** Remetente, assunto, data, quem descartou e quando. Corpo e anexos são apagados. Item descartado não é manifestação, então o ADR 0047 não o alcança, e o corpo de um e-mail pode carregar nome, CPF e leito sem uso nenhum. O cabeçalho basta para responder "sumiu o e-mail de fulano, quem descartou?".
6. **O transporte é cópia por roteamento do Workspace mais Resend Inbound, num subdomínio do domínio que o app já controla.** O admin do Workspace do hospital cria a regra: o que chega em `ouvidoria@hospitalsaomatheus.com.br` vai também para `ouvidoria@inbound.hospitalsaomatheus.cloud`, com a caixa original continuando a receber. O subdomínio é verificado no Resend com MX próprio, e o Resend chama um webhook do app. O endereço público não muda, a caixa humana continua viva, e nada depende de senha, token, cron ou consentimento OAuth. O webhook valida a assinatura, deduplica pelo identificador do evento, e busca corpo e anexos pela API **na hora**, porque o Resend guarda o e-mail por 30 dias e depois apaga.

## Alternativas consideradas

- **E-mail como Canal aberto (vira caso direto)**: rejeitado. Spam e resposta interna virariam manifestação, e manifestação não se apaga.
- **Resposta automática na chegada**: rejeitado. Loop com robôs, dois e-mails para a mesma pessoa, e o acuse do ADR 0042 já cumpre o papel.
- **Gmail API (push ou polling)**: rejeitado por peça móvel. Projeto no Google Cloud, delegação por super admin e cron de renovação para uma equipe sem operação.
- **IMAP com senha de app**: rejeitado. Sessão curta e credencial que morre na troca de senha da caixa.
- **Trocar o MX do domínio do hospital para o Resend**: rejeitado. Sequestraria todo o e-mail do hospital, não só a Ouvidoria.
- **Encaminhamento configurado pelo usuário da caixa** (em vez de regra do admin): não descartado, é a reserva. Exige confirmar o endereço de destino por link, que chega no painel do Resend.

## Consequências

- O Resend passa a ser processador também do que **entra**. O corpo cru do e-mail do manifestante, com o que ele quis escrever, atravessa a fronteira de fora para dentro. O ADR 0039 fecha o que sai; este ADR registra que o que entra chega inteiro, e é o app que decide o que fica (decisões 2 e 5). O aviso de privacidade do hospital precisa citar o e-mail como canal que passa pelo processador.
- Cada e-mail recebido conta na cota do Resend (plano Free: 100 por dia, enviados e recebidos juntos). Conferir o plano antes de ligar a regra é pré-requisito humano.
- Dois passos são humanos e ficam fora do código: a regra de roteamento no admin do Workspace e a confirmação do plano do Resend. O PRD os registra como issues `ready-for-human`.
- O canal de origem `email` não muda de significado: continua sendo "chegou por e-mail e o ouvidor registrou". O que muda é que o registro agora nasce pré-preenchido.
- Ficam fora deste ADR, mas nasceram na mesma conversa: a aba de Ouvidoria no site do hospital (o sócio do Pedro implementa, o app entrega o kit) e a resposta padrão nas avaliações do Google apontando para essa página, enquanto o PRD #472 espera a API do Google. Os dois viraram tickets `task` no mapa das avaliações do Google (#616).
