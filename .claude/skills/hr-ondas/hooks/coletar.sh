#!/bin/bash
# Coleta do hr-ondas: um JSON numa linha, lido de fontes que já existem (só leitura).
# PRDs, ondas e fases: o recorte do coletor do OS (collect.py --recorte), só dos PRDs com onda
# viva nesta máquina ou com fatia de PR aberto (de qualquer sócio); com --todos, o /api/data inteiro do Hospital OS (8799) ·
# issues sem PRD pai em andamento (fila fixa de sessão viva, PR aberto ou in-progress): `soltas` · `claude agents --json`: sessões vivas ·
# $TMPDIR/fechar_onda/<sessao>/*.sql: migrations que a subida pediu ·
# /api/health de produção: a última migration aplicada · ~/.claude/hr-ondas/aplicadas: as que o
# humano declarou aplicadas ("apliquei a migration N" numa sessão, ou /ondas aplicada N) ·
# transcript de cada sessão de onda (hooks/sessao.py): o shell em curso, a última fala e as subidas ·
# passagens em $TMPDIR/onda-enxuta/ (hooks/passagem.py): as ondas de cada linhagem de sessão ·
# check-runs de cada PR aberto (REST, não a cota do GraphQL): início e fim do CI.
#
# A parte local (sessões, agentes, subidas, migrations) é fresca a cada chamada e não gasta
# nada. A parte remota (PRDs, CI, health) fica num cache em $TMPDIR/hr-ondas/,
# compartilhado por todas as sessões: sem argumento, só recoleta com mais de 5 min;
# com --fresco (um evento do workflow), com mais de 30 s. Uma trava faz uma sessão só buscar.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
OS_URL="${HR_ONDAS_OS:-http://127.0.0.1:8799/api/data}"
HEALTH_URL="${HR_ONDAS_HEALTH:-https://api.hospitalsaomatheus.cloud/api/health}"
CACHE_DIR="${HR_ONDAS_CACHE:-$TMP/hr-ondas}"; CACHE="$CACHE_DIR/remoto.json"; TRAVA="$CACHE_DIR/trava"
# registro durável (fora do TMPDIR, que o macOS limpa): uma linha "<numero> <quando>" por declaração
REGISTRO="${HR_ONDAS_REGISTRO:-$HOME/.claude/hr-ondas/aplicadas}"
RECORTE="$(cd "$(dirname "$0")/../../../.." && pwd)/tools/workflow-dashboard/collect.py"
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
  {repo: .repo_slug,
     prds: [ $all[] | select(.is_prd and .state == "OPEN") | . as $p
       | {n: .number, titulo: .title,
          ondas: ($F.ondas[($p.number | tostring)] // []),
          issues: [ $all[] | select(.parent == $p.number) | fatia ] } ],
     soltas: [ $all[] | select(.parent == null and (.is_prd | not))
       | select(.number as $n | ($citadas | index($n))
           or (.state == "OPEN" and ((.labels | index("in-progress")) or $F.issues[($n | tostring)].fase == "pr_aberto")))
       | fatia ] }
' 2>/dev/null
}

