---
title: A Role que ninguém vê
description: O que é a etiqueta Role, por que ela só aparece nesta tela e o pouco que ela ainda decide.
prd: [731]
draft: false
sidebar:
  order: 21
---

## O que é

**Role** é uma etiqueta interna de administração, com quatro valores fixos:
`diretor`, `presidente`, `gerente` e `coordenador`. Ela vem da posição da
pessoa no hospital e existe desde o começo da plataforma.

Ela aparece em dois lugares, os dois dentro do painel de Usuários: a coluna
**Role** da lista e o campo **Role (cargo hospitalar)** do formulário. Em
nenhuma outra tela da plataforma ela é mostrada, e a própria pessoa nunca vê a
dela.

Essa invisibilidade é decidida, não esquecida. A etiqueta diz coisa sobre a
hierarquia de alguém, e o texto que identifica a pessoa para os colegas é o
**Cargo**, escrito por extenso. É o Cargo que aparece nas atas, nas pendências
e nas listas.

## Ela não é o que abre as telas

Quem decide o que a pessoa enxerga é o **Perfil de acesso**: Regular,
Secretária ou Super Admin. A Role não muda nada disso. Trocar a Role de alguém
não dá nem tira acesso a módulo nenhum.

## O pouco que sobrou

Dizer que a Role não faz nada seria errado. Ela ainda é consultada em três
situações, todas fora da área de Administração, e cada uma aceita uma lista
própria:

- apagar de vez uma reunião que ainda está programada, com **diretor**,
  **presidente** ou **gerente**;
- apagar a série inteira de uma reunião que se repete, com os mesmos três;
- cadastrar ou desligar uma pessoa pela porta antiga, fora do painel de
  Usuários, e aqui são só **diretor** e **gerente**: quem é **presidente** é
  recusado.

O Super Admin passa por cima dessas três checagens, e a Secretária tem regra
própria para reunião programada.

## O que isso significa na prática

Ao cadastrar alguém, escolha a Role que corresponde à posição real da pessoa,
porque ela ainda decide quem apaga reunião. O formulário começa em
**coordenador**, que é justamente o único dos quatro que não apaga nada. Mas não conte com ela para dar
acesso: isso é sempre o Perfil de acesso, ou os acessos de POPs e Ouvidoria.
Para a Secretária, o campo nem aparece, porque a função dela é de sistema e não
de organograma.
