---
title: O que a IA lê e o que ela não decide
description: O que a inteligência artificial faz na conta, o que fica com o programa, por que toda linha tem página e trecho e quanto custa cada conta.
prd: [1128]
draft: true
sidebar:
  order: 31
---

A inteligência artificial (IA) lê o que o programa sozinho não alcança: o texto
livre do prontuário. Preço, diária e as contas da nota continuam com o
programa.

## As duas tarefas da IA

Primeiro, ela lê as evoluções, as anotações, as prescrições e a descrição
cirúrgica e lista o que aconteceu com a paciente, dia a dia, com a página e o
trecho que provam cada fato. Essa leitura é feita uma vez por atendimento e
serve a todas as parciais.

Depois, ela compara esses fatos com a conta e com a memória da operadora e
propõe linhas para o guia. É assim que entram os acessórios de cada medicação
(diluente, seringa, agulha, equipo), os insumos por tempo de terapia, os
materiais com limite que depende de uma condição, as taxas por dia e o bloco
do centro cirúrgico.

## O prontuário chega limpo à IA

Antes da IA, o programa arruma o texto:

- **Caixas marcadas.** Nos formulários (ventilação, oxigênio, via da dieta), o
  programa enxerga a caixinha ou o botão marcado e guarda só a opção escolhida.
  Antes, "Assistência ventilatória: Sim Não" chegava sem dizer qual.
- **Formulário em branco.** As linhas fixas dos formulários, que se repetem em
  toda evolução de fisioterapia, saem do texto desde o primeiro prontuário.
  Formulário novo ou alterado é aprendido: a linha que se repete em 8 de cada
  10 documentos do mesmo tipo sai a partir do terceiro prontuário.
- **Prescrição por coluna.** A prescrição é lida pela posição das colunas, e
  não pelo espaço entre as palavras: dose, unidade e frequência não se
  misturam. Sem as colunas, vale a leitura de antes.

## O que a IA não decide

A IA não devolve valor em reais, não conta diária e não mexe na nota. E nenhuma
linha dela chega ao guia sem passar pelo programa, que confere seis coisas:

1. A regra citada existe na memória da operadora. Se não existe, a linha cai.
2. A regra está vigente. Regra pendente vira **Validar**, nunca ordem.
3. O trecho está na página citada ou na vizinha. Se não está, a linha sai com
   a etiqueta **conferir evidência**.
4. O código existe na tabela da operadora. Se não existe, o valor sai como
   **Não conferido**.
5. O limite por dia é recalculado pelo programa.
6. A linha está dentro do período da conta. Se não está, cai.

Linha que repete o que o programa já tinha apontado fica uma só.

## Por que toda linha tem página e trecho

Para você conferir em segundos, sem abrir o prontuário inteiro. **Ver
evidência** mostra a página e o trecho que sustentam a linha, e o programa já
conferiu que esse trecho está lá.

## Quanto custa cada conta

Cada leitura da IA tem um custo, em dólar, guardado por conta, inclusive
quando a conta é analisada de novo. O **Painel** mostra o custo da semana e o
custo médio por conta. O reenvio da conta corrigida não chama a IA.

O texto vai à IA sem o nome da paciente, e o serviço de IA não guarda nada nem
usa o texto para aprender.
