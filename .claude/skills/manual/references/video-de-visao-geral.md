# Vídeo de visão geral

Um vídeo por módulo, na abertura do módulo (`<modulo>/index.md`): o módulo
ponto a ponto, cada funcionalidade relevante uma vez, na ordem em que a pessoa
usa, com dados de exemplo. Narrado com a voz A, com a fala escrita na tela
palavra a palavra, sobre o print real do app animado. Feito em Remotion pela
skill global `motion`, no molde da `/divulgar` (ADR 0076, que emenda a 0072).
"Conheça a plataforma" é o de Primeiros passos, e a página inicial do Manual
mostra o mesmo arquivo. O Admin e a Central de Comando ficam sem vídeo.

**Página de tarefa não tem vídeo** (ADR 0072). O Vídeo de tarefa saiu do
Manual em 14/10/2026.

**Vídeo de visão geral não é Vídeo de percepção de valor.** O de percepção mora
em `docs/comunicacao/`, é do diretor e fala de uma entrega. Este é de quem usa
e fala do módulo como ele está no ar.

**Quando refazer.** Todo PRD que muda uma página de um módulo refaz o vídeo
daquele módulo, uma vez por PRD, na Fatia de manual. A exceção é escrita na
fatia ("o vídeo segue válido porque ...") e o revisor confere; nesse caso o PRD
entra em `prds_cobertos` do `meta.json` sem render novo, e o motivo vai no
corpo do PR. O `meta.json` guarda a lista dos PRDs que o vídeo cobre, e a
`/montar-manual` acusa `video-desatualizado` quando uma página do módulo cita
no `prd:` um PRD fora da lista.

**A composição HyperFrames antiga** (pasta com `index.html`, no Estilo do
manual de `docs/manual/video/_estilo/`) continua aceita pelo conferidor, com
os gates de antes, até o vídeo do módulo ser refeito por esta receita. A fatia
que sobe o vídeo novo apaga, no mesmo PR, a pasta HyperFrames do módulo e a
linha dele em `_estilo/pendentes-de-rerender.txt`, se houver; o `_estilo/` sai
com o último módulo. A receita HyperFrames está no histórico do git deste
arquivo (`git log -- .claude/skills/manual/references/video-de-visao-geral.md`).

## Onde cada coisa mora

- **Composição (a fonte, versionada):** `docs/manual/video/<modulo>/<slug>/`,
  no molde da `video/` da `/divulgar`:
  - `roteiro.md`: o briefing da skill `copy`, os três ganchos e o escolhido, a
    narração final e a tabela de cenas (fala, tela, transição de entrada,
    paradas planejadas em segundos).
  - `narracao.txt`: o texto que a voz A lê, um parágrafo por cena.
  - `tempos.json`: o tempo de cada palavra no formato da skill `motion`
    (`references/tempos.md`).
  - `cena/`: a composição Remotion (`src/videos/<Nome>/` do projeto de
    trabalho, com o `<Nome>.tsx` e o que mais a cena usar).
  - `meta.json`: o carimbo e os `prds_cobertos` (abaixo).
  - `VERIFY.md`: a saída de cada gate.
- **Telas:** saem do Roteiro de prints do módulo (`docs/manual/prints/<modulo>.py`,
  ADR 0057, decisão 7), uma função `video-NN-<passo>` por tela no `PRINTS`, em
  1920x1080 e sem balão numerado (no vídeo, quem aponta é o cursor e o
  destaque). Elas caem em `docs/manual/src/assets/<modulo>/` com os prints das
  páginas, versionadas, e o projeto de trabalho copia de lá. Print novo entra
  no roteiro, nunca à mão.
- **Projeto de trabalho do Remotion:** `${TMPDIR}manual-video/<modulo>/`, uma
  cópia do projeto modelo da skill `motion` com `node_modules`,
  `public/narracao.wav` e `out/`. É descartável: tudo que precisa voltar fica
  na composição.
