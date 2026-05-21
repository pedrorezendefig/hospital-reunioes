# Execução: terminar a migração REVERSA + workflow de time

Este documento te conduz, em **6 passos sequenciais**, do estado atual (branch `spec-and-workflow-migration` pushed, sem PR aberto) até o sistema totalmente operacional com time de 3 pessoas. No final tem um **resumo dos benefícios** e das **escolhas de arquitetura** implementadas.

> Pré-requisitos já validados: Node v24.14, gh CLI 2.88.1, git 2.39.5, autenticado como você no GitHub. Working tree do Hospital tem mudanças pendentes suas (backend pre-deploy-checklist) que **não foram tocadas** por esta sessão.

---

## Passo 1 — Revisar o que foi entregue

Antes de seguir, abre cada um destes e dá uma lida pra alinhar:

- **`plano.md`** (raiz, 601 linhas): plano consolidado da migração + workflow. Contém o "porquê" e o "como" de tudo.
- **`CLAUDE.md`** (raiz): regras do projeto reescritas. Inclui novas seções "Deploy e spec" e "Workflow de time".
- **`.claude/skills/spec/SKILL.md`** (555 linhas): skill nova `/spec` com 5 subcomandos (init, update, status, historico, migrate-blueprint).
- **`.claude/skills/ship/SKILL.md`** (495 linhas): skill nova `/ship` com 12 passos do ciclo end-to-end (branch → chronicle 🟡 → commit → PR → review → merge → deploy → Discord).
- **`.claude/skills/deploy/SKILL.md`**: cópia local do `/deploy` (sobrepõe a global do `~/.claude/skills/deploy/`). Lê `docs/spec/deploy/`, invoca `/spec update` no Passo 9.3, prepend em `docs/spec/CHANGELOG.md` no Passo 9.5, aceita flag `--skip-spec`.
- **`.claude/skills/deploy/scripts/changelog_prepend.py`**: helper Python que insere entrada no `CHANGELOG.md` ao fim do ship.
- **`.github/PULL_REQUEST_TEMPLATE.md`**: template das 6 seções (O que muda, Por quê, Como testar, Riscos/rollback, Plano vinculado, Checklist).
- **`.github/ISSUE_TEMPLATE/bug.md`** e **`feature.md`**: templates de Issue.
- **`docs/spec/deploy/{project,state,history}.json`**: JSONs migrados de `blueprint/deploy/`.
- **`docs/spec/chronicles/`**: 16 MDs com prefixos 🟡🟢 migrados de `blueprint/mudancas/`. Inclui seus 2 planos 🟡 em curso (pre-deploy-checklist e feedback-diretora).
- **`docs/operacional/{proposta-trabalho,sql}/`**: artefatos não-spec movidos.

Se algum SKILL.md tiver coisa que você quer ajustar, ajusta agora (Edit livre) antes de mergear.

---

## Passo 2 — Instalar REVERSA + primeira geração do spec

Seguir o tutorial: **[`INSTALL-REVERSA.md`](INSTALL-REVERSA.md)** (7 passos, 5-10 min).

Resumo do que esse doc cobre:
1. `npx reversa install` interativo (escolhe Claude Code engine + Reversa Core + Documentation Agents).
2. Editar `.reversa/config.toml` pra `folder = "docs/spec"`.
3. Confirmar `.gitignore` (já tá OK).
4. Rodar `/spec update` (ou `npx reversa update`) pra primeira geração (~10-15 min). Vai criar `docs/spec/architecture.md`, `c4-*.md`, `erd-complete.md`, `sdd/`, `gaps.md`, etc.
5. `git add docs/spec/ && git commit -m "docs(spec): primeira geração via REVERSA"`.
6. Apagar `~/.claude/skills/blueprint/` global (opcional, com backup).
7. Atualizar `~/.claude/CLAUDE.md` global (opcional).

Faz tudo na mesma branch `spec-and-workflow-migration`.

---

## Passo 3 — Abrir PR `spec-and-workflow-migration` → `main`

```bash
cd /Users/pedrorezende/PedroDev/Hospital
gh pr create \
  --base main \
  --head spec-and-workflow-migration \
  --title "feat: migrar pra REVERSA + workflow de time de 3" \
  --body-file plano.md
```

