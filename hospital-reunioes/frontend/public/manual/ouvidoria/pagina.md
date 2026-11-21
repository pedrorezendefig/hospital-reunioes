---
modulo: ouvidoria
titulo: Ouvidoria
---

Aqui chegam as reclamações, sugestões, elogios e denúncias de pacientes, acompanhantes e colaboradores. A Ouvidoria confere cada caso, manda para o setor certo, cobra a resposta e devolve o desfecho a quem manifestou.

Quem é da Ouvidoria ou da Diretoria Executiva, a secretária e o Super admin veem a lista de todos os casos. O responsável do setor vê os casos do setor dele e responde por eles no app. Os outros não veem a Ouvidoria no menu. As tarefas abaixo são de quem tem o acesso de ouvidor ou da Diretoria Executiva, menos a de responder um caso, que é do responsável do setor.

## O caminho de uma manifestação

Passe o mouse num passo para ver o detalhe, ou clique em **Percorrer** para andar um passo por vez. Os prazos são os padrões da tabela da Diretoria, que pode mudá-los na tela **Prazos**. Eles correm de segunda a sexta, das 8h às 17h, sem feriados. Só o aviso de recebimento conta horas corridas.

```fluxograma
inicio chega 1,1: A manifestação chega | Pelo QR, pelo site, pela Ana, por e-mail ou pelo registro da Ouvidoria. Quem deixou contato recebe o aviso de recebimento em até 24 horas.
passo validar 2,1: Validar e acionar | A Ouvidoria confere o tipo, o setor e a gravidade e envia à área. Prazo para isso: 1 dia útil no caso médio, 4 horas úteis no alto e na hora no crítico.
passo area 3,1: A área responde | O responsável do setor recebe o e-mail e responde pelo link. Prazo: 4 dias úteis no caso médio, 2 dias úteis no alto e 4 horas úteis no crítico.
decisao prazo 4,1: Respondeu no prazo?
passo cobrar 4,2: Cobrar a área | O botão Cobrar manda o pedido de novo. Quando o prazo vence, o sistema também cobra sozinho e depois avisa o gestor da área e a Diretoria.
passo revisar 5,1: Revisar a resposta | A Ouvidoria lê o que a área respondeu e escreve o desfecho em linguagem simples.
fim encerrar 6,1: Encerrar com o manifestante | O desfecho vai por e-mail a quem manifestou. Prazo contado da chegada do caso: 7 dias úteis no caso médio, 5 no alto e 2 no baixo.

chega -> validar
validar -> area
area -> prazo
prazo -> revisar: sim
prazo -> cobrar: não
cobrar -> area
revisar -> encerrar
```

## Registrar uma manifestação

Use quando a pessoa reclama por telefone, no balcão, pelo Instagram ou pelo Reclame Aqui. O que chega pelo QR, pelo site e pela Ana já entra sozinho na lista.

1. No menu da esquerda, clique em **Ouvidoria**.
2. No alto da tela, clique em **Nova manifestação**.

![O alto da tela da Ouvidoria, com o botão Nova manifestação](fila-topo.png)

3. Escolha o **Canal de origem** e confira a data e a hora em que a pessoa entrou em contato.
4. Escolha o **Tipo da manifestação** e o **Setor**. Denúncia e relato de conduta ficam restritos à Ouvidoria e à Diretoria Executiva.
5. Escreva o **Resumo** em uma linha e, no **Relato integral**, o que a pessoa contou, sem mudar as palavras dela.
6. Preencha **Quem manifestou** e o **Contato**, ou marque **Manifestação anônima**. Se o relato é sobre outra pessoa, preencha o nome do paciente.
7. Clique em **Registrar manifestação**. O caso entra na lista com um número de protocolo, para você passar à pessoa.

![A janela Nova manifestação preenchida](nova-manifestacao.png)

## Encaminhar ao setor

Todo caso novo fica no grupo **Em classificação** até a Ouvidoria conferir e mandar para a área, e nenhum setor recebe o caso antes disso.

1. Na lista, ache o caso e clique em **Validar e acionar**.

![Um caso novo na lista, com o botão Validar e acionar](linha-validar.png)

