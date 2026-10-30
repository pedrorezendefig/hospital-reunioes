---
title: Corrigir uma conta pelo guia
description: Puxar a conta da Fila, corrigir no MV o que o guia aponta, marcar cada linha e concluir.
prd: [1113, 1128, 1303]
draft: true
papel: [Faturista]
busca: [boleto, fatura, pegar conta]
proximas: [devolver-uma-conta-a-fila, reenviar-a-conta-corrigida, ler-o-painel]
sidebar:
  order: 3
---

## Quando usar

Quando há conta **A fazer** na **Fila**, que é a mesma para todas as
faturistas. Deixe o guia ao lado do MV: ele cabe em meia tela.

## Passo a passo

1. Na **Fila**, clique em **Abrir** na primeira conta. Ela vira sua, em
   **Minhas**.

   ![Fila com o link Abrir na conta A fazer](../../../assets/contas-medicas/fila-abrir.png)

2. Leia o topo: **Nota de entrada**, **R$ a ajustar** e **Itens feitos**.
   As linhas vêm por dia e setor.

   ![Topo do guia com os três números e a primeira linha](../../../assets/contas-medicas/guia.png)

3. Clique no código da linha para copiar, corrija no MV e clique em **Feito**.
   **Ver evidência** mostra a origem.

   ![Linha do guia com o código, Ver evidência e o botão Feito](../../../assets/contas-medicas/guia-linha.png)

4. A correção não cabe? Clique em **Não procede**, escolha o motivo e clique em
   **Confirmar**. Se o MV não deixou lançar, clique em **Bloqueado**. Errou a
   marcação? Clique em **Desfazer**.

   ![Linha com os quatro motivos do Não procede](../../../assets/contas-medicas/guia-nao-procede.png)

5. Pule a linha **Validar**: quem decide é a gestão.
6. Clique em **Concluir e abrir a próxima**. A **Observação para a gestão de
   contas médicas** vai junto, e a primeira conta livre da Fila abre já como
   sua.

   ![Rodapé do guia com a observação e o botão Concluir e abrir a próxima](../../../assets/contas-medicas/guia-concluir.png)

## Quando a linha pede conferência

- **SE NECESSÁRIO · SEM REGISTRO NO MV**: confira a checagem em papel; sem
  uso, marque **Não procede**.

  ![Linha se necessário com a etiqueta amarela e o texto para conferir](../../../assets/contas-medicas/guia-se-necessario.png)

- **conferir evidência** ou **Conferir classe de UTI**: confira o prontuário
  antes.

## Se der errado

- **Aparece "Outra faturista já pegou esta conta":** volte em **Contas
  médicas** e abra a próxima da Fila.
- **Aparece "itens sem marcação. Concluir assim mesmo?":** confirme para
  concluir com pendência, ou volte e marque.
- **O botão Confirmar está apagado:** falta o motivo, ou o texto em
  **Outro**.
