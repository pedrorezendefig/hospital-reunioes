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

Quando há conta **A fazer** na **Fila**. A Fila é a mesma para todas as
faturistas, na ordem de envio. Deixe o guia aberto ao lado do MV: ele cabe em
meia tela.

## Passo a passo

1. Na **Fila**, clique em **Abrir** na primeira conta. Ela passa a ser sua e
   vai para **Minhas**, onde **Continuar** reabre o guia.

   ![Fila com o link Abrir na conta A fazer](../../../assets/contas-medicas/fila-abrir.png)

2. Leia o topo: **Nota de entrada**, **R$ a ajustar** e **Itens feitos**.
   Abaixo vêm as linhas, por dia e setor.

   ![Topo do guia com os três números e a primeira linha](../../../assets/contas-medicas/guia.png)

3. Clique no código da linha para copiar, corrija no MV e clique em **Feito**.
   Para conferir a origem, clique em **Ver evidência**.

   ![Linha do guia com o código, Ver evidência e o botão Feito](../../../assets/contas-medicas/guia-linha.png)

4. A correção não cabe? Clique em **Não procede**, escolha o motivo e clique em
   **Confirmar**. Se o MV não deixou lançar, clique em **Bloqueado**. Errou a
   marcação? Clique em **Desfazer**.

   ![Linha com os quatro motivos do Não procede](../../../assets/contas-medicas/guia-nao-procede.png)

5. A linha **Validar** não tem botão, porque o item já foi para a gestão decidir.
6. Clique em **Concluir e abrir a próxima**. A primeira conta livre da Fila
   abre e passa a ser sua. A **Observação para a gestão de contas médicas**
   vai junto.

   ![Rodapé do guia com a observação e o botão Concluir e abrir a próxima](../../../assets/contas-medicas/guia-concluir.png)

## Quando a linha pede conferência

- **SE NECESSÁRIO · SEM REGISTRO NO MV**: confira a checagem em papel; sem
  uso, marque **Não procede**.

  ![Linha se necessário com a etiqueta amarela e o texto para conferir](../../../assets/contas-medicas/guia-se-necessario.png)

- **conferir evidência** ou **Conferir classe de UTI**: confira o prontuário
  antes.

## Se der errado

- **Aparece "Outra faturista já pegou esta conta":** ela abriu antes. Volte em
  **Contas médicas** e abra a próxima da Fila.
- **Aparece "itens sem marcação. Concluir assim mesmo?":** ainda há linha
  aberta. Confirme para concluir com pendência, ou volte e marque.
- **O botão Confirmar está apagado:** falta o motivo. Em **Outro**, escrever o
  texto é obrigatório.
