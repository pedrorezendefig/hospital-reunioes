---
title: O que vai para a página pública
description: O que sai do app quando a Demanda é ligada ao desenvolvimento, e o que nunca sai.
prd: [673, 1056]
draft: false
sidebar:
  order: 23
---

O trabalho de desenvolvimento da Vitta fica numa página que qualquer pessoa da
internet pode ler. Quando a Demanda é ligada a ele, parte do que está no card
passa a aparecer lá, para quem desenvolve ler o fio inteiro sem entrar no app.

## O que vai

- O título e o texto de quem pediu, no momento em que a Demanda é levada para o
  desenvolvimento.
- Cada resposta escrita na Conversa depois do Vínculo, como foi escrita.
- Quem tem login no GitHub aparece por esse login. Quem não tem aparece como
  "Pessoa do hospital".
- O link do card, que só abre para quem tem acesso ao app.

## O que nunca vai

- O nome de ninguém.
- Os prints. A página só diz quantas imagens a Demanda tem, e quem desenvolve
  vê as imagens pelo app.
- A prioridade, o prazo e o responsável.
- CPF, telefone e outros dados pessoais, que o app esconde antes de publicar.

Por isso, depois do Vínculo, a caixa de resposta do card avisa: "Esta resposta
também é publicada na página pública do pedido, fora do app. Não escreva dados
de paciente."

## Os prints apagam sozinhos

Os prints anexados à Demanda nunca saem do app e são apagados quando ela é
Concluída ou Cancelada. O card guarda só o registro de que existiram: o nome,
quem anexou e quando, marcado como apagado. Enquanto você confere uma entrega,
a Demanda está aberta e o print continua lá.
