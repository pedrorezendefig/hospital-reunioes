# Plano Hospital: REVERSA + workflow de time de 3 com Claude Code

> Este documento vai ser movido para `Hospital/plano.md` na primeira ação da execução. Abre exceção à regra do `CLAUDE.md` do projeto (que diz pra não criar `.md` de plano na raiz) porque você pediu explícito.

## TL;DR

Duas mudanças coordenadas no Hospital:

1. **Spec automatizado via REVERSA**: substitui a estrutura caseira `blueprint/` por `docs/spec/` gerado por agents IA. Nova skill `/spec` (init, update, status, migrate-blueprint). Skill `/deploy` atualizada pra ler de `docs/spec/deploy/` e regenerar o spec ao final de cada ship (~10-12 min extras).

2. **Workflow de time de 3**: você + 2 contratados. Nova skill `/ship` orquestra branch + PR + review automatizada + merge + deploy num único comando. GitHub Issues como backlog, Discord webhook como notificação, self-approval permitido (qualquer 1 dos 3 aprova, inclusive a própria pessoa).

Tudo conectado: cada `/ship` cria/atualiza um chronicle 🟡 com plano, abre PR usando esse plano como template, roda `/code-review` e `/security-review` como gate, aprova, mergeia e dispara `/deploy ship` que regenera o spec REVERSA em `docs/spec/` e renomeia o chronicle pra 🟢/🔴.

---

## Conceitos básicos (pra leigo)

- **Repo (repositório)**: pasta do projeto versionada no GitHub. Hospital é um repo.
- **Branch**: linha paralela do código. `main` é a "verdade", a versão que está em produção. Cada mudança começa em uma branch nova (`fix/login-bug`, `feature/relatorio-mensal`).
- **Commit**: foto pontual das mudanças com uma mensagem ("fix(login): corrigir validação de senha").
- **Push**: enviar commits da sua máquina pro GitHub.
- **PR (Pull Request)**: proposta formal "quero mesclar minha branch X na main, motivo Y". O PR tem descrição, lista de mudanças, e qualquer um do time pode comentar/aprovar.
- **Code review**: alguém olha o código antes de mesclar. Pode aprovar, comentar ou pedir mudanças.
- **Merge**: mesclar a branch aprovada na `main`. A partir daí, `/deploy` pode subir pra produção.
- **Issue**: tarefa registrada no GitHub (bug, feature, melhoria). Tem assignee (quem pega), labels (bug/feature), status (open/closed). PR pode "closes #N" pra fechar Issue automaticamente ao mergeable.
- **GitHub Projects**: board tipo kanban (Backlog, Doing, Review, Done) onde as Issues se movem.
- **Webhook**: URL que o GitHub chama quando algo acontece (PR aberto, merge, deploy). O Discord recebe e posta no canal.

---

## Parte 1: Spec automatizado via REVERSA

### O que é a REVERSA

