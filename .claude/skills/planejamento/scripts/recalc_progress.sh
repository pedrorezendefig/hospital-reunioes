#!/usr/bin/env bash
set -euo pipefail

# recalc_progress.sh — Recalcula header "Progresso: X%" + frontmatter de um plano.
#
# Uso:
#   recalc_progress.sh <path/to/plano.md>
#   recalc_progress.sh --help
#
# Lê checkboxes do body, atualiza tarefas_concluidas + date_last_touched +
# sha_atual no frontmatter, e reescreve o bloco de header de progresso
# (criando se não existir). Idempotente.

show_help() {
  cat <<EOF
Uso: recalc_progress.sh <path/to/plano.md>

Recalcula o header "> ## Progresso: X%" de um plano em docs/planejamento/.

- Conta - [x] vs - [ ] no body (exclui o bloco do header)
- Atualiza frontmatter: tarefas_concluidas, tarefas_total, date_last_touched, sha_atual
- Reescreve bloco de header de progresso (cria se não existir)
- Idempotente: rodar 2x não muda nada na 2ª (exceto date_last_touched)

Exit code 0 se atualizou, 1 se erro.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || -z "${1:-}" ]]; then
  show_help
  exit 0
fi

FILE="$1"
if [[ ! -f "$FILE" ]]; then
  echo "ERRO: arquivo '$FILE' não existe" >&2
  exit 1
fi

SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "nenhum")
BRANCH=$(git branch --show-current 2>/dev/null || echo "?")
NOW=$(date "+%Y-%m-%d %H:%M")
NOW_ISO=$(date "+%Y-%m-%dT%H:%M:%S%z" | sed 's/\(..\)$/:\1/')

python3 - "$FILE" "$SHA" "$BRANCH" "$NOW" "$NOW_ISO" <<'PY'
import sys, re, pathlib

path = pathlib.Path(sys.argv[1])
sha, branch, now, now_iso = sys.argv[2:6]

content = path.read_text(encoding="utf-8")

m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
if not m:
    print(f"ERRO: '{path}' não tem frontmatter YAML válido", file=sys.stderr)
    sys.exit(1)

fm_raw, body = m.group(1), m.group(2)

fm = {}
fm_order = []
for line in fm_raw.split("\n"):
    if ":" in line and not line.startswith(" "):
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
        fm_order.append(k.strip())

header_pattern = re.compile(
    r"^> ## Progresso:[^\n]*\n(?:> [^\n]*\n)*\n?", re.MULTILINE
)
body_no_header = header_pattern.sub("", body)
done = len(re.findall(r"^\s*-\s*\[x\]", body_no_header, re.MULTILINE | re.IGNORECASE))
todo = len(re.findall(r"^\s*-\s*\[\s\]", body_no_header, re.MULTILINE))
total = done + todo


def get(k, default=""):
    v = fm.get(k, default)
    return v.strip('"').strip("'") if v else default


fase_atual = get("fase_atual", "em curso")
fase_numero = get("fase_numero", "1")
fases_total = get("fases_total", "1")
pr_num = get("pr", "")

pct = round(done / total * 100) if total > 0 else 0

pr_link = ""
if pr_num and pr_num not in ("null", "None", ""):
    if re.fullmatch(r"\d+", pr_num):
        pr_link = f" → PR [#{pr_num}](https://github.com/pedrorezendefig/hospital-reunioes/pull/{pr_num})"
    else:
        pr_link = f" → PRs #{pr_num}"

header = (
    f"> ## Progresso: {pct}%\n"
    f"> **Fase {fase_numero} de {fases_total}** — {fase_atual}\n"
    f"> **{done} de {total} tarefas** concluídas\n"
    f"> **Última atualização:** {now} · SHA `{sha}`\n"
    f"> **Branch:** `{branch}`{pr_link}\n"
)

fm["tarefas_concluidas"] = str(done)
fm["tarefas_total"] = str(total)
fm["date_last_touched"] = now_iso
fm["sha_atual"] = sha
if "fase_numero" not in fm:
    fm["fase_numero"] = fase_numero
    fm_order.append("fase_numero")
if "fases_total" not in fm:
    fm["fases_total"] = fases_total
    fm_order.append("fases_total")

fm_lines = []
for k in fm_order:
    v = fm[k]
    if (
        v
        and (" " in v or ":" in v)
        and not v.startswith('"')
        and not v.startswith("[")
        and not v.startswith("{")
    ):
        v = '"' + v.replace('"', '\\"') + '"'
    fm_lines.append(f"{k}: {v}")
new_fm = "\n".join(fm_lines)

body_clean = header_pattern.sub("", body).lstrip("\n")

new_content = f"---\n{new_fm}\n---\n\n{header}\n{body_clean}"

# Idempotência relaxada: compara ignorando date_last_touched e sha_atual
def normalize(text):
    text = re.sub(r"date_last_touched: [^\n]+", "date_last_touched: X", text)
    text = re.sub(r"sha_atual: [^\n]+", "sha_atual: X", text)
    text = re.sub(r"Última atualização:[^\n]+", "Última atualização: X", text)
    return text


if normalize(content) == normalize(new_content):
    print(f"[noop] {path}")
    sys.exit(0)

path.write_text(new_content, encoding="utf-8")
print(f"[updated] {path}  →  {done}/{total} ({pct}%)  Fase {fase_numero}/{fases_total}")
PY
