# O vídeo que faltou: Arquivar um caso encerrado

**Um vídeo, um terminal.** O PR #783 deixou este de fora porque a página
afirmava algo errado (Arquivar e Desarquivar no menu da linha); a página foi
corrigida no #785. Pode rodar em paralelo com o `11`: só toca a composição
deste vídeo e o frontmatter `video` desta página.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git.

```
Produza o único Vídeo de tarefa que falta na seção Ouvidoria do Manual do usuário, no repo pedrorezendefig/hospital-reunioes: a página ouvidoria/arquivar-um-caso-encerrado.md. Ela ficou de fora do PR #783 porque afirmava algo errado, e foi corrigida no PR #785, já na main: Arquivar e Desarquivar são o botão visível da própria linha, não item do menu.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal, /Users/pedrorezende/PedroDev/Hospital, que é compartilhada e costuma estar numa branch antiga. Você NÃO trabalha nela. Primeiro ato:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/video-ouvidoria-arquivar -b docs/video-ouvidoria-arquivar origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/video-ouvidoria-arquivar
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..
Se branch ou pasta já existirem de uma tentativa anterior com PR mergeado ou fechado (gh pr list --head docs/video-ouvidoria-arquivar --state all), remova os restos e crie de novo; se o PR estiver aberto, PARE e reporte. Antes de cada commit, git branch --show-current tem que devolver docs/video-ouvidoria-arquivar e git rev-parse --show-toplevel a pasta do worktree. Nunca toque na árvore principal.

O TRABALHO
Siga o prompt docs/prompts/03-videos-ouvidoria.md inteiro (leia-o: a receita em .claude/skills/manual/references/video-de-tarefa.md, o carimbo em três lugares com a versão de produção, o gate anti-técnica, a auto-revisão de frames com ffmpeg olhando imagem por imagem, PII, a cópia do MP4 para /Users/pedrorezende/PedroDev/Hospital/local/manual-video-masters/ouvidoria/), mas só para este vídeo. Reuse a réplica da fila que já está em docs/manual/video/ouvidoria/ (copie a pasta de um vídeo vizinho e troque o carimbo antes de qualquer coisa: modulo, slug, pagina, app_version, gerado_em, nos três lugares). O vídeo mostra o botão Arquivar na linha do caso encerrado, a confirmação, o filtro Arquivados e o botão Desarquivar, na ordem dos passos da página. Se o /api/health de produção recusar conexão, use o last_app_version de docs/spec/deploy/state.json e diga no PR.

O QUE NÃO FAZER
Não toque em nenhuma outra página, em nenhum outro vídeo, em prints, em tema, em tools/. Não publique, não mergeie.

O PR
/ship "docs(manual): video de tarefa de arquivar um caso encerrado" --no-merge --skip-review --no-bump
Confirme quando o /ship avisar que a branch não é a main. Todo comentário em PR começa com <!-- automacao --> na primeira linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo alheio. Confira git branch --show-current antes de cada commit.

REPORTE NO FIM
O que a auto-revisão de frames pegou, a versão carimbada e de onde veio, e o caminho do MP4 nos masters.
```
