# Vídeo de tarefa

Um vídeo por Página de tarefa: a mesma tarefa da página, do primeiro toque ao
resultado, para quem prefere ver a fazer. É a receita de vídeo da `/divulgar`
aplicada a uma tarefa só, e não uma demonstração de entrega.

**Vídeo de tarefa não é Vídeo de percepção de valor.** O de percepção mora em
`docs/comunicacao/`, é do diretor e fala de uma entrega. Este é do usuário e
fala de uma tarefa.

Todo vídeo novo, e todo vídeo refeito, segue o **Estilo do manual**
(`docs/manual/video/_estilo/DESIGN.md`, emenda de 13/10/2026 à ADR 0057): leia o
`DESIGN.md` antes de compor. Ele diz a paleta e o papel de cada cor, a fonte, o
vocabulário de movimento, os cinco cards e o que não fazer. Esta receita diz
como montar, como conferir e como uma nota humana vira regra.

## Onde cada coisa mora

- Composição (a fonte, versionada): `docs/manual/video/<modulo>/<slug>/`, com
  `index.html`, `hyperframes.json`, `package.json`, `meta.json`, `VERIFY.md`,
  `compositions/` (as cópias dos cards que o vídeo usa) e dois links:
  `assets -> ../../../../comunicacao/_assets` (fonte e logo únicos, ADR 0044) e
  `tokens.css -> ../../_estilo/tokens.css`.
- Estilo do manual: `docs/manual/video/_estilo/`, com o `DESIGN.md`, o
  `tokens.css` (gerado do `globals.css` do app por
  `python3 tools/gerar_tokens_video.py`, nunca à mão), os cards em
  `cards/<card>/` e as Fichas de referência em `references/`.
- MP4 renderizado: `docs/manual/public/video/<modulo>/<slug>.mp4`, **fora do
  git** (o `.gitignore` do site já cobre `public/video/`). As strips do gate
  ficam em `renders/strips/` da composição, também fora do git.
- A página exibe pelo frontmatter `video: <slug>`; o tema monta o `<video>`.
- O HyperFrames Student Kit mora em `~/PedroDev/hyperframes-student-kit`, só
  para leitura. Nenhuma skill dele é instalada (três têm o nome das skills
  globais de HyperFrames). O HyperFrames do manual fica na 0.8.41.

`python3 tools/checar_video_manual.py --dir docs/manual` trava se a página
exibe vídeo sem composição, se falta carimbo, se algum MP4 foi parar na árvore
versionada e, em todo vídeo fora de `_estilo/pendentes-de-rerender.txt`, se
falta o `VERIFY.md`, se há cor em hex ou fonte fora dos tokens, ou se algum
timeline (da raiz ou de um card montado) é mais curto que o slot. Os mesmos
gates de cor, fonte e timeline valem para os cards de `_estilo/cards/`.

## Especificação

1920x1080, 30 fps, **30 a 60 s**, sem voz: o vídeo funciona no mudo, com a
legenda de passo na tela. Réplica do app real, com as cores e a fonte do
`tokens.css`. Na dúvida entre bonito e fiel, fiel vence.

Do kit vem a disciplina, não a cara: push-in no elemento do passo, câmera que
nunca para, transição com rastro entre telas, legenda que troca sem pop,
abertura e carimbo de 3 a 5 s e timeline que preenche o slot. Nada de canvas
preto, tipo cromado ou cena de 1,5 s: o vídeo tem que parecer o app.

Roteiro fixo:

1. **Abertura (3 a 5 s):** card `abertura`, com o título da tarefa no
   infinitivo, igual ao da página, e o selo de quem faz.
2. **A tarefa (o vídeo é isso):** os mesmos passos da página, na mesma ordem e
   com as mesmas palavras de tela, cada um com o seu card `legenda-de-passo`.
   Dedo fantasma toca, campo preenche, tela reage como o app reagiria. O
   `lower-third` diz em que tela a pessoa está quando a tela muda; o `callout`,
   no máximo um, é o par do Aviso destacado da página.
