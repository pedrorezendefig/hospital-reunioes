#!/usr/bin/env bash
# Refaz os prints da página de Ouvidoria do manual (issue #1723, ADR 0094,
# decisão 5) pelo playwright-cli, contra o app LOCAL e com o seed fictício.
#
# Uso (da pasta hospital-reunioes/frontend, com o app local no ar):
#   bash scripts/manual/ouvidoria/roteiro.sh
#   BASE=http://localhost:3010 bash scripts/manual/ouvidoria/roteiro.sh
#
# O roteiro semeia antes (semear.py), entra como a ouvidora de exemplo e fotografa
# só o pedaço da tela que o passo mostra: a linha do caso de exemplo ou a janela
# aberta. A lista inteira não entra, porque o banco local tem casos de outros
# trabalhos. Nenhum botão de confirmar é clicado: preencher a janela basta para
# o print, e confirmar acionaria o setor e mandaria email.

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/ouvidoria"
BASE="${BASE:-http://localhost:3000}"
SESSAO="manual-ouvidoria-1723"

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

# Fotografa um elemento e salva o PNG ao lado do Markdown da página.
print() { pw screenshot "$1" --filename="$SAIDA/$2"; echo "  $2"; }

linha() { echo "getByRole('listitem').filter({ hasText: '$1' }).first()"; }
janela() { echo "getByRole('dialog', { name: '$1' }).locator('> div').first()"; }

python3 "$AQUI/semear.py"
mkdir -p "$SAIDA"

pw open "$BASE/login"
pw resize 1440 900
pw fill "#email" "$(seed "['ouvidora']['email']")"
pw fill "#password" "$(seed "['ouvidora']['senha']")" --submit
pw run-code "async page => { await page.waitForURL(u => !u.pathname.startsWith('/login')) }"

abrir_a_fila() {
  pw goto "$BASE/ouvidoria"
  pw run-code "async page => { await page.getByRole('button', { name: 'Nova manifestação' }).waitFor() }"
}

# A janela inteira cabe no print numa tela mais alta, sem o cursor piscando
# no último campo preenchido.
print_janela() {
  pw resize 1440 1500
  pw run-code "async page => { await page.evaluate(() => document.activeElement && document.activeElement.blur()); await page.waitForTimeout(400) }"
  print "$(janela "$1")" "$2"
  pw resize 1440 900
}

echo "prints em $SAIDA:"

# Registrar uma manifestação: o topo da fila, com o botão, e a janela preenchida.
abrir_a_fila
print "getByRole('heading', { name: 'Ouvidoria', level: 1 }).locator('xpath=../..')" "fila-topo.png"
pw click "getByRole('button', { name: 'Nova manifestação' })"
NOVA="getByRole('dialog', { name: 'Nova manifestação' })"
pw select "$NOVA.getByLabel('Canal de origem', { exact: true })" "Telefone"
pw select "$NOVA.getByLabel('Tipo da manifestação', { exact: true })" "$(seed "['nova_manifestacao']['tipo']")"
pw select "$NOVA.getByLabel('Setor', { exact: true })" "$(seed "['nova_manifestacao']['setor']")"
pw fill "$NOVA.getByLabel('Resumo', { exact: true })" "$(seed "['nova_manifestacao']['assunto']")"
pw fill "$NOVA.getByLabel('Relato integral', { exact: true })" "$(seed "['nova_manifestacao']['relato']")"
pw fill "$NOVA.getByLabel('Quem manifestou', { exact: true })" "$(seed "['nova_manifestacao']['nome']")"
pw fill "$NOVA.getByLabel('Contato', { exact: true })" "$(seed "['nova_manifestacao']['contato']")"
print_janela "Nova manifestação" "nova-manifestacao.png"

# Encaminhar ao setor: a linha do caso novo e a janela Validar e acionar.
abrir_a_fila
PARA_VALIDAR="$(seed "['casos']['para_validar']['assunto']")"
print "$(linha "$PARA_VALIDAR")" "linha-validar.png"
pw click "$(linha "$PARA_VALIDAR").getByRole('button', { name: 'Validar e acionar' })"
VALIDAR="getByRole('dialog', { name: 'Validar e acionar' })"
pw select "$VALIDAR.getByLabel('Tipo da manifestação', { exact: true })" "$(seed "['validacao']['tipo']")"
pw uncheck "$VALIDAR.getByRole('checkbox', { name: 'Sigilo reforçado' })"
pw select "$VALIDAR.getByLabel('Área responsável', { exact: true })" "$(seed "['validacao']['setor']")"
pw click "$VALIDAR.getByRole('button', { name: '$(seed "['validacao']['gravidade']")' })"
pw fill "$VALIDAR.getByLabel('Extrato para o setor (obrigatório)', { exact: true })" "$(seed "['validacao']['extrato']")"
print_janela "Validar e acionar" "validar-e-acionar.png"

# Cobrar a resposta do setor: a linha do caso com o prazo vencido.
abrir_a_fila
print "$(linha "$(seed "['casos']['com_a_area']['assunto']")")" "linha-cobrar.png"

# Encerrar com o manifestante: a linha que aguarda o encerramento e a janela.
abrir_a_fila
RESPONDIDO="$(seed "['casos']['respondido']['assunto']")"
print "$(linha "$RESPONDIDO")" "linha-encerrar.png"
pw click "$(linha "$RESPONDIDO").getByRole('button', { name: 'Encerrar' })"
ENCERRAR="getByRole('dialog', { name: 'Encerrar' })"
pw click "$ENCERRAR.getByRole('button', { name: '$(seed "['encerramento']['desfecho']")', exact: true })"
pw fill "$ENCERRAR.getByRole('textbox')" "$(seed "['encerramento']['texto']")"
print_janela "Encerrar" "encerrar.png"

pw close
