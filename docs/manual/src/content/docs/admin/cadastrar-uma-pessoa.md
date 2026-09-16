---
title: Cadastrar uma pessoa
description: Criar a ficha de alguém na plataforma e escolher o perfil de acesso dela.
prd: [731]
draft: false
papel: [Só admin]
sidebar:
  order: 2
---

## Quando usar

Quando alguém novo vai usar a plataforma, ou quando você precisa que a pessoa
exista no cadastro para ser citada numa ata e receber pendências. Só o Super
Admin abre esta tela.

## Passo a passo

1. Na barra da esquerda, em **Pessoas**, clique em **Usuários**.
2. Clique em **Novo Usuário**, no alto à direita.
3. Escolha o **Perfil de acesso**: **Regular**, **Secretária** ou
   **Super Admin**. Cada opção traz embaixo a frase do que ela alcança.
4. Preencha **Nome completo** e **Email**. Os dois são obrigatórios e o email
   não pode se repetir.
5. Preencha **Cargo** e, se quiser, **Setor** e **Área**. Os campos sugerem o
   que já está cadastrado, e aceitam texto novo.
6. Clique em **Criar**. Aparece **Usuário criado com sucesso**.

![Formulário Novo usuário com o perfil de acesso, o nome, o email e o cargo preenchidos](../../../assets/admin/novo-usuario.png)

A pessoa ainda **não consegue entrar**: a ficha existe, a senha não. O passo
seguinte é [Entregar o acesso a uma pessoa](../entregar-o-acesso-a-uma-pessoa/).

## Se der errado

- **A gravação foi recusada por causa do email:** já existe alguém cadastrado
  com esse endereço. Procure a pessoa na busca da lista antes de criar de novo.
- **O campo Cargo virou opcional sozinho:** você marcou **Secretária**. Para
  esse perfil o cargo não se aplica, e o campo **Role** some do formulário.
- **A pessoa diz que a senha não funciona:** ela nunca recebeu uma. Toda ficha
  nova nasce com uma senha que ninguém vê.
