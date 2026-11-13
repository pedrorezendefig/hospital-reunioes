# Brief: O pedido chega explicado (PRD #1632, Hospital São Matheus)

Pedido respondido pela receita do `/divulgar` do Hospital (não perguntar de novo):

- Formato: 16:9 só, 1920x1080, final a 60 fps.
- Duração: a da narração mais a assinatura (meta: 55 a 70 s).
- Sem música. Efeitos sonoros reais pela skill `som` (cliques, trocas de tela, chegada do email, assinatura).
- Narração na voz B (skill `narracao`), legível no mudo: a fala aparece na tela palavra por palavra, presa ao `tempos.json`.
- Marca do Hospital São Matheus (`marca-hsm`): HP Simplified Regular em todo texto, peso 400; fundo azul-marinho escuro; um acento só (azul claro do app); logo só na assinatura, inteira e parada, sobre branco.
- Tela real do app: capturas do `playwright-cli` contra o app local com dados de exemplo fictícios.

## Quem vê e a ideia

- Quem vê: o diretor que pede melhorias e relata bugs na aba Tecnologia, no celular, entre uma reunião e outra.
- O que deve pensar no fim: "explico uma vez e quem programa já recebe tudo entendido".
- Ideia única: o card que você cria chega explicado a quem vai programar, na hora.
- Prova (issues #1633 a #1636): o card ganha a parte "Para o desenvolvedor" logo abaixo da do diretor, em seis partes; a conversa com o assistente não muda e a parte nova não aparece na tela do diretor; quem foi escolhido em "Quem cuida disto?" recebe um email com o pedido explicado e o link; se o email falhar, o card nasce do mesmo jeito; o bug ganha a mesma parte, com as mesmas perguntas; os pedidos que já estão na fila vão ganhar a parte, sem email e sem o diretor fazer nada.

## Material

Capturas em `assets/` (lista final em `docs/shotlist.md`), app local com dados de exemplo:
a conversa da melhoria, o resumo com "Quem cuida disto?" e "Criar o card", o resumo com a escolha feita, a tela depois do card criado, o resumo do bug, a lista de pedidos, o email real do card novo (template do app renderizado pelo código do app, sem envio) e o corpo do card que o "Criar o card" grava (saído da função do app, mostrado como Markdown do GitHub), da melhoria e do bug.

Exemplo seguido: a diretora Helena Prado pede "Filtrar a fila da Ouvidoria por setor" e escolhe a Marina Teles. Pessoas fictícias.

Cores: `#1A1C4E` e `#1E1D57` (fundo), `#2B2E7E` (cartões), `#3B6FB6` (acento), `#EEF2FA` (texto claro), branco na assinatura.
