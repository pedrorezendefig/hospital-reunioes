#!/usr/bin/env bash
# Semáforo de deploy entre sessões paralelas na mesma máquina.
#
# Uma pasta em /tmp criada com mkdir (atômico) é a trava. Quem segura a trava
# pode mergear na main e deployar; as outras sessões esperam na fila sozinhas,
# sem precisar do humano como porteiro.
#
# Uso:
#   semaforo.sh pegar  <chave> [descricao]   # espera até conseguir (ou até --espera segundos)
#   semaforo.sh soltar <chave> [--forcar]    # só o dono solta; --forcar ignora o dono
#   semaforo.sh status                        # quem segura e há quanto tempo
#
# Chave: identificador da sessão (basename do scratchpad da sessão serve).
# Reentrante: pegar com a mesma chave de quem já segura devolve 0 na hora.
#
# Saídas de `pegar`: 0 pegou (ou já era sua) · 3 ainda ocupado após --espera
# (chame de novo) · 2 trava velha (mais que --velha minutos): confira no Coolify
# se há build rodando e, se não houver, `soltar <chave-do-dono> --forcar`.
#
# Env opcionais: SEMAFORO_SLUG (default: lido de docs/spec/deploy/project.json),
# SEMAFORO_ESPERA (segundos, default 540: cabe no timeout de 10 min do Bash),
# SEMAFORO_VELHA (minutos, default 60), SEMAFORO_PASSO (segundos entre tentativas, default 20).
set -u

ACAO="${1:-}"; shift || true
SLUG="${SEMAFORO_SLUG:-}"
if [ -z "$SLUG" ]; then
  RAIZ="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  SLUG="$(jq -r '.project.slug // empty' "$RAIZ/docs/spec/deploy/project.json" 2>/dev/null || true)"
fi
SLUG="${SLUG:-projeto}"
LOCK="/tmp/deploy-semaforo-${SLUG}.lock"
ESPERA="${SEMAFORO_ESPERA:-540}"
VELHA_MIN="${SEMAFORO_VELHA:-60}"
PASSO="${SEMAFORO_PASSO:-20}"

agora() { date +%s; }
idade_min() {
  local desde; desde="$(cat "$LOCK/desde" 2>/dev/null || echo 0)"
  echo $(( ( $(agora) - desde ) / 60 ))
}
dono() { cat "$LOCK/chave" 2>/dev/null || echo "?"; }
descricao() { cat "$LOCK/descricao" 2>/dev/null || echo ""; }

case "$ACAO" in
  status)
    if [ -d "$LOCK" ]; then
      echo "ocupado por $(dono) há $(idade_min) min: $(descricao)"
    else
      echo "livre"
    fi
    ;;

  pegar)
    CHAVE="${1:-}"; DESC="${2:-}"
    [ -n "$CHAVE" ] || { echo "uso: semaforo.sh pegar <chave> [descricao]" >&2; exit 64; }
    INICIO="$(agora)"
    while :; do
      if mkdir "$LOCK" 2>/dev/null; then
        echo "$CHAVE" > "$LOCK/chave"
        echo "$DESC"  > "$LOCK/descricao"
        agora        > "$LOCK/desde"
        echo "pegou: $CHAVE ($DESC)"
        exit 0
      fi
      if [ "$(dono)" = "$CHAVE" ]; then
        echo "já é sua (reentrante): $CHAVE"
        exit 0
      fi
      if [ "$(idade_min)" -ge "$VELHA_MIN" ]; then
        echo "trava velha: $(dono) segura há $(idade_min) min ($(descricao)). Confira o Coolify; sem build rodando, solte com: semaforo.sh soltar $(dono) --forcar" >&2
        exit 2
      fi
      if [ $(( $(agora) - INICIO )) -ge "$ESPERA" ]; then
        echo "ainda ocupado por $(dono) há $(idade_min) min ($(descricao)). Chame pegar de novo." >&2
        exit 3
      fi
      sleep "$PASSO"
    done
    ;;

  soltar)
    CHAVE="${1:-}"; FORCAR="${2:-}"
    [ -n "$CHAVE" ] || { echo "uso: semaforo.sh soltar <chave> [--forcar]" >&2; exit 64; }
    if [ ! -d "$LOCK" ]; then echo "já estava livre"; exit 0; fi
    if [ "$(dono)" = "$CHAVE" ] || [ "$FORCAR" = "--forcar" ]; then
      rm -rf "$LOCK"; echo "soltou: $CHAVE"; exit 0
    fi
    echo "recusado: a trava é de $(dono), não de $CHAVE" >&2
    exit 1
    ;;

  *)
    echo "uso: semaforo.sh pegar|soltar|status" >&2; exit 64
    ;;
esac
