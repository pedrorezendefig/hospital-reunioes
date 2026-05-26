# Teste do Fluxo Ideal Completo — validação assistida

Roteiro pra você (Pedro) percorrer o pipeline Pocock **de ponta a ponta** numa melhoria pequena e real, validando cada skill e cada gate. É **assistido**: a cada etapa o Claude anuncia qual skill vai usar, executa, mostra o resultado e **espera seu OK** antes de seguir.

> **Como iniciar:** numa sessão do Claude Code, diga algo como
> _"vamos seguir o `docs/onboarding/testefluxoidealcompleto.md` etapa por etapa, parando pra eu validar cada uma e me dizendo qual skill você está invocando."_
> O Claude conduz; você confere e dá o OK pra avançar.

## Legenda
- 🔧 **Skill** — a skill invocada na etapa. O Claude **anuncia** ("Using `<skill>` …") antes de agir; é assim que você sabe o que está rodando.
- 👀 **Confirme** — comando ou sinal que prova que a etapa funcionou (rode você mesmo, ou peça pro Claude rodar).
- ✅ **Validar** — o critério de aceite da etapa.
- ⚠️ **Produção** — etapas marcadas tocam o ambiente real.

## ⚠️ Modo ensaio vs. produção
Faça a **primeira passada em modo ensaio** — exercita tudo até os 3 gates **sem** tocar produção:
- No `/ship`, use **`--no-merge --no-deploy --draft`** → abre o PR como rascunho, roda os 3 gates, mas **não** mergeia nem sobe.
- Use **`/deploy status`** (read-only) pra olhar a produção sem alterar nada.

Quando estiver confiante, repita as etapas 7–8 **sem** as flags pra fazer o ciclo real (merge + deploy).

---

## 0. Pré-requisitos (uma vez)
- [ ] Setup do [`claude-setup.md`](./claude-setup.md) feito (plugins, MCP Coolify conectado — confira com `/mcp`, e `gh auth status` ok)
- [ ] App local no ar: `/atualizar-app` → `curl -sf localhost:8000/api/health` retorna `{"status":"ok",...}`
- [ ] `git status` limpo e você sabe em qual branch está

## Escolha a cobaia
Pense numa melhoria **pequena e real**:
- Pra exercitar o **gate de segurança** (Gate 2), escolha algo que toque `auth`/RLS/`migrations`/env/`webhook`.
- Pra um teste mais simples, escolha algo só de UI/texto (o Gate 2 vai pular — e isso também é uma validação).

Anote a cobaia: `____________________________________________`

---

## Etapa 1 — Afie a ideia
**Você digita:** `/grill-with-docs`
🔧 **Skill:** `grill-with-docs`
O Claude questiona sua ideia contra o domínio (`CONTEXT.md` + `docs/adr/`), afina os termos e atualiza `CONTEXT.md`/ADR se uma decisão fechar.
👀 **Confirme:** o Claude cita termos do `CONTEXT.md`; se houve decisão arquitetural, `git status` mostra `CONTEXT.md` ou `docs/adr/` alterado.
✅ **Validar:** a ideia saiu mais nítida e o vocabulário bate com o domínio.
- [ ] ok

## Etapa 2 — Vire um PRD
**Você digita:** `/to-prd`
🔧 **Skill:** `to-prd`
Transforma a conversa num PRD (problema, solução, user stories, decisões) e publica como **1 issue** no GitHub com a label `ready-for-agent`.
👀 **Confirme:** `gh issue list --label ready-for-agent` mostra a nova issue; `gh issue view <N>` traz o corpo **em pt-BR**.
✅ **Validar:** 1 issue "PRD" criada, em pt-BR, com critérios de aceite.
- [ ] ok

## Etapa 3 — Quebre em fatias
**Você digita:** `/to-issues`
🔧 **Skill:** `to-issues`
Quebra o PRD em **N issues** vertical-slice independentes, com "Bloqueada por: #X" onde há dependência e marcação AFK/HITL.
👀 **Confirme:** `gh issue list --label ready-for-agent` mostra as N issues novas; as dependentes têm "Bloqueada por" no corpo.
✅ **Validar:** fatias finas e independentes; só as sem bloqueio aberto entram na fila.
- [ ] ok

## Etapa 4 — Pegue uma fatia
**Você digita:** `/pegar-issue` (sem nada, lista a fila) e depois `/pegar-issue <N>`
🔧 **Skill:** `pegar-issue`
Faz o **claim atômico** (tira `ready-for-agent`, põe `in-progress`, te marca como assignee), cria a branch determinística `<tipo>/<slug>-<N>` e carrega a spec no contexto.
👀 **Confirme:** `gh issue view <N>` → label `in-progress` + assignee você; `git branch --show-current` → a branch da issue.
✅ **Validar:** a issue **sumiu da fila** dos outros e virou sua, com branch criada.
- [ ] ok

## Etapa 5 — Teste primeiro (TDD)
**Você digita:** `/tdd`
🔧 **Skill:** `tdd` (apoiada por `superpowers:test-driven-development`)
Cada critério de aceite vira teste: **vermelho** (falha) → **verde** (passa) → refactor.
👀 **Confirme:** o Claude roda o teste e mostra **primeiro a falha**, depois o verde (ex.: `pytest`/`TestClient` no backend).
✅ **Validar:** o código nasceu coberto; os testes espelham os critérios da issue.
- [ ] ok

