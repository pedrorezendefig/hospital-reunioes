# Estilo do manual

O contrato visual dos Vídeos de tarefa (emenda de 13/10/2026 à ADR 0057). O
formato é o da style-library do HyperFrames Student Kit (`style-library/GUIDE.md`
do kit, clonado em `~/PedroDev/hyperframes-student-kit`, só leitura), com a cara
do app. Quem manda nas cores e na fonte é o app: elas saem do `globals.css` do
frontend para o `tokens.css`. Quem manda no ritmo são as Fichas de referência em
`references/`.

## O estilo em um parágrafo

O vídeo mostra a tela real do app, mudo, em 30 a 60 s. A câmera trabalha para
quem assiste: aproxima devagar do elemento que o passo cita, não fica parada e
passa de uma tela para a outra com um rastro curto. A legenda de passo mora numa
placa navy fixa embaixo da tela; o número e o texto trocam, a placa fica.
Abertura e carimbo são cartões brancos de 3 a 5 s com o título da tarefa. O
vídeo tem a cor e a fonte do app. Na dúvida entre bonito e fiel, fiel vence.

## O que tem aqui

- `DESIGN.md`: este contrato.
- `tokens.css`: GERADO por `python3 tools/gerar_tokens_video.py`, nunca à mão.
- `cards/<card>/index.html`: os cinco cards. Cada pasta tem `tokens.css` e
  `assets` como links (o `assets` aponta para `docs/comunicacao/_assets`, com a
  fonte e o logo), para o card rodar sozinho no HyperFrames.
- `references/`: as Fichas de referência, uma por vídeo de referência.
- `pendentes-de-rerender.txt`: os vídeos feitos antes deste estilo. O
  conferidor deixa esses fora dos gates novos. A lista só encolhe.

## Paleta

Cada cor fora da tela do app tem um papel. Cor sem papel não entra.

| Token | Vem do app | Papel |
| --- | --- | --- |
| `--video-marca` | `--color-primary`, o navy do logo | o hospital: título da abertura e do carimbo, nome da tela no lower-third |
| `--video-foco` | `--color-primary-light`, o azul médio do logo | onde olhar: anel do push-in, marcador, dedo, seção da abertura |
| `--video-passo` | `--color-accent`, âmbar | o número do passo, e só ele |
| `--video-atencao` | `--color-warning` | o callout do que não tem volta |
| `--video-legenda-fundo` e `--video-legenda-texto` | `--color-primary-dark` e `--color-bg` | a placa da legenda e o texto em cima dela |
| `--video-palco` | 6% do navy sobre o branco | o fundo atrás da janela do app |
| `--video-cartao`, `--video-borda`, `--video-sombra` | superfície, borda e sombra do app | os cartões claros |
| `--video-texto`, `--video-texto-apoio` | texto e texto secundário do app | o texto dos cards |

Dentro da réplica da tela vale a cor que a tela usa, pelo token de mesmo nome:
`var(--color-slate-500)` para `text-slate-500`, `var(--color-primary)` para
`bg-primary`. O `tokens.css` traz a paleta inteira que o app herda do Tailwind.

Mudar uma cor é mudar o `globals.css` e rodar o gerador. Token novo do estilo
entra no `ESTILO_DO_MANUAL` do gerador, derivado de um token do app por `var()`
ou `color-mix()`, com o papel escrito ao lado. Nenhuma cor nova nasce no vídeo.

## Tipografia

- HP Simplified (`var(--font-app)`), a mesma do app, em tudo. O `@font-face`
  vem no `tokens.css`; a composição não declara fonte.
- Número de protocolo e código em `var(--font-mono)`, como o app.
- Peso regular. Negrito só na palavra da tela, com `**palavra**` no slot.
- No quadro de 1920x1080: título da abertura 84px, legenda 40px, callout 30 e
  36px, lower-third 22 e 34px. Nada abaixo de 22px.
- Caixa de frase. Caixa alta só no rótulo pequeno (seção da abertura, lugar do
  lower-third), com espaçamento entre letras.

## Movimento

O vocabulário do kit (`MOTION_PHILOSOPHY.md`, leis 4, 5 e 11) no ritmo de quem
está aprendendo uma tarefa. As receitas em GSAP estão na skill `/manual`,
`references/video-de-tarefa.md`.

1. **Push-in no elemento do passo.** A câmera aproxima do botão ou do campo que
   o passo cita, em 2 a 3 s.
