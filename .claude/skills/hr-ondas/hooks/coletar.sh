#!/bin/bash
# Coleta do hr-ondas: um JSON numa linha, lido de fontes que já existem (só leitura).
# PRDs, ondas e fases: o recorte do coletor do PedroOS (coletor/collect.py --recorte), só dos PRDs com onda
# viva nesta máquina ou com fatia de PR aberto (de qualquer sócio); com --todos, a coleta inteira (collect.py --json) ·
# issues sem PRD pai em andamento (fila fixa de sessão viva, PR aberto ou in-progress): `soltas` · `claude agents --json`: sessões vivas ·
# $TMPDIR/fechar_onda/<sessao>/*.sql: migrations que a subida pediu ·
# /api/health de produção: a última migration aplicada · ~/.claude/hr-ondas/aplicadas: as que o
# humano declarou aplicadas ("apliquei a migration N" numa sessão, ou /ondas aplicada N) ·
# transcript de cada sessão de onda (hooks/sessao.py): o shell em curso, a última fala e as subidas ·
# passagens em $TMPDIR/onda-enxuta/ (hooks/passagem.py): as ondas de cada linhagem de sessão ·
# check-runs de cada PR aberto (REST, não a cota do GraphQL): início e fim do CI ·
# hooks/historico.py: os sub-agentes de toda sessão recente do Projeto, viva ou não (o tempo de cada etapa
# da Fatia) · CI de PR já mergeado (cache durável) · docs/spec/deploy/history.json da main: o tempo de cada subida.
#
# Vale para todo Projeto com o Pacote do fluxo: o slug, as migrations e o editor vêm do .claude/fluxo.json,
# o health do docs/spec/deploy/project.json.
#
# A parte local (sessões, agentes, subidas, migrations) é fresca a cada chamada e não gasta
# nada. A parte remota (PRDs, CI, health) fica num cache em $TMPDIR/hr-ondas/,
# compartilhado por todas as sessões: sem argumento, só recoleta com mais de 5 min;
# com --fresco (um evento do workflow), com mais de 30 s. Uma trava faz uma sessão só buscar.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
RAIZ="$(cd "$(dirname "$0")/../../../.." && pwd)"
# a pasta principal do Projeto (um worktree aponta para o .git dela): onde rodam as sessões de onda
COMUM=$(git -C "$RAIZ" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
PRINCIPAL="$RAIZ"; [ -n "$COMUM" ] && PRINCIPAL="$(dirname "$COMUM")"
FLUXO_JSON="$RAIZ/.claude/fluxo.json"
SLUG=$(jq -r '.slug // (.nome // empty | ascii_downcase)' "$FLUXO_JSON" 2>/dev/null)
[ -n "$SLUG" ] || SLUG=$(basename "$PRINCIPAL" | tr '[:upper:]' '[:lower:]')
# {pasta, aplicar, editor} das migrations; null = o Projeto não tem migration para o humano aplicar
MIGRACOES=$(jq -c '.migrations // null' "$FLUXO_JSON" 2>/dev/null); [ -n "$MIGRACOES" ] || MIGRACOES=null
REPO=$(git -C "$RAIZ" remote get-url origin 2>/dev/null | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
HEALTH_URL="${HR_ONDAS_HEALTH:-$(jq -r '[.services[]? | .health_check.url? // empty][0] // empty' "$RAIZ/docs/spec/deploy/project.json" 2>/dev/null)}"
CACHE_DIR="${HR_ONDAS_CACHE:-$TMP/hr-ondas/$SLUG}"; CACHE="$CACHE_DIR/remoto.json"; TRAVA="$CACHE_DIR/trava"
# registro durável (fora do TMPDIR, que o macOS limpa): uma linha "<numero> <quando>" por declaração;
# o do Hospital guarda o nome de antes
REGISTRO_PADRAO="$HOME/.claude/hr-ondas/aplicadas"; [ "$SLUG" = hospital ] || REGISTRO_PADRAO="$REGISTRO_PADRAO-$SLUG"
REGISTRO="${HR_ONDAS_REGISTRO:-$REGISTRO_PADRAO}"
# o coletor mora no PedroOS (ADR 0004 de lá, ADR 0062 do Hospital); a raiz do Projeto vai por --raiz
COLETOR="${HR_ONDAS_COLETOR:-$HOME/PedroDev/OS/coletor/collect.py}"
# as pastas de transcript do Projeto: a da pasta principal e as dos worktrees dela
PROJS="$HOME/.claude/projects/$(printf %s "$PRINCIPAL" | sed 's/[^A-Za-z0-9]/-/g')"
mkdir -p "$CACHE_DIR"
fresco=0; todos=0; registrar=""
for a in "$@"; do
  case "$a" in --fresco) fresco=1 ;; --todos) todos=1 ;; --registrar=*) registrar="${a#--registrar=}" ;; esac