O `plano.md` vira o body do PR (601 linhas), mas você pode escolher resumir antes via `--body "<resumo>"`. Como branch protection **ainda não está ativa**, dá pra aprovar e mergear sem CI verde (CI vai rodar mas não bloqueia).

Self-approval + squash merge:

```bash
gh pr review --approve --body "Aprovação da migração (sessão de implementação)"
gh pr merge --squash --delete-branch
```

Depois do merge, volte pra main local:

```bash
git checkout main
git pull origin main
```

---

## Passo 4 — Setup remoto GitHub (collaborators + branch protection + Discussions)

Seguir o tutorial: **[`GITHUB-SETUP.md`](GITHUB-SETUP.md)** (7 passos, 30-45 min).

> **Atualização (sem Discord)**: o Passo 5 desse tutorial foi adaptado. Em vez de webhook Discord, habilitamos GitHub Discussions e cada um instala GitHub Mobile pra push notifications nativas. Sem mais 1 app pra manter.

Resumo:
1. Adicionar collaborators (precisa do username GitHub de cada um — `pedroribbe` confirmado, segundo a definir).
2. Criar ~17 labels (`type:fix`, `area:backend`, `priority:high`, etc.).
3. Branch protection na `main` (1 approval, status checks, linear history, no force push).
4. Squash merge default + delete branch on merge.
5. **Habilitar GitHub Discussions** + criar 4 categorias (Anúncios, Ideias, Dúvidas, Decisões). Cada um instala GitHub Mobile e marca o repo como Watching.
6. GitHub Project "Hospital Sprint" com 5 colunas (Backlog, A fazer, Em progresso, Em review, Concluído).
7. Validação end-to-end: criar Issue dummy, rodar `/ship "teste"` ciclo inteiro, confirmar PR + approval + merge + deploy + push notification no GitHub Mobile dos 3.

---

## Passo 5 — Cleanup dos tutoriais

Depois que os passos 2 e 4 terminam e tudo funciona:

```bash
cd /Users/pedrorezende/PedroDev/Hospital
rm INSTALL-REVERSA.md GITHUB-SETUP.md EXECUCAO.md
git add -u
git commit -m "chore: cleanup tutoriais one-time (REVERSA + GitHub setup concluídos)"
git push
```

O `plano.md` pode ficar mais um tempo (referência histórica). Apaga quando achar que não precisa mais (`git log` ainda tem ele).

Também tira do `.gitignore` as exceções `!/INSTALL-REVERSA.md`, `!/GITHUB-SETUP.md`, `!/EXECUCAO.md` (linhas com `!/` no início).

---

## Passo 6 — Commitar seu trabalho em curso

Suas mudanças pendentes (backend pre-deploy-checklist, migration 038, middleware) devem virar PR próprio agora que a estrutura `docs/spec/` está pronta:

```bash
# Na main atualizada:
/ship "pre-deploy checklist: CORS audit + FK indexes + health rico" --issue <N>
```

O `/ship` vai pegar o plano 🟡 existente em `docs/spec/chronicles/🟡-2026-05-17-1804-pre-deploy-checklist-cors-indexes-logging.md`, criar branch `feature/pre-deploy-checklist`, commitar suas mudanças (você confirma), abrir PR, rodar review, mergear, e deployar com `/spec update` no final.

(Se não quiser usar /ship ainda, pode fazer manualmente: `git checkout -b feature/pre-deploy-checklist && git add hospital-reunioes/ && git commit -m "..." && git push && gh pr create ...`)

---

## Resumo dessa sessão

### O que é o REVERSA

