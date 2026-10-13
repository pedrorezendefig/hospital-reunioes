#!/bin/bash
# Coleta do hr-ondas: um JSON numa linha, lido de fontes que já existem (só leitura).
# Hospital OS (8799): PRDs, ondas e fases · `claude agents --json`: sessões vivas ·
# $TMPDIR/fechar_onda/<sessao>/*.sql: migrations que a subida pediu ·
# /api/health de produção: a última migration aplicada.
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
  --argjson subAgentes "$sub_agentes" \
  --argjson migs "$migs" --argjson aplicada "$aplicada" \
  '{os: $os, agentes: $agentes, prdSessoes: $prdSessoes, subAgentes: $subAgentes, migrations: $migs, aplicada: $aplicada}'
