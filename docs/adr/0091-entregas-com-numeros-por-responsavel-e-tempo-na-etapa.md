---
status: accepted
amends: 0054, 0083, 0084, 0090
---

# Entregas com números por Responsável, Tempo na Etapa e o PRD que não volta para Planejada

Decisão do Pedro (13/11/2026, grill no terminal em duas rodadas, todas as recomendações aceitas). A aba Entregas da ADR 0084 é uma lista de texto ("Semana de dd/mm: N") com os cards embaixo, sem gráfico. O Pedro pediu uma tela moderna, com motion discreto, para acompanhar a entrega: quanto o diretor pediu, quanto tempo cada card ficou em cada Etapa e os números de cada Desenvolvedor.

A ADR 0083 rejeitou "Painel ou Quadro com raias por pessoa", e a 0084 escreveu que a Entregas "não é o quadro por pessoa". As duas rejeitavam o gestor de tarefas que a 0077 desmontou: colunas por pessoa, card movido à mão. Números por pessoa, só de leitura, não movem nada. Esta ADR libera o corte por pessoa e mantém a rejeição das raias.

## Decisões

1. **A Entregas ganha números em cima da lista.** Vazão, tempo do pedido até a produção, Tempo na Etapa, cards em andamento por Etapa, cards parados e um gráfico de pedidos que chegam contra entregas por semana. Embaixo, a lista de cards de hoje. O nome continua Entregas. Rejeitado: taxa de Não será feita e issue reaberta (ruído com cerca de 20 Demandas); renomear para "Indicadores".

2. **O corte por pessoa é o Responsável da raiz.** O card inteiro conta para quem o diretor escolheu, numa tabela com uma linha por Responsável, e o filtro de Responsável vale para a tela toda. Rejeitado: quem pegou cada parte (dado novo, que depende de alguém pôr assignee em cada fatia); uma página por pessoa.

3. **Todos que veem a aba veem a mesma tela**, diretor e Desenvolvedores. O diretor já vê o Responsável e as datas em cada card; os números só somam isso. Rejeitado: esconder o corte por pessoa do diretor; tela só do Pedro.

4. **O Tempo na Etapa vem de passagens gravadas.** Uma tabela nova guarda cada mudança de Etapa com a data. O passado é reconstruído pela linha do tempo das issues no GitHub (labels, fechamento, PRs). Registrada conta da abertura da conversa até o "Criar o card". Rejeitado: só daqui para frente (o painel nasceria vazio); só os carimbos que já existem (não separam Em análise, Planejada e Em desenvolvimento).

5. **O PRD não volta para Planejada.** Emenda a decisão 3 da ADR 0054: depois que a primeira parte começa, a Demanda fica Em desenvolvimento até a raiz fechar, mesmo entre uma onda e outra. A regra continua derivada (alguma parte entregue ou em andamento, com a raiz aberta), sem estado novo. Vale também para o Quadro da ADR 0090. Rejeitado: manter o vaivém, que mostra "4 de 13 partes" em Planejada e quebra o Tempo na Etapa em pedaços.

6. **Pedidos do diretor.** Quantos pedidos por período, de que tipo, quantas partes cada melhoria gerou e o custo de IA do Planejamento da Demanda. Entram as Demandas das duas Origens, separáveis pelo filtro. Rejeitado: o tempo entre a primeira e a última pergunta (mede a agenda do diretor, não o esforço).

7. **Como os números se contam.** Mediana, e cada número abre os cards que entraram na conta. Dias corridos, e horas quando passou menos de um dia. Abre nos últimos 30 dias, com a variação contra os 30 anteriores escrita em texto, sem seta, e um seletor de semana, mês, trimestre e tudo. Card parado é o que passou do prazo da Etapa: Em análise 5 dias, Planejada 5, Em desenvolvimento 3; Registrada não conta, porque ali o ritmo é do diretor. Parado aparece só numa lista das Entregas, nunca no card do Quadro. Rejeitado: média (um PRD grande puxa sozinho); dias úteis (a onda roda no fim de semana); prazo ajustável na tela; selo de parado no Quadro.

8. **Visual com motion discreto.** `recharts`, que já está no app, com animação em CSS: números que sobem contando, barras que crescem e cards que entram em sequência, tudo curto e parado para quem pede menos movimento. O padrão visual é o do Painel de Contas médicas. Um protótipo com os números reais vem antes do PRD. Rejeitado: instalar `framer-motion`.

## Consequências

- Uma migration nova (a tabela de passagens) e a carga do passado lida do GitHub.
- A derivação da Etapa muda num ponto (decisão 5), e o Quadro passa a mostrar o PRD fixo em Em desenvolvimento.
- O `CONTEXT.md` ganha Vazão, Tempo na Etapa e Card parado, e a Entregas é redefinida.
