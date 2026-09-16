# `/manual publicar`

Publica o site do manual na Vercel. Um comando só:

```bash
bash docs/manual/publicar.sh            # publica
bash docs/manual/publicar.sh --dry-run  # monta a pasta e para antes de publicar
```

O script faz, nesta ordem: lint do texto, build do Starlight, conferidor do
draft, reencode de cada MP4 para 720p, trava de 90 MB e deploy de uma cópia
**fora do repo** (a Vercel recusa publicar de dentro de um repositório com
outro projeto vinculado, a mesma pedra da `/divulgar`). O vínculo `.vercel/`
volta para `docs/manual/` e fica fora do git.

Antes de chamar, rode também
`python3 tools/checar_video_manual.py --dir docs/manual`: o `publicar.sh` acusa
MP4 que falta, não composição que falta.

Depois de publicar, registre o link (`https://manual-hsm.vercel.app`)
em comentário na issue ou no PRD que pediu a publicação, com `<!-- automacao -->`
na primeira linha.

## Quando a publicação para

- **"vídeo que a página usa e não existe":** o MP4 não está em
  `docs/manual/public/video/` nem em `docs/comunicacao/`. Renderize a composição
  (`references/video-de-tarefa.md`) antes de publicar; MP4 não vem no clone.
- **Trava de 90 MB:** o plano onde o site mora recusa acima de 100 MB. Corte ou
  encurte vídeo. Hospedar vídeo fora do site é decisão nova, com ADR próprio.
- **Lint ou conferidor do draft:** conserte o texto ou o frontmatter. Não use
  `--pular-build` para contornar: ele existe para republicar uma saída já
  conferida e já força `--dry-run`.

## Quem chama

- O humano, via `/manual publicar`, quando quer o site no ar agora.
- O `/deploy ship`, sozinho, depois de tirar o `draft` das páginas dos PRDs que
  subiram naquele deploy. Antes de tirar o draft, o Passo 9.6 confere que o MP4
  de cada Vídeo de tarefa existe **naquela máquina** (ele não vem no clone) e
  que Node, corepack e ffmpeg estão lá. Faltando qualquer um, ele para sem
  tocar em arquivo nenhum: página sem draft e sem publicação fica no
  repositório e fora do ar.

A Fatia de manual **não publica**: ela para no checkpoint de merge.
