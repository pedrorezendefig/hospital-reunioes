# Vídeos de tarefa: Ouvidoria e Admin

**23 vídeos**, 12 de Ouvidoria e 11 de Admin. Parece o maior e é o mais barato:
a Ouvidoria já tem sete composições prontas para reusar, e o Admin tem cerca de
quatro telas para onze tarefas. Roda em paralelo com o 01 e o 02.

Copie o bloco inteiro e cole num terminal do Claude Code, na raiz do repositório.

```
Produza os 23 Vídeos de tarefa que faltam nas seções "Ouvidoria" (12) e "Admin" (11) do Manual do usuário, no repo pedrorezendefig/hospital-reunioes.

LEIA PRIMEIRO, NESTA ORDEM
1. .claude/skills/manual/references/video-de-tarefa.md, que é a receita: especificação, roteiro fixo, formato do carimbo e os gates.
2. As skills globais /hyperframes, depois /hyperframes-core, depois /hyperframes-animation.
3. docs/adr/0057-*.md, que é a decisão que criou o Manual, e CONTEXT.md, que é o glossário.

QUAL É O TRABALHO
As páginas sem vídeo estão em docs/manual/src/content/docs/ouvidoria/ e .../admin/. Rode `python3 tools/inventario_manual.py --dir docs/manual` para a lista exata das lacunas "sem-video" dos seus dois módulos. São 23. Não invente a lista: o inventário manda.

A ECONOMIA QUE FAZ 23 CABEREM, e ela é sua vantagem sobre os outros dois terminais:

- A OUVIDORIA JÁ TEM SETE COMPOSIÇÕES PRONTAS em docs/manual/video/ouvidoria/cap-1 a cap-7, com réplicas de quase toda tela do módulo. REUSE as telas. NÃO regere os capítulos e NÃO os edite: eles estão publicados e corretos, e dois deles acabaram de ser consertados.
- EM ADMIN, cadastrar-um-cargo, cadastrar-um-setor e cadastrar-um-tipo-de-reuniao são O MESMO COMPONENTE DE TELA (TaxonomyPage, com título e substantivo trocados). E seis tarefas acontecem na tela de Usuários com o mesmo modal: cadastrar-uma-pessoa, entregar-o-acesso-a-uma-pessoa, mudar-o-perfil-de-acesso, dar-acesso-aos-pops-e-a-ouvidoria, resolver-um-participante-externo e tirar-o-acesso-de-quem-saiu. São cerca de 4 telas para 11 tarefas.

Desenhe a BIBLIOTECA DE RÉPLICAS primeiro e monte os vídeos reusando. Não desenhe a mesma tela duas vezes.

COPIOU PASTA? TROQUE O CARIMBO ANTES DE QUALQUER COISA
Os campos modulo, slug e pagina vêm colados do vídeo antigo, e o conferidor compara os três com a página que exibe o vídeo: carimbo do vizinho trava o CI. Você vai copiar dos capítulos, então este risco é o seu maior.

O carimbo vive em TRÊS lugares por composição, e os três precisam bater:
- o script manual-video-meta no head (os cinco campos que o conferidor cobra);
- o carimbo visível do fecho;
- o rodapé da tela desenhada (.rodape-v), que aparece em toda cena com o app.
Use app_version 0.137.1, que é o que produção serve, e a data de hoje. ATENÇÃO: os capítulos que você vai copiar carregam 0.109.0 e 03/09/2026 em alguns pontos. Isso já travou uma sessão.

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

FATOS DOS SEUS MÓDULOS QUE FAZEM VÍDEO NASCER ERRADO
- CADASTRAR UM TIPO DE REUNIÃO NÃO TEM EFEITO NENHUM. Os cinco tipos são fixos no código e o servidor recusa valor novo (issue #755). A página já diz isso com todas as letras. O vídeo NÃO pode sugerir que o cadastro aparece em algum lugar.
- NÃO EXISTE convite por e-mail ao criar usuário. A conta nasce com senha aleatória que ninguém vê, e o acesso só é entregue num SEGUNDO passo, pela ação "Resetar senha", que mostra a senha uma vez para o admin copiar. São duas tarefas, não uma.
- Conceder acesso a quem ainda não tem login EXIGE e-mail, provisiona a conta na hora e mostra a senha uma única vez.
- O item Admin da barra aparece para quem tem qualquer papel de Reuniões, mas Secretária e Regular só alcançam "Dados do Atendimento" lá dentro.
- A Role ("cargo hospitalar") não abre tela nenhuma: quem abre é o Perfil de acesso. Ela decide só três coisas, todas fora do Admin.
- Na Ouvidoria, quem tem papel nas Reuniões lê na lista o protocolo, o setor, a situação, o prazo, a gravidade, o tipo, o desfecho E O RESUMO do caso. Dossiê, arquivo e sigiloso são exclusivos de Ouvidor e Diretoria Executiva.
- O resumo do caso vindo do formulário é um recorte literal das primeiras 200 letras do relato (issue #753).
- A Ana NÃO atende no WhatsApp do hospital: aquele número é de gente, no Kommo. O canal dela ainda é de teste.
- Ouvidor E diretoria executiva mantêm o cadastro de responsáveis. A Tabela de prazos, essa sim, é só da diretoria executiva.
- O endereço do app é https://app.hospitalsaomatheus.cloud. Nunca mostre localhost em tela nenhuma.

PII: O REPOSITÓRIO E O SITE SÃO PÚBLICOS, E A SUA TELA DE USUÁRIOS É O PIOR CASO DO MANUAL INTEIRO
Ela é literalmente a lista de nomes e e-mails reais. Use dados de exemplo em TODAS as linhas da lista, não só no cabeçalho: numa onda anterior o achado escapou justamente por estar no corpo da imagem. Use "Administrador / admin@hospital.com" como usuário logado e @exemplo.local ou @example.org nas linhas. Varra o fonte da composição e os frames de todos os 23.

ONDE OS ARQUIVOS FICAM
- composição, versionada: docs/manual/video/ouvidoria/<slug>/ e docs/manual/video/admin/<slug>/
- MP4, gitignorado: docs/manual/public/video/ouvidoria/<slug>.mp4 e .../admin/<slug>.mp4
- a página passa a exibir pelo frontmatter `video: <slug>`
- AO TERMINAR cada vídeo, copie o MP4 final para /Users/pedrorezende/PedroDev/Hospital/local/manual-video-masters/ouvidoria/ ou .../admin/ (caminho absoluto, fora do git). É a cópia durável de onde a publicação tira, e sem ela o vídeo não chega ao ar.

O QUE NÃO FAZER
- Não toque em docs/manual/astro.config.mjs, .github/workflows/manual.yml, docs/manual/src/rotulos-da-sidebar.ts, docs/manual/publicar.sh nem em tools/: outros dois terminais rodam em paralelo.
- Não toque em nenhum módulo que não seja ouvidoria/ e admin/.
- Não edite hospital-reunioes/. Ler o código é obrigatório; editar é proibido.
- NÃO PUBLIQUE: nada de publicar.sh, /manual publicar ou vercel deploy. A publicação é um passo único no fim, com os três terminais fechados.
- Não mergeie.
- Não regere os 9 vídeos que já existem, e não edite os sete capítulos da Ouvidoria.
- Render UM DE CADA VEZ, nunca em paralelo: a máquina está com três terminais.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): videos de tarefa das secoes Ouvidoria e Admin" --no-merge --skip-review

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha, senão a label revisor-comentou acusa a própria automação.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: o working tree é compartilhado.

REPORTE NO FIM
Quantas réplicas desenhou e quais telas, quantos vídeos saíram, o que a auto-revisão de frames pegou e você corrigiu, o que ficou de fora e por quê, e qualquer afirmação de página que você descobriu ser falsa ao conferir no código.
```