## Etapa 6 — Suba com os 3 gates (ENSAIO, sem tocar produção)
**Você digita:** `/ship --no-merge --no-deploy --draft`
🔧 **Skill:** `ship` (que chama `code-review` e, condicionalmente, `security-review`)
Abre o PR (rascunho) e roda os gates, **sem mergear nem subir**:
- **Gate 1 — code-review** (sempre): o Claude anuncia e mostra os achados.
- **Gate 2 — security-review** (só se o diff toca `auth`/RLS/`migrations`/env/`webhook`): o Claude diz se vai **rodar ou pular**, e por quê.
- **Gate 3 — CI** (GitHub Actions): lint + testes + build.
👀 **Confirme:** `gh pr view --json isDraft,title` (PR é draft, título pt-BR); `gh pr view --json body` tem `Closes #N`; `gh pr checks` mostra o CI.
✅ **Validar:** os 3 gates reportados; PR em pt-BR; `Closes #N` presente.
- [ ] ok

## Etapa 7 — Merge ⚠️ (real)
Quando confiante: **você digita** `/ship` (sem `--no-merge`), ou aprova e mergeia o PR rascunho.
🔧 **Skill:** `ship`
Faz o bump de versão, self-approve, **squash merge** — o `Closes #N` fecha a issue.
👀 **Confirme:** `gh issue view <N>` → **fechada**; `git log main --oneline -1` → o commit squash.
✅ **Validar:** issue fechada automaticamente pelo merge.
- [ ] ok

## Etapa 8 — Deploy ⚠️ PRODUÇÃO
**Antes, ensaie:** `/deploy status` (read-only — mostra o estado atual sem mexer).
Pra subir de verdade: o `/ship` já encadeia `/deploy ship` no fim (ou rode `/deploy ship` direto).
🔧 **Skill:** `deploy` (que chama `snapshot` no fim)
Coolify publica → migrations → **health** (`/api/health`) → **version-match** → **rollback automático** se falhar. Atualiza `state.json`, `history.json`, `CHANGELOG.md` e regenera `ARQUITETURA.md`/snapshots.
👀 **Confirme:** rodapé da app com a versão nova; `docs/spec/deploy/state.json` atualizado; `docs/spec/CHANGELOG.md` com entrada nova no topo.
✅ **Validar:** produção **healthy** (ou rollback funcionou); CHANGELOG + ARQUITETURA atualizados; **nenhum** chronicle/plano criado.
- [ ] ok

## Etapa 9 — Paralelismo (opcional)
Abra 2 terminais, cada um numa issue distinta. Em cada um:
```bash
git worktree add ../hospital-issue-<N> -b <tipo>/<slug>-<N>
# então, dentro do worktree:
/pegar-issue <N>
/tdd
```
👀 **Confirme:** depois do claim no terminal 1, rode `/pegar-issue` no terminal 2 — a issue já pega **não aparece** na fila.
✅ **Validar:** zero colisão de claim e de arquivos (worktrees isolados).
- [ ] ok

---

## Mapa skill-por-etapa (cola rápida)
| Etapa | Você digita | 🔧 Skill | Toca produção? |
|---|---|---|---|
| 1 | `/grill-with-docs` | `grill-with-docs` | não |
| 2 | `/to-prd` | `to-prd` | cria 1 issue (GitHub) |
| 3 | `/to-issues` | `to-issues` | cria N issues (GitHub) |
| 4 | `/pegar-issue [N]` | `pegar-issue` | edita labels/assignee (GitHub) |
| 5 | `/tdd` | `tdd` | não (local) |
| 6 | `/ship --no-merge --no-deploy --draft` | `ship` → `code-review`/`security-review` | abre PR rascunho |
| 7 | `/ship` | `ship` | merge + fecha issue |
| 8 | `/deploy ship` | `deploy` → `snapshot` | **sim — produção** |
| 9 | `git worktree` + `/pegar-issue` | `pegar-issue` | edita labels (GitHub) |

## Checklist de validação final
- [ ] Issue fechada por `Closes #N`
- [ ] PR e issues em **pt-BR**
- [ ] 3 gates reportados (code-review sempre · security condicional · CI)
- [ ] CI verde no GitHub Actions
- [ ] Deploy **healthy** — ou rollback testado
- [ ] `CHANGELOG.md` + `ARQUITETURA.md` atualizados pelo deploy
- [ ] **Nenhum** arquivo criado em `docs/planejamento/` nem `docs/spec/chronicles/`
- [ ] Fila do `/pegar-issue` reflete os claims (paralelismo sem colisão)

## Se algo der errado
- **Gate reprovou** → o Claude diz qual; corrija e rode `/ship` de novo (ele retoma).
- **Deploy falhou** → `/deploy status` + rollback automático; motivo em `docs/spec/deploy/history.json`.
- **Quer pausar e continuar depois** → `/passagem` salva o contexto pra outra sessão pegar.

---

_Este guia testa o workflow migrado para o modelo Matt Pocock. Visão geral do fluxo: [`workflow.html`](./workflow.html) · dia-a-dia: [`dev.md`](./dev.md)._
