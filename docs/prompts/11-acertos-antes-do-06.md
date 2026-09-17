# Acertos de fidelidade antes do 06

**Sozinho entre a Etapa B e o 06.** Os relatórios dos PRs #789, #790, #791 e
#793 apontaram o que a tela desmente e o que ficou sem print. Este prompt
fecha essas pontas numa sessão só: sobe a stack local com o código da main,
corrige as afirmações erradas (conferidas no código), põe print nas duas
páginas que ficaram sem, e refaz os prints dos cinco módulos para o menu sair
com o item **Ajuda**. Pode rodar em paralelo com o `12` (vídeo de Arquivar),
que não toca página nem print.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git.

```
Feche as pontas de fidelidade do Manual do usuário, no repo pedrorezendefig/hospital-reunioes, antes da passada de escrita (prompt 06). Quatro trabalhos, nesta ordem, numa sessão só.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal, /Users/pedrorezende/PedroDev/Hospital, que é compartilhada e costuma estar numa branch antiga. Você NÃO trabalha nela. Primeiro ato:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/acertos-antes-do-06 -b docs/acertos-antes-do-06 origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/acertos-antes-do-06
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..
  cp /Users/pedrorezende/PedroDev/Hospital/hospital-reunioes/.env hospital-reunioes/.env
Se branch ou pasta já existirem de uma tentativa anterior com PR mergeado ou fechado (gh pr list --head docs/acertos-antes-do-06 --state all), remova os restos e crie de novo; se o PR estiver aberto, PARE e reporte. Antes de cada commit, git branch --show-current tem que devolver docs/acertos-antes-do-06 e git rev-parse --show-toplevel a pasta do worktree. Nunca toque na árvore principal.

LEIA PRIMEIRO
1. .claude/skills/manual/SKILL.md e references/prints.md (a receita do balão, com o que o PR #793 acrescentou).
2. Os corpos dos PRs #790, #791, #789 e #793 (gh pr view N --json body -q .body): é de lá que vêm as pontas abaixo. Não invente lista: se um relatório citar algo que não está aqui, inclua.
3. CONTEXT.md, seção "Manual do usuário".

TRABALHO 1: A STACK LOCAL COM O CÓDIGO DA MAIN
Os prints da Etapa B saíram de uma stack em v0.135.0, sem o item Ajuda no menu (a regra da campanha era não reiniciar a stack compartilhada). Agora nenhum outro terminal usa a stack. Suba-a com o código do seu worktree, que é a origin/main:
  (cd /Users/pedrorezende/PedroDev/Hospital/hospital-reunioes && supabase start)
  bash .claude/skills/atualizar-app/scripts/apply.sh
Confira que a tela mostra o item Ajuda no fim do menu antes de capturar qualquer coisa. Se o apply.sh falhar, reporte com as últimas linhas e PARE.

TRABALHO 2: AS AFIRMAÇÕES QUE A TELA DESMENTE
Cada uma foi achada por uma sessão que parou em vez de reproduzir o erro. Confira no código (hospital-reunioes/, LEITURA APENAS) antes de escrever, e escreva a palavra da tela em negrito, como o molde manda:
a) reunioes/acompanhar-as-pendencias-na-lista.md, passo 6: "clique na linha" não abre nada. Quem abre é o botão com a lupa no fim da linha, com o rótulo "Abrir detalhes da pendência" (app/pendencias/page.tsx). Escreva o que a pessoa vê e clica.
b) reunioes/comentar-e-mencionar-numa-pendencia.md, passo 1: a metade da Lista tem o mesmo erro; a metade do Kanban está certa (o cartão inteiro abre).
c) reunioes/revisar-e-aprovar-a-ata.md, passo 1: o bloco Validação Necessária NÃO fica no fim da página. Ele fica no alto, logo abaixo dos cartões de Data, Horário, Tipo e Ações.
d) pops/index.md, "O caminho de ponta a ponta": a página pula o estado Em Elaboração. No código, a primeira conversa com o Consultor de POPs move a Versão de A Elaborar para Em Elaboração (iniciar_elaboracao_se_preciso), e é para Em Elaboração que toda devolução volta. O fluxograma da própria página (fluxo-caminho.svg, PR #789) já mostra essa caixa; a lista numerada precisa dizer o mesmo. Confira o nome do estado como a tela o mostra.
Mude só o que a tela desmente. Fora dessas quatro, nada de reescrever: o 06 é quem enxuga.

TRABALHO 3: PRINT NAS DUAS PÁGINAS QUE FICARAM SEM
As duas páginas do item 2a e 2b não receberam print nenhum porque a sessão parou nelas. Com o texto corrigido, amplie docs/manual/prints/reunioes.py (um print por mudança de tela, balão numerado igual ao passo, dentro do item da lista, como as outras páginas do módulo já têm) e insira as imagens. O passo do aviso no sino de quem foi mencionado só nasce com uma segunda pessoa logada: capture o sino da própria conta de exemplo se o roteiro conseguir gerar a menção, senão deixe esse passo sem print e diga no PR.

TRABALHO 4: REFAZER OS PRINTS DOS CINCO MÓDULOS
Com a stack na main, rode os cinco roteiros de ponta a ponta:
  python3 docs/manual/prints/primeiros-passos.py
  python3 docs/manual/prints/reunioes.py
  python3 docs/manual/prints/ouvidoria.py
  python3 docs/manual/prints/pops.py
  python3 docs/manual/prints/admin.py
Cada roteiro semeia o que precisa (idempotente). Depois OLHE cada imagem que mudou (git status mostra quais; abra com Read): o item Ajuda no menu, balão no elemento certo, nada de dado real, nenhum endereço local. Imagem que mudou por outro motivo além do menu merece uma linha no PR dizendo o quê. Se um roteiro quebrar com a tela nova, conserte o roteiro (é dele a responsabilidade de acompanhar a tela), nunca a tela.

O QUE NÃO FAZER
- Não edite hospital-reunioes/. Não toque em docs/manual/video/, nas composições nem no frontmatter `video` de página nenhuma: o prompt 12 está produzindo um vídeo em paralelo.
- Não toque em tema, componente, publicar.sh, astro.config.mjs, .github/ nem tools/*.py (exceto tools/test_prints_reunioes.py se o roteiro ganhar função nova).
- Não enxugue texto. Não publique. Não mergeie.
- Travessão e meia-risca são proibidos em tudo que o usuário vê.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/inventario_manual.py --dir docs/manual   (zero print-faltando; a única lacuna sem-video aceitável é ouvidoria/arquivar-um-caso-encerrado, que o prompt 12 fecha)
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): acertos de fidelidade e prints refeitos com a stack na main" --no-merge --skip-review --no-bump
Confirme quando o /ship avisar que a branch não é a main. Todo comentário em PR começa com <!-- automacao --> na primeira linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo alheio. Confira git branch --show-current antes de cada commit.

REPORTE NO FIM
As quatro afirmações corrigidas com o trecho antes e depois, os prints novos das duas páginas, quantas imagens mudaram por módulo ao refazer e por quê, o que ficou sem print, e qualquer outra afirmação que a tela nova desmentiu.
```
