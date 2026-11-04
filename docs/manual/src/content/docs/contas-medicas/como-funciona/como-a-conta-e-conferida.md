---
title: Como a conta é conferida
description: Como o sistema junta conta e prontuário, conta as diárias, decide o que vai para validação e o que guarda da paciente.
prd: [1113, 1128, 1397]
draft: true
sidebar:
  order: 30
---

O programa calcula preço, diária e quantidade por aritmética, contagem e busca
exata. A inteligência artificial lê o texto livre do prontuário e
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
diz que existe, ele termina antes do fim do período da conta, ou mais de 10%
das páginas ficam sem texto. O guia sai mesmo assim, com a faixa
**PARECER PARCIAL** no topo e a lista do que faltou. O que depende do pedaço que
faltou pode não aparecer no guia.

### Folhas digitalizadas

Algumas folhas do prontuário chegam escaneadas, como imagem, como a ficha
de anestesia preenchida em papel. O sistema lê
o texto dessas folhas e mede o quanto conseguiu: **legível**, **duvidosa** ou
**ilegível**. A folha ilegível conta como página sem texto. A folha impressa
escaneada de cabeça para baixo é virada e lida de novo.

Pelo título, o sistema sabe que documento é a folha e se ela pesa na
cobrança:

- Pesam: ficha de anestesia, folha de sala ou de consumo do centro
  cirúrgico, controle de fios, controle de OPME e etiquetas, horários
  cirúrgicos, uso de equipamento, descrição cirúrgica e prescrição escritas à
  mão, hemoterapia. A folha sem título reconhecido entra como
  **documento não identificado** e também pesa.
- Ficam de fora o checklist de cirurgia segura, o termo de consentimento, o
  receituário, a escala de risco, o eletrocardiograma, o documento pessoal, o
  boletim de internação, o laudo de exame e a guia da operadora.

Cada folha que pesa e não saiu legível, do período da conta, vira uma linha no
**PARECER PARCIAL**: "Confira à mão no prontuário a página 214 (ficha de
anestesia): é uma folha digitalizada que não consegui ler bem." Páginas
seguidas do mesmo documento vão numa linha só. É uma ressalva: o guia sai
normal, e você confere essas páginas no PDF do prontuário.

Quando as folhas ruins são as que sustentam a conta, ela para em
`CM-ARQ-DIGITALIZADO`: veja
[Quando a conta dá erro](../quando-a-conta-da-erro/#folhas-escaneadas-que-não-deram-para-ler).

## A linha Validar

Toda linha do guia se apoia numa regra da memória da operadora. Quando essa
regra ainda não foi validada pela diretoria ou pela gestão de contas médicas, a
linha nasce **Validar**, sem botão, com o valor em jogo. A decisão fica com
quem valida a regra, e você não precisa fazer nada nessa linha.

## Como a diária é contada

A diária sai das movimentações registradas no prontuário: internação, troca de
setor, alta, óbito. A hora em que a diária vence e o que acontece de madrugada
vêm da memória da operadora (em geral, vence às 10h e é sempre integral).

Quando a troca de setor não tem hora exata, o sistema usa a janela entre o
último registro no setor antigo e o primeiro no novo. Janela toda antes ou toda
depois do vencimento segue a regra. Janela que atravessa o vencimento vira
**Validar**, porque não dá para saber de que lado dele a troca aconteceu.

A diária cobrada é a da acomodação contratada, mesmo que o MV mostre outra.
Setor que o sistema não conhece também vira **Validar**.

Na UTI, a classe da diária sai do que o prontuário registra em cada dia.
Ventilação mecânica, monitorização invasiva, marca-passo ou droga vasoativa no
dia levam à classe mais alta que a memória da operadora liga a esse registro,
com a página e o trecho; sem nenhum deles, a classe mais baixa. Toda diária de
UTI termina com "Conferir classe de UTI".

## O que fica guardado da paciente

Da paciente ficam só o primeiro nome com a inicial do sobrenome (por exemplo,
"Ana P.") e a idade. CPF, carteira, data de nascimento,
endereço e telefone são apagados antes de qualquer gravação.

Os PDFs da conta e do prontuário, e o texto tirado deles, saem do sistema sete
dias depois do envio. Ficam as linhas do guia, as suas marcações e o trecho
curto do prontuário que sustenta cada linha. Precisa do PDF de novo depois
disso? Exporte do MV e envie outra vez.
