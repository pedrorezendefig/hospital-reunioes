---
title: Dar acesso aos POPs e à Ouvidoria
description: Conceder ou revogar os dois acessos que não dependem do perfil de acesso.
prd: [731]
draft: false
papel: [Só admin]
sidebar:
  order: 5
---

## Quando usar

Quando alguém vai cuidar de procedimentos ou de manifestações. Os dois acessos
são independentes do Perfil de acesso: nem o Super Admin abre a área de POPs
nem o caso da Ouvidoria sem eles.

## Passo a passo

1. Em **Usuários**, ache a pessoa e clique no lápis, **Editar**. Os dois blocos
   só aparecem ao editar, nunca ao criar.
2. Em **Acesso aos POPs**, escolha **Superadmin**, **Gestor de Qualidade**,
   **Gerente** ou **Coordenador**. **Sem acesso** revoga.
3. Em **Acesso à Ouvidoria**, escolha **Ouvidor** ou **Diretoria Executiva**.
   **Sem acesso** revoga.
4. Escreva o **Motivo da alteração** e clique em **Salvar**.
5. Se a pessoa ainda não entrava na plataforma, a senha dela aparece agora, uma
   única vez. Copie antes de fechar.
6. Quem recebeu acesso aos POPs precisa ainda ter os **Setores da pessoa**
   marcados, na própria tela de POPs.

## Se der errado

- **O toast diz que parte dos dados foi salva e o acesso falhou:** os três
  blocos são gravados um a um. O que passou ficou, e a lista já mostra o estado
  real. Repita só o que falhou.
- **A tela recusa com "Pessoa sem email cadastrado":** o acesso cria o login, e
  login precisa de endereço. Preencha o **Email** na mesma janela e salve.
- **A pessoa vê a lista da Ouvidoria mas não abre nenhum caso:** a lista é de
  toda a equipe de Reuniões; abrir o caso exige **Ouvidor** ou
  **Diretoria Executiva**. Confira se ela não ficou em **Sem acesso**.
