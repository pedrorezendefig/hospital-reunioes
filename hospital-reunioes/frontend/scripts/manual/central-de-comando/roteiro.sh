#!/usr/bin/env bash
# Refaz os prints da página de Central de Comando do manual (issue #1725, ADR
# 0094, decisão 5) pelo playwright-cli, contra o app LOCAL e com o seed fictício.
#
# Uso (da pasta hospital-reunioes/frontend, com o app local no ar):
#   bash scripts/manual/central-de-comando/roteiro.sh
#   BASE=http://localhost:3017 bash scripts/manual/central-de-comando/roteiro.sh
#
# O roteiro semeia a diretora de exemplo (semear.py), entra como ela e responde
# no lugar do backend só nas rotas da Central de Comando, com os números de
# exemplo do respostas.py. Assim nenhuma fonte de verdade (Google Analytics,
# Instagram, nota no Google) é consultada, e nenhum número real entra no print.

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/central-de-comando"
BASE="${BASE:-http://localhost:3000}"
SESSAO="manual-central-1725"
CENTRAL="$BASE/admin/central-de-comando"
API="**/api/admin/central-de-comando"

case "$BASE" in
  http://localhost:*|http://127.0.0.1:*) ;;
  *) echo "recusado: '$BASE' não é o app local." >&2; exit 1 ;;
esac

SEED="$AQUI/seed.json"
seed() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval('d'+sys.argv[2]))" "$SEED" "$1"; }

pw() {
  local saida
  if ! saida="$(playwright-cli -s="$SESSAO" "$@" 2>&1)" || grep -q "^### Error" <<<"$saida"; then
    echo "falhou: playwright-cli $*" >&2
    echo "$saida" | sed -n '/### Error/,/###/p' >&2
    return 1
  fi
}

# Responde no lugar do backend numa rota da Central, com a tela do respostas.py.
responder() { pw route "$API/$1" --body "$(python3 "$AQUI/respostas.py" "$2")" --content-type "application/json"; }

# A miniatura de uma publicação de exemplo, no endereço https que a tela pede.
miniatura() {
  pw route "https://miniaturas.exemplo.local/$1.svg" --body "$(python3 "$AQUI/respostas.py" miniatura "$1")" --content-type "image/svg+xml"
}

# Espera um texto aparecer e os gráficos terminarem de entrar. O selo do Next,
# que só existe com o app rodando em modo de desenvolvimento, sai do print.
esperar() {
  pw run-code "async page => { await page.getByText('$1', { exact: true }).first().waitFor(); await page.addStyleTag({ content: 'nextjs-portal { display: none !important }' }); await page.waitForTimeout(1500) }"
}

# Fotografa a tela inteira ou um pedaço dela, e salva o PNG ao lado do Markdown.
print_tela() { pw screenshot --filename="$SAIDA/$1"; echo "  $1"; }
print() { pw screenshot "$1" --filename="$SAIDA/$2"; echo "  $2"; }
bloco() { echo "getByRole('region', { name: '$1', exact: true })"; }

python3 "$AQUI/semear.py"
mkdir -p "$SAIDA"

pw open "$BASE/login"
pw resize 1440 900
pw fill "#email" "$(seed "['admin']['email']")"
pw fill "#password" "$(seed "['admin']['senha']")" --submit
pw run-code "async page => { await page.waitForURL(u => !u.pathname.startsWith('/login')) }"

responder "visao-geral*" visao-geral
responder "dados-do-google*" dados-do-google
responder "instagram*" instagram
responder "objetivos" objetivos
responder "objetivos/google-reputacao*" nota
responder "objetivos/$(seed "['lente']['id']")*" lente
responder "ao-vivo*" ao-vivo
for publicacao in $(python3 -c "import json,sys; print(' '.join(p['id'] for p in json.load(open(sys.argv[1]))['instagram']['principais_publicacoes']))" "$SEED"); do
  miniatura "$publicacao"
done

echo "prints em $SAIDA:"

# Ver o panorama na Visão Geral: a tela com o menu da Central ao lado.
pw goto "$CENTRAL/visao-geral"
esperar "Área do site que mais atrai"
print_tela "visao-geral.png"

# Ler os números do site: um print por gráfico de Dados do Google.
pw goto "$CENTRAL/dados-do-google"
esperar "Movimento do site"
print "$(bloco "Movimento do site")" "movimento-do-site.png"
print "$(bloco "Áreas do site")" "areas-do-site.png"
print "$(bloco "Origem do público")" "origem-do-publico.png"
print "$(bloco "Contatos gerados")" "contatos-gerados.png"

# Ler os números do Instagram: os cartões do alto e as Principais publicações.
pw goto "$CENTRAL/instagram"
esperar "Principais publicações"
print_tela "instagram-numeros.png"
print "$(bloco "Principais publicações")" "instagram-publicacoes.png"

# Acompanhar a nota no Google: a galeria dos Objetivos e a lente da nota.
pw goto "$CENTRAL/objetivos"
esperar "Melhorar a nota no Google"
print_tela "objetivos.png"
pw goto "$CENTRAL/objetivos/google-reputacao"
esperar "Avaliações novas no mês"
print "getByRole('heading', { name: 'Melhorar a nota no Google', level: 1 }).locator('xpath=../..')" "nota-no-google.png"

# Seguir um Objetivo: a lente com os números e a sugestão.
pw goto "$CENTRAL/objetivos/$(seed "['lente']['id']")"
esperar "$(seed "['lente']['sugestoes'][0]['titulo']")"
print_tela "lente-do-objetivo.png"

pw close
