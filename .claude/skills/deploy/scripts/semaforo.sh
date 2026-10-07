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
#   semaforo.sh parar  <chave> [linha]       # o dono marca a trava como parada
#   semaforo.sh status                        # quem segura e há quanto tempo
#
# Chave: identificador da sessão (basename do scratchpad da sessão serve).
# Reentrante: pegar com a mesma chave de quem já segura devolve 0 na hora.
#
# Saídas de `pegar`: 0 pegou (ou já era sua) · 3 ainda ocupado após --espera
# (chame de novo) · 2 trava velha (mais que --velha minutos) · 4 trava parada.
#
# Parada (issue #999): a subida que saiu com 3 ou 4 deixa a trava presa e marcada
# (`parar`, arquivo `parada` dentro da pasta, com a chave e a linha do erro).
# Quem chega, o dono inclusive, sai na hora com 4, sem esperar e sem pegar:
# prod espera o rollback humano. Na trava velha e na parada, quem confere o
# Coolify e solta a trava alheia é o humano (o `--forcar` é dele); o `soltar`
# do dono, depois do rollback, apaga a marca junto com a pasta.
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
motivo_da_parada() { sed -n 2p "$LOCK/parada" 2>/dev/null; }

case "$ACAO" in
  status)
    if [ -f "$LOCK/parada" ]; then
      echo "ocupado por $(dono) há $(idade_min) min: $(descricao) · parada: $(motivo_da_parada)"
    elif [ -d "$LOCK" ]; then
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
      if [ -f "$LOCK/parada" ]; then
        echo "parada: prod espera rollback humano, chave $(dono): $(motivo_da_parada)" >&2
        exit 4
      fi
      if [ "$(dono)" = "$CHAVE" ]; then
        echo "já é sua (reentrante): $CHAVE"
        exit 0
      fi
      if [ "$(idade_min)" -ge "$VELHA_MIN" ]; then
        echo "trava velha: $(dono) segura há $(idade_min) min ($(descricao)). Prod pode estar esperando rollback humano: quem confere o Coolify e solta a trava é o humano." >&2
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

  parar)
    CHAVE="${1:-}"; LINHA="${2:-}"
    [ -n "$CHAVE" ] || { echo "uso: semaforo.sh parar <chave> [linha]" >&2; exit 64; }
    if [ ! -d "$LOCK" ] || [ "$(dono)" != "$CHAVE" ]; then
      echo "recusado: a trava não é de $CHAVE" >&2
      exit 1
    fi
    printf '%s\n%s\n' "$CHAVE" "$LINHA" > "$LOCK/parada"
    echo "parada: $CHAVE ($LINHA)"
    ;;

  *)
    echo "uso: semaforo.sh pegar|soltar|parar|status" >&2; exit 64
    ;;
esac
