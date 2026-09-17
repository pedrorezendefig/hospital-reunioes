# Tema didático: o site aprende a mostrar passo, figura, aviso e capa

**Sozinho, antes dos prompts 08 e 09.** Mexe nos arquivos compartilhados do site
(tema, componente da página, `publicar.sh`, lint), por isso nenhum outro
terminal do Manual pode estar aberto ao mesmo tempo, exceto os quatro de vídeo
(01 a 04), que não tocam nenhum desses arquivos.

Nenhuma página muda de conteúdo aqui. É a fundação da camada didática (ADR
0057, emenda de 17/09/2026): depois deste PR, os prompts 08 (prints com balão)
e 09 (fluxogramas) só precisam escrever Markdown e rodar roteiro.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git. O [README](README.md) diz a ordem de tudo.

```
Prepare o tema do Manual do usuário para a camada didática, no repo pedrorezendefig/hospital-reunioes. Nenhuma página de conteúdo muda neste trabalho: é só o site aprendendo a desenhar o que os próximos prompts vão escrever.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal do repositório, /Users/pedrorezende/PedroDev/Hospital, que costuma estar numa branch antiga e é compartilhada com outros terminais abertos AO MESMO TEMPO. Você NÃO trabalha nela. Seu primeiro ato é criar um worktree próprio, a partir de origin/main, e entrar nele:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/tema-didatico -b docs/tema-didatico origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/tema-didatico
Se a branch ou a pasta já existirem de uma tentativa anterior deste mesmo prompt: veja com `gh pr list --head docs/tema-didatico --state all` se o PR dela já foi mergeado ou fechado. Se foi, remova os restos (git -C /Users/pedrorezende/PedroDev/Hospital worktree remove --force /Users/pedrorezende/PedroDev/Hospital/.worktrees/tema-didatico; git -C /Users/pedrorezende/PedroDev/Hospital branch -D docs/tema-didatico) e crie de novo. Se o PR ainda estiver aberto, PARE e reporte: alguém pode estar trabalhando nela.

A pasta de trabalho persiste entre os seus comandos, mas confira antes de cada commit:
  git branch --show-current      (tem que devolver docs/tema-didatico)
  git rev-parse --show-toplevel  (tem que devolver /Users/pedrorezende/PedroDev/Hospital/.worktrees/tema-didatico, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca edite arquivo fora do worktree, nunca toque na árvore principal. Ao terminar, não remova o worktree: a próxima rodada deste prompt sabe lidar com ele.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho dentro dele é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..

LEIA PRIMEIRO, NESTA ORDEM
1. docs/adr/0057-*.md, inteiro, com atenção à emenda de 17/09/2026: é ela que define o que você vai construir (decisões 2, 4, 10, 13 e 14 emendadas).
2. CONTEXT.md, seção "Manual do usuário": os termos Print de passo, Aviso destacado e Fluxograma de caminho.
3. .claude/skills/manual/SKILL.md e references/prints.md: o molde que as páginas vão seguir. O tema tem que desenhar exatamente esse molde.
4. docs/manual/src/components/MarkdownContent.astro, docs/manual/src/styles/tema.css, docs/manual/publicar.sh e tools/lint_manual.py, que são os arquivos que você vai mudar.
5. hospital-reunioes/frontend/src/app/globals.css (LEITURA APENAS): as cores e a tipografia do app, que o tema já usa e o balão e o fluxograma vão usar.

O QUE ENTREGAR, em ordem

1. O PASSO COM NÚMERO GRANDE E A FIGURA DENTRO DO PASSO
Nas Páginas de tarefa (as que têm `papel` no frontmatter), a lista numerada de "Passo a passo" passa a ter o número em círculo navy, maior que o texto, alinhado à esquerda, e a figura (print) que estiver DENTRO do item da lista (recuada três espaços no Markdown, logo abaixo do texto do passo) aparece sob o texto, ocupando a largura do item, com borda fina e cantos de 8 px como as imagens já têm. Faça isso pelo tema: envolva o conteúdo da Página de tarefa numa div com classe própria em MarkdownContent.astro e estilize em tema.css. Páginas sem `papel` (Visão geral, Como funciona, Novidades) não mudam.
Prove com uma página de teste TEMPORÁRIA em docs/manual/src/content/docs/primeiros-passos/ (apague antes do commit) que tem três passos, um print dentro do passo 1 e um print dentro do passo 3, e olhe o resultado no `pnpm dev` com o Chrome headless:
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --virtual-time-budget=20000 --screenshot=/tmp/passo.png --window-size=1440,1900 http://localhost:4321/primeiros-passos/<pagina-temporaria>/
e abra a imagem com Read. Confira no desktop e em 390 px de largura. Anexe os dois screenshots no PR.

2. O AVISO DESTACADO
O Starlight já entende `:::caution[Título]` em arquivos .md. Você não cria o componente: você garante que ele sai nas cores do app (fundo claro, borda navy ou âmbar, ícone do próprio Starlight) e que o rótulo padrão sai em português. Se o rótulo padrão sair em inglês, o caminho é a configuração de locale do Starlight (o site já declara pt-BR em astro.config.mjs): NÃO edite astro.config.mjs neste trabalho; se a única saída for mexer nele, PARE e reporte com o diff proposto. Prove na mesma página temporária.

3. O FLUXOGRAMA DE CAMINHO: O GERADOR
Crie docs/manual/scripts/gerar-fluxogramas.mjs (a pasta docs/manual/fluxogramas/ já existe, com um README que diz a regra; o tema.json nasce aqui). Ele lê todo docs/manual/fluxogramas/<modulo>/<slug>.mmd (sintaxe Mermaid, flowchart) e escreve docs/manual/src/assets/<modulo>/fluxo-<slug>.svg, chamando o mermaid-cli por `npx --yes @mermaid-js/mermaid-cli@<versão fixa que você escolher e conferir no registro do npm>`, com um arquivo de tema em docs/manual/fluxogramas/tema.json que usa as cores do globals.css (navy do app nas caixas de estado, fundo branco, texto escuro, a fonte HP Simplified se o mmdc aceitar, senão a fonte de sistema). Não adicione dependência em package.json: o mermaid-cli traz um navegador inteiro e pesaria em todo build do CI; o npx pinado é o mesmo caminho que o HyperFrames usa. O script aceita `--so <modulo>/<slug>` para regerar um só. Prove com um .mmd temporário de quatro caixas (apague o .mmd e o .svg antes do commit) e anexe o SVG gerado no PR. Se o SVG sair com travessão ou meia-risca em algum rótulo padrão, o script trava com mensagem: o CI do Manual varre travessão.
Registre como rodar no cabeçalho do script e em .claude/skills/manual/SKILL.md, no item "Fluxograma de caminho" da seção "Prints e vídeo": troque a frase entre parênteses pelo comando exato. O teste tools/test_skill_montar_manual.py confere que todo caminho que a skill cita existe, então o comando só entra na skill depois que o script existe.

4. A CAPA DO VÍDEO
Em publicar.sh, logo depois do reencode de cada MP4 para 720p, gere a capa `<mesmo caminho>.jpg` com o primeiro quadro (ffmpeg, -frames:v 1, qualidade 3). Em MarkdownContent.astro, o <video> ganha `poster="/video/<modulo>/<slug>.jpg"`. Capa que não existe (no `pnpm dev`, por exemplo) não quebra nada: o navegador ignora. O que a trava de tamanho conta (TETO_MB) passa a incluir as capas, porque elas vão para o mesmo dist. Os testes tools/test_publicar_manual.py ganham um caso para a capa.

5. O AVISO "VÍDEO EM PRODUÇÃO" SAI DA TELA
Em MarkdownContent.astro, a página sem `video` no frontmatter não mostra mais nada no lugar do vídeo. Apague também o estilo .tarefa-video-pendente. A lacuna continua sendo cobrada por tools/inventario_manual.py, que não muda.

6. O LINT PARA DE CONTAR O TEXTO ALTERNATIVO
Em tools/lint_manual.py, o teto de 250 palavras da Página de tarefa deixa de contar o texto alternativo das imagens (o que fica entre `![` e `]`). Ninguém lê o alt; com três prints por página ele empurraria toda tarefa para o aviso. A função texto_visivel continua servindo à varredura de jargão como está: jargão dentro do alt continua travando, porque o leitor de tela lê o alt. Faça a mudança só na contagem. tools/test_lint_manual.py ganha um caso: uma página com 240 palavras de texto e 30 de alt passa sem aviso.

O QUE NÃO FAZER
- Não edite nenhuma página em docs/manual/src/content/docs/ (a página de teste é temporária e some antes do commit).
- Não edite astro.config.mjs, .github/workflows/manual.yml, rotulos-da-sidebar.ts nem package.json/pnpm-lock.yaml do manual.
- Não edite hospital-reunioes/.
- Não publique (nada de publicar.sh de verdade, /manual publicar ou vercel deploy). Rode publicar.sh só pelos testes dele, se eles tiverem seam para isso.
- Não mergeie.

TIPOGRAFIA E JARGÃO
Travessão (U+2014) e meia-risca (U+2013) são proibidos em tudo que o usuário vê, inclusive em rótulo de callout e em texto de SVG. Comentário de código pode ser técnico; texto que aparece na tela, não.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): tema didatico, passo numerado, aviso, capa de video e gerador de fluxograma" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/tema-didatico é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/tema-didatico.

REPORTE NO FIM
Os dois screenshots da página temporária (desktop e 390 px), o SVG de prova, a versão do mermaid-cli que você fixou, o que mudou em cada um dos seis arquivos, e qualquer coisa que você não conseguiu fazer sem tocar em astro.config.mjs.
```
