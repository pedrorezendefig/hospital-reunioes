# Vídeo de tarefa

Um vídeo por Página de tarefa: a mesma tarefa da página, do primeiro toque ao
resultado, para quem prefere ver a fazer. É a receita de vídeo da `/divulgar`
aplicada a uma tarefa só, e não uma demonstração de entrega.

**Vídeo de tarefa não é Vídeo de percepção de valor.** O de percepção mora em
`docs/comunicacao/`, é do diretor e fala de uma entrega. Este é do usuário e
fala de uma tarefa.

## Onde cada coisa mora

- Composição (a fonte, versionada): `docs/manual/video/<modulo>/<slug>/`, com
  `index.html`, `hyperframes.json`, `package.json`, `meta.json` e o link
  `assets -> ../../../../comunicacao/_assets` (fonte e logo únicos, ADR 0044).
- MP4 renderizado: `docs/manual/public/video/<modulo>/<slug>.mp4`, **fora do
  git** (o `.gitignore` do site já cobre `public/video/`).
- A página exibe pelo frontmatter `video: <slug>`; o tema monta o `<video>`.

`python3 tools/checar_video_manual.py --dir docs/manual` trava se a página
exibe vídeo sem composição, se falta carimbo ou se algum MP4 foi parar na
árvore versionada.

## Especificação

1920x1080, 30 fps, **30 a 60 s**, sem voz: o vídeo funciona no mudo, com
legenda de passo na tela. Réplica do app real, com as cores e a tipografia do
`globals.css` do frontend, HP Simplified por `@font-face` apontando para
`assets/fonts/HPSimplified_Rg.ttf`. Na dúvida entre bonito e fiel, fiel vence.

Roteiro fixo:

1. **Abertura (3 a 5 s):** título da tarefa no infinitivo, igual ao da página,
   e os selos de quem faz.
2. **A tarefa (o vídeo é isso):** os mesmos passos da página, na mesma ordem e
   com as mesmas palavras de tela, cada um com a legenda numerada ao lado da
   tela. Dedo fantasma toca, campo preenche, tela reage como o app reagiria.
3. **Fecho (3 a 5 s):** carimbo de geração.

**Carimbo, dois níveis.** Visível no fecho:
`Manual · retrata o app em v<X.Y.Z> · gerado em DD/MM/AAAA` (versão de
`hospital-reunioes/frontend/package.json` no momento da geração). Legível por
máquina, no `<head>` da composição, com os cinco campos que o conferidor cobra:

```html
<script type="application/json" id="manual-video-meta">
{"modulo": "ouvidoria", "slug": "<slug>",
 "pagina": "ouvidoria/<slug>.md", "prd": 731, "issues": [736],
 "app_version": "0.136.0", "gerado_em": "<ISO-8601 com timezone>"}
</script>
```

## Produzir

Leia as skills globais na ordem `/hyperframes` → `/hyperframes-core` →
`/hyperframes-animation`. Copiar a estrutura de uma composição pronta sai mais
barato que `init`: `docs/manual/video/ouvidoria/registrar-manifestacao-pelo-formulario/`
já tem o palco de 960x540 ampliado 2x, o celular, o dedo fantasma e os
marcadores; as réplicas de tela interna do app estão nos capítulos em
`docs/comunicacao/ouvidoria/manual-cap-*/video/`.

```bash
cd docs/manual/video/<modulo>/<slug>
npx --yes hyperframes@0.8.41 check
npx --yes hyperframes@0.8.41 render --quality draft \
  -o ../../../public/video/<modulo>/<slug>.mp4
```

## Os três gates, nesta ordem

1. **Anti-técnica (antes de renderizar):** varra todo texto visível procurando
   `migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend,
   frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt`,
   mais travessão e meia-risca. Cada ocorrência vira linguagem funcional ou sai.
2. **Auto-revisão de frames:** `ffmpeg -i <mp4> -vf fps=1/3 frames/%02d.png` e
   olhe as imagens. Marcador em cima do elemento certo, dedo no botão que a
   legenda cita, texto legível, a tela batendo com o app real. O `check` do
   HyperFrames não vê nada disso.
3. **OK humano no draft:** entregue o caminho do MP4 de draft ao Pedro (na
   `/onda`, em comentário no PR com `<!-- automacao -->` na primeira linha) e
   espere. Ajuste pedido = novo draft, novo OK. Só depois do OK vem o render
   final (`--quality high`), e ele é o que a publicação sobe.
