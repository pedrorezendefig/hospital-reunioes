---
status: accepted
amends: 0050, 0054, 0077, 0083
amended_by: 0090, 0091, 0092, 0093
---

# Tecnologia: Entregas, documento do card, revisão com o código de hoje, apagar e demonstração

Decisão do Pedro (11/11/2026, grill no terminal em duas rodadas, todas as recomendações aceitas). A aba Tecnologia virou o chat do diretor com o agente (ADR 0077) e ganhou Responsável e a visão do Desenvolvedor (ADR 0083). No uso apareceram seis faltas. A tela ficou apertada, com quatro filtros espremidos e o menu fixo. O detalhe do card é um texto corrido, quase a fala do diretor transcrita. Não há como tirar da lista um card que não vale mais. Card planejado antes da ADR 0079, com teto de 12 perguntas, fica velho, e o código pode já ter andado por fora. O que o Desenvolvedor abre pelo terminal não aparece para o diretor. E ninguém vê o que foi entregue, quando subiu, nem um vídeo do que mudou.

## Decisões

1. **Um PRD no app, e a skill do vídeo à parte, no repositório do OS.** As frentes da aba (tela, apagar, revisão, cards do terminal, Entregas, demonstração no card) se cruzam e vão num PRD só, em fatias. A skill que gera o vídeo é ferramenta e vai num PR próprio no OS.

2. **Apagar.** O card some do app, com a conversa e os anexos. No GitHub, a issue-raiz e as partes fecham como "não planejada", com um comentário de motivo. A issue não é apagada de verdade: isso não tem volta, exigiria token com poder de administrador no app em produção (o de hoje só escreve issues) e levaria junto o histórico das decisões. Só se apaga até **Planejada**: em Em desenvolvimento já existe PR aberto. Quem apaga: o autor apaga a própria conversa Registrada; card criado, só o Desenvolvedor. Emenda a decisão 11 da ADR 0050 ("Nada se apaga"). Rejeitado: apagar a issue no GitHub; arquivar sem apagar.

3. **Revisar com o código de hoje.** Botão no card em Em análise ou Planejada, enquanto nenhuma parte está em desenvolvimento. Ele retoma a mesma conversa e a mesma issue. O agente relê a issue (corpo, comentários e o que mudou por fora), o código, as ADRs aceitas e o que subiu desde a data do card. Depois abre o **Retrato de hoje** em três blocos (Já existe, Mudou desde o card, Continua em aberto) e pergunta só pelas lacunas, sem teto. Todo item de "Já existe" diz a versão em que entrou e passa pelo "isso atende?" do diretor antes de sair do card. Nada sai em silêncio. "Atualizar o card" regrava o PRD na mesma issue, com um comentário do que mudou. Se o card já tinha partes não começadas, elas fecham como "não planejada" e o card volta para Em análise, para um novo `/to-issues`. Clicam o autor e o Desenvolvedor, com estimativa de custo e confirmação (ADR 0082), e a conversa registra quem respondeu cada turno. Rejeitado: conversa nova com issue nova (perde número e histórico); reescrita do PRD pelo agente sem conversa.

4. **Cards do terminal aparecem na aba.** Toda issue-raiz do app, PRD ou bug, ganha uma Demanda, com selo de **Origem**: "Pedido do diretor" ou "Vitta". Ferramenta e skills (`.claude/`, `tools/`, `docs/`) ficam de fora. A Demanda da Vitta não tem conversa com o agente; tem Etapa, documento e Conversa da Demanda. Emenda a decisão 3 da ADR 0077 (a aba tinha um sentido só) e a regra do glossário que evitava PRD criado pelo terminal. Rejeitado: label manual para mostrar ao diretor; mostrar todas as issues, ferramenta inclusive.

5. **Mesma tela para o diretor e para o Desenvolvedor.** Com `github_login`, ganha a mais o número, o link e o botão de apagar card criado, como já é a regra (ADR 0054, decisão 9; ADR 0083). Rejeitado: telas separadas.

6. **Tela.** O menu principal recolhe para só ícones, em todo o app, e lembra a escolha no navegador. A lista de conversas fica mais larga, com busca e filtros em chips (Tipo, Etapa, Origem, Responsável, Envio falhou), e recolhe quando o documento abre. **Ver a emenda de 11/11/2026 abaixo: os chips viraram uma barra de campos com rótulo.**

7. **Documento do card.** O detalhe deixa de ser texto corrido e vira um documento com seções fixas: Em uma frase, O que muda (até cinco tópicos), Partes (com Etapa e datas), Demonstração e Datas (criado, entregue, em produção). Durante o planejamento ele se monta ao vivo ao lado do chat, no molde da ata viva da Ata Guiada. Depois do card, é lido do GitHub. O bloco "Para o diretor" da issue ganha esse formato fixo e limite de tamanho, tanto no PRD do diretor quanto no `/to-prd` do terminal. Continua nunca digitado no app (ADR 0054, decisão 7). Rejeitado: só resumir o texto de hoje; documento editável à mão.