2. **Câmera que nunca para.** Entre um movimento e outro, uma deriva lenta.
   Abertura e carimbo também respiram.
3. **Transição com rastro entre telas.** A tela que sai desliza e desfoca; a
   que entra vem do lado oposto e entra em foco, no mesmo sentido. Nada de corte
   seco entre duas telas do app, nada de flash.
4. **Legenda que troca sem pop.** A placa não anima. Número e texto chegam com
   um fade curto.
5. **Abertura e carimbo de 3 a 5 s**, com entrada escalonada.
6. **Timeline que preenche o slot.** Todo timeline termina com
   `tl.to({}, { duration: N }, 0)`, com N pelo menos o `data-duration` do slot.
   O conferidor trava quem não tem.

Um passo fica de 3 a 8 s na tela, o tempo de ler a legenda duas vezes. Cena de
1,5 s é ritmo de reel e não serve aqui.

## Cards e slots

Cada card é uma composição que roda sozinha
(`npx --yes hyperframes@0.8.41 check docs/manual/video/_estilo/cards/<card>`
passa limpo) e entra no vídeo como sub-composição. O contrato, adaptado do kit:

1. Raiz `<div id="<card>" data-composition-id="<card>" data-start="0"
   data-width="1920" data-height="1080" data-duration="...">`.
2. Um timeline GSAP pausado em `window.__timelines["<card>"]`, determinístico
   (sem relógio, sem `Math.random`, sem repetição infinita), terminando na
   âncora do slot.
3. Cor e fonte só por `var(--...)` dos tokens.
4. Texto só em slot: elemento com `data-slot="<nome>"`, declarado no
   `data-composition-variables` do `<html>` com rótulo, `maxLength` e default.
   O vídeo preenche por `data-variable-values` no host.
5. Card de tela cheia é opaco. Card de apoio é transparente fora do próprio
   cartão, porque fica por cima da tela do app.

| Card | Tipo | Slots (máximo de caracteres) | No vídeo |
| --- | --- | --- | --- |
| `abertura` | tela cheia | `secao` (40), `titulo` (70), `papel` (24) | 3 a 5 s, no começo |
| `legenda-de-passo` | apoio | `numero` (2), `texto` (90) | um por passo, um encostado no outro |
| `callout` | apoio | `titulo` (40), `texto` (110) | no máximo um, antes do passo que não tem volta |
| `lower-third` | apoio | `lugar` (32), `tela` (48) | 2 a 3 s quando a tela muda |
| `carimbo` | tela cheia | `titulo` (70), `carimbo` (80), `assinatura` (60) | 3 a 5 s, no fim |

A placa da legenda mora no retângulo `--video-legenda-*` do `tokens.css`. O gate
de strips (`tools/strips_video_manual.py`) procura a placa ali em todo quadro
com legenda; mudar a placa de lugar é mudar o token, e o gate acompanha.

## O que não fazer

- Canvas preto, tipo cromado, halo de luz, grade em perspectiva. É a cara do
  kit, e o vídeo deixa de parecer o app.
- Cor em hex ou fonte com nome dentro da composição. O conferidor trava as duas.
- Cena de 1,5 s, corte a cada frase.
- Placa da legenda que entra e sai a cada passo.
- Câmera parada por mais de 2 s.
- Mais de um callout por vídeo, ou callout para o que não é aviso.
- Tela, botão ou palavra que o app não tem. Na dúvida, fiel vence.

## Fichas de referência

Os vídeos de referência ficam em `local/manual-video-referencias/`, fora do git.
Cada um ganha uma Ficha de referência em `references/` com o que copiar dele e o
que não copiar.

| Ficha | Vídeo | O que diz |
| --- | --- | --- |
| [`ficha-modelo.md`](references/ficha-modelo.md) | nenhum ainda | o molde para a primeira ficha |

Quando um MP4 chega: copie a ficha modelo para `references/<nome-do-mp4>.md`,
preencha e acrescente a linha nesta tabela.

## Quando o estilo muda

Nota humana no draft de um vídeo vira regra no mesmo PR, para não se repetir. Se
a nota é de cor, fonte ou card, a regra entra aqui ou no card. Se é de ritmo,
montagem ou gate, entra na receita da skill `/manual`
(`references/video-de-tarefa.md`, seção "Regras que vieram de nota").