3. **Fecho (3 a 5 s):** card `carimbo`, com a linha do carimbo de geração.

**Carimbo, dois níveis.** Visível no fecho, no slot `carimbo`:
`Manual · retrata o app em v<X.Y.Z> · gerado em DD/MM/AAAA` (a versão em
produção, `last_app_version` de `docs/spec/deploy/state.json`; o
`package.json` do frontend parou na 0.163.2 quando a versão passou a ser da
subida). Legível por
máquina, no `<head>` da composição, com os cinco campos que o conferidor cobra:

```html
<script type="application/json" id="manual-video-meta">
{"modulo": "ouvidoria", "slug": "<slug>",
 "pagina": "ouvidoria/<slug>.md", "prd": 731, "issues": [736],
 "app_version": "0.136.0", "gerado_em": "<ISO-8601 com timezone>"}
</script>
```

## Montar

Leia as skills globais na ordem `/hyperframes` → `/hyperframes-core` →
`/hyperframes-animation`, e o `DESIGN.md` do estilo.

```bash
cd docs/manual/video/<modulo>/<slug>
ln -s ../../../../comunicacao/_assets assets
ln -s ../../_estilo/tokens.css tokens.css
mkdir -p compositions
cp ../../_estilo/cards/abertura/index.html compositions/abertura.html
cp ../../_estilo/cards/legenda-de-passo/index.html compositions/legenda-de-passo.html
cp ../../_estilo/cards/carimbo/index.html compositions/carimbo.html
# lower-third e callout só se o vídeo usar
```

O card entra copiado e inteiro: a cópia dentro do projeto é o que o empacotador
do HyperFrames aceita (link para fora do projeto ele pula). Não mexa na cópia;
card que precisa mudar muda em `_estilo/cards/`, e a nota vira regra.

A raiz carrega os tokens e monta cada card como sub-composição, com o texto nos
slots por `data-variable-values`. O mesmo card entra quantas vezes for preciso
com o mesmo `data-composition-id`, um host por instância:

```html
<head>
  <link rel="stylesheet" href="tokens.css" />
  <!-- GSAP e o carimbo legível por máquina, como acima -->
</head>
<body>
<div id="main" data-composition-id="main" data-start="0" data-width="1920" data-height="1080" data-duration="42">
  <div id="slot-abertura" data-composition-id="abertura" data-composition-src="compositions/abertura.html"
    data-variable-values='{"secao":"Manual · Ouvidoria","titulo":"Registrar uma manifestação pelo formulário","papel":"Sem login"}'
    data-start="0" data-duration="4" data-track-index="1" data-width="1920" data-height="1080"></div>

  <section id="c-tarefa" class="clip" data-start="4" data-duration="33" data-track-index="2">
    <!-- a réplica da tela, dentro de um .camera -->
  </section>

  <div id="slot-passo-1" data-composition-id="legenda-de-passo" data-composition-src="compositions/legenda-de-passo.html"
    data-variable-values='{"numero":"1","texto":"Abra o formulário pelo **QR do cartaz**."}'
    data-start="4" data-duration="5" data-track-index="3" data-width="1920" data-height="1080"></div>
  <div id="slot-passo-2" data-composition-id="legenda-de-passo" data-composition-src="compositions/legenda-de-passo.html"
    data-variable-values='{"numero":"2","texto":"Escreva o relato em **O que aconteceu?**."}'
    data-start="9" data-duration="5" data-track-index="4" data-width="1920" data-height="1080"></div>

  <div id="slot-carimbo" data-composition-id="carimbo" data-composition-src="compositions/carimbo.html"
    data-variable-values='{"titulo":"Registrar uma manifestação pelo formulário","carimbo":"Manual · retrata o app em v0.195.1 · gerado em 13/10/2026"}'
    data-start="37" data-duration="5" data-track-index="1" data-width="1920" data-height="1080"></div>
</div>
<script>
window.__timelines = window.__timelines || {};
const tl = gsap.timeline({ paused: true });
/* ... os movimentos da tarefa ... */
tl.to({}, { duration: 42 }, 0); // âncora: o timeline preenche o slot inteiro
window.__timelines["main"] = tl;
</script>
</body>
```