agentes=$(claude agents --json 2>/dev/null | jq -c --arg tmp "$TMP" '
  [ .[] | select(.name // "" | test("^onda-")) | select(.cwd | test("Hospital"))
    | {nome: .name, status: .status, estado: (.state // null), inicio: .startedAt, sessao: .sessionId} ]' 2>/dev/null)
[ -n "$agentes" ] || agentes='[]'

# Sub-agentes de cada sessão de onda: tipo e alvo no .meta.json, modelo, contexto e fim
# na última resposta do .jsonl (end_turn na última linha = terminou)
PROJ="$HOME/.claude/projects/$(pwd | tr '/.' '--')"
[ -d "$PROJ" ] || PROJ="$HOME/.claude/projects/-Users-pedrorezende-PedroDev-Hospital"
iso='sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000'
sub_agentes='[]'
for linha in $(echo "$agentes" | jq -r '.[] | "\(.nome)=\(.sessao)"'); do
  nome=${linha%%=*}; sid=${linha#*=}
  for meta in "$PROJ/$sid"/subagents/*.meta.json; do
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

# Shell em curso e subidas de cada sessão, lidos do transcript dela
subidas='[]'
for linha in $(echo "$agentes" | jq -r '.[] | "\(.nome)=\(.sessao)"'); do
  nome=${linha%%=*}; sid=${linha#*=}
  jl="$PROJ/$sid.jsonl"; [ -f "$jl" ] || continue
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
  [ -f "$f" ] || continue
  base=$(basename "$f"); num=${base%%_*}; sess=$(basename "$(dirname "$f")")
  mt=$(stat -f %m "$f" 2>/dev/null || echo 0); linhas=$(wc -l < "$f" | tr -d ' ')
  migs=$(echo "$migs" | jq -c --arg c "$f" --arg s "$sess" --arg a "$base" \
    --argjson n "$((10#$num))" --argjson m "$mt" --argjson l "$linhas" \
    '. + [{numero: $n, arquivo: $a, caminho: $c, sessao: $s, mtime: ($m * 1000), linhas: $l}]')
done

# Parte remota: recoleta se o cache passou da idade e ninguém está buscando
[ -d "$TRAVA" ] && [ $(( $(date +%s) - $(stat -f %m "$TRAVA") )) -gt 180 ] && rmdir "$TRAVA" 2>/dev/null
idade=$(( $(date +%s) - $(stat -f %m "$CACHE" 2>/dev/null || echo 0) ))
if [ $fresco = 1 ]; then minimo=30; url="$OS_URL?fresh=1"; else minimo=300; url="$OS_URL"; fi
if [ "$idade" -ge "$minimo" ] && mkdir "$TRAVA" 2>/dev/null; then
  trap 'rmdir "$TRAVA" 2>/dev/null' EXIT
  agora=$(( $(date +%s) * 1000 ))
  # Só os PRDs com sessão de onda viva ou PR aberto (~7 pontos de GraphQL); --todos, ou árvore sem o
  # recorte (branch antiga), cai no /api/data inteiro do OS (~35 pontos)
  bruto=""
  if [ $todos = 0 ]; then
    prds=$(echo "$prd_sessoes" | jq -r '[.[]] | unique | join(",")')
    bruto=$(python3 "$RECORTE" --recorte "$prds" --soltas "$(echo "$citadas" | jq -r 'join(",")')" 2>/dev/null) || bruto=""
  fi
  # a coleta fresca do OS inteiro leva uns 30 s
  [ -n "$bruto" ] || bruto=$(curl -s -m 75 "$url")
  os=$(echo "$bruto" | filtrar_os "$citadas"); osEm=$agora
  # OS sem resposta: fica o último retrato bom do cache, com a hora dele
  if [ -z "$os" ]; then
    os=$(jq -c '.os' "$CACHE" 2>/dev/null); osEm=$(jq -c '.osEm' "$CACHE" 2>/dev/null)
    [ -n "$os" ] || os=null; [ -n "$osEm" ] || osEm=null
  fi

  # CI de cada PR aberto: check-runs do commit da cabeça, em paralelo
  ci='{}'
  repo=$(echo "$os" | jq -r '.repo // empty' 2>/dev/null)
  CIDIR=$(mktemp -d "$TMP/hr-ondas-ci.XXXXXX")
  for pr in $(echo "$os" | jq -r '[.prds[]?.issues[]?, .soltas[]? | select(.fase == "pr_aberto" and .pr != null) | .pr] | unique | .[]' 2>/dev/null); do
    ( sha=$(gh api "repos/$repo/pulls/$pr" --jq .head.sha 2>/dev/null) && [ -n "$sha" ] &&
      gh api "repos/$repo/commits/$sha/check-runs?per_page=100" 2>/dev/null | jq -c '
        [ .check_runs[] | select(.started_at != null) ] | select(length > 0)
        | {inicio: (map(.started_at | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | min),
           fim: (if all(.completed_at != null) then (map(.completed_at | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | max) else null end)}
      ' > "$CIDIR/$pr" 2>/dev/null ) &
  done
  wait
  for f in "$CIDIR"/*; do
    [ -s "$f" ] || continue
    ci=$(echo "$ci" | jq -c --arg k "$(basename "$f")" --argjson v "$(cat "$f")" '. + {($k): $v}')
  done
  rm -r "$CIDIR"

  # health sem resposta (ou sem o número): fica o último valor bom do cache, como o retrato do OS
  aplicada=$(curl -s -m 8 "$HEALTH_URL" | jq -c '.migracao // empty' 2>/dev/null)
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

jq -n -c --argjson r "$remoto" --argjson agentes "$agentes" --argjson prdSessoes "$prd_sessoes" \
  --argjson subAgentes "$sub_agentes" --argjson subidas "$subidas" --argjson migs "$migs" \
  --argjson passagens "$passagens" \
  '{os: $r.os, osEm: $r.osEm, remotoEm: $r.em, ci: $r.ci, aplicada: $r.aplicada, agentes: $agentes,
    prdSessoes: $prdSessoes, subAgentes: $subAgentes, subidas: $subidas, migrations: $migs, passagens: $passagens}'
