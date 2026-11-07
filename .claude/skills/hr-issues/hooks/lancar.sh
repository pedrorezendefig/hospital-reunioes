#!/bin/bash
# Clique num número da aba Issues: abre uma sessão de fundo (Claude Agents) para aquela issue.
# Nenhuma sessão roda trabalho sem o OK do Pedro: a de onda para no "Posso lançar?" da
# /montar-ondas-enxutas, a de guia só escreve o passo a passo, a de triagem pergunta.
#
# Uso: lancar.sh <prd|issue|humana|triagem> <N>
# Saída: a linha do `claude --bg` (id e nome da sessão), para o painel mostrar.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
umask 077
TIPO="${1:-}"; N="${2:-}"
case "$N" in ''|*[!0-9]*) echo "número inválido: $N" >&2; exit 1 ;; esac

RAIZ="$(cd "$(dirname "$0")/../../../.." && pwd)"
PASTA="${TMPDIR:-$HOME/.cache}"; PASTA="${PASTA%/}/onda-enxuta"
mkdir -p "$PASTA"

case "$TIPO" in
  prd)
    NOME="onda-prd-$N"
    PROMPT="/montar-ondas-enxutas só para o PRD #$N: planeje apenas as fatias abertas dele. As outras issues abertas ficam fora deste plano (não precisam de balde nem de prestação de contas).
Esta sessão foi aberta por um clique na aba Issues. Mostre o resumo da onda (o que entra em cada onda, o que é humano no meio, o prompt da sessão) e termine em \"Posso lançar?\". Nada roda antes do \"pode\" do Pedro." ;;
  issue)
    NOME="onda-$N"
    PROMPT="/montar-ondas-enxutas só para a issue #$N: uma fila, uma onda, só ela. As outras issues abertas ficam fora deste plano (não precisam de balde nem de prestação de contas).
Esta sessão foi aberta por um clique na aba Issues. Mostre o resumo da onda (o que a issue muda, o que é humano no meio, o prompt da sessão) e termine em \"Posso lançar?\". Nada roda antes do \"pode\" do Pedro." ;;
  humana)
    NOME="guia-$N"
    PROMPT="A issue #$N é humana. Monte só o passo a passo dela, no formato da seção \"4. Humanas: passo a passo\" do /minhas-issues (leia o corpo e os comentários com gh issue view $N --comments, confira se já foi feito, separe o que é do Pedro e o que o agente roda).
Esta sessão foi aberta por um clique na aba Issues. Não mude nada no GitHub nem no código: mostre o guia e espere o Pedro. Se ele pedir, rode a parte que é do agente." ;;
  triagem)
    NOME="triagem-$N"
    PROMPT="/triage da issue #$N.
Esta sessão foi aberta por um clique na aba Issues: o Pedro responde aqui. Termine dizendo o próximo passo (ready-for-agent vira onda, ready-for-human vira guia)." ;;
  *) echo "tipo inválido: $TIPO" >&2; exit 1 ;;
esac

ARQ="$PASTA/$NOME.md"
printf '%s\n' "$PROMPT" > "$ARQ"
cd "$RAIZ" || exit 1
bash "$RAIZ/.claude/skills/onda-enxuta/scripts/lancar_sessao.sh" "$NOME" "$ARQ" --cwd "$RAIZ" 2>&1 | tail -3
exit "${PIPESTATUS[0]}"