- Os passos encostam: o `data-start` de um é o fim do anterior, alternando
  entre duas trilhas. A placa fica no lugar e só o texto troca.
- O slot de um card de apoio vai até 60 s (a âncora do card); o de abertura e
  carimbo, até 5 s. Slot maior que a âncora trava o conferidor.
- `**palavra**` no slot sai em negrito: é a palavra da tela, como na página.
- Cor e fonte só por `var(--...)`. Na réplica, a cor é a da classe do app:
  `var(--color-slate-500)` para `text-slate-500`.

**Movimento, em GSAP** (o porquê de cada um está no `DESIGN.md`):

```js
/* Push-in no elemento do passo: o wrapper .camera (com
   data-layout-allow-overflow) aproxima e centraliza o botão citado. */
tl.fromTo("#camera", { scale: 1, x: 0, y: 0 },
  { scale: 1.08, x: 120, y: 40, duration: 2.5, ease: "power1.inOut" }, 4);
/* Câmera que nunca para: deriva lenta até o próximo movimento. */
tl.to("#camera", { scale: 1.11, duration: 3, ease: "none" }, 6.5);
/* Transição com rastro: a tela A sai, a B entra pelo lado oposto. */
tl.fromTo("#tela-a", { x: 0, filter: "blur(0px)", opacity: 1 },
  { x: -300, filter: "blur(24px)", opacity: 0, duration: 0.35, ease: "power2.in" }, 8.8);
tl.fromTo("#tela-b", { x: 300, filter: "blur(24px)", opacity: 0 },
  { x: 0, filter: "blur(0px)", opacity: 1, duration: 0.6, ease: "power2.out" }, 9);
```

- O primeiro movimento de um alvo é `fromTo`; os seguintes do mesmo alvo são
  `to`. Dois `fromTo` no mesmo alvo dão o aviso
  `gsap_repeated_fromto_without_baseline` no `check`.
- Cor que muda (botão que acende, campo que ganha borda) vira duas camadas, uma
  com o token de cada estado, e um fade de `opacity` entre elas. Tween de cor
  com `var()` ou com o `oklch` do Tailwind não interpola de forma confiável.

