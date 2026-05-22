# Planejamento — fonte única da verdade do plano de trabalho

Esta pasta é onde mora **o plano** de cada feature/fix/refactor do Hospital Reuniões. Distinta de:

| Caminho | O que é | Versionado? | Quem usa |
|---|---|---|---|
| `~/.claude/plans/*.md` | Rascunho do plan mode nativo do Claude Code | ❌ local | Sessão atual do Claude |
| `.superpowers/brainstorm/<id>/` | Cache visual da skill `superpowers:brainstorming` | ❌ gitignored | Sessão atual |
| **`docs/planejamento/em-andamento/*.md`** | **Plano canônico do trabalho ativo** | **✅ git** | **Todas as sessões + dev humano** |
| **`docs/planejamento/finalizado/*.md`** | **Planos concluídos com sucesso** | **✅ git** | **Histórico** |
| `docs/spec/chronicles/{🟡,🟢,🔴}-*.md` | Diário enxuto de execução pós-fato | ✅ git | CHANGELOG, GitHub Mobile, explorer |

**Por que duas pastas?** O chronicle é o "post-it na geladeira" — cabe em 1 tela, vai pro CHANGELOG, alimenta a timeline. O plano é o "manual de instruções" — pode ter 200+ linhas, mapeia todo o contexto que uma LLM nova precisa pra retomar o trabalho.

---

## Estrutura

```
docs/planejamento/
├── README.md                                  ← este arquivo
├── em-andamento/                              ← planos ativos (status: rascunho | ativo)
│   ├── .gitkeep
│   └── 2026-05-22-1830-<slug>.md
└── finalizado/                                ← planos concluídos com sucesso (status: finalizado)
    ├── .gitkeep
    └── 2026-05-22-1241-<slug>.md
```

Filename: `YYYY-MM-DD-HHMM-<kebab-slug>.md`. Timestamp = criação do plano. Slug = título kebab-case sem acentos.

**Trajetória do arquivo:**

- Sucesso (`/deploy ship` healthy) → **move** de `em-andamento/` pra `finalizado/`. Nome permanece (hora de criação é arquivo morta).
- Abandono (deploy falhou sem recovery OU dev desistiu) → arquivo é **deletado**. Não polui o histórico com tentativas malsucedidas; a cronologia da falha vive no chronicle 🔴 em `docs/spec/chronicles/` e no `history.json`.

---

## Schema obrigatório

Cada plano segue este schema. **Tamanho mínimo recomendado**:

- Mudança cosmética: ~40 linhas (frontmatter + §1 + §5 + §7 enxutos basta)
- Trabalho médio: ~150 linhas (todas as seções preenchidas)
- Refactor/feature grande: 300+ linhas (com §3 detalhada e §6 cobrindo decisões)

### Frontmatter YAML

```yaml
---
slug: secretaria-pode-ver-reuniao
title: "Coluna `secretaria_pode_ver` + filtro no endpoint + checkbox no form"
status: rascunho | ativo | finalizado
plan_source: plan-mode-claude | superpowers-writing-plans | manual | skipped
author: Pedro Rezende <pmrdef@gmail.com>
date_created: 2026-05-22T18:30:00Z
date_last_touched: 2026-05-22T19:45:00Z
branch: feature/secretaria-pode-ver        # null antes do /start começar
chronicle: docs/spec/chronicles/🟡-2026-05-22-1830-secretaria-pode-ver.md   # null antes do /ship
pr: 42                                       # null antes do PR aberto
sha_inicio: 805daa0                          # SHA da main quando começou
sha_atual: f99c81d                           # SHA atual da branch
estimativa_horas: 3
fase_atual: "implementando 4.3 (checkbox no form)"
tarefas_total: 5
tarefas_concluidas: 2
---
```

| Campo | Função | Quem atualiza |
|---|---|---|
| `slug` | id curto do plano (kebab-case) | `/start` na criação |
| `title` | título humano completo | `/start` na criação |
| `status` | rascunho (sem código) / ativo (codando) / finalizado (deploy ok). Abandonos não viram status — o arquivo é deletado. | `/start`, `/deploy` |
| `plan_source` | de onde o plano veio | `/start` na criação |
| `branch` | branch git da implementação | `/start` ao criar branch |
| `chronicle` | path do chronicle 🟡 quando existir | `/ship` Passo 3 |
| `pr` | número do PR no GitHub | `/ship` Passo 7 |
| `sha_inicio` | SHA do main quando começou | `/start` na criação |
| `sha_atual` | SHA do último commit da branch | `/ship` a cada checkpoint |
| `fase_atual` | descrição curta da fase em curso | `/ship` a cada checkpoint |
| `tarefas_total` / `tarefas_concluidas` | progresso quantitativo | `/ship` a cada checkpoint |

