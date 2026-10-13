#!/bin/bash
# Coleta do hr-ondas: um JSON numa linha, lido de fontes que já existem (só leitura).
# Hospital OS (8799): PRDs, ondas e fases · `claude agents --json`: sessões vivas ·
# $TMPDIR/fechar_onda/<sessao>/*.sql: migrations que a subida pediu ·
# /api/health de produção: a última migration aplicada ·
# transcript de cada sessão de onda (hooks/sessao.py): o shell em curso e as subidas ·
# `gh pr checks` de cada PR aberto: início e fim do CI.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
TMP="${TMPDIR:-/tmp}"; TMP="${TMP%/}"
OS_URL="${HR_ONDAS_OS:-http://127.0.0.1:8799/api/data}"
HEALTH_URL="${HR_ONDAS_HEALTH:-https://api.hospitalsaomatheus.cloud/api/health}"

os=$(curl -s -m 20 "$OS_URL" | jq -c '
  .fases as $F
  | .github.issues as $all
  | ($all | map(select(.state == "OPEN") | .number)) as $abertas
  | {repo: .repo_slug,
     prds: [ $all[] | select(.is_prd and .state == "OPEN") | . as $p
       | {n: .number, titulo: .title,
          ondas: ($F.ondas[($p.number | tostring)] // []),
          issues: [ $all[] | select(.parent == $p.number)
            | ($F.issues[(.number | tostring)] // {}) as $f
            | {n: .number, titulo: .title, estado: .state, url: .url,
               fase: ($f.fase // "triagem"), pr: $f.pr,
               ci: ($f.sinal.ci // null), veredito: ($f.sinal.veredito // null),
               conflito: ($f.sinal.conflito // false), versao: $f.versao,
               por: [ .blocked_by[] as $b | select($abertas | index($b)) | $b ]} ] } ] }
' 2>/dev/null)
[ -n "$os" ] || os=null

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
  agentes=$(echo "$agentes" | jq -c --arg n "$nome" --argjson i "$info" 'map(if .nome == $n then . + {shell: $i.shell} else . end)')
  subidas=$(echo "$subidas" | jq -c --arg n "$nome" --argjson i "$info" '. + ($i.subidas | map(. + {sessao: $n}))')
done

# CI de cada PR aberto: início e fim pelos checks do GitHub, em paralelo. A coleta roda a cada
# 10 s em cada sessão e o `gh pr checks` gasta o GraphQL que o fechar_onda.py usa: cache comum
# a todas as sessões em $TMP/hr-ondas-ci-cache/<pr>.json, 60 s com CI rodando e 10 min com
# CI terminado. Falha do gh não apaga o valor anterior, só renova o mtime (espera o TTL).
ci='{}'
CACHE="$TMP/hr-ondas-ci-cache"; mkdir -p "$CACHE"
agora=$(date +%s)
prs=$(echo "$os" | jq -r '[.prds[]?.issues[]? | select(.fase == "pr_aberto" and .pr != null) | .pr] | unique | .[]' 2>/dev/null)
for pr in $prs; do
  arq="$CACHE/$pr.json"
  if [ -f "$arq" ]; then
    ttl=60; jq -e '.fim != null' "$arq" >/dev/null 2>&1 && ttl=600
    [ $((agora - $(stat -f %m "$arq"))) -lt "$ttl" ] && continue
  fi
  ( tmp=$(mktemp "$CACHE/.$pr.XXXXXX")
    gh pr checks "$pr" --json startedAt,completedAt 2>/dev/null | jq -c '
      [ .[] | select(.startedAt != null) ] | select(length > 0)
      | {inicio: (map(.startedAt | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | min),
         fim: (if all(.completedAt != null) then (map(.completedAt | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601 * 1000) | max) else null end)}
    ' > "$tmp" 2>/dev/null
    if [ -s "$tmp" ]; then mv "$tmp" "$arq"; else rm -f "$tmp"; touch "$arq"; fi ) &
done
wait
for pr in $prs; do
  [ -s "$CACHE/$pr.json" ] || continue
  ci=$(echo "$ci" | jq -c --arg k "$pr" --argjson v "$(cat "$CACHE/$pr.json")" '. + {($k): $v}')
done

# PRD de cada sessão: o primeiro "PRD #N" da passagem que a lançou
prd_sessoes='{}'
for nome in $(echo "$agentes" | jq -r '.[].nome'); do
  arq="$TMP/onda-enxuta/$nome.md"
  [ -f "$arq" ] || continue
  prd=$(grep -o -m1 -E 'PRD #[0-9]+' "$arq" | head -1 | tr -dc '0-9')
  [ -n "$prd" ] && prd_sessoes=$(echo "$prd_sessoes" | jq -c --arg k "$nome" --argjson v "$prd" '. + {($k): $v}')
done

migs='[]'
for f in "$TMP"/fechar_onda/*/[0-9]*.sql; do
  [ -f "$f" ] || continue
  base=$(basename "$f"); num=${base%%_*}; sess=$(basename "$(dirname "$f")")
  mt=$(stat -f %m "$f" 2>/dev/null || echo 0); linhas=$(wc -l < "$f" | tr -d ' ')
  migs=$(echo "$migs" | jq -c --arg c "$f" --arg s "$sess" --arg a "$base" \
    --argjson n "$((10#$num))" --argjson m "$mt" --argjson l "$linhas" \
    '. + [{numero: $n, arquivo: $a, caminho: $c, sessao: $s, mtime: ($m * 1000), linhas: $l}]')
done

aplicada=$(curl -s -m 8 "$HEALTH_URL" | jq -c '.migracao // null' 2>/dev/null)
[ -n "$aplicada" ] || aplicada=null

jq -n -c --argjson os "$os" --argjson agentes "$agentes" --argjson prdSessoes "$prd_sessoes" \
  --argjson subAgentes "$sub_agentes" --argjson subidas "$subidas" --argjson ci "$ci" \
  --argjson migs "$migs" --argjson aplicada "$aplicada" \
  '{os: $os, agentes: $agentes, prdSessoes: $prdSessoes, subAgentes: $subAgentes, subidas: $subidas, ci: $ci, migrations: $migs, aplicada: $aplicada}'