**REVERSA** (https://github.com/sandeco/reversa, pacote npm v1.2.40, Node 18+) é um framework de **engenharia reversa de especificações**. Ela lê o código existente e gera uma especificação executável via **46+ agents IA** orquestrados.

Agents-chave usados no Hospital:

- **Reversa**: orquestrador.
- **Scout**: descoberta inicial e inventário.
- **Archaeologist**: dependências e camadas.
- **Architect**: C4 (context, containers, components) + ERD.
- **Writer**: gera os MDs do SDD (Software Design Document).
- **Reviewer**: valida com escala 🟢 confirmado, 🟡 inferido, 🔴 lacuna, ancorada em `arquivo:linha`.
- **Visor**: documenta UI (telas, fluxos).
- **Data Master**: schema completo do banco.
- **Design System**: tokens, componentes, padrões.
- **Chronicler**: evolução (mencionado no README upstream, agent específico ainda é lacuna).

Pipeline fullstack escolhido: ~9 agents, ~10-12 min por execução.

### Como ela se separa do `blueprint/` atual

| Aspecto | `blueprint/` caseiro | `docs/spec/` via REVERSA |
|---|---|---|
| Origem | Skills `/blueprint` + escrita humana | Pipeline de agents IA + escrita humana onde faz sentido |
| Padronização | Inventada pro Hospital | Padrão da indústria (C4, SDD, ERD, traceability) |
| Cobertura | `PROJETO.md` monolítico + `mudancas/` | Arquitetura, ERD, UI, dados, permissões, state machines, gaps |
| Atualização | `/blueprint update` regrava 1 MD | `/spec update` regrava dezenas |
| Rastreabilidade | Implícita | Matrizes `code-spec-matrix.md` e `spec-impact-matrix.md` |
| Custo por ciclo | Segundos | ~10-12 min |

### O que ela contribui

1. **Estrutura padronizada** (`sdd/`, `c4-*.md`, `erd-complete.md`, `gaps.md`, `confidence-report.md`, etc.).
2. **Geração automática via agents**.
3. **Escala de confiança** 🟢🟡🔴 em cada afirmação.
4. **Rastreabilidade código↔spec**.
5. **Preservação de customizações** via manifesto SHA-256.
6. **Pacote de agents reutilizáveis** (dá pra disparar agents pontuais).

### Qual framework ela impulsiona

**Spec-Driven Development (SDD)**: doc vira fonte cruzada sempre atualizada, regenerada continuamente a partir do código. No Hospital, isso elimina o drift entre código e doc, e dá onboarding instantâneo pra qualquer um (humano ou agent).

### Skill `/spec` (nova)

- `/spec init`: roda `npx reversa install`, edita `config.toml` (output.folder = "docs/spec"), adiciona `.reversa/` e `.agents/` no `.gitignore`, cria diretórios.
- `/spec update`: dispara pipeline fullstack do REVERSA. Atualiza `docs/spec/`. Reporta resultado.
- `/spec status`: SHA do último spec gerado, agents pendentes, drift detectado, idade do spec.
- `/spec historico`: regenera `docs/spec/historico/YYYY-MM.md` (changelog mensal, agrupado por tipo de commit, com autor de cada um). Herda algoritmo do antigo `/blueprint historico`.
- `/spec migrate-blueprint`: move `blueprint/deploy/*.json` → `docs/spec/deploy/`, `blueprint/mudancas/` → `docs/spec/chronicles/`, `blueprint/proposta-trabalho/` e `blueprint/sql/` → `docs/operacional/`, deleta `blueprint/PROJETO.md`, apaga `blueprint/` vazio, reescreve `CLAUDE.md` do projeto.

### Skill `/deploy` (modificada)

- Lê de `docs/spec/deploy/`.
- Escreve em `docs/spec/deploy/state.json` e `history.json`.
- Aplica 🟡🟢🔴 em `docs/spec/chronicles/`.
- **Passo 9 novo**: invoca `/spec update` foreground (~12 min). Se falhar, ship segue healthy mas marca chronicle com warning.
- Commit separado pra `docs/spec/`.
- Flag opcional `--skip-spec`.

### Skill `/blueprint` (apagada)

Remove `~/.claude/skills/blueprint/`. Atualiza `~/.claude/CLAUDE.md` global.

---

## Parte 2: Workflow de time de 3

### Roles

| Pessoa | Conta GitHub | Permissão repo | Setup local |
|---|---|---|---|
| Pedro (você) | sua conta | admin (owner) | tudo já configurado |
| Contratado A | conta dele | collaborator write | precisa onboarding |
| Contratado B | conta dele | collaborator write | precisa onboarding |

Nenhuma org GitHub. Repo segue pessoal do Pedro. Cada contratado entra como collaborator com permissão write (free).

### Regras de aprovação

- **PR precisa de 1 approval**. Não importa de quem (self-approval permitido).
- **Branch protection na `main`**:
  - Sem push direto (só via PR).
  - 1 approval obrigatório (qualquer um).
  - Status checks obrigatórios (lint, tests).
  - Linear history (squash merge only).
- **Quem pode mergear**: qualquer um dos 3 após approval + checks verdes.
- **Quem pode rodar /deploy**: todos os 3. Cada contratado precisa de credenciais Coolify locais (token + URL). Setup feito no onboarding.

Por que self-approval funciona: o `/ship` roda `/code-review` e `/security-review` como gate automatizado antes de aprovar. Claude é o "outro reviewer" virtual. Approval humano é registro formal de quem deu OK.

### Skill `/ship` (nova, coração do workflow)

Comando único end-to-end. Sintaxe:

```bash
/ship "<descrição curta>" [--issue <N>] [--no-deploy] [--no-merge] [--skip-review] [--type fix|feature|chore|refactor]
```

Fluxo de `/ship "corrigir bug login" --issue 42 --type fix`:

```
1. Pre-flight
   - Verifica que você está na main e atualizada (git pull)
   - Verifica que /spec status está OK
2. Cria branch fix/corrigir-bug-login-42 a partir da main
3. Cria chronicle 🟡-YYYY-MM-DD-HHMM-corrigir-bug-login.md em docs/spec/chronicles/
   - Pré-preenchido com seções obrigatórias (## Plano, ## Execução / Resultados)
   - Vincula Issue #42 no header
4. PAUSA pra você fazer as mudanças (interativo)
   - Você edita os arquivos
   - Atualiza chronicle 🟡 conforme avança
   - Quando terminar, retoma /ship
5. Commit (conventional commits)
   - Mensagem: "fix(login): corrigir bug Y"
   - Inclui chronicle 🟡 atualizado no commit
6. Push da branch
7. Abre PR via gh CLI
   - Título: "fix(login): corrigir bug Y (#42)"
   - Body: template robusto (ver abaixo) preenchido a partir do chronicle 🟡
   - Closes #42
   - Labels automáticas (type:fix, area:backend, etc)
8. Roda gates automatizados em paralelo
   - /code-review na branch
   - /security-review na branch
   - Linter, tests (via gh check)
9. Se todos passam (ou --skip-review):
   - Aprova PR via gh pr review --approve (self-approval ok)
   - Aguarda checks de CI marcarem verde
   - Mergeia via gh pr merge --squash
10. Pull da main local pra trazer o merge
11. Roda /deploy ship
    - Inclui /spec update automaticamente
    - Renomeia chronicle 🟡 → 🟢-<sha7>-... (ou 🔴 se deploy falhar)
    - Atualiza frontmatter YAML do chronicle (autor, date_deployed, sha, pr, issue, result, duration_seconds)
    - Anexa seção ## Implementação / Deploy no chronicle
    - Prepend entrada nova em docs/spec/CHANGELOG.md (formato "## YYYY-MM-DD HH:MM - tipo(escopo): título - @autor - sha 🟢")
12. Posta resumo no Discord
    - 🚀 fix(login): corrigir bug Y mergeado e em produção (deploy 720s, sha abc1234)
    - Link pro PR, chronicle, deploy URL
```

Flags úteis:
- `--no-deploy`: faz tudo menos o /deploy. Útil pra subir mudança sem afetar produção (ex: doc only).
- `--no-merge`: abre PR mas não mergeia. Útil pra deixar review humana acontecer antes.
- `--skip-review`: pula /code-review e /security-review. Emergência.
- `--issue <N>`: vincula Issue existente.

### PR template (`.github/PULL_REQUEST_TEMPLATE.md`)

```markdown
## O que muda

[1-3 frases descrevendo a mudança técnica]

## Por quê (valor pro negócio)

[Por que isso importa pro Hospital, pros usuários, pra operação]

## Como testar

[Passos pra reproduzir o comportamento esperado]

## Riscos e rollback

[O que pode quebrar, como reverter se quebrar]

## Plano vinculado

[Link pro chronicle 🟡 em docs/spec/chronicles/]

## Checklist automatizado

- [ ] /code-review passou
- [ ] /security-review passou
- [ ] CI (lint + tests) verde
- [ ] /spec update vai rodar no /deploy
- [ ] Chronicle 🟡 atualizado

## Closes

Closes #<N>
```

O `/ship` preenche todas as seções a partir do chronicle 🟡 + flags. Reviewer humano pode editar livremente antes de aprovar.

### Backlog: GitHub Issues + Projects

- Cada bug/feature/melhoria é uma **Issue** no GitHub.
  - Title curto e claro ("Bug: webhook ClickSign 404")
  - Body: contexto, prints, log se relevante
  - Labels: `bug`, `feature`, `chore`, `refactor`, `priority:high/medium/low`, `area:backend/frontend/infra`
  - Assignee: quem está pegando
- **GitHub Projects** (board) chamado "Hospital Sprint" com colunas:
  - **Backlog**: idéias, sem assignee
  - **A fazer**: priorizada, sem assignee ainda
  - **Em progresso**: alguém pegou e tem branch aberta
  - **Em review**: PR aberto, aguardando merge
  - **Concluído**: PR mergeado + deploy concluído
- Issues movem entre colunas via automação do Projects (status field).

### Notificações: Discord webhook

- Canal `#hospital-dev` no seu servidor Discord.
- Webhook nativo do GitHub posta automaticamente:
  - PR aberto / aprovado / mergeado / fechado
  - Push na `main`
  - Workflow run (CI) sucesso / falha
  - Release (se vocês usarem)
- Eventos do `/deploy` (sucesso / falha de deploy em produção) postados via mensagem custom feita pelo `/ship` no final do fluxo.
- Cada um decide se quer notificação push do app Discord.

### Branches e commits

**Branch naming**:
- `fix/<slug>` pra bug
- `feature/<slug>` pra feature nova
- `chore/<slug>` pra manutenção (dep update, lint, doc)
- `refactor/<slug>` pra refactor sem mudança comportamental
- `spec/<slug>` pra mudança só em `docs/spec/` ou nas skills

**Commit convention** (Conventional Commits, já adotado no `/deploy`):
- `fix(escopo): mensagem`
- `feat(escopo): mensagem`
- `chore(escopo): mensagem`
- `refactor(escopo): mensagem`
- `docs(escopo): mensagem`

Escopos seguem `commit_inference.scope_map` em `docs/spec/deploy/project.json`.

---

## Histórico e auditoria no repo (não dependente do GitHub)

Você pediu explícito: o lastro do que foi feito, com data, hora e autor, tem que estar **dentro do repo**, pra quem clonar receber o histórico junto. O plano garante isso em **três lugares complementares**, todos versionados em git:

### 1. `docs/spec/chronicles/` (granular, 1 arquivo por mudança)

Cada `/ship` cria/finaliza um arquivo MD com prefixo 🟡 (plano) → 🟢 (deploy healthy) ou 🔴 (deploy falhou). Nome do arquivo:

```
🟢-2026-05-19-1455-abc1234-fix-webhook-clicksign-404.md
```

Captura: data + hora exata + SHA + slug. Conteúdo:

```markdown
---
title: fix(webhook): corrigir path do ClickSign 404
author: Contratado A <contratadoa@gmail.com>
type: fix
issue: 58
pr: 67
date_planned: 2026-05-19T14:30:00-03:00
date_deployed: 2026-05-19T14:55:00-03:00
sha: abc1234
branch: fix/fix-webhook-clicksign-404
result: healthy
duration_deploy_s: 720
duration_spec_s: 720
services_touched: [backend]
migrations_applied: 0
---

## Plano

[o que vai fazer, por quê, como, riscos]

## Execução / Resultados

[o que foi feito, desvios, decisões]

## Implementação / Deploy

[autor, sha, PR, deploy ID Coolify, log de health check, link pro chronicle do REVERSA chronicler se existir]
```

Quem fez = `author` no YAML. Quando = `date_planned` + `date_deployed`. O que = título + plano. Por que = seção `## Plano`. Como = `## Execução`. Resultado = `## Implementação / Deploy` + `result`.

### 2. `docs/spec/CHANGELOG.md` (cronologia única, append-only)

Um arquivo flat, em ordem cronológica reversa (mais recente no topo). O `/ship` faz prepend a cada deploy concluído:

```markdown
# Changelog Hospital Reuniões

## 2026-05-19 14:55 - fix(webhook): corrigir path do ClickSign 404
- Autor: Contratado A <contratadoa@gmail.com>
- SHA: abc1234
- PR: #67 · Issue: #58
- Resultado: 🟢 healthy (720s deploy + 720s spec)
- Detalhe: [chronicles/🟢-2026-05-19-1455-abc1234-fix-webhook-clicksign-404.md](chronicles/🟢-2026-05-19-1455-abc1234-fix-webhook-clicksign-404.md)

## 2026-05-15 20:35 - feat(secretaria): perfil access_profile + email pro facilitador
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: a98e3d5
- PR: #65 · Issue: #54
- Resultado: 🟢 healthy (360s)
- Detalhe: [chronicles/🟢-2026-05-15-2035-a98e3d5-perfil-secretaria-access-profile.md](chronicles/🟢-2026-05-15-2035-a98e3d5-perfil-secretaria-access-profile.md)
```

Vantagem: clonou o repo, abre o `CHANGELOG.md` e tem 100% do histórico em uma página, sem precisar de internet, sem depender do GitHub.

### 3. `docs/spec/historico/YYYY-MM.md` (resumo mensal, agrupado)

Um arquivo por mês, gerado pelo `/spec historico`. Agrupa commits por tipo (fix, feat, chore, refactor, docs), lista autor de cada um, link pro PR.

```markdown
# Histórico 2026-05

## Features (5)
- feat(secretaria): perfil access_profile - @pedro - #65 - a98e3d5
- feat(reuniao): convite + lembrete 24h - @pedro - #64 - 418f298
- ...

## Fixes (3)
- fix(webhook): path ClickSign 404 - @contratadoA - #67 - abc1234
- ...

## Chores (2)
- ...
```

Bom pra leitura mensal "o que rolou em maio".

### Resumo

| Onde | Granularidade | Conteúdo | Atualizado por |
|---|---|---|---|
| `docs/spec/chronicles/<arquivo>.md` | 1 por mudança | Plano + execução + deploy + autor + SHA + PR + Issue | `/ship` (cria 🟡, renomeia 🟢/🔴) |
| `docs/spec/CHANGELOG.md` | Flat, cronológico | 1 linha por deploy + link pro chronicle | `/ship` (prepend ao final do fluxo) |
| `docs/spec/historico/YYYY-MM.md` | Resumo mensal | Agrupado por tipo, com autor | `/spec historico` (manual ou mensal) |

Tudo em git. Tudo em arquivo. Tudo acessível offline. Tudo vai junto no `git clone`.

GitHub (Issues, Projects, PRs) continua existindo como **interface de trabalho** (board, comments, review UI), mas **não é fonte da verdade do histórico**. Se você cancelar o repo no GitHub amanhã, o histórico inteiro está no clone local.

---

## Onboarding dos contratados

Documento `docs/onboarding/dev.md` (gerado pelo `/ship init-dev` ou manualmente) cobre:

1. **GitHub**
   - Pedro convida pelo username (Settings → Collaborators).
   - Aceitar convite por email.
   - Clone do repo: `gh repo clone pedrorezendefig/hospital-reunioes`.
2. **Claude Code**
   - Instalar Claude Code (mac/linux/windows).
   - Login com conta Anthropic Pro/Team.
   - Configurar `~/.claude/CLAUDE.md` global com instruções essenciais (linguagem pt-BR, sem travessões, etc.).
3. **Skills**
   - Instalar plugins/skills: `/spec`, `/deploy`, `/ship`, `/code-review`, `/security-review`.
4. **Credenciais Coolify**
   - Receber do Pedro: URL Coolify + token API.
   - Salvar em `~/.config/hospital/coolify.env` (fora do repo).
5. **Discord**
   - Entrar no canal `#hospital-dev`.
6. **Primeiro PR de teste**
   - Branch `chore/setup-<seu-nome>`.
   - Adicionar nome em `docs/team.md`.
   - Rodar `/ship "adicionar X ao time" --no-deploy`.
   - Conferir que tudo funcionou.

---

## Fluxo end-to-end (exemplo prático)

> Contratado A vai corrigir um bug reportado.

```
1. Pedro cria Issue #58 "Bug: webhook ClickSign 404" no GitHub
   - Label: bug, priority:high, area:backend
2. Pedro arrasta Issue pra coluna "A fazer" no Projects
3. Contratado A vê notificação Discord, abre o GitHub
   - Lê a Issue, decide pegar
   - Atribui pra si (assignee = @contratadoA)
   - Move pra coluna "Em progresso"
4. Contratado A abre Claude Code, na pasta Hospital
   - Roda /ship "fix webhook clicksign 404" --issue 58 --type fix
5. /ship cria branch fix/fix-webhook-clicksign-404
   - Cria chronicle 🟡-2026-05-19-1430-fix-webhook-clicksign-404.md
   - Vincula Issue #58
6. Contratado A edita os arquivos do webhook
   - Atualiza chronicle 🟡 conforme avança
   - Quando terminar, retoma /ship
7. /ship commita, push, abre PR
   - Title: "fix(webhook): corrigir path do ClickSign 404 (#58)"
   - Body: template robusto
   - Closes #58
8. /ship roda /code-review e /security-review
   - Discord posta: PR #67 aberto
9. Tudo passa. /ship aprova (self), mergeia (squash)
   - Discord posta: PR #67 mergeado
   - Issue #58 fecha automaticamente (closes)
   - Projects move card pra "Concluído"
10. /ship roda /deploy ship
    - Lê docs/spec/deploy/project.json
    - Sobe pro Coolify, monitora, healthcheck OK
    - Atualiza docs/spec/deploy/state.json e history.json
    - Roda /spec update (12 min, regenera docs/spec/)
    - Renomeia chronicle: 🟡 → 🟢-<sha7>-fix-webhook-clicksign-404
    - Anexa seção ## Implementação / Deploy no chronicle
    - Commit separado: "docs(spec): regenerar via REVERSA pos <sha7>"
11. /ship posta resumo no Discord
    - 🚀 fix(webhook): corrigido e em produção (720s + 720s spec, sha abc1234)
    - Link pro PR #67, chronicle 🟢, deploy URL
12. Pedro e Contratado B veem no Discord, tudo visível
```

Total: ~25 min de wall-clock (12 min código + 12 min spec + alguns segundos de overhead). Contratado A só interage no passo 6.

---

## Arquivos a criar / modificar / apagar

### Criar
- `~/.claude/skills/spec/SKILL.md` (nova skill, 5 subcomandos)
- `~/.claude/skills/ship/SKILL.md` (nova skill, comando único end-to-end)
- `Hospital/docs/spec/` (root do spec, populado por REVERSA)
- `Hospital/docs/spec/README.md` (humano vs auto-gerado)
- `Hospital/docs/spec/CHANGELOG.md` (cronologia flat, append-only pelo /ship)
- `Hospital/docs/spec/chronicles/` (1 MD por mudança, com YAML frontmatter contendo autor)
- `Hospital/docs/spec/historico/` (changelog mensal, gerado por /spec historico)
- `Hospital/docs/operacional/` (artefatos não-spec)
- `Hospital/docs/onboarding/dev.md` (guia pros contratados)
- `Hospital/docs/team.md` (lista de quem é quem, contato)
- `Hospital/.reversa/config.toml` (gerado pelo install + editado por `/spec init`)
- `Hospital/.github/PULL_REQUEST_TEMPLATE.md`
- `Hospital/.github/ISSUE_TEMPLATE/bug.md`
- `Hospital/.github/ISSUE_TEMPLATE/feature.md`
- `Hospital/.github/workflows/ci.yml` (lint + tests + opcional /spec update via Claude Action)
- `Hospital/plano.md` (este plano, movido aqui)

### Mover (de blueprint/ pra docs/spec/ ou docs/operacional/)
- `blueprint/deploy/*.json` → `docs/spec/deploy/`
- `blueprint/mudancas/*` → `docs/spec/chronicles/`
- `blueprint/proposta-trabalho/` → `docs/operacional/proposta-trabalho/`
- `blueprint/sql/` → `docs/operacional/sql/`
- `blueprint/historico/` (se existir) → `docs/spec/historico/`

### Apagar
- `Hospital/blueprint/` inteiro
- `Hospital/blueprint/PROJETO.md`
- `~/.claude/skills/blueprint/`

### Modificar
- `~/.claude/skills/deploy/SKILL.md` (lê de `docs/spec/deploy/`, invoca `/spec update`, flag `--skip-spec`)
- `Hospital/CLAUDE.md` (substitui `blueprint/` por `docs/spec/`, remove `/blueprint`, atualiza seção pra "Deploy e spec", adiciona seção "Workflow de time")
- `~/.claude/CLAUDE.md` global (substitui "Blueprint do projeto" por "Spec do projeto", referencia `/spec` e `/ship`)
- `Hospital/.gitignore` (adiciona `.reversa/`, `.agents/`, `_reversa_sdd/`)

### Configurar no GitHub (via UI ou gh CLI)
- Branch protection rules na `main` (1 approval, status checks, linear history, no direct push)
- Convidar 2 contratados como collaborators (write)
- Criar Project "Hospital Sprint" com colunas
- Configurar webhook do Discord
- Criar labels (bug, feature, chore, refactor, priority:high/medium/low, area:backend/frontend/infra)

---

## Sequência de implementação

> Toda a implementação roda em branch `spec-and-workflow-migration` e vai pra `main` via PR único.

1. **Mover este plano pra `Hospital/plano.md`**
   - Commit: `docs: adicionar plano REVERSA + workflow time`

2. **Criar skill `/spec`** em `~/.claude/skills/spec/SKILL.md`
   - 4 subcomandos (`init`, `update`, `status`, `migrate-blueprint`)

3. **Modificar skill `/deploy`**
   - Trocar paths `blueprint/` → `docs/spec/`
   - Adicionar Passo 9 que invoca `/spec update`
   - Adicionar flag `--skip-spec`

4. **Criar skill `/ship`** em `~/.claude/skills/ship/SKILL.md`
   - Comando único end-to-end
   - Integra com `gh` CLI + MCP Coolify + skills de review

5. **Migração no Hospital**
   - `/spec init` (instala REVERSA, config, gitignore, README)
   - `/spec migrate-blueprint` (move arquivos, deleta `blueprint/`, atualiza CLAUDE.md)
   - Commit: `chore(spec): migrar blueprint pra docs/spec via REVERSA`
   - `/spec update` manual pela primeira vez
   - Commit: `docs(spec): primeira geração REVERSA`

6. **Configurar GitHub**
   - Criar `.github/PULL_REQUEST_TEMPLATE.md`
   - Criar `.github/ISSUE_TEMPLATE/{bug,feature}.md`
   - Criar `.github/workflows/ci.yml` (lint + tests)
   - Configurar branch protection na `main` via UI ou `gh api`
   - Criar labels
   - Criar Project "Hospital Sprint"
   - Adicionar webhook do Discord

7. **Onboarding setup**
   - Criar `docs/onboarding/dev.md`
   - Criar `docs/team.md` com seu nome

8. **Apagar skill `/blueprint`**
   - Remove `~/.claude/skills/blueprint/`
   - Atualiza `~/.claude/CLAUDE.md` global

9. **Validação end-to-end**
   - `/deploy status` lê do novo path
   - `/deploy --dry-run` num commit pequeno
   - `/ship "teste de fluxo" --no-deploy --no-merge` num commit dummy
   - `/ship "ajuste de texto" --type chore` ciclo completo
   - Confirmar: PR aberto + aprovado + mergeado + spec regenerado + chronicle 🟢 + post no Discord

10. **Convidar contratados**
    - Manda `docs/onboarding/dev.md` pra cada um
    - Adiciona como collaborator no GitHub
    - Compartilha credenciais Coolify (via 1Password/Bitwarden, não Slack/Discord)

11. **Merge do PR `spec-and-workflow-migration`**

---

## Verificação end-to-end

1. `ls Hospital/` não tem `blueprint/`.
2. `ls Hospital/docs/spec/` tem `deploy/`, `chronicles/`, `sdd/`, `architecture.md`, etc.
3. `ls Hospital/.github/` tem `PULL_REQUEST_TEMPLATE.md`, `ISSUE_TEMPLATE/`, `workflows/ci.yml`.
4. `gh repo view --json branchProtectionRules` mostra protection ativa na `main`.
5. `gh api /repos/<owner>/<repo>/collaborators` lista os 3 collaborators.
6. `ls ~/.claude/skills/` tem `spec/` e `ship/`, não tem `blueprint/`.
7. `/spec status` retorna estado consistente.
8. `/deploy status` lê de `docs/spec/deploy/state.json`.
9. `/ship "ajuste de texto" --type chore` completa o fluxo end-to-end (PR + approval + merge + deploy + spec + chronicle + Discord) em ~15-25 min.
10. Discord recebe a notificação no canal `#hospital-dev`.
11. Issue de teste fecha sozinha quando o PR mergeia (closes).
12. Project board move o card automaticamente.

---

## Riscos e mitigações

- **Chronicler nativo do REVERSA é lacuna**: pipeline funciona sem ele, sistema 🟡🟢🔴 humano continua sendo a cronologia. Documentado em `SKILL.md`.
- **Self-approval anula code review humano**: mitigado pelo `/code-review` e `/security-review` automatizados rodados pelo `/ship`. Pra mudanças sensíveis (auth, schema DB, /deploy), recomendar `--no-merge` pra forçar review humana.
- **Spec update demora 12 min por ship**: aceito. Flag `--skip-spec` no `/deploy` permite pular em emergências.
- **Contratado quebra produção via `/ship`**: rollback via `/deploy rollback`. Branch protection + status checks + Claude review reduzem chance.
- **Credenciais Coolify vazadas**: nunca por chat, sempre via password manager. Token rotacionável pelo Pedro a qualquer momento.
- **Discord como ponto único de comunicação**: se cair, GitHub continua sendo a fonte da verdade. Não é blocker.
- **`npx reversa install` requer Node 18+** em cada máquina do time. Documentar no onboarding.
- **`/ship` é skill complexa, propensa a bugs no início**: começar usando só você, validar, depois ensinar contratados. Versionar `~/.claude/skills/ship/SKILL.md` num repo separado (ou pasta `skills/` no Hospital sync via git).

---

## Trade-offs aceitos

- Ship demora ~15-25 min wall-clock. Aceito em troca de spec sempre fresco + fluxo padronizado.
- `/ship` faz muita coisa em um comando. Aceito (flags permitem parar no meio).
- Self-approval permitido. Aceito (Claude review automatizada compensa).
- Discord como notificação central. Aceito.
- Plan na raiz do projeto (contra regra do `CLAUDE.md`). Aceito (você pediu explícito).

---

## Pontos abertos (decidir na implementação)

- Confirmar lista exata de agents que existem no pacote `sandeco/reversa` v1.2.40 (Visor, Data Master, Design System, Chronicler).
- Onde compartilhar as skills (`/spec`, `/ship`, `/deploy`) entre as 3 máquinas: repo separado de skills sincronizado por git, ou copy-paste manual no onboarding?
- Definir mensagem exata do commit "docs(spec): regenerar via REVERSA pos <sha7>".
- Configurar `.github/workflows/ci.yml`: rodar `npx reversa update --check` no PR pra detectar drift do spec? Ou só rodar lint + tests?
- Definir se Issues seguem template fixo (`.github/ISSUE_TEMPLATE/bug.md` e `feature.md`) ou são livres.
- Definir se cada `/ship` cria sempre chronicle 🟡 obrigatório, ou se `chore/` pequenos podem pular.