**REVERSA** (https://github.com/sandeco/reversa, npm v1.2.43) é um framework open-source de **engenharia reversa de especificações**. Ele lê o código existente e gera uma especificação executável (arquitetura, dados, fluxos, gaps) por meio de uma equipe de **46+ agents IA orquestrados** (Scout, Architect, Writer, Reviewer, Visor, Data Master, Design System e mais).

Cada afirmação no spec vem com escala de confiança 🟢 confirmado (com `arquivo:linha`), 🟡 inferido, 🔴 lacuna. Quem lê o spec sabe exatamente o que veio do código vs o que foi suposto.

### Benefícios concretos pra você

1. **Spec sempre fresco**: cada `/deploy ship` regenera `docs/spec/` automaticamente. Drift entre código e doc some.
2. **Onboarding instantâneo**: novo dev (humano ou agent) abre `docs/spec/` e tem o sistema mapeado. Não precisa garimpar código primeiro.
3. **Rastreabilidade código↔spec**: `traceability/code-spec-matrix.md` responde "qual código satisfaz qual requisito?". `spec-impact-matrix.md` responde "qual mudança afeta qual seção do spec?".
4. **Padronização da indústria**: C4 (Context, Containers, Components), ERD completo, SDD (Software Design Document), state machines, RBAC. Igual ao que empresas grandes usam.
5. **Histórico no repo, offline**: 3 lugares complementares versionados em git:
   - `docs/spec/chronicles/<arquivo>.md`: 1 MD por mudança, com YAML frontmatter (autor, SHA, PR, Issue, resultado, duração).
   - `docs/spec/CHANGELOG.md`: cronologia flat, prepended a cada ship. 100% do histórico em 1 página.
   - `docs/spec/historico/YYYY-MM.md`: resumo mensal agrupado por tipo, com autor de cada commit.
6. **Time de 3 sem caos**: cada um tem GitHub próprio, branches isoladas, PR template padronizado, Claude faz review automatizada (`/code-review` + `/security-review`), self-approval permitido pra agilidade, Discord notifica em tempo real.

### Escolhas de arquitetura implementadas

| Decisão | O que ficou | Por quê |
|---|---|---|
| Escopo da troca | Apagar `blueprint/` inteiro. Tudo migra pra `docs/spec/` + `docs/operacional/`. | "Unificar tudo em `docs/spec/`" foi a sua escolha no brainstorming. |
| Acoplamento deploy↔spec | `/deploy ship` invoca `/spec update` no Passo 9.3 (foreground, ~12 min). | Spec sempre fresco. Aceita custo de tempo em cada ship. Flag `--skip-spec` pra emergências. |
| Subset de agents | Reversa Core + Documentation Agents (~9 agents) | Você escolheu "fullstack ~10-12 min". Equilíbrio entre detalhe e tempo. |
| Install | `npx reversa install` na raiz. `.reversa/` + `.agents/` no `.gitignore`. `.claude/skills/reversa-*` versionado. | `output.folder = "docs/spec"` no `.reversa/config.toml`. By-the-book, atualizável via `npx reversa update`. |
| Formato chronicle | Sistema 🟡🟢🔴 atual preservado em `docs/spec/chronicles/` | Você já gostava. Chronicler nativo do REVERSA é lacuna documental, então mantemos o que funciona. |
| Skill nova | `/spec` (5 sub) + `/ship` (12 passos end-to-end) versionadas em `.claude/skills/` | Time clona o repo e já tem as skills. Não precisa setup global. |
| Acesso GitHub | Collaborators no seu repo pessoal (não cria Organization) | Free, simples, pra 3 pessoas. Você segue admin único. |
| Aprovação PR | Qualquer 1 aprova (self-approval permitido) | Você escolheu "qualquer 1". Compensa: `/ship` roda `/code-review` + `/security-review` automaticamente. |
| Quem deploya | Todos os 3 | Você escolheu. Cada um precisa de credenciais Coolify locais. |
| Backlog | GitHub Issues + GitHub Projects board "Hospital Sprint" | Centralizado, free, integrado com PR (Closes #N fecha sozinho). |
| Notificação | Discord webhook em `#hospital-dev` | Você escolheu Discord. Setup via `gh api repos/.../hooks`. |
| Histórico | 3 lugares no repo (`chronicles/`, `CHANGELOG.md`, `historico/YYYY-MM.md`) | Você pediu "lastro dentro do diretório". Tudo offline, vai junto no `git clone`. |

### Especificações técnicas

- **Stack mantida**: FastAPI 3.12 + uv (backend), Next.js 15 App Router + pnpm (frontend), Supabase self-hosted (banco), Coolify (orquestração) em VPS Hostinger 16GB.
- **Versionamento de skills**: `.claude/skills/{spec,ship,deploy,atualizar-app}/` versionadas no git (todos no time recebem via `git clone`).
- **Ignorado no git**: `.reversa/`, `.agents/`, `_reversa_sdd/`, secrets locais, `.claude/settings.json`.
- **Branch model**: trunk-based (1 branch `main`), branches feature efêmeras (`fix/`, `feature/`, `chore/`, `refactor/`, `docs/`, `spec/`).
- **Commit convention**: Conventional Commits (`fix(escopo): ...`).
- **Merge strategy**: squash merge only (1 commit por PR na main, history linear).
- **CI**: GitHub Actions com 2 jobs (Backend Lint+Tests via ruff+pytest, Frontend Lint+Type Check via pnpm+tsc). Não modificado, já existia.
- **Branch protection**: 1 approval + status checks + linear history + no direct push + no force push. Ativada no Passo 4 do `GITHUB-SETUP.md`.

### Fluxo end-to-end (exemplo do que você vai ter)

```
1. Você (ou contratado) cria Issue #67 "Bug: webhook X"
2. Issue cai no Projects board "Backlog"
3. Você arrasta pra "A fazer"
4. Contratado pega: assigne pra si, arrasta pra "Em progresso"
5. Roda /ship "fix webhook X" --issue 67 --type fix
   ├─ Cria branch fix/fix-webhook-x-67
   ├─ Cria chronicle 🟡 com YAML frontmatter (autor, type, issue, pr=null, ...)
   ├─ PAUSA: contratado edita código + chronicle
   ├─ Commit conventional, push, abre PR via gh CLI
   ├─ Roda /code-review + /security-review (gate)
   ├─ Aprova (self), mergeia (squash)
   ├─ Pull main local
   ├─ /deploy ship:
   │   ├─ Pre-flight (lint, secrets, CORS, FK indexes, env_example, etc.)
   │   ├─ Coolify deploy + monitor + health check
   │   ├─ Atualiza state.json + history.json
   │   ├─ Aplica 🟡 → 🟢 no chronicle + YAML frontmatter (sha, date_deployed, result)
   │   ├─ Invoca /spec update (~12 min: pipeline REVERSA regenera docs/spec/)
   │   ├─ Prepend entrada em CHANGELOG.md (autor, SHA, serviços, link pro chronicle)
   │   └─ Commit "docs(spec): regenerar via REVERSA pos <sha7>"
   └─ Posta resumo no Discord #hospital-dev
6. Issue #67 fecha sozinha (Closes #67 no PR body)
7. Projects board move card pra "Concluído"
8. Total: ~25 min wall-clock. Contratado só interage no passo 5b.
```

Tudo automatizado via skills + gh CLI + MCP Coolify. Zero abertura de browser.

### Lacunas conhecidas (a resolver depois)

- **`reversa-chronicler` agent**: mencionado no README do REVERSA mas não encontrado na pesquisa do pacote v1.2.43. Pipeline funciona sem ele. Sistema 🟡🟢🔴 humano continua sendo a única cronologia. Verificar a cada `npx reversa update` se surgiu.
- **`/spec init` ainda não rodado**: você roda manual via `INSTALL-REVERSA.md`. Depois disso, `docs/spec/architecture.md`, `c4-*.md`, etc. são gerados pela primeira vez.
- **Branch protection ainda não ativa**: ativada no Passo 4 (`GITHUB-SETUP.md`).
- **Collaborators ainda não convidados**: depende dos usernames dos contratados. Passo 4.
- **Discord webhook ainda não criado**: depende de você criar canal + copiar URL. Passo 4.

Quando esses 5 itens estiverem resolvidos, o sistema está 100% operacional pro time.

---

## Comandos rápidos de referência

```bash
# Ver status do spec
/spec status

# Regenerar spec manualmente (fora do ship)
/spec update

# Histórico mensal
/spec historico

# Ship completo (branch + plano + PR + review + merge + deploy)
/ship "descrição" --issue 67 --type fix

# Ship sem deploy (só PR)
/ship "descrição" --no-deploy

# Ship sem mergear (PR aberto pra review humana)
/ship "descrição" --no-merge

# Deploy sem regenerar spec (emergência)
/deploy ship --skip-spec

# Deploy só status (sem mexer)
/deploy status

# Rollback
/deploy rollback
```

---

Quando terminar tudo (passos 1-6), apaga este arquivo (`rm EXECUCAO.md`) e remove a exceção do `.gitignore`.
