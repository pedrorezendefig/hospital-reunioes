# Manual da Ouvidoria (publicado na Vercel)

Fonte: `index.html` + `img/`. Logo e fonte não ficam aqui (ADR 0044, decisão 4): a cópia única mora em `docs/comunicacao/_assets/`.

Publicar (o script traz o logo e a fonte de `_assets`, monta a pasta fora do repo e sobe):

```bash
bash docs/manual/ouvidoria/publicar.sh            # publica
bash docs/manual/ouvidoria/publicar.sh --dry-run  # só monta a pasta, não publica
```

Para abrir o `index.html` local sem publicar, copie os dois assets para cá primeiro:

```bash
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf docs/manual/ouvidoria/
```
