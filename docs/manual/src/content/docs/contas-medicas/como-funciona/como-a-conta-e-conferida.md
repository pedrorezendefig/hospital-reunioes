---
title: Como a conta é conferida
description: Como o sistema junta conta e prontuário, conta as diárias, decide o que vai para validação e o que guarda da paciente.
prd: [1113, 1128]
draft: false
sidebar:
  order: 30
---

Preço, diária e quantidade são conta do programa: aritmética, contagem e busca
exata, nunca chute. A inteligência artificial lê o texto livre do prontuário e
propõe linhas, que o programa confere antes de chegarem ao guia: veja
[O que a IA lê e o que ela não decide](../o-que-a-ia-le-e-o-que-ela-nao-decide/).

## Conta e prontuário se encontram pelo atendimento

O sistema abre cada PDF, descobre se é conta ou prontuário e lê o número do
atendimento lá dentro. Os dois se juntam por esse número, mesmo que cheguem em
envios separados: por isso você não renomeia nada.

A operadora sai do plano impresso na conta, comparado com a lista de planos
cadastrados, sem diferença de acento nem de maiúscula. Plano sem cadastro é
recusado na hora, com o nome dele, e a conta nunca é conferida com a regra de
outra operadora.

Internação cobrada em parciais vira uma conta por parcial na fila, todas lidas
contra o mesmo prontuário.

## Parecer parcial

Às vezes o prontuário chega incompleto: falta um grupo de documentos que a capa
diz que existe, ele termina antes do fim do período da conta, ou tem muitas
páginas sem texto (digitalizadas). O guia sai mesmo assim, com a faixa
**PARECER PARCIAL** no topo e a lista do que faltou. O que depende do pedaço que
faltou pode não aparecer no guia.

## A linha Validar

Toda linha do guia se apoia numa regra da memória da operadora. Quando essa
regra ainda não foi validada pela diretoria ou pela gestão de contas médicas, a
linha não vira ordem: ela nasce **Validar**, sem botão, com o valor em jogo. A
decisão é de quem valida a regra, e por isso você não precisa decidir nada
nela.

## Como a diária é contada

A diária sai das movimentações registradas no prontuário: internação, troca de
setor, alta, óbito. A hora em que a diária vence e o que acontece de madrugada
vêm da memória da operadora (em geral, vence às 10h e é sempre integral).

Quando a troca de setor não tem hora exata, o sistema usa a janela entre o
último registro no setor antigo e o primeiro no novo. Janela toda antes ou toda
depois do vencimento segue a regra; janela que atravessa o vencimento vira
**Validar**, em vez de chute.

A diária cobrada é a da acomodação contratada, mesmo que o MV mostre outra.
Setor que o sistema não conhece também vira **Validar**.

Na UTI, a classe da diária sai do que o prontuário registra em cada dia.
Ventilação mecânica, monitorização invasiva, marca-passo ou droga vasoativa no
dia levam à classe mais alta que a memória da operadora liga a esse registro,
com a página e o trecho; sem nenhum deles, a classe mais baixa. Toda diária de
UTI termina com "Conferir classe de UTI".

## O que fica guardado da paciente

Nenhum nome completo fica guardado: só o primeiro nome com a inicial do
sobrenome (por exemplo, "Ana P.") e a idade. CPF, carteira, data de nascimento,
endereço e telefone são apagados antes de qualquer gravação.

Os PDFs da conta e do prontuário, e o texto tirado deles, saem do sistema sete
dias depois do envio. Ficam as linhas do guia, as suas marcações e o trecho
curto do prontuário que sustenta cada linha. Precisa do PDF de novo depois
disso? Exporte do MV e envie outra vez.
