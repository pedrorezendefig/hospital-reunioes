#!/usr/bin/env bash
# Gera o zip "fluxo-origem" para mandar a quem vai instalar o fluxo sem clonar o repo.
#
#   tools/instalar-fluxo/empacotar.sh [pasta-de-saida]   # default: ~/Downloads
#
# O zip descompacta numa pasta fluxo-origem/ com os mesmos caminhos do repo,
# então o ROTEIRO.md funciona igual apontando ORIGEM para ela. O conteúdo segue
# o MANIFESTO.md: vai o que é "copiar", "adaptar" e os modelos de formato do que
# é "gerar". Não vai o app nem o conteúdo do Hospital.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${1:-$HOME/Downloads}"
SHA="$(git -C "$ROOT" rev-parse --short HEAD)"
DATA="$(date +%Y-%m-%d)"
STAGE="$(mktemp -d)"
PKG="$STAGE/fluxo-origem"
ZIP="$OUT_DIR/fluxo-origem-$DATA-$SHA.zip"

mkdir -p "$PKG" "$OUT_DIR"

copiar() {  # copiar <caminho relativo ao repo> (arquivo ou pasta)
  local rel="$1"
  if [ ! -e "$ROOT/$rel" ]; then echo "  aviso: $rel não existe, pulando" >&2; return; fi
  mkdir -p "$PKG/$(dirname "$rel")"
  cp -R "$ROOT/$rel" "$PKG/$rel"
}

echo "Empacotando a partir de $ROOT @ $SHA"

# raiz
for f in CLAUDE.md README.md skills-lock.json .gitignore; do copiar "$f"; done

# skills (menos divulgar, que o manifesto exclui)
for d in "$ROOT"/.claude/skills/*/; do
  nome="$(basename "$d")"
  [ "$nome" = "divulgar" ] && continue
  copiar ".claude/skills/$nome"
done

# docs
copiar docs/agents
copiar docs/onboarding
copiar docs/spec
copiar docs/adr/README.md
for adr in 0013 0020 0022 0025 0027 0028 0043 0044 0053; do
  for f in "$ROOT"/docs/adr/$adr-*.md; do [ -e "$f" ] && copiar "docs/adr/$(basename "$f")"; done
done

# CI, templates e a regra ESLint do travessão
copiar .github
copiar hospital-reunioes/frontend/eslint.config.mjs

# tools
copiar tools/lint_adr.py
copiar tools/workflow-dashboard
copiar tools/instalar-fluxo

# limpeza de caches e artefatos
find "$PKG" \( -name __pycache__ -o -name .DS_Store -o -name '*.pyc' -o -name .pytest_cache \) -prune -exec rm -rf {} + 2>/dev/null || true

# carimbo de origem (o roteiro lê daqui quando ORIGEM não é um clone git)
cat > "$PKG/ORIGEM.txt" <<EOF
repo: https://github.com/pedrorezendefig/hospital-reunioes
sha: $SHA
data: $DATA
EOF

# instruções para quem recebe
cat > "$PKG/LEIA-ME.md" <<'EOF'
# Instalar o fluxo de trabalho no seu projeto

Esta pasta é a ORIGEM: o painel, as skills, os CIs e o roteiro de instalação do fluxo de trabalho do repositório `pedrorezendefig/hospital-reunioes`.

## O que você precisa antes

- Claude Code instalado.
- Seu projeto num repositório git com remoto no GitHub.
- GitHub CLI logado: `gh auth status` (se não, `gh auth login`).
- Python 3.10 ou mais (o painel é só stdlib).

## O que fazer

1. Descompacte este zip em `~/fluxo-origem` (a pasta tem que se chamar assim, ou ajuste o caminho abaixo).
2. Abra o Claude Code **na raiz do seu projeto**.
3. Cole:

```
A pasta ~/fluxo-origem é a ORIGEM do fluxo de trabalho que quero instalar aqui.
Leia ~/fluxo-origem/tools/instalar-fluxo/ROTEIRO.md inteiro e siga as fases na ordem, sem pular a entrevista.
O projeto de destino é este diretório. Não faça merge de nada: o merge é meu.
```

O agente vai explorar seu projeto, fazer uma pergunta por vez (com recomendação), copiar e adaptar tudo, e terminar com um PR aberto e uma pendência na sua fila. O merge é seu.

Detalhes do que vai e do que muda: `tools/instalar-fluxo/MANIFESTO.md`.
EOF

rm -f "$ZIP"
(cd "$STAGE" && zip -qr "$ZIP" fluxo-origem)
rm -rf "$STAGE"

echo "✓ $ZIP"
echo "  $(unzip -l "$ZIP" | tail -1)"
