# Vídeos de tarefa: Reuniões e metas

**11 vídeos.** O pior caso de reuso da campanha: cerca de 8 telas distintas para
11 tarefas. Roda em paralelo com o 02, o 03 e o 04.

Copie o bloco inteiro e cole num terminal do Claude Code aberto DENTRO do worktree deste prompt. O [README](README.md) ensina a criar o worktree e a ordem de tudo.

```
Produza os 11 Vídeos de tarefa que faltam na seção "Reuniões e metas" do Manual do usuário, no repo pedrorezendefig/hospital-reunioes.

ONDE VOCÊ ESTÁ
Você está num git worktree próprio, na branch docs/videos-reunioes, criado a partir de origin/main. Outros terminais trabalham AO MESMO TEMPO em worktrees irmãos. Antes de qualquer coisa, confira:
  git branch --show-current      (tem que devolver docs/videos-reunioes)
  git rev-parse --show-toplevel  (tem que ser a pasta deste worktree, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca saia deste worktree, nunca toque na árvore principal.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..

LEIA PRIMEIRO, NESTA ORDEM
1. .claude/skills/manual/references/video-de-tarefa.md, que é a receita: especificação, roteiro fixo, formato do carimbo e os gates.
2. As skills globais /hyperframes, depois /hyperframes-core, depois /hyperframes-animation.
3. docs/adr/0057-*.md, que é a decisão que criou o Manual.

QUAL É O TRABALHO
As páginas sem vídeo estão em docs/manual/src/content/docs/reunioes/. Rode `python3 tools/inventario_manual.py --dir docs/manual` para a lista exata das lacunas "sem-video" do seu módulo. São 11. Não invente a lista: o inventário manda.

A ECONOMIA QUE DECIDE O CUSTO
As 11 tarefas acontecem em cerca de 8 telas distintas do app. Desenhe a BIBLIOTECA DE RÉPLICAS primeiro, uma réplica por tela, e depois monte os vídeos reusando. Não desenhe a mesma tela duas vezes. Cada vídeo é uma composição HyperFrames que redesenha a tela do app, fiel às cores e à tipografia do globals.css do frontend: o render é barato, desenhar a tela é o trabalho.

Copie a estrutura de docs/manual/video/primeiros-passos/entrar-na-plataforma/, que já tem o palco, o dedo fantasma e os marcadores prontos.

COPIOU PASTA? TROQUE O CARIMBO ANTES DE QUALQUER COISA
Os campos modulo, slug e pagina vêm colados do vídeo antigo, e o conferidor compara os três com a página que exibe o vídeo: carimbo do vizinho trava o CI.

O carimbo vive em TRÊS lugares por composição, e os três precisam bater:
- o script manual-video-meta no head (os cinco campos que o conferidor cobra);
- o carimbo visível do fecho;
- o rodapé da tela desenhada (.rodape-v), que aparece em toda cena com o app.
Em app_version use a versão que produção serve NA HORA em que você carimba, lida assim:
  curl -s https://app.hospitalsaomatheus.cloud/api/health | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'
Não copie de outro vídeo nem de memória: a versão muda com os deploys. Em gerado_em, a data de hoje.

A EXCEÇÃO AUTORIZADA PELO PEDRO, QUE MUDA O GATE 3
NÃO pare no draft esperando OK humano. Renderize direto em --quality high e siga.

Em troca, o gate 2 vira a ÚNICA barreira antes do ar, então ele é obrigatório e rigoroso:
  ffmpeg -i <mp4> -vf fps=1/3 frames/%02d.png
e OLHE cada imagem, uma por uma. Marcador em cima do elemento certo, dedo no botão que a legenda cita, texto legível, a tela batendo com o app real. O `check` do HyperFrames não vê nada disso: numa sessão anterior ele passou nas duas versões de um vídeo em que o marcador e o dedo apontavam um campo acima do certo, e só a olhada nos frames pegou. Conserte e re-renderize quando achar defeito. Documente no PR o que você viu em cada vídeo.

GATE ANTI-TÉCNICA, ANTES DE RENDERIZAR
Varra todo texto visível procurando: migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt. Mais travessão (U+2014) e meia-risca (U+2013), que o CI trava. Cada ocorrência vira linguagem funcional ou sai.

FIDELIDADE
O vídeo mostra o que o app faz, não o que seria bom que fizesse. Confira no código (hospital-reunioes/, LEITURA APENAS, edição proibida) toda afirmação e todo rótulo de tela. Na dúvida entre bonito e fiel, fiel vence.

Se a página que você está ilustrando afirmar algo que o código não faz, PARE e reporte em vez de reproduzir o erro em vídeo. Isso já aconteceu: um vídeo publicado afirmava "Só a diretoria executiva cadastra responsável. O ouvidor não" enquanto a página ao lado ensinava o ouvidor a fazer exatamente isso.

FATOS DO SEU MÓDULO QUE FAZEM VÍDEO NASCER ERRADO
- A Repactuação NÃO cria Pendência nova: a mesma Pendência passa a REPACTUADA e fica sem prazo, aparecendo como "A repactuar" até alguém marcar a data nova.
- O aceite da Ata pelo link é sem login, e depois de aceitar a tela mostra só "Aceite registrado" mais o agradecimento: não há carimbo de data e hora, nem nome, nem contagem.
- Os cinco tipos de reunião são fixos no código (Diretoria, Gerencial, Coordenação, Mensal, Extraordinária).
- A Secretária NÃO tem acesso a Pendências: as rotas devolvem 403 e ela não tem o grupo na barra.
- O badge e a coluna de Pendências mostram "Concluido" SEM acento, e a legenda dos gráficos do dashboard mostra "Concluído" COM acento. Reproduza o que cada tela mostra; não "corrija" a grafia no vídeo.

PII: O REPOSITÓRIO E O SITE SÃO PÚBLICOS
Use sempre "Administrador / admin@hospital.com" e dados de exemplo (@exemplo.local, @example.org, nomes inventados). Numa onda anterior foram achados cinco prints e três vídeos com e-mail real e telefone de terceiro indo para o ar, e dois deles escaparam por estar no CORPO da imagem e não no cabeçalho. Varra o fonte da composição e os frames.

ONDE OS ARQUIVOS FICAM
- composição, versionada: docs/manual/video/reunioes/<slug>/
- MP4, gitignorado: docs/manual/public/video/reunioes/<slug>.mp4
- a página passa a exibir pelo frontmatter `video: <slug>`
- AO TERMINAR cada vídeo, copie o MP4 final para /Users/pedrorezende/PedroDev/Hospital/local/manual-video-masters/reunioes/ (caminho absoluto, fora do git). É a cópia durável de onde a publicação tira: o public/video/ deste worktree é gitignorado e some quando o worktree for apagado. Sem a cópia o vídeo não chega ao ar.

O QUE NÃO FAZER
- Não toque em docs/manual/astro.config.mjs, .github/workflows/manual.yml, docs/manual/src/rotulos-da-sidebar.ts, docs/manual/publicar.sh nem em tools/: outros três terminais rodam em paralelo em worktrees irmãos.
- Não toque em nenhum módulo que não seja reunioes/.
- Não edite hospital-reunioes/. Ler o código é obrigatório; editar é proibido.
- NÃO PUBLIQUE: nada de publicar.sh, /manual publicar ou vercel deploy. A publicação é um passo único no fim, com os três terminais fechados.
- Não mergeie.
- Não regere os 9 vídeos que já existem.
- Render UM DE CADA VEZ, nunca em paralelo: a máquina está com quatro terminais renderizando.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): videos de tarefa da secao Reunioes e metas" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/videos-reunioes é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha, senão a label revisor-comentou acusa a própria automação.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/videos-reunioes.

REPORTE NO FIM
Quantas réplicas desenhou e quais telas, quantos vídeos saíram, o que a auto-revisão de frames pegou e você corrigiu, o que ficou de fora e por quê, e qualquer afirmação de página que você descobriu ser falsa ao conferir no código.
```