### Corpo — 8 seções

#### §1. Visão (1 parágrafo)

Resumo executivo: **o que** vai ser construído e **por que**. Quem lê isso em 30s entende o objetivo. Sem detalhes técnicos.

#### §2. Contexto técnico

##### §2.1 Estado atual do código

Lista de arquivos JÁ existentes relevantes ao trabalho, com path absoluto + linha + descrição curta. **Crítico:** a próxima sessão não precisa re-explorar o repo.

```markdown
- `hospital-reunioes/backend/app/routers/reunioes.py:142` — endpoint POST /reunioes que vamos estender
- `hospital-reunioes/frontend/src/components/ReuniaoForm.tsx` — componente form que ganha campo X
- `hospital-reunioes/supabase/migrations/037_cargo_nullable.sql` — última migration aplicada
```

##### §2.2 Achados de exploração

O que descobri lendo o código. Padrões a seguir, gotchas, decisões implícitas, utilitários existentes a reusar.

```markdown
- Padrão de erro nesta área é `try/except + raise HTTPException(...)`, NÃO middleware
- Frontend usa `useSWR` em todos os fetches (ver `hooks/useReunioes.ts:14`)
- Existe `validarCargo` em `lib/canonicalCargos.ts:23` — reusar
```

##### §2.3 Restrições e premissas

```markdown
- API tem que continuar compatível com clientes antigos (sem breaking change)
- Migration nova precisa ter index na FK (gate `fk_index_warning`)
- Não pode tocar em routers/auth/ (PR à parte planejado)
```

#### §3. Arquitetura proposta

Diagrama (mermaid ou ascii) + lista de componentes a criar/modificar + fluxo de dados.

```markdown
\`\`\`mermaid
graph LR
  Form[ReuniaoForm.tsx] --POST--> API[POST /reunioes]
  API --INSERT--> DB[(reunioes table + secretaria_pode_ver col)]
  Calendar[/reunioes/calendario] --GET--> API2[GET /reunioes?role=secretaria]
  API2 --SELECT WHERE pode_ver--> DB
\`\`\`

Componentes:
- Migration 038 — adiciona coluna NOT NULL DEFAULT false
- Endpoint POST /reunioes — aceita campo opcional, default false
- Endpoint GET /reunioes — filtra por pode_ver se role=secretaria
- ReuniaoForm.tsx — checkbox controlado
- Tests em test_secretaria_gates.py — 3 casos
```

#### §4. Tarefas (checkboxes com critério verificável)

Cada tarefa tem um **arquivo** e um **critério de aceite executável**. Sem "verificar manualmente" vago.

```markdown
- [x] 4.1 Migration 038
  - Arquivo: `hospital-reunioes/supabase/migrations/038_add_secretaria_pode_ver.sql`
  - Critério: `grep -q "secretaria_pode_ver" hospital-reunioes/supabase/migrations/038*.sql`
- [x] 4.2 Endpoint GET /reunioes filtra
  - Arquivo: `hospital-reunioes/backend/app/routers/reunioes.py:142-170`
  - Critério: `pytest tests/test_secretaria_gates.py::test_filter_pode_ver -v` retorna green
- [ ] 4.3 Checkbox no form
  - Arquivo: `hospital-reunioes/frontend/src/components/ReuniaoForm.tsx`
  - Critério: `pnpm test -- ReuniaoForm` passa + manual: checkbox aparece e envia
- [ ] 4.4 Testes E2E
  - Arquivo: `tests/test_secretaria_gates.py`
  - Critério: 3 testes novos passando
- [ ] 4.5 Atualizar SECRETARIA.md (docs/)
  - Arquivo: `docs/spec/SECRETARIA.md`
  - Critério: seção "Visibilidade" menciona a nova coluna
```

#### §5. Estado de execução (SEMPRE snapshot — nunca append)

**Esta seção é REESCRITA a cada commit WIP.** Não acumula histórico. Sempre reflete o agora.

```markdown
**Fase atual:** implementando 4.3 (checkbox no form, 50%)
**Última atualização:** 2026-05-22T19:45:00Z
**SHA atual:** f99c81d
**Branch:** feature/secretaria-pode-ver

**Já feito:**
- [x] 4.1 Migration 038 criada — commit `b3a51c2`
- [x] 4.2 Endpoint atualizado + 2 testes passando — commit `f99c81d`

**Em andamento:**
- [ ] 4.3 Checkbox no form (50% — checkbox aparece mas não envia o campo)

**Próximo passo (1 frase explícita):**
Adicionar `secretaria_pode_ver` ao body do submit em `ReuniaoForm.tsx:142` (função `handleSubmit`).

**Bloqueios atuais:** nenhum
```

