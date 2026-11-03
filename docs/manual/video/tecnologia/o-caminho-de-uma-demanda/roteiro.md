# Roteiro: O caminho de uma Demanda (Tecnologia)

Vídeo de visão geral do módulo Tecnologia, na abertura da seção
(`tecnologia/index.md`). Refeito na Fatia de manual do PRD #1380 (issue
#1387): desde a ADR 0077 a aba é o chat do Assistente de Tecnologia, e a
conversa é a cena central (ADR 0076, decisão 4). O slug ficou o mesmo para a
abertura não mudar de endereço; o caso de exemplo agora é um pedido.

## Briefing (skill `copy`)

- **Quem vê:** o diretor do hospital, que entra como Super Admin com um botão
  que não salvou ou uma ideia para um dos sistemas, e até ontem mandava isso
  pelo WhatsApp ou abria um card no Quadro.
- **O que deve pensar ao final:** "é só responder às perguntas; nada sai sem
  o meu clique, e a lista me diz em que pé está".
- **A única ideia:** o pedido nasce de uma conversa que começa com uma
  pergunta, e é você quem decide o que vai para a Vitta.
- **A prova:** a abertura do módulo ("O caminho de um pedido"), as Páginas de
  tarefa (Relatar um bug, Pedir uma melhoria, Acompanhar um pedido), o Como
  funciona (O que a IA consulta, O que vai para a Vitta, A Etapa e o O que
  muda) e o `novidades.md`. Os fatos da fala saem do código da tela
  (`ChatDaTecnologia.tsx`, `ConversasDaTecnologia.tsx`) e do Kit
  `backend/app/conhecimento/tecnologia.md`.

## Ganchos

1. Começo no meio: "Isso é um bug ou uma melhoria?"
   **Escolhido:** é a primeira fala da IA na tela, palavra por palavra, então
   o primeiro quadro (a fala da IA e os dois botões) diz a mesma coisa que a
   voz e funciona no mudo. Sete palavras, e a pergunta volta na virada.
2. Situação: "O botão não salvou. E agora, conta pra quem?" (bom, mas abre
   pelo bug e deixa a melhoria de fora)
3. Detalhe específico: "Duas opções por pergunta, com a recomendada marcada."
   (é o miolo da melhoria, não a porta de entrada)

Virada (responde o gancho): "Começou com uma pergunta e chegou à Vitta do
jeito que você decidiu."

## Nota da copy

| Critério | Nota |
| --- | --- |
| Gancho | 2 |
| Uma ideia | 2 |
| Ouvido | 2 |
| Repetição | 1 ("pergunta" volta de propósito: é o gancho, o mecanismo da melhoria e a virada; "Criar o card" repete porque é o nome do botão nos dois caminhos) |
| Cena casada | 2 |
| Virada | 2 |
| Verdade | 2 |
| **Total** | **13 de 14** |

Humanizer (ADR 0071) passado na narração e no texto de tela: "Vitta" vinha em
quatro frases seguidas, e a frase do "nada sai" passou a falar do app; a fala
da consulta diz só o que o Kit diz (ela consulta o que já foi decidido e
avisa). Varredura
anti-técnica (migration, endpoint, API, PR, pull request, deploy, RLS,
schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase,
Coolify, prompt) e de travessão: sem achado. O vídeo diz "card" porque é a
palavra do botão, nunca o nome do sistema de desenvolvimento.

## Narração

O texto que a voz A lê está em `narracao.txt`, um parágrafo por frase.

## Cenas

Uma cena por tela do app. As frases da mesma tela dividem a cena: a câmera
anda de um alvo ao outro na palavra que cita o alvo, e a legenda troca de
frase. Cada corte entre telas usa uma transição diferente do catálogo.
Destaque é o contorno azul com o resto da tela velado; cursor é a seta
branca, com o anel no clique. Os casos de exemplo são o bug do botão Salvar
do POP e a melhoria do nome do setor no cartaz do QR da Ouvidoria.

