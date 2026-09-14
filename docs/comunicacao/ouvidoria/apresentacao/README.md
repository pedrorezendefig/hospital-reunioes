# Apresentação da Ouvidoria (PowerPoint)

Deck de 35 slides para o diretor apresentar o módulo às áreas do hospital. Espelha o
manual publicado (`docs/manual/ouvidoria/index.html`), com os prints reais de
`docs/manual/ouvidoria/img/` e os 7 vídeos de capítulo embutidos. Mostra o sistema na
versão 0.116.1 (a constante `VERSAO_APP` no `gerar.py`).

```bash
uv run docs/comunicacao/ouvidoria/apresentacao/gerar.py               # gera ouvidoria-apresentacao.pptx (~10 MB, vídeos em 720p)
uv run docs/comunicacao/ouvidoria/apresentacao/gerar.py --sem-videos  # versão leve, sem MP4 (~6 MB)
```

- `gerar.py`: o texto dos slides mora aqui. Manual mudou? Ajuste e rode de novo.
- `img/`: prints das telas que ainda não estão no manual publicado (devolução à Ouvidoria,
  arquivar, apagar). Tirados do app rodando em localhost com o Playwright do python3 do
  sistema, na versão que a capa anuncia. Quando o manual for atualizado, estes prints podem
  migrar para `docs/manual/ouvidoria/img/` e a constante `IMG_NOVA` deixa de ser usada.
- `modelo.pptx`: arquivo vazio exportado pelo Keynote. Só serve para trazer um modelo de
  notas do apresentador que Keynote e PowerPoint aceitam. Não edite.
- `videos/` e o `.pptx` gerado ficam fora do git. Os vídeos são baixados do manual na Vercel
  na primeira execução (precisa de `ffmpeg` para o quadro de capa de cada vídeo).
- A fonte é HP Simplified. Instale `docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf` na
  máquina que apresenta, senão o Office troca a fonte.
