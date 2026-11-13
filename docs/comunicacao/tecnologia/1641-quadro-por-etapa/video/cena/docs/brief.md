# Brief: Quadro da Tecnologia por Etapa (PRD #1641, Hospital São Matheus)

Pedido respondido pela receita do `/divulgar` do Hospital (não perguntar de novo):

- Formato: 16:9 só, 1920x1080, final a 60 fps.
- Duração: a da narração mais a assinatura (meta: 65 a 80 s).
- Sem música. Efeitos sonoros reais pela skill `som` (cliques, trocas de tela, o aviso do sino, assinatura).
- Sem narração (pedido do Pedro na parada 2, 13/11/2026): o texto aparece na tela palavra por palavra, preso ao `tempos.json`, que vem de uma leitura na voz B usada só como metrônomo. Som só de efeitos de motion graphic.
- Marca do Hospital São Matheus (`marca-hsm`): HP Simplified Regular em todo texto, peso 400; fundo azul-marinho escuro; um acento só (azul claro do app); logo só na assinatura, inteira e parada, sobre branco.
- Tela real do app: capturas do `playwright-cli` contra o app local, com dados de exemplo fictícios (diretor Augusto Medeiros; Tiago Lins e Beatriz Arantes cuidando dos pedidos).

## Quem vê e a ideia

- Quem vê: o diretor do hospital, no computador da sala dele, querendo saber como andam os pedidos que fez à Tecnologia antes de cobrar alguém.
- Ideia única: a aba Tecnologia virou um quadro, e cada pedido fica na coluna da etapa em que está.

## Material

Capturas (`assets/`, app local com o código do PRD, dados de exemplo):

| arquivo | tela |
|---|---|
| 01-quadro.png | Quadro na tela larga: Registrada 3, Em análise 2, Planejada 2, Em desenvolvimento 3, Entregue 10; Novo pedido; barra com busca, Tipo, Origem e o interruptor |
| 02-quadro-inteiro.png | O mesmo Quadro de página inteira (1920x1627), com os 8 cards de Entregue e o Ver todos nas Entregas |
| 03-quadro-rolado.png | Página rolada: cabeçalhos das colunas presos no alto |
| 04-painel.png | Demanda 20 (Assinatura da Ata pelo celular) aberta no painel à direita, com o Documento do card e a Conversa da Demanda; Quadro atrás |
| 05-ampliado.png | O mesmo pedido em tela inteira (Ampliar), com Voltar ao quadro |
| 06-novo-pedido.png | Novo pedido: o Assistente de Tecnologia na largura toda |
| 07-registrada.png | Demanda 32 (Registrada, do próprio diretor): a conversa retomada, com o Documento do pedido ao lado |
| 08-nao-sera-feita.png | Interruptor ligado: sexta coluna Não será feita e o Limpar filtros |
| 09-entregas.png | Aba Entregas, por semana (Ver todos nas Entregas) |
| 10-celular.png | No celular (390 px): a lista de sempre, com o filtro de Etapa |
| 11-sino.png | O aviso do sino: "Tiago Lins escreveu na Demanda" |

Cores: `#1A1C4E` e `#1E1D57` (fundo), `#2B2E7E` (cartões), `#3B6FB6` (acento), `#EEF2FA` (texto claro), branco na assinatura.

Achado na captura: o botão "Ampliar" e o "Fechar o pedido" do painel ficam embaixo da barra do topo do app (painel na camada 40, barra na 100). O Esc fecha; o Ampliar foi acionado pelo teclado para a captura 05.
