---
name: planejamento
description: Skill universal de gerenciamento de planos versionados em docs/planejamento/{em-andamento,finalizado}/{plan-mode,superpowers,manual}/. Atualiza header de progresso ("Progresso X% · Fase N de M"), importa plano do plan mode nativo do Claude Code, lista planos abertos com %, finaliza ou aborta. Use sempre que o usuário disser "/planejamento", "atualiza progresso", "como tá meu plano", "importa plano", "finaliza plano", "abandonei o plano", "marquei checkbox", "recalcula plano", ou referenciar planejamento/plano-de-trabalho/fase atual do trabalho. Sub-skill central pra rastreamento entre sessões — quando você abre uma sessão nova num terminal e quer saber "onde parei", invocar /planejamento status. Helpers em scripts/ são chamados também por /ship (a cada checkpoint) e /deploy (move plano pra finalizado/).
---

# /planejamento — gerenciar planos versionados

Os planos do projeto Hospital vivem em **`docs/planejamento/`** com 3 sub-origens dentro de `em-andamento/` e `finalizado/`:

```
docs/planejamento/
├── em-andamento/
│   ├── plan-mode/        ← Planos do plan mode nativo (Shift+Tab+Tab), importados via hook
│   ├── superpowers/      ← Output da skill superpowers:writing-plans
│   └── manual/           ← Você escreveu à mão no VS Code
└── finalizado/
    ├── plan-mode/
    ├── superpowers/
    └── manual/
```

Cada plano tem **YAML frontmatter** + **bloco de header de progresso** (blockquote markdown, renderiza no GitHub Mobile) + **8 seções**:

```markdown
---
slug: <kebab-case>
status: rascunho | ativo | finalizado
plan_source: plan-mode-claude | superpowers-writing-plans | manual | skipped
tarefas_total: 15
tarefas_concluidas: 6
fase_numero: 2
fases_total: 3
fase_atual: "PR2 — implementando SignatariosCard.tsx"
sha_atual: f99c81d
branch: feat/clicksign-signatarios-status
pr: 15
date_last_touched: 2026-05-22T19:45:00Z
---

> ## Progresso: 40%
> **Fase 2 de 3** — PR2: implementando SignatariosCard.tsx
> **6 de 15 tarefas** concluídas
> **Última atualização:** 2026-05-22 19:45 · SHA `f99c81d`
> **Branch:** `feat/clicksign-signatarios-status` → PR [#15](https://github.com/.../pull/15)

## 1. Visão
...
```

Schema completo: `docs/planejamento/README.md`.

---

## Subcomandos

### `/planejamento progresso [--file <path>]`

Recalcula o header de progresso de um plano. Default: detecta o único plano em `em-andamento/*/` cujo `branch:` no frontmatter casa com a branch atual. Se houver mais de um, lista e pede pra escolher.

**Algoritmo (helper bash):**
1. Lê o arquivo, parsea frontmatter YAML.
2. Conta `- [x]` (case-insensitive) e `- [ ]` no body, **excluindo** o bloco do header de progresso.
3. Calcula `pct = round(done / total * 100)`.
4. Atualiza frontmatter: `tarefas_concluidas`, `tarefas_total`, `date_last_touched`, `sha_atual`.
5. Reescreve o bloco de header de progresso no topo (cria se não existir, mantendo `fase_atual`, `fase_numero`, `fases_total`, `pr` do frontmatter).
6. Idempotência: rodar 2x não altera o arquivo (exceto `date_last_touched` e `sha_atual`, que sempre refletem o agora).

**Execução:**
```bash
bash .claude/skills/planejamento/scripts/recalc_progress.sh <path/to/plano.md>
```

**Quando rodar:**
- Manualmente após editar checkboxes no VS Code.
- Automaticamente: `/ship` chama após cada commit; `/deploy` chama antes de mover pra `finalizado/`.

**Output:**
```
[updated] docs/planejamento/em-andamento/plan-mode/2026-05-22-1900-clicksign.md  →  6/15 (40%)  Fase 2/3
```

---

### `/planejamento importar [--source <path>] [--type plan-mode|superpowers]`

Importa plano externo pra `em-andamento/<type>/<YYYY-MM-DD-HHMM>-<slug>.md` adicionando frontmatter mínimo + header de progresso vazio.

**Defaults:**
- `--source`: arquivo mais recente em `~/.claude/plans/` (plan mode nativo).
- `--type`: `plan-mode`.

**Slug:** derivado da primeira H1 do conteúdo (normalizado: lowercase, sem acentos, kebab-case, max 60 chars). Fallback: nome do arquivo limpo.

**Execução:**
```bash
bash .claude/skills/planejamento/scripts/import_planmode.sh                  # auto
bash .claude/skills/planejamento/scripts/import_planmode.sh --source <path>  # manual
```

O script **não commita** — deixa o arquivo staged. Você (ou `/start`) decide quando commitar.

**Idempotência:** se já existir arquivo com mesmo slug nos últimos 60s, skipa (evita duplicação se hook + comando manual rodarem juntos).

**Importação automática via hook:** quando você sai do plan mode (`Shift+Tab+Tab`), o hook `PostToolUse:ExitPlanMode` em `~/.claude/settings.json` dispara este script automaticamente — desde que `docs/planejamento/em-andamento/plan-mode/` exista no CWD (guard pra não vazar pra outros projetos).

