# Brief: Pergunte ao seu Claude (PRD #1571, Hospital São Matheus)

Pedido respondido pela receita do `/divulgar` do Hospital (não perguntar de novo):

- Formato: 16:9 só, 1920x1080, final a 60 fps.
- Duração: a da narração mais a assinatura (meta: 60 a 75 s).
- Sem música. Efeitos sonoros reais pela skill `som` (cliques, trocas de tela, notificação, assinatura).
- Narração na voz B (skill `narracao`), legível no mudo: a fala aparece na tela palavra por palavra, presa ao `tempos.json`.
- Marca do Hospital São Matheus (`marca-hsm`): HP Simplified Regular em todo texto, peso 400; fundo azul-marinho escuro; um acento só (azul claro do app); logo só na assinatura, inteira e parada, sobre branco.
- Tela real do app: capturas do `playwright-cli` contra o app local com dados de exemplo fictícios.

## Quem vê e a ideia

- Quem vê: o diretor do hospital, no celular, entre uma reunião e outra.
- Ideia única: ele pergunta ao próprio Claude e recebe os dados do aplicativo, os mesmos que a tela mostra.

## Material

Capturas (`assets/`, app local v0.275.0 do código, dados de exemplo):

| arquivo | tela |
|---|---|
| 01-pendencias-atrasadas.png | Pendências, filtro ATRASADO (3): Renata Fontes 27/10, Otávio Serra 04/11 e 11/11 |
| 02-ouvidoria-fila.png | Fila da Ouvidoria: 5 em andamento, 3 com prazo estourado (2026-0151 UTI Adulto, 0152 Farmácia, 0153 Recepção) |
| 03-dossie-topo.png | Dossiê do caso 2026-0151, topo (quem manifestou, paciente, setor, gravidade) |
| 04-dossie-inteiro.png | Dossiê 2026-0151 de página inteira (1920x2559): relato integral, resposta da área, linha do tempo |
| 05-reuniao-cme.png | Reunião Acompanhamento da CME, 03/11, Ata assinada (1920x2306): resumo executivo, participantes, decisões |
| 06-usuario-diretoria.png | Editar usuário: Acesso à Ouvidoria = Diretoria Executiva |
| 06c-acesso-retirado.png | O mesmo campo trocado para Sem acesso (não salvo) |
| 07-guia-conector.png | Guia do Conector de página inteira (1920x1992): passo 4 da privacidade, perguntas da diretoria executiva, aviso do registro |

Respostas reais das ferramentas do Conector, rodadas no banco local como a diretora de exemplo: `docs/respostas-das-ferramentas/*.json`. O texto das respostas do Claude no filme sai desses dados.

A conversa com o Claude é desenhada pelo filme, sem copiar a tela do claude.ai: o Claude de verdade do diretor consulta a produção, com dados reais de pacientes, que não podem aparecer. As respostas mostradas são os dados que as ferramentas devolveram.

Cores: `#1A1C4E` e `#1E1D57` (fundo), `#2B2E7E` (cartões), `#3B6FB6` (acento), `#EEF2FA` (texto claro), branco na assinatura.
