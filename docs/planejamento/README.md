# Planejamento — fonte única da verdade do plano de trabalho

Esta pasta é onde mora **o plano** de cada feature/fix/refactor do Hospital Reuniões. Cada plano é versionado em git, tem **frontmatter YAML** + **header de progresso visível** + **8 seções** estruturadas pra qualquer sessão Claude (ou dev humano) retomar trabalho de onde a sessão anterior parou.

| Caminho | O que é | Versionado? | Quem usa |
|---|---|---|---|
| `~/.claude/plans/*.md` | Rascunho do plan mode nativo do Claude Code | ❌ local | Sessão atual do Claude |
| `.superpowers/brainstorm/<id>/` | Cache visual da skill `superpowers:brainstorming` | ❌ gitignored | Sessão atual |
| **`docs/planejamento/em-andamento/<source>/*.md`** | **Plano canônico do trabalho ativo** | **✅ git** | **Todas as sessões + dev humano** |
| **`docs/planejamento/finalizado/<source>/*.md`** | **Planos concluídos com sucesso** | **✅ git** | **Histórico** |
| `docs/spec/chronicles/{🟡,🟢,🔴}-*.md` | Diário enxuto de execução pós-fato (por PR) | ✅ git | CHANGELOG, GitHub Mobile, explorer |

**Por que duas pastas (chronicles + planejamento)?** O chronicle é o "post-it na geladeira" — 1 por PR, cabe em 1 tela, vai pro CHANGELOG, alimenta a timeline. O plano é o "manual de instruções" — pode cobrir múltiplos PRs sequenciais, 200+ linhas, mapeia todo o contexto que uma LLM nova precisa pra retomar o trabalho.

---

## Estrutura

```
docs/planejamento/
├── README.md
├── em-andamento/                              ← planos ativos
│   ├── plan-mode/                             ← Shift+Tab+Tab, importado via hook
│   │   └── .gitkeep
│   ├── superpowers/                           ← output de superpowers:writing-plans
│   │   └── .gitkeep
│   └── manual/                                ← você escreveu à mão no VS Code
│       └── .gitkeep
└── finalizado/                                ← planos concluídos
    ├── plan-mode/.gitkeep
    ├── superpowers/.gitkeep
    └── manual/
        └── 2026-05-22-1714-planejamento-estrutura.md
```

**Filename:** `YYYY-MM-DD-HHMM-<kebab-slug>.md`. Timestamp = criação do plano. Slug = título kebab-case sem acentos.

**Subdivisão por origem:**

