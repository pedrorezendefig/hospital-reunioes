# Vídeos de tarefa: Ouvidoria

**12 vídeos.** O mais barato da campanha: a Ouvidoria já tem sete composições
prontas (cap-1 a cap-7) com réplicas de quase toda tela do módulo. Roda em
paralelo com o 01, o 02 e o 04.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git. O [README](README.md) diz a ordem de tudo.

```
Produza os 12 Vídeos de tarefa que faltam na seção "Ouvidoria" do Manual do usuário, no repo pedrorezendefig/hospital-reunioes.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal do repositório, /Users/pedrorezende/PedroDev/Hospital, que costuma estar numa branch antiga e é compartilhada com outros terminais abertos AO MESMO TEMPO. Você NÃO trabalha nela. Seu primeiro ato é criar um worktree próprio, a partir de origin/main, e entrar nele:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria -b docs/videos-ouvidoria origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria
Se a branch ou a pasta já existirem de uma tentativa anterior deste mesmo prompt: veja com `gh pr list --head docs/videos-ouvidoria --state all` se o PR dela já foi mergeado ou fechado. Se foi, remova os restos (git -C /Users/pedrorezende/PedroDev/Hospital worktree remove --force /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria; git -C /Users/pedrorezende/PedroDev/Hospital branch -D docs/videos-ouvidoria) e crie de novo. Se o PR ainda estiver aberto, PARE e reporte: alguém pode estar trabalhando nela.

A pasta de trabalho persiste entre os seus comandos, mas confira antes de cada commit:
  git branch --show-current      (tem que devolver docs/videos-ouvidoria)
  git rev-parse --show-toplevel  (tem que devolver /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca edite arquivo fora do worktree, nunca toque na árvore principal. Ao terminar, não remova o worktree: a próxima rodada deste prompt sabe lidar com ele.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho dentro dele é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..

LEIA PRIMEIRO, NESTA ORDEM
1. .claude/skills/manual/references/video-de-tarefa.md, que é a receita: especificação, roteiro fixo, formato do carimbo e os gates.
2. As skills globais /hyperframes, depois /hyperframes-core, depois /hyperframes-animation.
3. docs/adr/0057-*.md, que é a decisão que criou o Manual, e CONTEXT.md, que é o glossário.

QUAL É O TRABALHO
As páginas sem vídeo estão em docs/manual/src/content/docs/ouvidoria/. Rode `python3 tools/inventario_manual.py --dir docs/manual` para a lista exata das lacunas "sem-video" do seu módulo. São 12. Não invente a lista: o inventário manda.

A ECONOMIA QUE DECIDE O CUSTO, e ela é sua vantagem sobre os outros terminais
A OUVIDORIA JÁ TEM SETE COMPOSIÇÕES PRONTAS em docs/manual/video/ouvidoria/cap-1 a cap-7, com réplicas de quase toda tela do módulo. REUSE as telas. NÃO regere os capítulos e NÃO os edite: eles estão publicados e corretos, e dois deles acabaram de ser consertados. Copie a réplica para a composição nova e adapte.

Desenhe a BIBLIOTECA DE RÉPLICAS primeiro (o que faltar nos capítulos) e monte os vídeos reusando. Não desenhe a mesma tela duas vezes. Cada vídeo é uma composição HyperFrames fiel às cores e à tipografia do globals.css do frontend: o render é barato, desenhar a tela é o trabalho.

O molde de Vídeo de tarefa (palco, dedo fantasma, marcadores, carimbo) é docs/manual/video/primeiros-passos/entrar-na-plataforma/. Os capítulos são molde de TELA, não de roteiro: o roteiro fixo do Vídeo de tarefa está na receita.

COPIOU PASTA? TROQUE O CARIMBO ANTES DE QUALQUER COISA
Os campos modulo, slug e pagina vêm colados do vídeo antigo, e o conferidor compara os três com a página que exibe o vídeo: carimbo do vizinho trava o CI. Você vai copiar dos capítulos, então este risco é o seu maior.

O carimbo vive em TRÊS lugares por composição, e os três precisam bater:
- o script manual-video-meta no head (os cinco campos que o conferidor cobra);
- o carimbo visível do fecho;
- o rodapé da tela desenhada (.rodape-v), que aparece em toda cena com o app.
Em app_version use a versão que produção serve NA HORA em que você carimba, lida assim:
  curl -s https://app.hospitalsaomatheus.cloud/api/health | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'
Não copie de outro vídeo nem de memória: a versão muda com os deploys. Em gerado_em, a data de hoje. ATENÇÃO: os capítulos que você vai copiar carregam 0.109.0 e 03/09/2026 em alguns pontos. Isso já travou uma sessão.

A EXCEÇÃO AUTORIZADA PELO PEDRO, QUE MUDA O GATE 3
NÃO pare no draft esperando OK humano. Renderize direto em --quality high e siga.

Em troca, o gate 2 vira a ÚNICA barreira antes do ar, então ele é obrigatório e rigoroso:
  ffmpeg -i <mp4> -vf fps=1/3 frames/%02d.png
e OLHE cada imagem, uma por uma. Marcador em cima do elemento certo, dedo no botão que a legenda cita, texto legível, a tela batendo com o app real. O `check` do HyperFrames não vê nada disso: numa sessão anterior ele passou nas duas versões de um vídeo em que o marcador e o dedo apontavam um campo acima do certo, e só a olhada nos frames pegou. Conserte e re-renderize quando achar defeito. Documente no PR o que você viu em cada vídeo.

GATE ANTI-TÉCNICA, ANTES DE RENDERIZAR
Varra todo texto visível procurando: migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt. Mais travessão (U+2014) e meia-risca (U+2013), que o CI trava. Cada ocorrência vira linguagem funcional ou sai.

FIDELIDADE
O vídeo mostra o que o app faz, não o que seria bom que fizesse. Confira no código (hospital-reunioes/, LEITURA APENAS, edição proibida) toda afirmação e todo rótulo de tela. Na dúvida entre bonito e fiel, fiel vence.

Se a página que você está ilustrando afirmar algo que o código não faz, PARE e reporte em vez de reproduzir o erro em vídeo. Isso já aconteceu exatamente no seu módulo: um vídeo publicado afirmava "Só a diretoria executiva cadastra responsável. O ouvidor não" enquanto a página ao lado ensinava o ouvidor a fazer isso. Foi corrigido, e o custo foi re-renderizar.

FATOS DO SEU MÓDULO QUE FAZEM VÍDEO NASCER ERRADO
- Quem tem papel nas Reuniões lê na lista o protocolo, o setor, a situação, o prazo, a gravidade, o tipo, o desfecho E O RESUMO do caso. Dossiê, arquivo e sigiloso são exclusivos de Ouvidor e Diretoria Executiva.
- O resumo do caso vindo do formulário é um recorte literal das primeiras 200 letras do relato (issue #753).
- A Ana NÃO atende no WhatsApp do hospital: aquele número é de gente, no Kommo. O canal dela ainda é de teste.
- Ouvidor E diretoria executiva mantêm o cadastro de responsáveis. A Tabela de prazos, essa sim, é só da diretoria executiva.
- O portal do setor (pedir mais prazo, responder) é sem login, pelo link do e-mail: o vídeo não pode mostrar o setor logado no app.
- O endereço do app é https://app.hospitalsaomatheus.cloud. Nunca mostre localhost em tela nenhuma.

PII: O REPOSITÓRIO E O SITE SÃO PÚBLICOS
Use sempre "Administrador / admin@hospital.com" e dados de exemplo (@exemplo.local, @example.org, nomes inventados), inclusive no relato do caso, no nome de quem falou, no responsável do setor e em toda linha de lista. Numa onda anterior foram achados cinco prints e três vídeos com e-mail real e telefone de terceiro indo para o ar, e dois deles escaparam por estar no CORPO da imagem e não no cabeçalho. Varra o fonte da composição e os frames dos 12.

ONDE OS ARQUIVOS FICAM
- composição, versionada: docs/manual/video/ouvidoria/<slug>/
- MP4, gitignorado: docs/manual/public/video/ouvidoria/<slug>.mp4
- a página passa a exibir pelo frontmatter `video: <slug>`
- AO TERMINAR cada vídeo, copie o MP4 final para /Users/pedrorezende/PedroDev/Hospital/local/manual-video-masters/ouvidoria/ (caminho absoluto, fora do git). É a cópia durável de onde a publicação tira: o public/video/ deste worktree é gitignorado e some quando o worktree for apagado. Sem a cópia o vídeo não chega ao ar.

O QUE NÃO FAZER
- Não toque em docs/manual/astro.config.mjs, .github/workflows/manual.yml, docs/manual/src/rotulos-da-sidebar.ts, docs/manual/publicar.sh nem em tools/: outros três terminais rodam em paralelo em worktrees irmãos.
- Não toque em nenhum módulo que não seja ouvidoria/. Admin é de outro terminal.
- Não edite hospital-reunioes/. Ler o código é obrigatório; editar é proibido.
- NÃO PUBLIQUE: nada de publicar.sh, /manual publicar ou vercel deploy. A publicação é um passo único no fim, com os quatro terminais fechados.
- Não mergeie.
- Não regere os 9 vídeos que já existem, e não edite os sete capítulos da Ouvidoria nem o registrar-manifestacao-pelo-formulario.
- Render UM DE CADA VEZ, nunca em paralelo: a máquina está com quatro terminais renderizando.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): videos de tarefa da secao Ouvidoria" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/videos-ouvidoria é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha, senão a label revisor-comentou acusa a própria automação.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/videos-ouvidoria.

REPORTE NO FIM
Quantas réplicas reusou dos capítulos e quantas desenhou, quantos vídeos saíram, o que a auto-revisão de frames pegou e você corrigiu, o que ficou de fora e por quê, e qualquer afirmação de página que você descobriu ser falsa ao conferir no código.
```