| Cena | Tempo (s) | Fala | Tela | Entrada |
| --- | --- | --- | --- | --- |
| 1 | 0,0 a 3,0 | Isso é um bug ou uma melhoria? | tipografia: a fala da IA ("Isso é um bug, algo que não funciona como deveria, ou uma melhoria?") e os botões Bug e Melhoria acendendo na palavra | (abre) |
| 2 | 3,0 a 21,9 | É com essa pergunta que a aba Tecnologia abre a conversa. Clique em Nova conversa e escolha Bug ou Melhoria. Dá pra escrever, falar no microfone ou mandar o print da tela. Se for só uma dúvida, a IA responde ali mesmo e diz de onde tirou. | video-01-abertura | pontoAbre |
| 3 | 21,9 a 36,3 | No bug, ela pergunta uma coisa de cada vez, no máximo cinco. Onde foi, o que aconteceu, o que você esperava e como repetir. O print entra pelo botão de imagem e fica guardado no app. | video-02-bug | fusao |
| 4 | 36,3 a 55,0 | No fim vem o resumo, com o jeito de saber que foi resolvido. Algo errado? Clique em Não bateu e diga o quê. Se está certo, Criar o card manda o bug pra Vitta. Ele entra na fila do desenvolvimento, sem ninguém precisar assumir antes. | video-03-resumo-do-bug, video-04-enviado | estica |
| 5 | 55,0 a 82,2 | Na melhoria, a IA pergunta o que a Vitta perguntaria antes de começar. Ela consulta o que já foi decidido e avisa se o pedido esbarra numa regra. Cada pergunta traz duas opções, com a recomendada marcada. Escolha uma, ou responda do seu jeito, por escrito ou por voz. São no máximo doze perguntas, e Fechar e resumir encerra quando você quiser. | video-05-melhoria | tunel |
| 6 | 82,2 a 91,7 | O resumo mostra cada decisão com o porquê, e o que ficou em aberto. Nada sai do app antes do seu clique em Criar o card. | video-06-resumo-da-melhoria | retangulo |
| 7 | 91,7 a 108,9 | Ao lado da conversa fica a lista dos seus pedidos. A conversa parada aparece como Registrada: clique e continue de onde parou. As outras mostram a Etapa, que anda sozinha: Em análise, Em desenvolvimento, Em produção. | video-07-lista | chicoteLuz |
| 8 | 108,9 a 113,8 | Abra um pedido e leia O que muda, o que a entrega traz pra você. | video-08-acompanhamento | peliculaGira |
| 9 | 113,8 a 118,2 | Começou com uma pergunta e chegou à Vitta do jeito que você decidiu. | tipografia: a pergunta sobe, o pedido chega com Em análise e O que muda, e a logo | despenca |

A conversa (cenas 2 a 6) vai de 3,0 s a 91,7 s, a maior parte dos 121,7 s do vídeo. Parada planejada: de 118,8 s ao fim (121,7 s), a logo do hospital inteira e parada na assinatura. Fora dela, nada fica parado: a câmera empurra devagar dentro de cada tela e a grade do fundo corre.

## Como refazer

1. Telas: `python3 docs/manual/prints/tecnologia.py --semear` e
   `python3 docs/manual/prints/tecnologia.py --video` (o app local com o
   código da produção). Saem `video-*.png` e `video-alvos.json` em
   `docs/manual/src/assets/tecnologia/`. A lista e a conversa entram pela tela
   de verdade, com a resposta do servidor trocada no navegador: nenhuma fala
   chama a IA, e nada grava no banco.
2. Projeto de trabalho: o da receita
   (`.claude/skills/manual/references/video-de-visao-geral.md`), mais
   `patch -p1 -d "$W" < cena/projeto/identidade.patch` (fonte HP Simplified,
   paleta azul-marinho, sem grão, `swangle`, as transições sem o verde do
   modelo, o `flash` e o `pulsoJanela` sem clarear a cena que sai inteira, e a
   composição registrada no `Root.tsx`), as cenas
   (`mkdir -p "$W/src/videos/Tecnologia" && cp cena/*.tsx tempos.json "$W/src/videos/Tecnologia/"`),
   as telas (`cp docs/manual/src/assets/tecnologia/video-*.png "$W/public/"`
   e `cp docs/manual/src/assets/tecnologia/video-alvos.json "$W/src/videos/Tecnologia/alvos.json"`),
   o roteiro dos tempos (`cp cena/projeto/tempos-da-narracao.mjs "$W/scripts/"`)
   e a logo branca da `marca-hsm` em `public/logo-hsm-branca.png`.
3. Narração: `python3 ~/.claude/voz/narrar.py --file narracao.txt --output "$W/public/narracao.wav"`.
4. Tempos: `node cena/projeto/tempos-da-narracao.mjs "$W/public/narracao.json" narracao.txt "1|2,3,4,5|6,7,8|9,10,11,12|13,14,15,16,17|18,19|20,21,22|23|24" > tempos.json`, e copie de novo para `$W/src/videos/Tecnologia/`.
5. `npx tsc --noEmit`, stills, draft e render (receita), composição `Tecnologia`.
