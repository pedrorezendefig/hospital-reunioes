# Publicar o Manual

**Sozinho, por último, com todos os PRs da campanha mergeados.** É o único
prompt que mexe na árvore principal (ele a põe na main), por isso nenhum outro
terminal do Manual pode estar aberto.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`).

```
Publique o Manual do usuário do repo pedrorezendefig/hospital-reunioes na Vercel, com tudo o que já foi mergeado na main.

ONDE VOCÊ ESTÁ
Você está na árvore principal, /Users/pedrorezende/PedroDev/Hospital. Este é o único trabalho do Manual que roda nela, porque o vínculo com o projeto da Vercel (docs/manual/.vercel, fora do git) mora aqui. Antes de qualquer coisa:
  git status --porcelain      (tem que vir VAZIO; se houver mudança não commitada, PARE e reporte, sem descartar nada)
  git worktree list           (se houver worktree de prompt da campanha com PR ainda aberto, confira com gh pr list --state open e PARE se algum PR docs/videos-*, docs/prints-*, docs/tema-didatico, docs/fluxogramas ou docs/enxugar-a-escrita estiver aberto: publicar antes do merge deixa o site sem o trabalho deles)
Depois:
  git fetch origin --prune && git checkout main && git pull --ff-only origin main
Se o pull não for fast-forward, PARE e reporte.

LEIA PRIMEIRO
1. .claude/skills/manual/references/publicar.md: a receita.
2. docs/manual/publicar.sh, inteiro: o que ele faz e onde trava.

O QUE FAZER, nesta ordem
1. Traga os MP4 dos masters para onde o publicar.sh monta o site (public/video/ é gitignorado, então este passo é obrigatório e cobre os vídeos velhos e os novos):
     for m in reunioes pops primeiros-passos ouvidoria admin; do mkdir -p docs/manual/public/video/$m; cp local/manual-video-masters/$m/*.mp4 docs/manual/public/video/$m/ 2>/dev/null; done
   Pasta de módulo sem master é normal se aquele módulo ainda não tem vídeo; diga no relatório quais ficaram vazias.
2. Confira antes de subir, e só siga com os dois em zero:
     python3 tools/inventario_manual.py --dir docs/manual | tail -3     (zero lacunas sem-video e print-faltando; se sobrar lacuna, liste-as e PARE: falta merge ou falta master)
     python3 tools/checar_video_manual.py --dir docs/manual
3. Publique:
     bash docs/manual/publicar.sh
   Se travar por página que exibe vídeo sem arquivo, faltou MP4 no passo 1: diga qual e PARE. Se travar pela trava de tamanho (TETO_MB), PARE e reporte o tamanho: subir de plano é decisão do Pedro.
4. Confira no ar: abra https://manual-hsm.vercel.app e uma Página de tarefa de cada um dos cinco módulos com o Chrome headless
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --virtual-time-budget=20000 --screenshot=/tmp/<modulo>.png --window-size=390,1600 <url>
   e olhe cada imagem: o vídeo com capa, os prints com balão dentro dos passos, o fluxograma na Visão geral. Anexe as cinco imagens no relatório.

O QUE NÃO FAZER
- Não edite nenhum arquivo do repositório. Se algo precisar mudar para publicar, PARE e reporte.
- Não faça commit nem push.
- Não rode publicar.sh duas vezes: se a primeira falhou, reporte.

REPORTE NO FIM
O endereço publicado, quantos MP4 foram trazidos por módulo, o resultado do inventário e do conferidor, o que o publicar.sh imprimiu sobre tamanho, e as cinco imagens.
```
