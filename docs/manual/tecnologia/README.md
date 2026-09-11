# Manual da Tecnologia (publicado na Vercel)

Fonte: `index.html`. Logo e fonte não ficam aqui (ADR 0044, decisão 4): a cópia única mora em `docs/comunicacao/_assets/`. Os vídeos (`video-*.mp4`) ficam fora do git.

Publicar (o script traz o logo, a fonte e os vídeos, monta a pasta fora do repo e sobe):

```bash
bash docs/manual/tecnologia/publicar.sh            # publica
bash docs/manual/tecnologia/publicar.sh --dry-run  # só monta a pasta, não publica
```

Para abrir o `index.html` local sem publicar, copie os dois assets para cá primeiro:

```bash
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf docs/manual/tecnologia/
```

Os vídeos vêm dos projetos HyperFrames em `docs/comunicacao/tecnologia/`, renomeados para `video-<capítulo>.mp4`.
