#!/bin/bash
# Cache do CI no coletar.sh: uma chamada `gh pr checks` por PR por minuto entre todas as
# sessões, e 10 min quando o CI já terminou. Roda com: bash tests/coletar_ci_cache.test.sh
# Um `gh` falso no HOME falso conta as chamadas; o Hospital OS e o health vêm de arquivo.
set -u
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/home/.local/bin" "$T/tmp"
cat > "$T/home/.local/bin/gh" <<EOF
#!/bin/bash
echo "\$*" >> "$T/chamadas"
cat "$T/checks.json"
EOF
chmod +x "$T/home/.local/bin/gh"
cat > "$T/os.json" <<'EOF'
{"repo_slug":"o/r","fases":{"ondas":{},"issues":{"1135":{"fase":"pr_aberto","pr":1179}}},
 "github":{"issues":[{"number":1128,"title":"PRD","state":"OPEN","is_prd":true,"url":"u","blocked_by":[]},
  {"number":1135,"title":"fatia","state":"OPEN","is_prd":false,"parent":1128,"url":"u","blocked_by":[]}]}}
EOF
rodando='[{"startedAt":"2026-10-13T05:00:00Z","completedAt":null}]'
terminado='[{"startedAt":"2026-10-13T05:00:00Z","completedAt":"2026-10-13T05:08:00Z"}]'

falhas=0
coletar() {
  HOME="$T/home" TMPDIR="$T/tmp" HR_ONDAS_OS="file://$T/os.json" HR_ONDAS_HEALTH="file:///dev/null" \
    /bin/bash "$RAIZ/hooks/coletar.sh"
}
chamadas() { [ -f "$T/chamadas" ] && wc -l < "$T/chamadas" | tr -d ' ' || echo 0; }
envelhecer() { touch -t "$(date -v-"$1"S +%Y%m%d%H%M.%S)" "$T/tmp/hr-ondas-ci-cache/1179.json"; }
confere() {
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FALHA $1: esperado $3, veio $2"; falhas=$((falhas + 1)); fi
}

echo "$rodando" > "$T/checks.json"
confere "1a coleta chama o gh" "$(coletar | jq -c '.ci["1179"].fim')" "null"
confere "2a coleta reusa o cache e ainda traz o CI" "$(coletar | jq -c '.ci["1179"] != null')" "true"
confere "uma chamada nas duas coletas" "$(chamadas)" "1"
envelhecer 61; coletar > /dev/null
confere "CI rodando: cache de 61 s chama de novo" "$(chamadas)" "2"

echo "$terminado" > "$T/checks.json"
envelhecer 61; coletar > /dev/null
envelhecer 120
confere "CI terminado: cache de 2 min ainda vale" "$(coletar | jq -c '.ci["1179"].fim != null')" "true"
confere "sem chamada nova com CI terminado" "$(chamadas)" "3"
envelhecer 601; coletar > /dev/null
confere "CI terminado: cache de 10 min chama de novo" "$(chamadas)" "4"

: > "$T/checks.json"   # gh sem resposta (limite do GraphQL)
envelhecer 601
confere "gh falhou: fica o valor anterior" "$(coletar | jq -c '.ci["1179"].fim != null')" "true"
confere "gh falhou: espera o TTL antes de tentar de novo" "$(coletar > /dev/null; chamadas)" "5"

[ "$falhas" -eq 0 ] && echo "tudo verde" || { echo "$falhas falha(s)"; exit 1; }
