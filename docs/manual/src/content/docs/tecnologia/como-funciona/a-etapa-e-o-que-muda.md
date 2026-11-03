---
title: A Etapa e o O que muda
description: Como a lista sabe sozinha em que pé está cada pedido, e de onde vem o texto do que a entrega muda.
prd: [673, 1056, 1380]
draft: true
sidebar:
  order: 23
---

A Etapa diz o que o desenvolvimento já fez com o seu pedido. Ninguém a digita:
o app a lê do trabalho da Vitta e a mostra na lista ao lado da conversa.

## As sete Etapas

| Etapa | O que quer dizer |
| --- | --- |
| **Registrada** | A conversa ainda não virou card. Clique nela para continuar. |
| **Em análise** | A Vitta está entendendo o que precisa ser feito. |
| **Planejada** | Já se sabe o que fazer, e o trabalho está na fila. |
| **Em desenvolvimento** | Alguém está construindo agora. |
| **Entregue** | Está pronto, mas ainda não chegou ao app que você usa. |
| **Em produção** | Já está no ar. A lista diz desde qual versão. |
| **Não será feita** | Decidiu-se não fazer. |

Quando a entrega tem partes, a Etapa conta quantas já foram entregues, como
"1 de 2 partes".

## Como o app fica sabendo

O desenvolvimento avisa o app quando algo muda, em segundos. Quando uma versão
nova do app sobe, ela avisa quais trabalhos foram junto, e eles viram
**Em produção**. De hora em hora, o app confere de novo tudo que já foi para a
Vitta, para nenhuma Etapa ficar parada por um aviso perdido.

## O que muda

É o texto que você lê ao abrir um pedido que já foi para a Vitta: o que a
entrega acrescenta, em linguagem de quem usa, com a lista das partes e a
situação de cada uma. Ele vem do planejamento da Vitta, ou das suas decisões
quando o pedido foi uma melhoria, e ninguém o edita no app. Enquanto não foi
escrito, aparece "Descrição em preparação".