done

# --registrar=118[,119]: o humano declarou a migration aplicada; só grava e sai
if [ -n "$registrar" ]; then
  mkdir -p "$(dirname "$REGISTRO")"
  for n in ${registrar//,/ }; do
    case "$n" in ''|*[!0-9]*) echo "número inválido: $n" >&2; exit 2 ;; esac
    echo "$((10#$n)) $(date +%Y-%m-%dT%H:%M:%S%z)" >> "$REGISTRO"
  done
  exit 0
fi

filtrar_os() {
  # GitHub fora (cota do GraphQL zerada) também conta como sem resposta: não apaga o retrato
  # $1: as issues da fila fixa das sessões vivas; sem PRD pai, entram em `soltas` até fechadas
  jq -c --argjson citadas "$1" 'select(.github.error == null)
  | 
  .fases as $F
  | .github.issues as $all
  | ($all | map(select(.state == "OPEN") | .number)) as $abertas
  | def fatia: ($F.issues[(.number | tostring)] // {}) as $f
      | {n: .number, titulo: .title, estado: .state, url: .url,
         fase: ($f.fase // "triagem"), pr: $f.pr,
         ci: ($f.sinal.ci // null), veredito: ($f.sinal.veredito // null),
         conflito: ($f.sinal.conflito // false), versao: $f.versao,
         por: [ .blocked_by[] as $b | select($abertas | index($b)) | $b ]};
  # PRD fechado volta ao painel enquanto tiver fatia aberta (lacuna achada na auditoria, reaberta por fatia nova)
  {repo: .repo_slug,
     prds: [ $all[] | select(.is_prd and (.state == "OPEN"
         or (.number as $p | any($all[]; .parent == $p and .state == "OPEN")))) | . as $p
       | {n: .number, titulo: .title,
          ondas: ($F.ondas[($p.number | tostring)] // []),
          issues: [ $all[] | select(.parent == $p.number) | fatia ] } ],
     soltas: [ $all[] | select(.parent == null and (.is_prd | not))
       | select(.number as $n | ($citadas | index($n))
           or (.state == "OPEN" and ((.labels | index("in-progress")) or $F.issues[($n | tostring)].fase == "pr_aberto")))
       | fatia ] }
' 2>/dev/null
}

# Candidatas: toda sessão viva no Projeto (na pasta principal ou num worktree dela). Fica no painel a
# que se chama `onda-*` ou `<linhagem>-onda<N>` (sessão de fundo da /onda-enxuta) ou a que tem
# sub-agente da onda (implementador, revisor, corretor) vivo ou terminado há menos de 30 min: uma onda
# rodada numa sessão interativa (filtro mais abaixo).
agentes=$(claude agents --json 2>/dev/null | jq -c --arg p "$PRINCIPAL" '
  [ .[] | select(.cwd // "" | . == $p or startswith($p + "/"))
    | {nome: (.name // .sessionId), status: .status, estado: (.state // null), inicio: .startedAt, sessao: .sessionId,
       onda: ((.name // "") | test("^onda-|-onda[0-9]+$"))} ]' 2>/dev/null)
[ -n "$agentes" ] || agentes='[]'

# Sub-agentes de cada sessão: tipo e alvo no .meta.json, modelo, contexto e fim
# na última resposta do .jsonl (end_turn na última linha = terminou)
# a pasta da sessão é achada pelo id em qualquer pasta de transcript do Projeto (a sessão pode ter entrado num worktree)
pasta_da_sessao() { ls -d "$PROJS/$1" "$PROJS"-*/"$1" 2>/dev/null | head -1; }
iso='sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000'
sub_agentes='[]'
for linha in $(echo "$agentes" | jq -r '.[] | "\(.nome)=\(.sessao)"'); do
  nome=${linha%%=*}; sid=${linha#*=}
  sdir=$(pasta_da_sessao "$sid"); [ -n "$sdir" ] || continue
  for meta in "$sdir"/subagents/*.meta.json; do
    [ -f "$meta" ] || continue
    jl="${meta%.meta.json}.jsonl"; [ -f "$jl" ] || continue
    id=$(basename "$jl" .jsonl)
    primeira=$(head -1 "$jl"); ultima=$(tail -1 "$jl")
    resposta=$(grep '"type":"assistant"' "$jl" | tail -1)
    [ -n "$resposta" ] || resposta='{}'
    item=$(jq -n -c --arg s "$nome" --arg id "$id" --argjson m "$(cat "$meta")" \
      --argjson p "$primeira" --argjson u "$ultima" --argjson r "$resposta" "
      {sessao: \$s, id: \$id, tipo: (\$m.agentType // \"?\"), descricao: (\$m.description // \"\"),
       esforco: (\$m.effort // null), modelo: (\$r.message.model // null),
       inicio: (\$p.timestamp | $iso), fim: (\$u.timestamp // \$p.timestamp | $iso),
       ctx: ((\$r.message.usage // {}) | (.input_tokens // 0) + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0)),
       terminou: (\$u.type == \"assistant\" and \$u.message.stop_reason == \"end_turn\")}" 2>/dev/null)
    [ -n "$item" ] && sub_agentes=$(echo "$sub_agentes" | jq -c --argjson i "$item" '. + [$i]')
  done
done

# O filtro: sessão `onda-*`, ou sessão com sub-agente hr-* vivo ou recém-terminado. As demais
# saem, com os sub-agentes delas.
agentes=$(echo "$agentes" | jq -c --argjson subs "$sub_agentes" --argjson agora "$(( $(date +%s) * 1000 ))" '
  map(select(.onda or (.nome as $n | any($subs[]; .sessao == $n and (.tipo | test("^(hr|onda)-"))
        and ((.terminou | not) or ($agora - .fim) < 1800000)))) | del(.onda))')
sub_agentes=$(echo "$sub_agentes" | jq -c --argjson ags "$agentes" '[ .[] | select(.sessao as $s | any($ags[]; .nome == $s)) ]')

# Shell em curso e subidas de cada sessão, lidos do transcript dela
subidas='[]'
for linha in $(echo "$agentes" | jq -r '.[] | "\(.nome)=\(.sessao)"'); do
  nome=${linha%%=*}; sid=${linha#*=}
  sdir=$(pasta_da_sessao "$sid"); jl="$sdir.jsonl"; [ -n "$sdir" ] && [ -f "$jl" ] || continue
  info=$(python3 -I "$(dirname "$0")/sessao.py" "$jl" "$nome" 2>/dev/null)
  [ -n "$info" ] || continue
  agentes=$(echo "$agentes" | jq -c --arg n "$nome" --argjson i "$info" 'map(if .nome == $n then . + {shell: $i.shell, fala: $i.fala} else . end)')
  subidas=$(echo "$subidas" | jq -c --arg n "$nome" --argjson i "$info" '. + ($i.subidas | map(. + {sessao: $n}))')
done

# PRD de cada sessão: o primeiro "PRD #N" da passagem que a lançou
prd_sessoes='{}'
for nome in $(echo "$agentes" | jq -r '.[].nome'); do
  arq="$TMP/onda-enxuta/$nome.md"
  [ -f "$arq" ] || continue
  prd=$(grep -o -m1 -E 'PRD #[0-9]+' "$arq" | head -1 | tr -dc '0-9')
  [ -n "$prd" ] && prd_sessoes=$(echo "$prd_sessoes" | jq -c --arg k "$nome" --argjson v "$prd" '. + {($k): $v}')
done

# Ondas de cada linhagem ("onda-gestao"): a fila-alvo fixa das passagens e quais já foram escritas
passagens=$(python3 -I "$(dirname "$0")/passagem.py" "$TMP/onda-enxuta" 2>/dev/null)
[ -n "$passagens" ] || passagens='{}'
# A fila fixa de cada sessão viva ("onda-b-onda1" é a onda 1 da linhagem "onda-b"): a issue sem
# PRD pai entra no recorte por ela
citadas=$(jq -n -c --argjson a "$agentes" --argjson p "$passagens" \
  '[ $a[].nome | capture("^(?<l>.+)-onda(?<n>[0-9]+)$") | $p[.l].ondas[.n] // [] | .[] ] | unique' 2>/dev/null)
[ -n "$citadas" ] || citadas='[]'

migs='[]'
for f in "$TMP"/fechar_onda/*/[0-9]*.sql; do
  [ -f "$f" ] && [ "$MIGRACOES" != null ] || continue
  base=$(basename "$f"); num=${base%%_*}; sess=$(basename "$(dirname "$f")")
  # a sessão é Onda de outro Projeto: a migration é de lá
  ls "$HOME"/.pedroos/ondas/*/"$sess".json 2>/dev/null | grep -qv "/ondas/$SLUG/" && continue
  mt=$(stat -f %m "$f" 2>/dev/null || echo 0); linhas=$(wc -l < "$f" | tr -d ' ')
  migs=$(echo "$migs" | jq -c --arg c "$f" --arg s "$sess" --arg a "$base" \
    --argjson n "$((10#$num))" --argjson m "$mt" --argjson l "$linhas" \
    '. + [{numero: $n, arquivo: $a, caminho: $c, sessao: $s, mtime: ($m * 1000), linhas: $l}]')
done

# Parte remota: recoleta se o cache passou da idade e ninguém está buscando
[ -d "$TRAVA" ] && [ $(( $(date +%s) - $(stat -f %m "$TRAVA") )) -gt 180 ] && rmdir "$TRAVA" 2>/dev/null
idade=$(( $(date +%s) - $(stat -f %m "$CACHE" 2>/dev/null || echo 0) ))
if [ $fresco = 1 ]; then minimo=30; else minimo=300; fi
if [ "$idade" -ge "$minimo" ] && mkdir "$TRAVA" 2>/dev/null; then
  trap 'rmdir "$TRAVA" 2>/dev/null' EXIT
  agora=$(( $(date +%s) * 1000 ))
  # Só os PRDs com sessão de onda viva ou PR aberto (~7 pontos de GraphQL); --todos, ou recorte
  # sem resposta, cai na coleta inteira (~35 pontos)
  bruto=""
  if [ $todos = 0 ]; then
    prds=$(echo "$prd_sessoes" | jq -r '[.[]] | unique | join(",")')
    bruto=$(python3 "$COLETOR" --raiz "$RAIZ" --recorte "$prds" --soltas "$(echo "$citadas" | jq -r 'join(",")')" 2>/dev/null) || bruto=""
  fi
  # a coleta fresca do OS inteiro leva uns 30 s
  [ -n "$bruto" ] || bruto=$(python3 "$COLETOR" --raiz "$RAIZ" --json 2>/dev/null)
  os=$(echo "$bruto" | filtrar_os "$citadas"); osEm=$agora
  # OS sem resposta: fica o último retrato bom do cache, com a hora dele
  if [ -z "$os" ]; then
    os=$(jq -c '.os' "$CACHE" 2>/dev/null); osEm=$(jq -c '.osEm' "$CACHE" 2>/dev/null)
    [ -n "$os" ] || os=null; [ -n "$osEm" ] || osEm=null
  fi

  # CI de cada PR: check-runs do commit da cabeça, em paralelo. O do PR aberto sempre; o do PR já mergeado
  # (mergeada, em produção) não muda mais e vai para um cache durável, buscado uma vez (até 20 por coleta).
  # ci_do_pr imprime {inicio, fim}, null (PR sem check-run) ou nada (o GitHub falhou: tenta de novo depois).
  ci='{}'
  repo=$(echo "$os" | jq -r '.repo // empty' 2>/dev/null); [ -n "$repo" ] || repo="$REPO"
  CI_FECHADO="$CACHE_DIR/ci-fechado.json"; [ -s "$CI_FECHADO" ] || echo '{}' > "$CI_FECHADO"
  ci_do_pr() {
    local sha runs
    sha=$(gh api "repos/$repo/pulls/$1" --jq .head.sha 2>/dev/null) && [ -n "$sha" ] || return 0
    runs=$(gh api "repos/$repo/commits/$sha/check-runs?per_page=100" 2>/dev/null) || return 0
    echo "$runs" | jq -c '
      [ .check_runs[] | select(.started_at != null) ]
      | if length == 0 then null else
        {inicio: (map(.started_at | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | min),
         fim: (if all(.completed_at != null) then (map(.completed_at | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | max) else null end)} end'
  }
  CIDIR=$(mktemp -d "$TMP/hr-ondas-ci.XXXXXX")
  for pr in $(echo "$os" | jq -r '[.prds[]?.issues[]?, .soltas[]? | select(.fase == "pr_aberto" and .pr != null) | .pr] | unique | .[]' 2>/dev/null); do
    ci_do_pr "$pr" > "$CIDIR/a$pr" 2>/dev/null &
  done
  for pr in $(echo "$os" | jq -r --slurpfile f "$CI_FECHADO" '[.prds[]?.issues[]?, .soltas[]? | select((.fase == "mergeada" or .fase == "em_producao") and .pr != null) | .pr | tostring] | unique | map(select(. as $k | $f[0] | has($k) | not)) | .[:20][]' 2>/dev/null); do
    ci_do_pr "$pr" > "$CIDIR/f$pr" 2>/dev/null &
  done
  wait
  for f in "$CIDIR"/*; do
    [ -s "$f" ] || continue
    nome=$(basename "$f"); pr=${nome#?}; v=$(cat "$f")
    if [ "${nome%"$pr"}" = f ] && [ "$(echo "$v" | jq 'if . == null then true else .fim != null end')" = true ]; then
      jq -c --arg k "$pr" --argjson v "$v" '. + {($k): $v}' "$CI_FECHADO" > "$CI_FECHADO.$$" && mv "$CI_FECHADO.$$" "$CI_FECHADO"
    elif [ "$v" != null ]; then
      ci=$(echo "$ci" | jq -c --arg k "$pr" --argjson v "$v" '. + {($k): $v}')
    fi
  done
  rm -r "$CIDIR"
  ci=$(jq -c --argjson a "$ci" 'with_entries(select(.value != null)) + $a' "$CI_FECHADO")

  # Tempo de cada subida, do registro da main (docs/spec/deploy/history.json): PR -> segundos, o maior
  # registro de cada PR. Busca de novo com mais de 5 min.
  SUBIDAS="$CACHE_DIR/subidas-feitas.json"
  if [ -n "$repo" ] && [ $(( $(date +%s) - $(stat -f %m "$SUBIDAS" 2>/dev/null || echo 0) )) -ge 300 ]; then
    novo=$(gh api -H 'Accept: application/vnd.github.raw' "repos/$repo/contents/docs/spec/deploy/history.json" 2>/dev/null | jq -c '
      [ .deploys[:400][]? | select(.duration_seconds != null) | .duration_seconds as $s
        | (.raw_subject // "" | [scan("#([0-9]+)") | .[0]]) | .[] | {k: ., s: $s} ]
      | group_by(.k) | map({key: .[0].k, value: (map(.s) | max)}) | from_entries' 2>/dev/null)
    [ -n "$novo" ] && echo "$novo" > "$SUBIDAS.$$" && mv "$SUBIDAS.$$" "$SUBIDAS"
  fi

  # health sem resposta (ou sem o número): fica o último valor bom do cache, como o retrato do OS
  aplicada=""
  [ "$MIGRACOES" != null ] && [ -n "$HEALTH_URL" ] && aplicada=$(curl -s -m 8 "$HEALTH_URL" | jq -c '.migracao // empty' 2>/dev/null)
  [ -n "$aplicada" ] || aplicada=$(jq -c '.aplicada // null' "$CACHE" 2>/dev/null)
  [ -n "$aplicada" ] || aplicada=null

  jq -n -c --argjson os "$os" --argjson osEm "$osEm" --argjson ci "$ci" --argjson aplicada "$aplicada" \
    --argjson em "$agora" '{os: $os, osEm: $osEm, ci: $ci, aplicada: $aplicada, em: $em}' > "$CACHE.$$" &&
    mv "$CACHE.$$" "$CACHE"
fi
remoto=$(cat "$CACHE" 2>/dev/null)
[ -n "$remoto" ] || remoto='{"os":null,"osEm":null,"ci":{},"aplicada":null,"em":null}'

# a maior migration que o humano declarou aplicada vale tanto quanto a do health
declarada=$(awk '/^[0-9]+ /{ if ($1+0 > m) m = $1+0 } END { print (m ? m : "null") }' "$REGISTRO" 2>/dev/null)
[ -n "$declarada" ] || declarada=null
remoto=$(echo "$remoto" | jq -c --argjson d "$declarada" '.aplicada = ([.aplicada, $d] | map(select(. != null)) | max)')

# Ondas que quebraram ou esperam o humano: o Estado da Onda que a sessão grava
# (docs/estado-da-onda.md do PedroOS), com o texto do último evento daquele estado
ESTADOS="${HR_ONDAS_ESTADOS:-$HOME/.pedroos/ondas/$SLUG}"
ondas_estado=$(cat "$ESTADOS"/*.json 2>/dev/null | jq -s -c '
  [ .[] | select(.contrato == 1 and (.estado == "erro" or .estado == "pronto-para-voce")) | . as $o
    | {id: $o.id, estado: $o.estado, prd: $o.prd, sessao: ($o.sessao // null), onda: ($o.onda // null),
       texto: ([$o.eventos[]? | select(.tipo == $o.estado)] | last | .texto // null),
       baixas: [$o.issues[]? | select(.status == "baixa") | .numero]} ]' 2>/dev/null)
[ -n "$ondas_estado" ] || ondas_estado='[]'

# Sub-agentes de toda sessão recente do Projeto, viva ou encerrada, que citam uma issue ou PR do painel
numeros=$(echo "$remoto" | jq -r '[.os.prds[]?.issues[]?, .os.soltas[]? | .n, .pr] | map(select(. != null)) | unique | join(",")' 2>/dev/null)
# shellcheck disable=SC2046
historico=$(python3 -I "$(dirname "$0")/historico.py" "$CACHE_DIR/historico.json" 14 "${numeros:-0}" \
  $(ls -d "$PROJS" "$PROJS"-* 2>/dev/null) 2>/dev/null)
[ -n "$historico" ] || historico='[]'
subidas_feitas=$(cat "$CACHE_DIR/subidas-feitas.json" 2>/dev/null); [ -n "$subidas_feitas" ] || subidas_feitas='{}'

jq -n -c --argjson r "$remoto" --argjson agentes "$agentes" --argjson prdSessoes "$prd_sessoes" \
  --argjson subAgentes "$sub_agentes" --argjson subidas "$subidas" --argjson migs "$migs" \
  --argjson passagens "$passagens" --argjson ondasEstado "$ondas_estado" \
  --argjson historico "$historico" --argjson subidasFeitas "$subidas_feitas" --argjson migracoes "$MIGRACOES" \
  --arg repo "$REPO" \
  '{os: $r.os, osEm: $r.osEm, remotoEm: $r.em, ci: $r.ci, aplicada: $r.aplicada, agentes: $agentes,
    prdSessoes: $prdSessoes, subAgentes: $subAgentes, subidas: $subidas, migrations: $migs, passagens: $passagens,
    ondasEstado: $ondasEstado, historico: $historico, subidasFeitas: $subidasFeitas, migracoes: $migracoes,
    repo: (if $repo == "" then null else $repo end)}'
