# `/manual publicar`

Tira o draft que a Action deixou e publica o site do manual na Vercel. Quem
roda é o humano, da máquina que tem os MP4 dos Vídeos de tarefa, depois do
deploy que fecha PRD com Fatia de manual: a Action pós-merge não publica, e o
aviso dela no PRD fechado lista o que saiu e o que ficou em draft (issue #951).

1. Atualize a `main` (o commit da Action pode ter tirado draft) e tire o draft
   do que ficou, com os PRDs do aviso:

   ```bash
   python3 tools/tirar_draft_manual.py --prd <N> [--prd <M>]
   ```

   Sem página em draft, ele diz isso e não mexe em nada. Saída 2 é o que falta
   nesta máquina, com o caminho na saída de erro: o MP4 (renderize pela
   `references/video-de-tarefa.md`), Node, corepack ou ffmpeg.
2. Publique:

   ```bash
   python3 tools/checar_video_manual.py --dir docs/manual
   bash docs/manual/publicar.sh            # publica
   bash docs/manual/publicar.sh --dry-run  # monta a pasta e para antes de publicar
   ```

   O conferidor de vídeo vem antes porque o `publicar.sh` acusa MP4 que falta,
   não composição que falta.
3. Se o passo 1 mudou página, leve a troca do draft à `main` por PR (`/ship`;
   a `main` é protegida). Sem ele, a próxima publicação, de outra máquina,
   esconde a página de novo.
4. Registre o link (`https://manual-hsm.vercel.app`) em comentário no PRD, com
   `<!-- automacao -->` na primeira linha.

O `publicar.sh` faz, nesta ordem: lint do texto, build do Starlight, conferidor
do draft, reencode de cada MP4 para 720p, trava de 90 MB e deploy de uma cópia
**fora do repo** (a Vercel recusa publicar de dentro de um repositório com
outro projeto vinculado, a mesma pedra da `/divulgar`). O vínculo `.vercel/`
volta para `docs/manual/` e fica fora do git.

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

- O humano, via `/manual publicar`, depois do deploy que fecha PRD com Fatia
  de manual (o aviso da Action no PRD lembra), ou quando quer o site no ar
  agora.
- O rabo (`fechar_onda.py`) não publica nem tira draft (ADR 0068): quem tira o
  `draft` das páginas dos PRDs que subiram é uma Action no push da `main`,
  depois do registro, e ela não publica. Antes de tirar o draft, o
  `tools/tirar_draft_manual.py` confere que o MP4 de cada Vídeo de tarefa
  existe **naquela máquina** (ele não vem no clone) e que Node, corepack e
  ffmpeg estão lá. Faltando qualquer um, ele sai bloqueado sem tocar em nada:
  basta uma página com vídeo para o lote inteiro ficar em `draft` e fora do ar
  até o humano rodar o `/manual publicar` numa máquina que tenha tudo.

A Fatia de manual **não publica**: ela para no PR verde, fora do rabo, e quem
viu o draft do vídeo roda o `fechar_onda.py`.
