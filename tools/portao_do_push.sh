#!/usr/bin/env bash
# Portão do push: as conferências rápidas do job "Backend Lint, Format & Tests"
# rodam no Mac antes de o PR chegar ao CI. Em uma semana, 8 PRs ficaram
# vermelhos por erro que leva segundos para achar aqui: migration sem recibo,
# formatação do ruff e teste sem encoding="utf-8".
#
# Só o rápido. A suíte inteira do pytest fica com o CI: com várias sessões no
# Mac ao mesmo tempo, ela derruba os testes de tempo e memória.
#
# Quem chama é o .githooks/pre-push, com as linhas do push na entrada padrão.
# Sem entrada (rodando à mão), confere o HEAD. Pular uma vez: git push --no-verify.
set -uo pipefail

raiz=$(git rev-parse --show-toplevel)
cd "$raiz"
base=origin/main
zero=0000000000000000000000000000000000000000

heads=()
if [ -t 0 ]; then
  heads=(HEAD)
else
  while read -r _local_ref local_sha remote_ref _remote_sha; do
    [ "$local_sha" = "$zero" ] && continue
    case "$remote_ref" in refs/heads/main) ;; refs/heads/*) heads+=("$local_sha") ;; esac
  done
fi
[ ${#heads[@]} -eq 0 ] && exit 0

git fetch -q origin main 2>/dev/null || true
py() { uv run --no-project --python 3.12 python "$@"; }

falhas=()
conferir() {
  local nome=$1; shift
  if ! "$@"; then falhas+=("$nome"); fi
}

for head in "${heads[@]}"; do
  arquivos=$(git diff --name-only "$base...$head" 2>/dev/null) || continue

  if grep -q '^hospital-reunioes/supabase/migrations/' <<<"$arquivos"; then
    conferir "migration com número repetido" py tools/checar_migration_repetida.py --base "$base" --head "$head"
    conferir "migration com recibo" py tools/checar_recibo_da_migration.py --base "$base" --head "$head"
  fi

  if grep -q '^hospital-reunioes/backend/' <<<"$arquivos"; then
    (
      cd hospital-reunioes/backend || exit 1
      ok=0
      # Mesmo lint do CI: os bytes do UTF-8 do travessão e da meia-risca (ADR 0013).
      if LC_ALL=C grep -rlE "$(printf '\342\200\224|\342\200\223')" app/templates/; then
        echo "Travessão ou meia-risca nos templates acima. Use vírgula, ou hífen entre números (ADR 0013)."
        ok=1
      fi
      uv lock --check -q || { echo "uv.lock fora de sincronia: rode 'uv lock' em hospital-reunioes/backend."; ok=1; }
      # A versão do ruff que o uv.lock fixa, a mesma que o CI instala.
      versao=$(awk '/^name = "ruff"$/{getline; gsub(/[^0-9.]/, ""); print; exit}' uv.lock)
      uvx -q "ruff@$versao" check . || ok=1
      uvx -q "ruff@$versao" format --check . || { echo "Rode: uvx ruff@$versao format . (em hospital-reunioes/backend)"; ok=1; }
      exit $ok
    ) || falhas+=("backend (travessão, uv.lock ou ruff)")
  fi

  if grep -q '^hospital-reunioes/backend/tests/' <<<"$arquivos"; then
    (
      cd hospital-reunioes/backend || exit 1
      SUPABASE_URL=http://localhost:54321 SUPABASE_SERVICE_ROLE_KEY=dummy-key-for-ci ENVIRONMENT=ci \
        uv run -q --frozen --extra dev --python 3.12 pytest -q --no-header -p no:cacheprovider \
        tests/test_ambiente_windows.py::test_os_testes_leem_e_escrevem_arquivo_em_utf8
    ) || falhas+=('teste sem encoding="utf-8"')
  fi
done

if [ ${#falhas[@]} -gt 0 ]; then
  echo
  echo "Portão do push: o push parou. O CI reprovaria o PR por:"
  printf '  - %s\n' "${falhas[@]}"
  echo "Corrija e empurre de novo. Pular uma vez: git push --no-verify"
  exit 1
fi
exit 0
