# Roteiro: O caminho de uma Demanda (Tecnologia)

Vídeo de visão geral do módulo Tecnologia, na abertura da seção
(`tecnologia/index.md`). Segue a receita narrada em Remotion ajustada pelo
piloto de Contas médicas (ADR 0076, issue #1373 do PRD #1365), com o
Planejamento da Demanda como cena central.

## Briefing (skill `copy`)

- **Quem vê:** o diretor ou a gestora do hospital que entra como Super Admin e
  tem um pedido sobre os sistemas, que até ontem mandava pelo WhatsApp; e quem
  da Vitta responde do outro lado.
- **O que deve pensar ao final:** "sei levar o meu pedido do registro à
  entrega, e o plano sai das minhas respostas".
- **A única ideia:** o pedido vira uma Demanda que anda num caminho só, e no
  Planejamento quem decide é você.
- **A prova:** a abertura do módulo ("O caminho de uma Demanda"), as Páginas
  de tarefa (Registrar uma Demanda pelo assistente, Acompanhar o Quadro,
  Conversar na Demanda, Planejar a Demanda com a IA, Levar a Demanda para o
  desenvolvimento, Conferir e concluir uma entrega), o Como funciona "A Etapa
  e o O que muda" e o `novidades.md`.

## Ganchos

1. Situação: "O pedido que ia pelo WhatsApp agora tem lugar."
   **Escolhido:** quem vê se reconhece na mensagem solta no grupo, a frase
   cabe em 3 s e o primeiro quadro mostra as mensagens virando o card que cai
   na raia Nova, então funciona no mudo.
2. Detalhe específico: "Duas opções por pergunta, e o plano sai das suas
   respostas." (bom para a cena central, mas pula o registro e o Quadro)
3. Começo no meio: "Você conta o que precisa, e o pedido se monta sozinho."

Virada (responde o gancho): "O pedido saiu do WhatsApp, ganhou um plano e
voltou entregue a quem pediu."

## Nota da copy

| Critério | Nota |
| --- | --- |
| Gancho | 2 |
| Uma ideia | 2 |
| Ouvido | 2 |
| Repetição | 1 (Demanda, card e Conversa repetem de propósito: são nomes da tela; "decisão" volta no resumo porque é o assunto do Planejamento) |
| Cena casada | 2 |
| Virada | 2 |
| Verdade | 2 |
| **Total** | **13 de 14** |

Humanizer (ADR 0071) passado na narração e no texto de tela: saíram a
repetição de "clique" (ficou em Criar Demanda e Concluir), "pedido" no meio do
vídeo (fica no gancho e na virada), "responda" e "escreva" em três frases
seguidas, e a promessa de que todo pedido vira plano (só Novo e Ajuste se
planejam, e a cena diz isso). Varredura anti-técnica (migration, endpoint,
API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch,
merge, token, env, SQL, Supabase, Coolify, prompt) e de travessão: sem achado.
O "sim" cria o plano do diretor para a Vitta; o vídeo diz "plano", nunca a
sigla.

## Narração

O texto que a voz A lê está em `narracao.txt`, um parágrafo por frase.

## Cenas

Uma cena por tela do app. As frases da mesma tela dividem a cena: a câmera
anda de um alvo ao outro na palavra que cita o alvo, e a legenda troca de
frase. Cada corte entre telas usa uma transição diferente do catálogo.
Destaque é o contorno azul com o resto da tela velado; cursor é a seta
branca, com o anel no clique. O caso de exemplo é a Demanda "Mostrar o nome
do setor no cartaz do QR da Ouvidoria", do assistente ao sim.

| Cena | Tempo (s) | Fala | Tela | Entrada |
| --- | --- | --- | --- | --- |
| 1 | 0.0 a 3.9 | O pedido que ia pelo WhatsApp agora tem lugar. | tipografia: as mensagens soltas viram o card que cai na raia Nova | (abre) |
| 2 | 3.9 a 12.3 | Na aba Tecnologia, cada assunto dos sistemas é uma Demanda. Para registrar a sua, abra Nova Demanda. | video-01-quadro | pontoAbre |
| 3 | 12.3 a 28.0 | Conte o que precisa do seu jeito: escrevendo, falando ou com um print da tela. O assistente faz no máximo três perguntas, e o Rascunho da Demanda se monta ao lado. Confira e clique em Criar Demanda. | video-02-assistente | fusao |
| 4 | 28.0 a 38.9 | Ela nasce em Nova, com o dono do Produto como responsável, e ele recebe um e-mail. Entre Nova, Em andamento e Aguardando, quem move é gente. | video-01-quadro | chicoteLuz |
| 5 | 38.9 a 50.2 | Dentro do card fica a Conversa. Digite arroba e escolha o nome, e a pessoa é avisada. O que se combina ali fica guardado, com autor, data e hora. | video-03-conversa | estica |
| 6 | 50.2 a 55.8 | Numa Demanda do tipo Novo ou Ajuste, aparece o botão Planejar com a IA. | video-04-planejar | flash |
| 7 | 55.8 a 78.2 | A IA faz as perguntas que a Vitta faria antes de começar, uma de cada vez. Cada pergunta traz o contexto e duas opções, com a recomendada marcada. Escolha uma delas. Se nenhuma serve, responda falando no microfone. À direita, O que já decidimos ganha uma linha a cada decisão fechada. | video-05-planejamento | tunel |
| 8 | 78.2 a 90.9 | Quando quiser parar, use Fechar e resumir. O resumo traz o porquê de cada decisão e o que ficou em aberto. Algo não bateu? Diga o quê, e as perguntas seguem. | video-05-planejamento, video-06-resumo | peliculaGira |
| 9 | 90.9 a 102.1 | Se está certo, o sim manda o plano para os desenvolvedores. A Demanda passa para Em análise, e o card mostra O que muda com o que você decidiu. | video-06-resumo, video-07-enviado, video-08-em-analise, video-09-o-que-muda | retangulo |
| 10 | 102.1 a 112.2 | Nas outras Demandas, quem faz o Vínculo é a Vitta. Pelo número do trabalho, ou criando na hora, em Levar para desenvolvimento. | video-10-vinculo | glitchRGB |
| 11 | 112.2 a 119.1 | Daí em diante, o selo da Etapa anda sozinho: Planejada, Em desenvolvimento, Em produção. | video-01-quadro | flood |
| 12 | 119.1 a 125.3 | Quando a entrega chega ao app, a Demanda volta para você, no Com você do Painel. | video-11-painel | pulsoJanela |
| 13 | 125.3 a 133.8 | Teste o que mudou e, se está bom, clique em Concluir. Se faltou algo, avise na Conversa, e a Vitta refaz. | video-12-entrega, video-13-entrega-conversa | corteBatida |
| 14 | 133.8 a 138.6 | O pedido saiu do WhatsApp, ganhou um plano e voltou entregue a quem pediu. | tipografia: o card ganha O que muda e o selo Em produção, e a logo | despenca |

O Planejamento da Demanda (cenas 6 a 9) vai de 50,2 s a 102,1 s: 52 s dos
142 s do vídeo, o maior trecho. Parada planejada: de 139,2 s ao fim (142,0 s),
a logo do hospital inteira e parada na assinatura. Fora dela, nada fica
parado: a câmera empurra devagar dentro de cada tela e a grade do fundo corre.

## Como refazer

1. Telas: `python3 docs/manual/prints/tecnologia.py --semear` e
   `python3 docs/manual/prints/tecnologia.py --video` (o app local na versão
   de produção). Saem `video-*.png` e `video-alvos.json` em
   `docs/manual/src/assets/tecnologia/`. Os estados que o banco de exemplo não
   guarda (a conversa do assistente, o resumo, o enviado, o card depois do
   sim) entram pela tela de verdade, com a resposta do servidor trocada no
   navegador.
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
4. Tempos: `node cena/projeto/tempos-da-narracao.mjs "$W/public/narracao.json" narracao.txt "1|2,3|4,5,6|7,8|9,10|11|12,13,14,15|16,17,18|19,20|21,22|23|24|25,26|27" > tempos.json`, e copie de novo para `$W/src/videos/Tecnologia/`.
5. `npx tsc --noEmit`, stills, draft e render (receita), composição `Tecnologia`.
