---
title: A Etapa e o O que muda
description: Como o card sabe sozinho em que pé está o desenvolvimento, e de onde vem o texto do que a entrega muda.
prd: [673, 1056]
draft: false
sidebar:
  order: 22
---

A Etapa é o segundo eixo do card, ao lado da raia. A raia diz o que as pessoas
estão fazendo com o pedido; a Etapa diz o que o desenvolvimento já fez. Ninguém
digita a Etapa. O app a lê do trabalho da Vitta e a mostra como um selo.

## As sete Etapas

| Selo | O que quer dizer |
| --- | --- |
| **Registrada** | O pedido está no Quadro e ainda não virou trabalho. É a Demanda sem selo. |
| **Em análise** | Alguém da Vitta ainda vai olhar e decidir o que fazer. |
| **Planejada** | Já se sabe o que fazer, e o trabalho está na fila. |
| **Em desenvolvimento** | Alguém está construindo agora. |
| **Entregue** | Está pronto, mas ainda não chegou ao app que você usa. |
| **Em produção** | Já está no ar. O selo diz desde qual versão. |
| **Não será feita** | A Vitta decidiu não fazer e explica na Conversa. |

Quando o trabalho tem partes, o selo conta quantas já foram entregues, como
"3 de 7 partes".

## Como o app fica sabendo

O sistema de desenvolvimento avisa o app quando algo muda, em segundos. Quando
uma versão nova do app sobe, ela avisa quais trabalhos foram junto, e eles
viram **Em produção**. De hora em hora, o app confere de novo tudo que está
ligado, para nenhum selo ficar parado por um aviso perdido.

Quando a Etapa muda, a Conversa ganha uma linha sem autor, como "Etapa: Em
desenvolvimento". Se nada mudou, nada é escrito.

## O que muda

É o único texto do desenvolvimento que quem pediu lê: o que a entrega
acrescenta, em linguagem de quem usa, com a lista das partes e a situação de
cada uma. Ele vem do trabalho da Vitta, ou das suas decisões quando a Demanda
foi [planejada com a IA](../../planejar-a-demanda-com-a-ia/), e ninguém o edita
no app. Enquanto não foi escrito, o card mostra "Descrição em preparação".