2. Confira o **Tipo da manifestação**. Se o caso não precisa de sigilo, desmarque **Sigilo reforçado**.
3. Escolha a **Área responsável**.
4. Escolha a **Gravidade**. É ela que decide o prazo que a área recebe.
5. Escreva o **Extrato para o setor**: com as suas palavras, o que a área precisa apurar e responder. Sem esse texto, o envio não sai.
6. Clique em **Enviar à área**. O responsável do setor recebe o e-mail com o caso e o prazo, e o caso passa para **Aguardando área**.

![A janela Validar e acionar preenchida](validar-e-acionar.png)

Se o responsável do setor tem login, ele também acha o caso no app, em **A responder**, e pode responder por lá ou pelo link do e-mail.

Se o caso fala de um incidente com o paciente, como uma queda ou um erro de medicação, clique no número do protocolo, depois em **Enviar ao NSP** e em **Confirmar envio ao NSP**: o caso vira uma notificação do Núcleo de Segurança do Paciente, com o relato e sem o nome de quem manifestou, e o link do e-mail ao Núcleo pede login.

## Responder um caso do seu setor pelo app

Esta tarefa é de quem responde por um setor: o titular, o substituto ou o gestor que a Ouvidoria cadastrou com o seu e-mail. Com o login no app, você acha os casos do seu setor sem depender do e-mail.

1. Entre no app com o seu e-mail e a sua senha.
2. No menu da esquerda, clique em **Ouvidoria**. A lista mostra só os casos do seu setor: no alto, **A responder**, do prazo mais curto ao mais longo; embaixo, **Respondidos pelo setor**, só para consulta.
3. Ache o caso em **A responder** e clique em **Responder** na linha dele.

![Um caso do setor em A responder, com o botão Responder](linha-responder.png)

4. Leia o caso. É a mesma tela do link do e-mail, com a gravidade, o prazo, o relato e a **Nota da Ouvidoria**, que diz o que o setor precisa apurar.
5. Em **O que foi feito**, conte o que o setor fez para corrigir. Se tiver foto ou documento, clique em **Anexar arquivos**.
6. Clique em **Responder à Ouvidoria**. A Ouvidoria confere a resposta e encerra o caso com quem manifestou.

![A Tela do responsável aberta pelo app, com O que foi feito preenchido](tela-do-responsavel.png)

Cada caso recebe uma resposta só. Respondeu pelo app, o link do e-mail desse caso deixa de valer. Se você já respondeu pelo link, o botão **Responder** some da lista. Na mesma tela dá para pedir mais prazo ou devolver à Ouvidoria o caso que não é do seu setor.

## Cobrar a resposta do setor

A data de cada caso fica vermelha quando o prazo da área venceu, com o tempo de atraso ao lado.

1. Na lista, ache o caso com o prazo em vermelho. O botão principal dele é **Cobrar**.
2. Clique em **Cobrar**. O pedido sai de novo para o responsável do setor, e a linha mostra para quem foi.

![Um caso com o prazo vencido e o botão Cobrar](linha-cobrar.png)

Você não precisa cobrar todo dia: quando o prazo vence, o sistema cobra o setor sozinho. Se o atraso continua, ele avisa o gestor da área e, depois, a Diretoria Executiva.

## Encerrar com o manifestante

Quando a área responde, o caso sobe para o bloco **Aguardando seu encerramento**, no alto da lista.

1. Para ler a resposta da área, clique no número do protocolo do caso.
2. De volta à lista, clique em **Encerrar** na linha do caso.

![Um caso respondido pela área, com o botão Encerrar](linha-encerrar.png)

3. Escolha o **Desfecho**: procedente, improcedente, parcialmente procedente, sem condições de apuração ou sem retorno do manifestante.
4. Escreva o desfecho para quem manifestou, em linguagem simples. Esse texto sai do hospital: não escreva nome de colaborador nem detalhe da apuração interna.
5. Clique em **Encerrar caso**. Quem deixou e-mail recebe o desfecho junto do protocolo.

![A janela Encerrar com o desfecho escrito](encerrar.png)
