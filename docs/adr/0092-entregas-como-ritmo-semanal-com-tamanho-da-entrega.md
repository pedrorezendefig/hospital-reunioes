---
status: accepted
supersedes: 0091
amends: 0054, 0084, 0090
---

# Entregas como ritmo semanal, com Tamanho da entrega e o que cada entrega fez

Decisão do Pedro (13/11/2026, mesmo dia da ADR 0091, antes de qualquer fatia). Com o protótipo da 0091 na mão, o Pedro achou a tela cheia demais e com controle demais: tempo do card até a produção, Tempo na Etapa, Parados e números por pessoa dão ao diretor um instrumento de cobrança que não é o objetivo da aba. O que ele quer é sentir o ritmo, quantos pedidos chegam e quantas entregas saem por semana, e que qualquer pessoa entenda o que cada entrega fez. Esta ADR substitui a 0091 inteira e repete dela só a regra do PRD em Em desenvolvimento.

## Decisões

1. **A aba Entregas mostra o ritmo, não controla quem entrega.** No topo, dois números: pedidos e entregas das últimas 4 semanas, com a variação contra as 4 anteriores escrita em texto. Abaixo, o gráfico das últimas 12 semanas, com pedidos e entregas lado a lado. Embaixo, as entregas agrupadas por semana, a mais nova em cima, com "Ver semanas anteriores" no fim. Rejeitado: tudo o que a 0091 trazia de tempo e cobrança, ou seja, do card até a produção, Tempo na Etapa, Parados com prazo, tabela por Responsável e custo de IA; manter o seletor de período (a semana é a unidade da tela).

2. **Sem tabela de passagens.** Sem o Tempo na Etapa, nada mais lê as passagens, então saem a tabela, a migration e a reconstrução do passado pelo GitHub. Rejeitado: deixar a tabela gravando para um uso futuro que ninguém pediu.

3. **Tamanho da entrega: P, M ou G, pelas partes.** Até 1 parte é P, de 2 a 5 é M, 6 ou mais é G. Calculado do GitHub, nunca estimado nem digitado, como a Etapa e o O que muda. No gráfico, a barra de entregas da semana empilha G, M e P. Rejeitado: story points estimados no planejamento (ritual de estimativa que ninguém faz hoje); tamanho escolhido à mão no card.

4. **Expandir e recolher com o mouse.** Passar o mouse num número mostra a composição (bugs e melhorias; G, M e P). Passar o mouse numa barra mostra a prévia da semana, com os títulos e o tamanho de cada entrega; o clique filtra a lista para aquela semana e rola até ela. Passar o mouse numa entrega por 150 ms abre o O que muda e os links, uma por vez; o clique fixa. No celular, o toque faz o papel do mouse. Rejeitado: abrir só no clique.

5. **Cada entrega diz o que fez.** Recolhida, a linha mostra o Tamanho da entrega, o título, o tipo, a versão e o ícone de vídeo quando há Demonstração. Aberta, mostra o O que muda e três links: Demonstração (o link que o card já guarda, a página onde o vídeo toca), Abrir o card (o Documento do card) e Copiar link. Rejeitado: guardar também o link do vídeo à parte.

6. **O PRD não volta para Planejada** (repete a decisão 5 da 0091, emenda a decisão 3 da ADR 0054). Depois que a primeira parte começa, a Demanda fica Em desenvolvimento até a raiz fechar, mesmo entre uma onda e outra. A regra continua derivada, sem estado novo, e vale para o Quadro (ADR 0090).

7. **Mesma tela para todos e motion discreto.** Diretor e Desenvolvedores veem a mesma coisa. Os filtros de Tipo, Origem e Responsável que a aba já tem continuam. Números que sobem contando, barras que crescem em sequência e linhas que abrem com um deslize curto, tudo parado para quem pede menos movimento, com o `recharts` e animação em CSS.

## Consequências

- A 0091 passa a `superseded`. A 0083 volta a valer sem emenda: não há número por pessoa.
- O PRD da 0091 é reescrito na mesma issue, sem migration.
- O `CONTEXT.md` perde Vazão, Tempo na Etapa e Card parado, ganha Tamanho da entrega e redefine a Entregas.
