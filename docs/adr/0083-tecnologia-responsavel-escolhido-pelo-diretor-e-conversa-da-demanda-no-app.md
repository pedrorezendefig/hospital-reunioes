---
status: accepted
amends: 0077
amended_by: 0084
---

# Tecnologia: o diretor escolhe o Responsável, o Desenvolvedor vê as Demandas de todos e a Conversa da Demanda volta, só no app

Decisão do Pedro (10/11/2026, grill no terminal em duas rodadas). A ADR 0077 reduziu a aba Tecnologia ao chat do diretor com o agente e tirou Responsável, Conversa, menções e e-mail. Oito dias de uso mostraram o que faltou do lado da Vitta: cada pessoa via só as próprias conversas, então o Pedro não enxergava os cards que o diretor criava nem a entrevista que os gerou; a melhoria nascia sempre designada ao Pedro e o bug a ninguém escolhido; uma falha na criação da issue virava um erro na tela e não ficava registrada; e não havia como responder ao diretor dentro da Demanda. Esta ADR devolve três coisas, e só três: o Responsável, a visão do Desenvolvedor e a conversa entre pessoas.

## Decisões

1. **Voltam Responsável, Conversa da Demanda e a visão do Desenvolvedor.** Prioridade, Prazo, Quadro, Painel, os sete Tipos e Produto com dono continuam aposentados. Emenda a decisão 1 da ADR 0077. Rejeitado: Painel ou Quadro com raias por pessoa (é o gestor de tarefas que a 0077 desmontou).

2. **Desenvolvedor não é perfil novo.** É o Super admin que tem login do GitHub no cadastro. A aba segue sem eixo de permissão próprio (ADR 0050). Hoje são três: Pedro Rezende, Pedro Rib e Lucas Sampaio. Rejeitado: perfil "Tecnologia" com permissão própria (eixo novo para três pessoas que já têm acesso).

3. **Mesma tela, com mais para o Desenvolvedor.** Ele vê as Demandas de todos, a entrevista inteira, o número e o link da issue e o estado do envio. A lista dele abre em "Para mim" e tem "Todas" e "Envio falhou", com autor e Responsável em cada linha. O diretor segue vendo só as Demandas dele, sem número nem link. Rejeitado: tela separada para desenvolvedores.

4. **A entrevista fica no app.** A issue leva um link para a Demanda, e não a conversa. Rejeitado: copiar a entrevista para a issue depois da peneira (o repositório é público e a fala crua do diretor não precisa estar lá para o Desenvolvedor ler).

5. **O diretor escolhe o Responsável antes de "Criar o card", e a escolha é opcional.** O Responsável é o dono do card no GitHub (o assignee), então o card cai na fila de quem foi escolhido. Sem escolha, bug e melhoria caem no Pedro, que repassa trocando o dono. O bug continua nascendo pronto para a onda, agora na fila do Responsável. Rejeitado: escolha obrigatória (o diretor nem sempre sabe de quem é, e travar a criação tira o canal dele); card sem dono até alguém assumir (não entra em nenhuma fila e some).

6. **Depois de criado, o Responsável é derivado do GitHub**, como a Etapa: troca-se lá e o app reflete. Rejeitado: trocar no app e gravar no GitHub (duas fontes, e risco de dois donos).

7. **Falha de envio fica registrada na Demanda.** "Envio falhou" guarda o motivo e aparece na lista; diretor e Desenvolvedor têm "Reenviar". Designação que falhou com a issue já criada aparece só para o Desenvolvedor, com "Designar de novo". A falha avisa os Desenvolvedores no sino. Rejeitado: reenvio automático pelo cron (se a primeira tentativa passou e só a resposta se perdeu, nasce issue duplicada no repositório público).

8. **A Conversa da Demanda vive só no app**, separada da conversa com o agente, com menção. Menção e mensagem nova avisam por sino e por e-mail. Sem menção, a mensagem do diretor avisa o Responsável e a do Desenvolvedor avisa o autor da Demanda. Emenda as decisões 1 e 3 da ADR 0077: a aba volta a ter os dois sentidos, mas só dentro de uma Demanda que o diretor abriu. Rejeitado: espelhar com os comentários da issue (o diretor não está no GitHub e a fala dele iria para o repositório público); só o sino (o diretor não fica com o app aberto).

9. **O card do diretor é reconhecível no GitHub.** A issue nasce com uma label de origem e, no topo, uma frase de resumo escrita pelo agente e passada pela peneira, em bug e em melhoria. O Hospital OS deriva daí o destaque, o aviso por voz e o resumo diário (ADR 0062): voz e destaque só para card designado a quem usa o OS; os dos outros Responsáveis entram no resumo do dia. Essa parte é uma issue no repositório do OS. Rejeitado: o app avisar o OS por chamada direta (o OS roda na máquina de cada um e a produção não o alcança); voz para todo card do diretor (aviso que toca por card alheio perde valor).

## Consequências

- O glossário da Tecnologia ganha Desenvolvedor, Responsável, Conversa da Demanda e Envio falhou; Responsável e Conversa da Demanda saem da lista de aposentados com definição nova.
- A Demanda precisa guardar o estado do envio e o motivo da falha, o que pede migration.
- A leitura de uma Demanda passa a conferir quem pede: autor ou Desenvolvedor.
- A label de origem entra em `docs/agents/triage-labels.md`.
- O Kit `tecnologia.md` muda no mesmo PR da tela.