**Tipo superpowers:** a skill `superpowers:writing-plans` está configurada (via instrução em `CLAUDE.md`) pra escrever direto em `docs/planejamento/em-andamento/superpowers/`. Não passa por importação.

---

### `/planejamento status`

Lista todos os planos em `em-andamento/*/` com nome curto + progresso + branch.

**Execução:** Claude lê glob `docs/planejamento/em-andamento/*/*.md`, parsea frontmatter de cada um, monta tabela markdown:

```
| Origem | Plano | Progresso | Fase | Branch |
|---|---|---|---|---|
| plan-mode | 2026-05-22-1900-clicksign-signatarios-card | 40% (6/15) | 2/3 | feat/clicksign-signatarios-status |
| manual | 2026-05-23-1000-redesign-dashboard | 12% (3/25) | 1/2 | feat/dashboard-redesign |
```

Útil pra responder "onde parei?" entre sessões. Se vazio, output: "Nenhum plano em andamento."

---

### `/planejamento finalizar [--abort]`

**Default (sucesso):** move o plano da branch atual de `em-andamento/<source>/<X>.md` pra `finalizado/<source>/<X>.md` (preserva blame via `git mv`), atualiza `status: finalizado` no frontmatter. Sobrescreve `date_last_touched`.

**Com `--abort`:** deleta o arquivo de `em-andamento/<source>/`. A cronologia da falha sobrevive em `docs/spec/chronicles/🔴-*.md` (criado pelo `/deploy` se aplicável) ou no `history.json` (gerado pelo `/deploy`).

**Execução manual:**
```bash
git mv docs/planejamento/em-andamento/<source>/<X>.md docs/planejamento/finalizado/<source>/<X>.md
# editar status: finalizado no frontmatter
bash .claude/skills/planejamento/scripts/recalc_progress.sh docs/planejamento/finalizado/<source>/<X>.md
```

**Quando rodar:**
- Automaticamente: `/deploy ship` healthy chama essa lógica no Passo 9.3.5.
- Manualmente: quando você decide arquivar/abandonar sem passar pelo `/deploy`.

---

## Integração com outras skills

| Skill | Como usa /planejamento |
|---|---|
| `/start` | Modo A (planejamento): cria plano em `em-andamento/<source>/`. Modo D (retomar): glob nas 3 subpastas pra detectar plano da branch atual. Bootstrap chama `recalc_progress.sh` antes de mostrar o resumo. |
| `/ship` | Após cada checkpoint (commit, push, PR, merge), chama `recalc_progress.sh` no plano da branch pra atualizar header com SHA novo. |
| `/deploy` | Passo 9.3.5: healthy → move plano `em-andamento/<source>/` → `finalizado/<source>/`. Failed sem recovery → deleta plano. |
| `superpowers:writing-plans` | Configurada (via `CLAUDE.md`) pra salvar em `docs/planejamento/em-andamento/superpowers/<slug>.md`. |
| Hook `PostToolUse:ExitPlanMode` | Dispara `import_planmode.sh` quando você sai do plan mode nativo. |

---

## Convenções

1. **Header de progresso é derivado** — frontmatter + body são fonte da verdade. `recalc_progress.sh` sempre reescreve o bloco do header.
2. **Frontmatter é parcialmente derivado** — `tarefas_total`, `tarefas_concluidas`, `date_last_touched`, `sha_atual` são atualizados pelo script. Os outros campos (slug, title, fase_atual, fase_numero, fases_total, etc.) você edita à mão ou via `/start` / `/ship`.
3. **`fase_atual` é descritivo curto** (max 60 chars). Ex: "PR2 — implementando SignatariosCard.tsx". Não é o número da fase (que é `fase_numero`).
4. **`fases_total` default 1** — pra planos de PR único. Use >1 quando o plano cobre múltiplos PRs sequenciais.
5. **Arquivos `.md` são versionados** — você pode editar livremente no VS Code, commitar, pushar. As skills não bloqueiam edição manual.
6. **Continuidade entre sessões:** mini-commits "wip" feitos a cada checkbox conclusa preservam o estado em git. Próxima sessão Claude roda `/planejamento status` + `cat <plano>` em <5s pra retomar.

---

## Helpers (scripts/)

| Script | Propósito | Chamado por |
|---|---|---|
| `scripts/recalc_progress.sh <path>` | Reescreve header + atualiza frontmatter | `/planejamento progresso`, `/ship`, `/deploy` |
| `scripts/import_planmode.sh [--source <path>]` | Importa plan-mode pra em-andamento/plan-mode/ | Hook ExitPlanMode, `/planejamento importar` |

Ambos são bash + python3 inline (sem dependências extras). Idempotentes.

---

## Quando NÃO usar

- Para registrar **deploys** — use `docs/spec/chronicles/` (skill `/deploy` cuida).
- Para registrar **decisões arquiteturais permanentes** — use `docs/spec/snapshots/` ou comentário no código.
- Para rascunhos descartáveis — fique em `~/.claude/plans/` mesmo. Só importe pra `docs/planejamento/` quando o plano vai virar trabalho real.