8. **Entregas.** Segunda aba dentro de Tecnologia ("Conversas" e "Entregas"), que conta por card, com as partes no detalhe. Mostra entregues por semana e por mês, a data de entrega (fechamento), a data em produção (Subida) e o Responsável. O histórico vem do que o `history.json` registra desde o primeiro deploy, e card antigo sem bloco aparece com "Descrição em preparação". Não é o Painel que a ADR 0077 aposentou nem o quadro por pessoa que a 0083 rejeitou. É retrato do que já foi entregue, não gestor de tarefa: ninguém move nada ali. Rejeitado: na Central de Comando; contar por fatia.

9. **Demonstração.** O vídeo nasce de um clique do Pedro, nunca da Subida. O botão "Gerar demonstração", no PedroOS, por card entregue (PRD ou bug), abre uma sessão no Claude Agents que roda o `/divulgar` (ADR 0045). No fim, a sessão grava na issue-raiz o marcador `<!-- demonstracao: <url> -->`, e o webhook que já existe leva o link da Vercel ao card, que ganha o selo "Tem demonstração". O GitHub segue fonte única, e o caminho vale também para card do terminal. Rejeitado: vídeo em toda subida (custo, ADR 0082); rota de automação nova no app.

10. **O diretor fica sabendo.** Sino e e-mail em dois momentos: quando o card entra **Em produção**, com o resumo do que entrou e para que serve, e quando a **demonstração fica pronta**. O resumo é montado do documento estruturado, sem IA. Rejeitado: só o sino; um aviso só no vídeo (card sem vídeo ficaria mudo).

## Consequências

- Aparece uma escrita nova no GitHub: fechar issue e partes como "não planejada", e regravar o corpo do PRD. O token do app continua só com Issues: write.
- A Demanda deixa de nascer só do chat, e a tabela ganha a origem. Precisa de migration.
- O formato fixo do bloco "Para o diretor" muda o `/to-prd` e o prompt do Planejamento da Demanda no mesmo PRD.
- O PRD lista os dois cards velhos, #1426 e #1427, como primeiro uso da revisão.

## Emenda de 11/11/2026: filtros por categoria e card completo (issue #1578)

Com os chips no ar, a lista continuou apertada. Eram dezesseis chips sem rótulo, sete só de Etapa, numa coluna de 22rem, e o card mostrava pouco e só ganhava contorno no hover. O Pedro pediu filtros separados por categoria, em cima, e cards com mais informação e mais ajuda para conversar. Grill no terminal, todas as recomendações aceitas.

1. **Barra de filtros em cima, na largura toda.** Fica acima da lista e do chat e recolhe junto com a lista quando a Demanda abre. Tipo, Etapa, Origem e Responsável são campos com rótulo, no padrão do Painel de Contas médicas. O recorte do Desenvolvedor (Para mim, Minhas, Todas) é um controle segmentado, porque um dos três está sempre escolhido. "Só envio falhou" é um interruptor, porque Envio falhou não é Etapa. "Limpar filtros" aparece só com filtro ativo e não mexe no recorte. Rejeitado: os chips agrupados com título (continuavam ocupando várias linhas); um botão "Filtros" que abre painel (esconde o que está filtrado).
2. **Card com contorno e com o que importa.** Borda sempre visível, data de abertura ("Aberto em 01/11, há 10 dias", pelo calendário do hospital), quem pediu e o Responsável com as iniciais, a Etapa em destaque e, no PRD, as partes numa barra. No hover e no foco o card se destaca e sobe um pouco; quem pede menos animação ao sistema não vê movimento.
3. **Conversar sem procurar.** O card tem o botão "Conversar", que abre a Demanda com a caixa da Conversa da Demanda em foco. Na tela larga, a Demanda aberta mostra a Conversa da Demanda numa coluna à direita, fixa na rolagem. Rejeitado: abrir a Demanda num modal, que esconde a lista e quebra o link direto do aviso do sino.

A aba Entregas segue com os chips. A contagem de mensagens não lidas no card fica de fora, porque pede backend.

## Emenda de 12/11/2026: o Desenvolvedor tira da lista o que não vale mais (issue #1637)

Na limpeza da aba, dois tipos de pedido não saíam da lista. A conversa Registrada antiga do diretor só o autor apagava. O card fechado como não planejado pelo GitHub antes de alguém apagar no app vai para Não será feita, e ali o Apagar recusava com 409. A decisão 2 muda em dois pontos:

1. **O Desenvolvedor também apaga a conversa Registrada de outra pessoa.** O autor continua apagando a própria, e quem não é Desenvolvedor segue sem apagar a conversa de outro.
2. **O card em Não será feita também se apaga, só pelo Desenvolvedor.** A issue-raiz já fechada não fecha de novo nem ganha um segundo comentário, e as partes ainda abertas fecham como não planejadas. O estado da raiz vem da issue, e não da Etapa, porque a label `wontfix` leva a Não será feita com a issue aberta.

Em desenvolvimento, Entregue e Em produção continuam recusados.
