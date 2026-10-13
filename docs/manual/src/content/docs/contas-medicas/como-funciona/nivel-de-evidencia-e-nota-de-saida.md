---
title: Nível de evidência e nota de saída
description: Quanto o prontuário prova cada linha, como entra o remédio "se necessário" e o que a nota de saída mede.
prd: [1128]
draft: true
sidebar:
  order: 32
---

## O nível de evidência

Toda linha que inclui um item diz quanto o prontuário prova que ele foi usado.
O nível aparece em **Ver evidência**:

- **Registrado**: o prontuário registra o uso (checagem, dispensação,
  evolução citando a dose, balanço hídrico ou ficha anestésica).
- **Prescrito**: só a prescrição mostra o item.
- **Prescrito SN**: remédio "se necessário" sem nenhum registro de uso.
- **Por regra**: a linha sai de uma regra da memória da operadora, como a
  diária.

No **Painel**, o R$ incluído por nível mostra quanto do valor depende só da
prescrição.

## O remédio "se necessário"

Ele entra sempre no guia. Com registro de uso no dia, a linha inclui as doses
dadas, nível **Registrado**. Sem nenhum registro, inclui uma dose por dia de
prescrição, nível **Prescrito SN**, com a etiqueta amarela **SE NECESSÁRIO ·
SEM REGISTRO NO MV** e o texto "Confira a checagem em papel. Sem uso, marque
NÃO PROCEDE." Essa quantidade é provisória: a memória da operadora pode
mudar.

Não entra o dia em que o remédio foi suspenso ou alterado, nem dia depois da
alta. Na operadora de diária global, só entra o que é cobrado à parte.

## Nota de entrada e nota de saída

A **Nota de entrada**, de 0 a 100, diz quanto a conta estava certa antes da
sua correção: quanto mais R$ o guia aponta, menor a nota. Na conclusão, ela é
refeita sem as linhas **Não procede**.

A **Nota de saída** só existe quando você reenvia a conta corrigida. É a mesma
conta, feita sobre a conta nova e só com as linhas **Feito** que continuam
**ainda na conta**. Tudo corrigido no MV, a nota de saída é 100.

O **Painel** conta a nota de entrada, na semana em que a conta foi concluída:
o reenvio não muda o Painel nem a sua produção.