- **MP4 renderizado (o master):** `~/Videos/Hospital/Manual/<modulo>/<slug>.mp4`,
  **fora do repositório**, nem rascunho fica no repo (regra 10 do CLAUDE.md
  global). O `publicar.sh` copia de lá direto para a pasta de montagem, sempre
  por cima, então o que vai ao ar é sempre o master atual. `MANUAL_VIDEOS`
  troca a pasta dos masters. Master substituído num re-render vai antes para
  `~/Videos/Hospital/Manual/<modulo>/anteriores/`, nunca é sobrescrito.
- A abertura do módulo exibe pelo frontmatter `video: <slug>`; o tema monta o
  `<video>` com a capa, com som e sem autoplay. "Conheça a plataforma" vai no
  `index.md` de `primeiros-passos/` e no `index.mdx` da página inicial, com o
  mesmo slug; a composição e o MP4 moram em `primeiros-passos/`.

`python3 tools/checar_video_manual.py --dir docs/manual` trava se a abertura
exibe vídeo sem composição, se uma página que não é abertura declara vídeo, se
algum MP4 foi parar na árvore versionada e, na composição nova, se falta o
`roteiro.md`, as cenas em `cena/*.tsx`, o `VERIFY.md` ou o `meta.json`, se o
carimbo está incompleto ou é de outra página, ou se faltam os `prds_cobertos`.

### O `meta.json`

```json
{"modulo": "contas-medicas", "slug": "o-caminho-de-uma-conta",
 "pagina": "contas-medicas/index.md",
 "prds_cobertos": [1080, 1150, 1259, 1303],
 "app_version": "0.206.0", "gerado_em": "<ISO-8601 com timezone>",
 "duracao_s": 165, "paradas": ["161-165"]}
```

- `pagina` é a abertura que exibe o vídeo ("Conheça a plataforma" carimba
  `primeiros-passos/index.md`). Copiou a pasta de outro vídeo? Troque
  `modulo`, `slug` e `pagina` primeiro: carimbo do vizinho trava o CI.
- `app_version` é a versão em produção, `last_app_version` de
  `docs/spec/deploy/state.json`.
- `prds_cobertos` é todo PRD citado no `prd:` das páginas do módulo na hora do
  render (abertura, tarefas, Como funciona e Novidades), mais o PRD da fatia:

  ```bash
  grep -rh '^prd:' docs/manual/src/content/docs/<modulo>/ | sed 's/#.*//' \
    | grep -oE '[0-9]+' | sort -nu | paste -sd, -
  ```

- `paradas` são as janelas de imagem parada planejada (a assinatura), as
  mesmas que o gate anti-travamento recebe.

O carimbo é só este arquivo: nada de versão, PRD ou data escritos no vídeo.

## Especificação

1920x1080, 30 fps constante, **2 a 3 min** (Tecnologia até 3 min e meio),
narrado com a voz A e legível no mudo: a fala aparece na tela como texto
cinético, palavra a palavra, quando é dita (`<Fala>` da skill motion). Print
real do app animado (zoom, foco, cursor, destaque) entre cenas de tipografia
cinética. Identidade da `marca-hsm` e dos tokens do app (HP Simplified,
azul-marinho, logo), sem grão de filme.

**Orçamento.** O `publicar.sh` reencoda cada vídeo para 720p H.264 com áudio
AAC de 64 kbps e trava, com a regra e o vídeo na mensagem: **até 10 MB por
vídeo**, **até 60 MB somando** os vídeos, um vídeo por módulo e o site inteiro
**até 90 MB** (o site sem vídeo mede uns 20 MB). Confira antes do PR com
`bash docs/manual/publicar.sh --dry-run`: ele monta, reencoda, mede e para.
Vídeo que passa de 10 MB é vídeo longo demais ou com movimento demais; encurte
a cena, não a qualidade.

**Roteiro fixo:**

1. **Gancho (2 a 4 s):** o momento do dia a dia que o módulo resolve, em uma
   frase falada e escrita. Nada de tela de título com metadado.
2. **O módulo ponto a ponto (o vídeo é isso):** cada funcionalidade relevante
   aparece uma vez, na ordem em que a pessoa usa. A fonte é a abertura do
   módulo ("O caminho de ponta a ponta"), as Páginas de tarefa e o
   `novidades.md`; fato só com fonte. Um caso de exemplo anda do começo ao fim;
   quem muda de papel no meio (o setor que responde, o facilitador que assina)
   é dito pelo nome do papel. Uma frase por cena.
