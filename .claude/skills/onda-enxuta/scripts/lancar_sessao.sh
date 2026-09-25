#!/usr/bin/env bash
# Lança uma sessão de onda em segundo plano, com ambiente limpo e MCP zero.
#
# Uso:
#   lancar_sessao.sh <nome> <arquivo-com-o-prompt> [--dry-run] [--effort high] [--model opus] [--cwd <raiz do repo>]
#
# Por que o ambiente precisa ser limpo: dentro do Bash de uma sessão existem
# ANTHROPIC_API_KEY (chave de sessão), CLAUDE_EFFORT e outras variáveis da
# sessão pai. Um `claude` lançado dali usa a chave e falha com
# "Credit balance is too low" em vez de cobrar da assinatura (medido em 22/09/2026).
#
# --strict-mcp-config sem --mcp-config = nenhum servidor MCP; --no-chrome tira a
# integração com o Chrome (aparecia como 1 MCP na sessão de fundo); --settings
# onda-settings.json desliga os plugins (lista de skills cai de 136 para 78). O pipeline da onda
# só usa `gh` e o CLI do Coolify; a bagagem de Vercel, Notion, Figma, Gmail,
# Resend e Supabase não entra. Conectores da conta claude.ai: se ainda aparecerem,
# desligue-os para este projeto nas configurações da conta (uma vez só).
#
# Saída: o id curto que `claude attach <id>`, `claude logs <id>` e `claude stop <id>` usam.
set -u

NOME="${1:-}"; PROMPT_ARQ="${2:-}"; shift 2 || true
DRY=0; EFFORT="high"; MODEL="opus"; CWD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --effort) EFFORT="$2"; shift ;;
    --model) MODEL="$2"; shift ;;
    --cwd) CWD="$2"; shift ;;
    *) echo "argumento desconhecido: $1" >&2; exit 1 ;;
  esac
  shift
done

if [ -z "$NOME" ] || [ -z "$PROMPT_ARQ" ] || [ ! -f "$PROMPT_ARQ" ]; then
  echo "uso: lancar_sessao.sh <nome> <arquivo-com-o-prompt> [--dry-run] [--effort high] [--model opus] [--cwd <repo>]" >&2
  exit 1
fi

if [ -z "$CWD" ]; then
  CWD="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi

LIMPAR=(ANTHROPIC_API_KEY CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID
        CLAUDE_CODE_BRIDGE_SESSION_ID CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN
        CLAUDE_CODE_SSE_PORT CLAUDE_CODE_ENTRYPOINT CLAUDE_PID CLAUDE_EFFORT CLAUDE_CODE_SESSION_ATTENDED)
ENV_ARGS=()
for v in "${LIMPAR[@]}"; do ENV_ARGS+=("-u" "$v"); done

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMD=(env "${ENV_ARGS[@]}" claude --bg --name "$NOME" --strict-mcp-config --no-chrome --settings "$SKILL_DIR/onda-settings.json" --model "$MODEL" --effort "$EFFORT")

if [ "$DRY" -eq 1 ]; then
  echo "cwd: $CWD"
  echo "comando: ${CMD[*]} '<prompt de $(wc -c < "$PROMPT_ARQ") bytes em $PROMPT_ARQ>'"
  exit 0
fi

cd "$CWD" || exit 1
"${CMD[@]}" "$(cat "$PROMPT_ARQ")"