#### §6. Decisões tomadas

Cada decisão importante + alternativa rejeitada + motivo. Evita reabrir discussão na próxima sessão.

```markdown
### 6.1 Coluna na tabela em vez de RLS

**Decidido:** adicionar `secretaria_pode_ver BOOLEAN NOT NULL DEFAULT false` na tabela `reunioes`.
**Alternativa rejeitada:** policy RLS por role.
**Por quê:** Supabase RLS já tem 7 policies em `reunioes`, adicionar 8ª aumenta superfície de bug. Coluna explícita é trivial de auditar.

### 6.2 Checkbox controlado vs uncontrolled

**Decidido:** controlado via `useState`.
**Por quê:** form já usa pattern controlled em outros 5 campos. Consistência > performance marginal.
```

#### §7. Comandos pra retomada (próxima sessão)

Comandos bash exatos que uma LLM nova roda pra se situar em <5min. Não é checklist — é cópia-cola.

```markdown
\`\`\`bash
# 1. Confirma branch
git branch --show-current  # esperado: feature/secretaria-pode-ver

# 2. Lista commits WIP
git log --oneline main..HEAD

# 3. Confirma onde parou
grep -A 5 "^**Próximo passo" docs/planejamento/em-andamento/2026-05-22-1830-secretaria-pode-ver.md

# 4. Verifica último checkpoint verde
cd hospital-reunioes/backend && pytest tests/test_secretaria_gates.py -v
\`\`\`
```

#### §8. Histórico desta sessão (opcional)

Quando útil — log curto da sessão atual. Não é obrigatório.

```markdown
- 2026-05-22T18:30 — Plano criado a partir do brainstorming (superpowers)
- 2026-05-22T18:45 — Tarefa 4.1 concluída
- 2026-05-22T19:00 — Tarefa 4.2 concluída
- 2026-05-22T19:45 — Bloqueio em 4.3, deixar pra próxima sessão
```

---

## Quem cria e atualiza

| Evento | Quem atualiza | O que atualiza |
|---|---|---|
| `/start` em working tree limpo, decide planejar | `/start` | Cria arquivo em `em-andamento/`, popula frontmatter + §1–§4 |
| Plan mode nativo (`Shift+Tab+Tab`) → "implementar" | `/start` | Copia `~/.claude/plans/<X>.md` pra `em-andamento/`, expande no schema |
| `superpowers:writing-plans` rodou | `/start` | Importa output pra `em-andamento/`, expande no schema |
| Cada commit WIP durante implementação | `/ship` | Reescreve §5 e atualiza `sha_atual`, `fase_atual`, `tarefas_concluidas` no frontmatter |
| `/ship` cria chronicle 🟡 | `/ship` | Atualiza frontmatter do plano: `chronicle: <path>`, `branch: <name>`, `pr: <N>` |
| `/deploy ship` healthy | `/deploy` | Frontmatter: `status: finalizado`, **move** arquivo pra `finalizado/` |
| `/deploy ship` failed/rolled-back (sem recovery) | `/deploy` | **Deleta** o arquivo do `em-andamento/`. Cronologia da falha sobrevive no chronicle 🔴 e no `history.json`. |

---

## Convenções importantes

1. **§5 é sempre snapshot.** Nunca append. Próxima LLM lê estado atual, não tem que parsear histórico.
2. **§4 tem critério executável.** "Verificar manualmente" é proibido — escreva o comando bash exato.
3. **§7 é cópia-cola.** Próxima LLM roda os comandos sem entender o contexto e em <5min sabe onde parou.
4. **Não duplica chronicle.** O plano (aqui) é mapa do trabalho. O chronicle (`docs/spec/chronicles/`) é diário curto pós-fato. Cada um tem propósito distinto.
5. **Arquivos `.md` versionados.** Editáveis livremente pelo dev humano fora do `/start`. Pode editar no VS Code, comitar, pushar.
6. **Move (não copia)** quando concluir com sucesso. `git mv em-andamento/X.md finalizado/X.md` preserva blame.
7. **Status: rascunho** = plano ainda sendo refinado, sem branch criada. **Status: ativo** = branch criada e código em desenvolvimento. **Status: finalizado** = deploy healthy. **Abandono = `git rm`** — o arquivo deixa de existir; histórico do que deu errado vive no chronicle 🔴 em `docs/spec/chronicles/` e no `history.json`.

---

## Exemplo completo

Ver `docs/planejamento/finalizado/` (após o primeiro plano ser concluído).

Primeiro plano de teste deste sistema: `2026-05-22-1714-planejamento-estrutura.md` (este próprio PR).
