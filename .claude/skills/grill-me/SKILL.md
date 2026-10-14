---
name: grill-me
description: 'Entrevista em rodadas que testa um plano ou uma ideia até chegar a um entendimento comum. Não grava nada (sem CONTEXT.md, sem ADR). Use quando a pessoa disser "grill me", "/grill-me", "me desafia", "testa esse plano" fora de um repositório ou quando não quer documentação. Para gravar glossário e ADRs, use grill-with-docs.'
---

Entreviste a pessoa sem dar trégua até chegar a um entendimento comum. Conduza em **pt-BR**. Esta skill **não grava arquivo nenhum**: nada de `CONTEXT.md`, nada de ADR. Se a pessoa quiser registrar as decisões, troque para `grill-with-docs`.

## Árvore de decisões

Monte o assunto como uma **árvore de decisões**: cada decisão abre as decisões que dependem dela.

Trabalhe a árvore em **rodadas**. A **fronteira** é o conjunto de decisões cujos pré-requisitos já estão fechados: as perguntas que dá para fazer _agora_ sem chutar respostas que você ainda não ouviu. Faça a fronteira inteira em uma rodada, com cada pergunta numerada e a sua recomendação. Depois espere as respostas.

Cada rodada respondida muda a árvore. Decisões fechadas empurram a fronteira para frente e liberam as perguntas que dependiam delas. Recalcule a fronteira e faça a próxima rodada. Uma pergunta que depende de outra ainda aberta nesta rodada fica para a rodada seguinte.

## Fatos são seus, decisões são da pessoa

Achar _fatos_ é trabalho seu, nunca da pessoa. Se uma pergunta precisa de um fato do ambiente (arquivos, código, ferramentas, documentação oficial), mande um subagente buscar. Não pergunte à pessoa nada que você consegue descobrir sozinho. Não trave a rodada por isso: só as perguntas que dependem daquele fato esperam. Faça o resto da fronteira agora.

As _decisões_ são da pessoa. Ponha cada uma para ela e espere.

## Formato da rodada

Regras fixas:

- Sem emoji. Sem travessão (nem o longo, nem o médio). Use vírgula, dois-pontos, parênteses ou ponto.
- Cada opção numa linha própria, uma embaixo da outra. Nunca duas opções na mesma linha.
- Toda pergunta fecha com uma linha "Recomendo:".
- Uma pergunta de sim ou não também lista duas opções: (a) a recomendada e (b) o contrário. Assim toda pergunta tem a mesma forma.
- Cada opção cabe em uma linha. O custo e o ganho vão no contexto, não dentro da opção.
- Escreva a pergunta de modo que "sim" aceite a recomendação.

Modelo de uma rodada:

```
**Rodada 1**

**P1. <título da pergunta>**

<uma ou duas frases de contexto: o que está em jogo e por que importa>

- **(a)** <primeira opção, o que ela quer dizer na prática>
- **(b)** <segunda opção>

**Recomendo:** (a). <uma frase com o motivo>

**P2. <título da pergunta>**

<contexto>

- **(a)** <opção>
- **(b)** <opção>
- **(c)** <opção, se houver>

**Recomendo:** (b). <motivo>

Responda só os números que quer mudar. O resto eu aceito como recomendado.
```

A numeração das perguntas continua entre as rodadas (P1 a P6 na rodada 1, P7 em diante na rodada 2). Assim "P4" aponta sempre para a mesma pergunta.

## Fim

A sessão termina quando a fronteira fica vazia: todo galho da árvore visitado, nada assumido em silêncio. Mostre um resumo curto das decisões, uma por linha. Não execute o plano até a pessoa confirmar que vocês chegaram a um entendimento comum.
