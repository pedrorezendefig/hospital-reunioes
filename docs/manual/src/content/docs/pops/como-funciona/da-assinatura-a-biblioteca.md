---
title: Da assinatura à Biblioteca
description: O que o sistema faz sozinho depois da validação, e o que acontece quando uma assinatura não sai.
prd: [76]
draft: false
sidebar:
  order: 22
---

## O envio é automático

Não existe botão de "enviar para assinatura". No instante em que o Validador
clica em **Aprovar validação**, o sistema monta o documento oficial da Versão e
o envia para as três pessoas do POP assinarem por email, na ordem
institucional: quem elaborou, quem revisou, quem validou.

Se a mesma pessoa acumula dois papéis, ela assina uma vez só.

## O que a Versão faz enquanto isso

Ela fica em **Em Assinatura**. O conteúdo está travado: ninguém edita, nem quem
elaborou. Na lista, o botão da linha vira **Ver**, e o documento pode ser lido
e baixado por quem tem o Setor no escopo.

Assinaram os três, a Versão passa a **Publicado**, ganha a data de publicação e
aparece na Biblioteca com o documento assinado.

## Quando a assinatura não sai

O envio depende de cada pessoa ter email no cadastro. Faltando um, o documento
não sai e a Versão fica parada em **Em Assinatura**, esperando.

Nesse caso o caminho é avisar o Superadmin: ele corrige o cadastro e o
documento é enviado de novo. A Versão não volta para trás e nada do que já foi
aprovado se perde.

## O POP vencido não sai da Biblioteca

Procedimento com prazo de revisão vencido continua publicado e continua
acessível. Tirar da Biblioteca deixaria a equipe sem referência nenhuma, que é
pior do que uma referência antiga.