**Os pilotos são o molde.** `contas-medicas/decidir-na-validacao` e
`ouvidoria/redirecionar-o-caso-para-outra-area` (issue #1231) foram os
primeiros no estilo: a janela do navegador, a casca do app (barra lateral e
topo) desenhada em 1280x643 e ampliada 1,25x, a câmera, o marcador e o dedo.
Comece copiando o mais parecido com a sua tarefa. O que eles ensinaram:

- A tela sai do código do frontend e do print atual do roteiro, nesta ordem.
  A tela de um vídeo antigo é rascunho: a do Redirecionar estava 54 versões
  atrás (botão desligado cinza no lugar do apagado, ajuda dos campos faltando).
- Medida pelo `offsetLeft`/`offsetTop` até a raiz do app, que ignora a câmera e
  a rolagem; a rolagem entra na conta à mão. A medida nunca é feita na
  montagem (veja a regra de 14/10/2026 no fim deste arquivo): o alvo é uma
  função, e o GSAP a chama quando o tween começa.
- Tela que muda de estado (fila relida, janela que abre, campo preenchido) é
  um quadro por estado, um em cima do outro, e a troca é de `opacity`. Nada de
  `display` no timeline (o `check` trava) e nada de layout que reflui no meio
  do vídeo.
- Helper do timeline sem `if`: o `check` lê os dois ramos e acusa `fromTo`
  repetido e tween sobreposto que não existem. Estado inicial escondido vai no
  CSS (`opacity: 0`), e a câmera ganha um `tl.set("#camera", { scale: 1, x: 0,
  y: 0 }, 0)` de base; daí em diante, só `to`.
- A composição tem no máximo 300 linhas fora do `<style>` (aviso
  `composition_file_too_large`). Junte em linhas longas o HTML da réplica.
- Classe da réplica não repete classe de card (`.tela`, `.cartao`, `.cabeca`,
  `.titulo`, `.texto`): depois de montado, o card divide a página com a
  réplica e a regra pega os dois. O conferidor trava.
- Popup do navegador (lista do seletor, aviso de download) fica fora da caixa
  que corta, por cima do app, como o navegador desenha.

**Réplica a partir dos vídeos antigos.** As composições de
`_estilo/pendentes-de-rerender.txt` já têm as telas desenhadas (palco de
960x540 ampliado 2x, celular, janela, dedo, marcadores). Elas servem de ponto
de partida para o que os pilotos não têm (celular, e-mail, portal do setor):
confira contra o código, troque cada hex pelo token e apague a linha do vídeo
na lista no mesmo PR que o refaz. Os hex mais comuns:

| Hex antigo | Token |
| --- | --- |
| `#2B2E7E` | `var(--color-primary)` |
| `#3B6FB6` | `var(--color-primary-light)` |
| `#1E293B` | `var(--color-text)` |
| `#64748B` | `var(--color-text-secondary)` |
| `#E2E8F0` | `var(--color-border)` |
| `#0F172A` | `var(--color-slate-900)` |
| `#334155` | `var(--color-slate-700)` |
| `#475569` | `var(--color-slate-600)` |
| `#94A3B8` | `var(--color-slate-400)` |
| `#F1F5F9` | `var(--color-slate-100)` |
| `#F8FAFC` | `var(--color-slate-50)` |
| `#EEF1F6` (palco) | `var(--video-palco)` |

**Copiou pasta? Troque o carimbo primeiro.** `modulo`, `slug` e `pagina` vêm
colados do vídeo antigo, e o conferidor compara os três com a página que exibe
o vídeo: carimbo do vizinho trava o CI.

## Os gates, nesta ordem

1. **Texto da tela (antes de renderizar):** todo texto visível (slots, réplica)
   passa pelo humanizer (ADR 0071) e pela varredura anti-técnica:
   `migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend,
   frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt`,
   mais travessão e meia-risca. Cada ocorrência vira linguagem funcional ou sai.
2. **Check e anel:** `npx --yes hyperframes@0.8.41 check` na pasta da
   composição, com 0 erros e 0 avisos. Depois o gate do anel:

   ```bash
   python3 tools/anel_video_manual.py \
     --composicao docs/manual/video/<modulo>/<slug>/index.html
   ```

   Ele abre a composição no navegador, espera a fonte como o render espera e,
   de 0,1 em 0,1 s, compara o anel aceso (`#mk`) com o alvo que o `marca()`
   declara em `data-alvo`. Reprova o anel fora do alvo, com folga de mais de
   20 px de um lado, sem `data-alvo`, ou passando por cima de texto visível de
   fora do alvo. O `check` não vê nada disso: para ele o anel é um elemento
   válido em qualquer lugar do quadro.
3. **Draft:**

   ```bash
   npx --yes hyperframes@0.8.41 render --quality draft \
     -o ../../../public/video/<modulo>/<slug>.mp4
   ```

4. **Strips de cada corte:**

   ```bash
   python3 tools/strips_video_manual.py \
     --mp4 docs/manual/public/video/<modulo>/<slug>.mp4 \
     --composicao docs/manual/video/<modulo>/<slug>/index.html
   ```

   O gate tira dez quadros de cada lado de cada corte (início e fim de cada
   clipe e de cada card) e reprova quadro preto e legenda sem fundo (quadro com
   card de legenda e sem a placa no retângulo do `tokens.css`). Passou? Olhe as
   strips mesmo assim: a de cima é antes do corte, a de baixo é depois. A placa
   fica parada enquanto o texto troca? A transição tem rastro? O dedo está no
   botão que a legenda cita?
5. **Quadros a cada 3 s:** `ffmpeg -i <mp4> -vf fps=1/3 frames/%02d.png` e olhe.
   Marcador em cima do elemento certo, texto legível, a tela batendo com o app
   real. O `check` não vê nada disso.
6. **`VERIFY.md`** ao lado da composição, com o que foi conferido de verdade:

   ```markdown
   # VERIFY: <título da tarefa>

   - Draft: docs/manual/public/video/<modulo>/<slug>.mp4, NN s, sha256 <12 primeiros>
   - Check (HyperFrames 0.8.41): 0 erros, 0 avisos; gate do anel OK
   - Strips: N cortes, gate OK; olhei corte-01 a corte-NN
   - Quadros a cada 3 s: o que conferi (marcador, dedo, legenda, tela igual ao app)
   - Texto da tela: humanizer e varredura anti-técnica, sem achados
   - Ressalvas: o que não deu para conferir, e por quê
   - Render final: caminho, NN s, sha256 <12 primeiros>
   ```

7. **Conferidor:** `python3 tools/checar_video_manual.py --dir docs/manual`.
8. **Render final, sem esperar ninguém:** com os gates acima limpos, renderize
   de novo com `--quality high` no mesmo caminho; é ele que a publicação sobe.
   Copie o MP4 para `local/manual-video-masters/<modulo>/<slug>.mp4` da árvore
   principal (o worktree some na subida e o MP4 não vem no clone) e ponha o
   caminho no corpo do PR. O vídeo não espera OK humano (emenda de 14/10/2026
   à ADR 0057): o PR sobe como qualquer outro. Na campanha de rerender dos
   vídeos antigos, a Folha de contato (os quadros-chave de todos os vídeos do
   módulo numa imagem e um MP4 inteiro) vai no corpo do PR como evidência.

## Nota vira regra

Toda nota humana sobre um vídeo, que agora chega com ele já no ar, vira duas
coisas no mesmo PR: o conserto neste vídeo
e uma regra, para a nota não voltar no próximo. Nota de cor, fonte ou card vai
para o `DESIGN.md` ou para o card em `_estilo/cards/`. Nota de ritmo, montagem
ou gate vai para a lista abaixo, com a data e o vídeo de origem. Se a regra dá
para checar por máquina, ela vira teste em `tools/` em vez de linha aqui. Antes
de compor um vídeo novo, leia a lista.

## Regras que vieram de nota

Formato: `- DD/MM/AAAA, <modulo>/<slug>: a regra, no imperativo.`

- 14/10/2026, contas-medicas/decidir-na-validacao e
  ouvidoria/redirecionar-o-caso-para-outra-area: nunca meça o layout na
  montagem. O script da composição roda antes de a fonte do app carregar, o
  layout ainda está na fonte de reserva (mais larga), e toda medida feita ali
  sai errada: o anel caiu ao lado do botão Validação, cortando "Painel", e
  desceu abaixo da Leitura da IA, que quebrava em mais linhas. Valem o anel,
  o dedo, a câmera, a rolagem e a posição de popup. Declare o alvo como
  função (`alvo("id", rolagem)` dos pilotos) e passe ao GSAP valores-função
  (`x: () => a.caixa().x`), que ele calcula quando o tween começa; o render
  só busca o primeiro quadro depois da fonte. Popup que depende do layout
  ganha a posição num `tl.set` com valor-função, não num `style.top` solto.
- 14/10/2026, mesmos vídeos: o anel contorna o que a pessoa lê, inteiro, com
  ar em volta. Campo é rótulo e valor juntos (o anel só no valor cortou o
  rótulo "SETOR"); texto curto num bloco de largura cheia ganha
  `width: fit-content` para o anel não sobrar pela linha toda; e a folga do
  anel (8 px vezes o zoom) não pode cair em cima de vizinho: o aviso de
  download afinou para o anel não cortar o número do sino. O gate do anel
  (`tools/anel_video_manual.py`) trava os três casos.
- 14/10/2026, ouvidoria/redirecionar-o-caso-para-outra-area: a faixa azul de
  item escolhido numa lista é filha da lista e herda o `padding` das linhas
  (`.lista-sel div`); zere o `padding` dela, ou o texto da faixa desce e
  anda para a direita da linha que ela cobre. Confira a faixa no quadro em
  que ela acende.