| Subpasta | Origem | Como chega lá |
|---|---|---|
| `plan-mode/` | Plan mode nativo do Claude Code (`Shift+Tab+Tab`) | Hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json` dispara `import_planmode.sh` que copia o arquivo de `~/.claude/plans/` pra cá. |
| `superpowers/` | Skill `superpowers:writing-plans` | A skill está configurada (via `CLAUDE.md`) pra escrever direto aqui. |
| `manual/` | Você escreveu à mão no VS Code, ou `/start` Modo A criou | Diretamente. |

**Trajetória do arquivo:**

- Sucesso (`/deploy ship` healthy) → **move** de `em-andamento/<source>/` pra `finalizado/<source>/`. Nome permanece.
- Abandono (deploy falhou sem recovery OU dev desistiu) → arquivo é **deletado**. Não polui o histórico com tentativas malsucedidas; a cronologia da falha vive no chronicle 🔴 em `docs/spec/chronicles/` e no `history.json`.

---

## Schema obrigatório

Cada plano tem **frontmatter** + **header de progresso** + **8 seções**.

### Frontmatter YAML

```yaml
---
slug: secretaria-pode-ver-reuniao
title: "Coluna secretaria_pode_ver + filtro no endpoint + checkbox no form"
status: rascunho | ativo | finalizado
plan_source: plan-mode-claude | superpowers-writing-plans | manual | skipped
author: Pedro Rezende <pmrdef@gmail.com>
date_created: 2026-05-22T18:30:00Z
date_last_touched: 2026-05-22T19:45:00Z
branch: feature/secretaria-pode-ver
chronicle: docs/spec/chronicles/🟡-2026-05-22-1830-secretaria-pode-ver.md
pr: 42
sha_inicio: 805daa0
sha_atual: f99c81d
estimativa_horas: 3
fase_atual: "implementando 4.3 (checkbox no form)"
fase_numero: 2
fases_total: 3
tarefas_total: 5
tarefas_concluidas: 2
---
```

| Campo | Função | Quem atualiza |
|---|---|---|
| `slug` | id curto (kebab-case) | criação |
| `title` | título humano completo | criação |
| `status` | rascunho / ativo / finalizado | `/start`, `/deploy` |
| `plan_source` | origem do plano (= nome da subpasta) | criação |
| `branch` | branch git da implementação | `/start` |
| `chronicle` | path do chronicle 🟡 quando existir | `/ship` |
| `pr` | número do PR no GitHub | `/ship` |
| `sha_inicio` | SHA da main quando começou | `/start` |
| `sha_atual` | SHA do último commit da branch | `/ship`, `recalc_progress.sh` |
| `fase_atual` | descrição curta da fase em curso | manual / `/start` / `/ship` |
| `fase_numero` / `fases_total` | progresso quantitativo de fases | manual (default 1/1) |
| `tarefas_total` / `tarefas_concluidas` | contagem de `[x]`/`[ ]` no body | **derivado** — `recalc_progress.sh` |
| `date_last_touched` | última edição do plano | `recalc_progress.sh` |

### Header de progresso (logo após frontmatter)

Bloco blockquote markdown padronizado. Reescrito automaticamente por `recalc_progress.sh` (chamado por `/ship`, `/deploy` e `/planejamento progresso`):

```markdown
> ## Progresso: 40%
> **Fase 2 de 3** — PR2: implementando SignatariosCard.tsx
> **6 de 15 tarefas** concluídas
> **Última atualização:** 2026-05-22 19:45 · SHA `f99c81d`
> **Branch:** `feat/clicksign-signatarios-status` → PR [#15](https://github.com/pedrorezendefig/hospital-reunioes/pull/15)
```

**Algoritmo:** `pct = round(tarefas_concluidas / tarefas_total * 100)`. Quando `tarefas_total = 0` (plano recém-importado sem checkboxes), mostra `0%`.

**Fonte da verdade:** o **body** (checkboxes `[x]`/`[ ]`). O frontmatter é derivado e o header é derivado do frontmatter. Logo: você marca `[x]` no body, roda `/planejamento progresso`, e o frontmatter + header atualizam.

### Corpo — 8 seções

#### §1. Visão (1 parágrafo)

Resumo executivo: **o que** vai ser construído e **por que**. Quem lê isso em 30s entende o objetivo.

#### §2. Contexto técnico

Subseções 2.1 (arquivos existentes relevantes), 2.2 (achados de exploração, padrões a seguir, gotchas), 2.3 (restrições e premissas).

#### §3. Arquitetura proposta

Diagrama (mermaid ou ascii) + lista de componentes a criar/modificar + fluxo de dados.

#### §4. Tarefas (checkboxes com critério verificável)

```markdown
- [x] 4.1 Migration 038
  - Critério: `grep -q "secretaria_pode_ver" supabase/migrations/038*.sql`
- [ ] 4.2 Endpoint filtra por role
  - Critério: `pytest tests/test_secretaria_gates.py::test_filter -v` retorna green
```

Cada tarefa tem arquivo + critério executável. Sem "verificar manualmente" vago.

#### §5. Estado de execução (snapshot — não append)

Reescrita a cada commit WIP. Sempre reflete o agora.

```markdown
**Fase atual:** implementando 4.3 (checkbox no form, 50%)
**Próximo passo:** Adicionar `secretaria_pode_ver` ao body do submit em `ReuniaoForm.tsx:142`.
**Bloqueios atuais:** nenhum
```

#### §6. Decisões tomadas

Decisão + alternativa rejeitada + motivo. Evita reabrir discussão na próxima sessão.

#### §7. Comandos pra retomada (cópia-cola)

Comandos bash exatos que uma LLM nova roda em <5min pra se situar.

#### §8. Histórico desta sessão (opcional)

Log curto. Não obrigatório.

---

## Skill `/planejamento` (gerenciar os planos)

Skill versionada em `.claude/skills/planejamento/`. 4 subcomandos:

| Subcomando | O que faz |
|---|---|
| `/planejamento progresso [--file <path>]` | Recalcula header de progresso (% + fase + tarefas). Idempotente. |
| `/planejamento importar [--source <path>] [--type plan-mode\|superpowers]` | Importa plano externo (default: mais recente em `~/.claude/plans/`). Adiciona frontmatter + header. Deixa staged. |
| `/planejamento status` | Lista todos os planos em `em-andamento/*/` com % e branch. |
| `/planejamento finalizar [--abort]` | Move pra `finalizado/<source>/` (sucesso) ou deleta (`--abort`). |

Helpers em `.claude/skills/planejamento/scripts/`:
- `recalc_progress.sh <path>` — reescreve header + atualiza frontmatter. Chamado também por `/ship` e `/deploy`.
- `import_planmode.sh [--source <path>]` — importa plan-mode. Chamado pelo hook `PostToolUse:ExitPlanMode`.

---

## Quem cria e atualiza

| Evento | Quem | O que faz |
|---|---|---|
| Plan mode nativo (`Shift+Tab+Tab`) → você aceita | Hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json` | Dispara `import_planmode.sh`. Copia plano pra `em-andamento/plan-mode/<YYYY-MM-DD-HHMM>-<slug>.md`. Adiciona frontmatter + header vazio. `git add` (não commita). |
| `superpowers:writing-plans` rodou (geralmente via `/start --rigoroso`) | A própria skill | Escreve direto em `em-andamento/superpowers/<slug>.md`. |
| `/start` Modo A em working tree limpo | `/start` | Cria plano em `em-andamento/manual/<slug>.md` (ou `superpowers/` se `--rigoroso`). |
| Você editou plano à mão no VS Code | Você | Edita livre. Header fica desatualizado até próximo `/planejamento progresso` ou `/ship`. |
| Cada commit WIP durante implementação | `/ship` | Chama `recalc_progress.sh` no plano da branch atual. Atualiza header + frontmatter. |
| `/ship` cria chronicle 🟡 | `/ship` | Atualiza frontmatter do plano: `chronicle: <path>`, `pr: <N>`. |
| `/deploy ship` healthy | `/deploy` | Move arquivo pra `finalizado/<source>/`, frontmatter `status: finalizado`. |
| `/deploy ship` failed sem recovery | `/deploy` | **Deleta** arquivo de `em-andamento/<source>/`. Cronologia sobrevive no chronicle 🔴 + `history.json`. |

---

## Continuidade entre sessões (caso de uso central)

Você fechou o terminal. Próxima sessão Claude num terminal novo, no mesmo projeto:

```bash
# 1. Confirma branch (estado de git é a memória autoritativa)
git branch --show-current
# → feat/clicksign-signatarios-status

# 2. Lista planos abertos
/planejamento status
# →  | plan-mode | 2026-05-22-1900-clicksign-signatarios-card | 40% (6/15) | 2/3 | feat/clicksign-signatarios-status |

# 3. Lê o plano da branch atual
cat docs/planejamento/em-andamento/plan-mode/2026-05-22-1900-clicksign-signatarios-card.md
# → header de progresso no topo + §5 (Estado: "Próximo passo: ...") + §7 (comandos de retomada)

# 4. Retoma trabalho seguindo §5 / §7
```

Mini-commits "wip" feitos a cada checkbox conclusa garantem que o estado fica em git. Quando `/ship` mergeia, faz **squash** — wip some, fica só 1 commit conventional. Resultado: chronicle 🟡 + plano commitado = memória independente de sessão Claude.

---

## Convenções importantes

1. **Header é derivado** — não edite o bloco `> ## Progresso:` à mão. `recalc_progress.sh` reescreve.
2. **`tarefas_total` / `tarefas_concluidas` no frontmatter são derivados** — contados de `[x]`/`[ ]` no body. Edição à mão é sobrescrita.
3. **§4 tem critério executável** — "verificar manualmente" é proibido. Escreva o comando bash exato.
4. **§5 é snapshot** — reescrita a cada commit, não append. Próxima LLM lê estado atual.
5. **§7 é cópia-cola** — comandos exatos pra <5min de retomada.
6. **Move (não copia) ao arquivar** — `git mv` preserva blame.
7. **Status: rascunho** = plano sem branch. **ativo** = código em desenvolvimento. **finalizado** = deploy healthy. **Abandono = `git rm`** — arquivo deixa de existir.
8. **`fase_numero` / `fases_total`** — padrão 1/1 (PR único). Use >1 quando o plano cobre múltiplos PRs sequenciais (ex: PR1 hotfix + PR2 feature).

---

## Setup do hook ExitPlanMode (1x por dev)

O hook que importa planos do plan mode pra `em-andamento/plan-mode/` vive em `~/.claude/settings.json` (config local, fora do repo). Cada dev do time precisa instalar uma vez:

```bash
# 1. Backup do settings.json atual
cp ~/.claude/settings.json ~/.claude/settings.json.bak

# 2. Adicionar matcher no array PostToolUse
# Edite ~/.claude/settings.json e adicione (junto dos outros matchers):
```

```json
{
  "matcher": "ExitPlanMode",
  "hooks": [
    {
      "type": "command",
      "command": "INPUT=$(cat); CWD=$(echo \"$INPUT\" | jq -r '.cwd // \"\"'); SCRIPT=\"$CWD/.claude/skills/planejamento/scripts/import_planmode.sh\"; if [ -d \"$CWD/docs/planejamento/em-andamento/plan-mode\" ] && [ -x \"$SCRIPT\" ]; then (cd \"$CWD\" && bash \"$SCRIPT\" \"$INPUT\") 2>&1; fi; true"
    }
  ]
}
```

**Validar:** `python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))"` deve sair com exit 0.

**Comportamento:** o hook dispara após `ExitPlanMode` em qualquer sessão Claude. Guarda interno: só age se o CWD atual tem `docs/planejamento/em-andamento/plan-mode/` (não vaza pra outros projetos). Caso o projeto não tenha a estrutura, skipa silenciosamente.

**Reinício necessário:** abrir terminal novo / sessão nova do Claude Code (o `settings.json` é lido no início da sessão).

## Exemplos

- Plano `manual/` finalizado: `docs/planejamento/finalizado/manual/2026-05-22-1714-planejamento-estrutura.md`
- Plano `plan-mode/` em andamento: ver `docs/planejamento/em-andamento/plan-mode/` (gerado pelo hook quando você sai de plan mode no projeto).
