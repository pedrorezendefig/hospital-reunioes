# Roteiro: O pedido chega explicado (PRD #1632)

Vídeo de percepção de valor do PRD #1632 (fatias #1633, #1634, #1635 e #1636), feito no Motion studio. A lista de tomadas completa está em `cena/docs/shotlist.md`.

## Briefing (skill `copy`)

- **Quem vê:** o diretor que pede melhorias e relata bugs na aba Tecnologia, no celular, entre uma reunião e outra.
- **O que deve pensar no fim:** explico uma vez e quem programa já recebe tudo entendido.
- **A única ideia:** o card que você cria chega explicado a quem vai programar, na hora.
- **A prova:** o card ganha a parte "Para o desenvolvedor" logo abaixo da do diretor, em seis partes (#1633); a conversa com o assistente não muda e a parte nova não aparece na tela do diretor (#1633); o bug ganha a mesma parte, com as mesmas perguntas (#1634); quem foi escolhido em "Quem cuida disto?" recebe um email com o pedido explicado e o link, e o card nasce mesmo se o email falhar (#1635); os pedidos que já estão na fila vão ganhar a parte, sem email e sem o diretor fazer nada (#1636).

## Ganchos

1. Situação: "Você explicou uma vez. Não precisa repetir."
2. Verdade incômoda: "Pedido mal entendido volta com pergunta."
3. **Começo no meio (escolhido):** "Card criado. Quem vai programar já sabe."

Escolhido porque abre no próprio clique do "Criar o card" com o email chegando: o primeiro quadro diz o mesmo que a fala, e funciona no mudo. A virada ("Quem programa começa já sabendo") responde a ele.

## Nota da copy

Gancho 2, uma ideia 2, ouvido 2, repetição 2 ("card" é o objeto, repetido de propósito; "parte" contrasta a sua com a nova), cena casada 2, virada 2, verdade 2 (todo fato vem das issues; "vão ganhar" porque a passada única ainda não rodou em produção, #1673). Total 14 de 14. Depois, o humanizer em modo embutido, com a página do PRD #272 como amostra de voz: o par de listas de três (partes 1 a 3 e 4 a 6) virou duas frases de formas diferentes.

## Narração final (`narracao.txt`, voz B)

Card criado. Quem vai programar já sabe. *(animada)*

Até agora, o card nascia em silêncio.

A conversa com o assistente continua igual. Você não escreve uma linha a mais.

No resumo, escolhe quem cuida disto e clica em Criar o card.

Sua parte segue no topo, como sempre.

Logo abaixo, entra uma parte nova, só pra quem vai programar.

Ela conta o que você quer e por que pediu.

Depois vem o que ficou decidido, onde mexer, os cuidados e quando está pronto.

Na hora, a pessoa escolhida recebe um email com tudo isso e o link.

Se o email falhar, o card nasce assim mesmo.

No bug, as perguntas não mudam, e o card ganha a mesma parte.

Os pedidos que já estão na fila também vão ganhar essa explicação. Você não faz nada, e ninguém recebe email por isso.

Você explica uma vez. Quem programa começa já sabendo. *(confiante)*

Respiros de silêncio depois dos trechos 2, 4, 8, 10, 11 e 12 (0,3 a 0,5 s), gravados em `tempos.json`.

## Cenas

| # | Fala | Tela capturada | Transição de entrada | Tempo (s) |
|---|---|---|---|---|
| 1 | Card criado. Quem vai programar já sabe. | resumo com a Marina Teles escolhida, clique em Criar o card, o email chega | abre no clique | 0,0 a 3,45 |
| 2 | Até agora, o card nascia em silêncio. | o Quadro, desbotado | recuo com perda de cor | 3,45 a 6,36 |
| 3 | A conversa com o assistente continua igual... | a conversa da melhoria com a pergunta em cartão | cortina vertical | 6,36 a 10,9 |
| 4 | No resumo, escolhe quem cuida disto e clica em Criar o card. | o resumo da melhoria, o seletor e o botão | empurrão lateral | 10,9 a 15,1 |
| 5 a 8 | Sua parte segue no topo... até quando está pronto. | o corpo do card: "Para o diretor" e, abaixo, as seis partes do "Para o desenvolvedor" | íris a partir do botão | 15,1 a 29,8 |
| 9 | Na hora, a pessoa escolhida recebe um email... | o email do card novo | cartão que gira | 29,8 a 33,5 |
| 10 | Se o email falhar, o card nasce assim mesmo. | a confirmação depois do Criar o card | zoom através | 33,5 a 37,1 |
| 11 | No bug, as perguntas não mudam... | o resumo do bug e o corpo do card do bug | persiana | 37,1 a 41,6 |
| 12 | Os pedidos que já estão na fila... | o Quadro com os pedidos abertos | janela que abre | 41,6 a 49,1 |
| 13 | Você explica uma vez... | o resumo da diretora e o email lado a lado | lados opostos | 49,1 a 53,2 |
| 14 | (assinatura) | logo do Hospital São Matheus, inteira e parada | cortina branca | 53,2 a 56,8 |

Parada planejada: só a assinatura (54,3 a 56,8 s).

## Telas

Capturas em `capturas/`, do app local com o código da v0.275.0 e dados fictícios (Helena Prado, Marina Teles, Caio Brandão, Demandas 34 a 39). O email (`07`) é o template real, gerado por `enviar_card_novo` com o envio trocado por uma função que só guarda o HTML. O corpo do card (`08`, `09`) é o texto de `corpo_do_prd_do_diretor` e `corpo_da_issue_do_bug`, mostrado como Markdown do GitHub. Nada foi enviado nem gravado no GitHub.
