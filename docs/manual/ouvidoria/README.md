# Manual da Ouvidoria (publicado na Vercel)

Fonte: `index.html` + `img/`. Logo e fonte não ficam aqui (ADR 0044, decisão 4): a cópia única mora em `docs/comunicacao/_assets/`.

Antes de publicar, copie os dois para esta pasta (ficam fora do git):

```bash
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf docs/manual/ouvidoria/
```

Publicação: copiar a pasta para fora do repo e rodar `npx vercel@latest deploy --prod --yes` (mesmo passo da `/divulgar`).