3. **Fecho:** uma virada curta (o que a pessoa ganha) e a assinatura com a logo
   do hospital **inteira e parada** (`marca-hsm`), a única parada planejada.

Configuração que só o admin faz fica na Página de tarefa, fora do vídeo.

## Montar

**Antes de tudo, leia as skills globais:** `motion` (o `SKILL.md` e, inteiros,
`references/guia-motion.md`, `references/catalogo.md` e `references/tempos.md`),
`narracao`, `copy` e `marca-hsm`. Os valores do guia (ritmo, easing,
transições, checklist) são o padrão; esta receita só diz o que muda no Manual.
O passo a passo da `/divulgar` (`.claude/skills/divulgar/SKILL.md`, "Passo 1:
o vídeo") é o molde: o que estiver lá e não for contrariado aqui vale.

1. **Copy e roteiro.** Briefing e três ganchos pela skill `copy` (nota mínima
   12 de 14): quem vê é quem usa o módulo no hospital, a ideia é o que o
   módulo faz por ele, a prova são as páginas do módulo. Depois, a narração e
   todo texto de tela passam pela skill `humanizer` em modo embutido (ADR
   0071); a amostra de voz é o `roteiro.md` de outro Vídeo de visão geral já
   refeito (na falta, o de uma entrega em `docs/comunicacao/` feita em
   motion). Vocabulário do `CONTEXT.md`, nome de botão e de tela igual ao app.
   Gate anti-técnica no falado e no escrito: `migration, endpoint, API, PR,
   pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge,
   token, env, SQL, Supabase, Coolify, prompt`, mais travessão e meia-risca.
   Grave `roteiro.md` e `narracao.txt`.
2. **Telas.** Acrescente ao Roteiro de prints do módulo as funções
   `video-NN-<passo>` e rode o roteiro (receita em `prints.md`), com o app
   local na versão de produção e os dados de exemplo da faixa de id do módulo
   (os roteiros dividem o mesmo Supabase local). Confira a versão no rodapé do
   app antes de capturar: tela de versão velha mostra o app errado.
3. **Narração e tempos.**
   `python3 ~/.claude/voz/narrar.py --file <composição>/narracao.txt --output "$W/public/narracao.wav"`
   (voz A, skill `narracao`). Se o VoiceStudio falhar, pare e avise: nunca
   outra voz. Converta o `narracao.json` para o `tempos.json` da skill motion
   (uma cena por parágrafo; corrija a grafia, não os tempos) e grave na
   composição.
4. **Composição em Remotion**, no projeto de trabalho:

   ```bash
   W="${TMPDIR}manual-video/<modulo>"
   mkdir -p "$W" && cp -R ~/.claude/skills/motion/projeto/. "$W"/ && rm -rf "$W/node_modules"
   cp docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$W/public/fonts/"
   cp docs/comunicacao/_assets/logo-hsm.png "$W/public/"
   cp docs/manual/src/assets/<modulo>/video-*.png "$W/public/"
   (cd "$W" && npm install)
   ```

   `Config.setChromiumOpenGlRenderer('swangle')` no `remotion.config.ts`
   (skill `narracao`: sem isso o texto treme). A identidade do Hospital entra
   no projeto de trabalho como na `/divulgar` (HP Simplified em todo texto,
   `PALETA` com as cores do app e da `marca-hsm`, um acento só, logo só na
   assinatura). Uma cena por frase; cada tela entra na `<Camera>` com push-in,
   cursor fantasma e destaque no elemento que a fala cita. Nada parado mais de
   0,5 s, todo evento preso a uma palavra, uma transição diferente do catálogo
   em cada corte, `audio="narracao.wav"` no `<VideoMontado>`.
5. **Volta para o repo:** copie `src/videos/<Nome>/` para `cena/` da
   composição e grave o `meta.json`.

Render disputa a CPU: no máximo dois renders ao mesmo tempo na mesma máquina.

## Os gates, nesta ordem

1. **Tipos:** `npx tsc --noEmit` no projeto de trabalho, sem erro.
2. **Stills e draft:** stills no meio de cada cena, no pico de cada transição e
   dois quadros depois de cada palavra-chave
   (`node scripts/stills.mjs <Comp> out/stills 0.5 <quadros>`), e um draft
   (`npx remotion render src/index.ts <Comp> out/draft.mp4 --scale=0.5`).
   Abra e passe o checklist da seção 9 do guia da skill motion: telas iguais
   ao app, cada funcionalidade do módulo aparece, texto legível, zero jargão,
   zero travessão, o destaque em cima do elemento que a fala cita.
3. **Render final, direto no caminho do master,** sem esperar ninguém. Se já
   existe um master desse vídeo, ele sai do caminho antes, com a data dele:

   ```bash
   M="$HOME/Videos/Hospital/Manual/<modulo>"; mkdir -p "$M/anteriores"
   [ -f "$M/<slug>.mp4" ] && mv -n "$M/<slug>.mp4" \
     "$M/anteriores/$(date -r "$M/<slug>.mp4" +%F)-<slug>.mp4"
   (cd "$W" && npx remotion render src/index.ts <Comp> "$M/<slug>.mp4")
   rm -f "$W/out/draft.mp4"
   ```

   O `mv -n` não apaga nada: se o nome em `anteriores/` já existe, o master
   fica onde está. Some `-v2` ao nome e mova à mão antes de renderizar.
4. **Anti-travamento:** fps constante 30, nenhum congelamento de 0,5 s ou mais
   fora das `paradas` do `meta.json` e o MP4 tocando no Chrome real:

   ```bash
   bash .claude/skills/divulgar/scripts/gate-video.sh "$M/<slug>.mp4" --parada <ini>-<fim>
   ```

   Falhou, não entrega: conserte a cena, renderize de novo, rode de novo.
5. **Orçamento:** `bash docs/manual/publicar.sh --dry-run` passa nas travas, e
   o tamanho do vídeo depois do reencode vai no corpo do PR.
6. **`VERIFY.md`** ao lado da composição, com o que foi conferido de verdade:

   ```markdown
   # VERIFY: <nome do módulo>

   - tsc: 0 erros
   - Stills e draft: o que conferi (telas iguais ao app, destaque, fala, legibilidade)
   - Copy: nota N de 14; humanizer e varredura anti-técnica sem achados
   - gate-video.sh: fps 30/1, sem congelamento fora de <paradas>, tocou no Chrome
   - Orçamento: NN MB depois do reencode (teto 10 MB); soma NN MB (teto 60 MB)
   - Render final: ~/Videos/Hospital/Manual/<modulo>/<slug>.mp4, NN s, sha256 <12 primeiros>
   - Ressalvas: o que não deu para conferir, e por quê
   ```

7. **Conferidores:** `python3 tools/checar_video_manual.py --dir docs/manual`
   e `python3 tools/inventario_manual.py --dir docs/manual`, sem
   `video-desatualizado` no módulo.

O master mora fora do worktree e sobrevive à subida, que apaga o worktree.
Ponha o caminho e o sha256 no corpo do PR; o PR sobe como qualquer outro.

## Nota vira regra

Toda nota humana sobre um vídeo, que chega com ele já no ar, vira duas coisas
no mesmo PR: o conserto neste vídeo e uma regra, para a nota não voltar no
próximo. Nota de ritmo, montagem ou gate vai para a lista abaixo, com a data e
o vídeo de origem. Se a regra dá para checar por máquina, ela vira teste em
`tools/` em vez de linha aqui. Antes de compor um vídeo novo, leia a lista.

## Regras que vieram de nota

Formato: `- DD/MM/AAAA, <modulo>/<slug>: a regra, no imperativo.`

- 14/10/2026, contas-medicas/decidir-na-validacao e
  ouvidoria/redirecionar-o-caso-para-outra-area (vídeos HyperFrames): o
  destaque contorna o que a pessoa lê, inteiro, com ar em volta. Campo é
  rótulo e valor juntos (o anel só no valor cortou o rótulo "SETOR"), e a
  folga do destaque não pode cair em cima de vizinho.
