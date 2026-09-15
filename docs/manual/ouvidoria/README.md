# Manual da Ouvidoria (publicado na Vercel)

Fonte: `index.html` + `img/`. Logo e fonte não ficam aqui (ADR 0044, decisão 4): a cópia única mora em `docs/comunicacao/_assets/`.

Publicar (o script traz o logo e a fonte de `_assets`, monta a pasta fora do repo e sobe):

```bash
bash docs/manual/ouvidoria/publicar.sh            # publica
bash docs/manual/ouvidoria/publicar.sh --dry-run  # só monta a pasta, não publica
```

Os MP4 dos capítulos não ficam no git (`.gitignore` desta pasta) e cada deploy da Vercel
é uma cópia nova: sem os arquivos aqui, o manual sobe com os quadros de vídeo quebrados.
O script confere antes e para, dizendo quais faltam e o `curl` que baixa cada um do manual
publicado. Baixe, e só então publique. A conferência tem piso de sanidade: se o número de
`.mp4` que o `index.html` menciona não bater com o que o parsing reconheceu, o script aborta
em vez de publicar um vídeo a menos em silêncio.

Para abrir o `index.html` local sem publicar, copie os dois assets para cá primeiro:

```bash
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf docs/manual/ouvidoria/
```

## Prints de `img/`

São capturas reais do app rodando em localhost, tiradas com o Playwright do `python3` do
sistema (`page.screenshot`, `device_scale_factor=2`). A receita, na ordem:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`). Se o PostgREST não subir,
   o backend fica `degraded` e a tela da Ouvidoria trava em "Carregando manifestações...":
   `supabase stop` e `supabase start` recriam o container.
2. Stack do app com o código que o print vai mostrar: `bash .claude/skills/atualizar-app/scripts/apply.sh`.
   Confira depois que a tela nova está mesmo no build, senão o print sai da versão antiga.
3. Login como ouvidor (`admin@hospital.com`). A senha do ambiente local sai do
   `DEFAULT_USER_PASSWORD` do `.env`; se estiver vazio, defina uma pela API de admin do
   Supabase **local** (nunca de produção).
4. Navegue até a tela, abra o que precisa aparecer e capture.

Lista de `<select>`: o menu nativo do sistema operacional não sai na captura. Antes do
screenshot, transforme o campo em lista visível (`el.size = <n>`) e recorte a área dele.
É assim que `canal-de-origem.png` mostra as sete opções do "Canal de origem".
