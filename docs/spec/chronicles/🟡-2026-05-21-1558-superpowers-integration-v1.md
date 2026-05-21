---
title: "feat(skills): integrar Superpowers + snapshot vivo + PR self-approval em 5 camadas"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: 6
date_planned: 2026-05-21T15:58:00-03:00
date_deployed: null
sha: null
branch: feat/superpowers-integration-v1
result: pending
status: in_progress
last_touched: 2026-05-21T16:16:00-03:00
plan_source: brainstorming
---

## Contexto

Três problemas hoje:

1. O plugin Superpowers v5.1.0 está instalado mas as skills mais valiosas (`brainstorming`, `writing-plans`, `verification-before-completion`) não estão conectadas ao fluxo do time. O `/start` recomenda plan mode nativo mas não roda brainstorming nem cria plano executável.
2. Quando uma sessão Claude estoura contexto, o próximo Claude (novo terminal) não tem como achar trabalho em progresso, ver o que foi feito e retomar fresco. Chronicles 🟡 são narrativos, sem checkboxes.
3. `docs/spec/` documenta deploys mas não documenta o estado **atual** da aplicação (rotas, entidades, schema, migrations, integrações, fluxogramas). Falta um mapa enxuto e atualizado pra leigo, especialmente útil pros contratados novos.

Além disso, o self-approval do PR (Pedro aprova o próprio PR) hoje tem 2 gates (`/code-review` + `/security-review` no `/ship`). Reforçar com mais camadas independentes pra que self-approval seja defensável, e que tudo apareça visualmente bonito no GitHub Mobile.

Resultado esperado: time iniciante decora **uma palavra** (`/start`) e o sistema decide quando puxar Superpowers; novo Claude em terminal novo retoma trabalho parado lendo chronicle 🟡; snapshot fresco automaticamente a cada deploy; PR com 5 camadas de gate independentes.

## Plano

**Tarefa atual:** 11. Commit + push + PR

- [x] 1. Criar branch `feat/superpowers-integration-v1` + chronicle 🟡 inicial
  - Critério: `git branch --show-current` retorna a branch nova; arquivo existe em `docs/spec/chronicles/`
- [x] 2. Criar `.claude/skills/snapshot/SKILL.md` (peça maior nova)
  - Critério: arquivo válido com frontmatter, fluxo definido (parser de rotas/migrations/integracoes), flags `--check` e `--diff`, idempotência declarada
- [x] 3. Geração inicial dos 7 snapshots em `docs/spec/snapshots/`
  - Critério: 7 arquivos existem (ROTAS, ENTIDADES, SCHEMA, MIGRATIONS, INTEGRACOES, FLUXOGRAMAS, ESTRUTURA); FLUXOGRAMAS e ESTRUTURA têm blocos `<!-- curated -->`
- [x] 4. Atualizar `.claude/skills/deploy/SKILL.md` pra invocar `/snapshot` pós-health
  - Critério: novo passo (9.4) descreve invocação de `/snapshot`; menção a scope_map evitando loop
- [x] 5. Atualizar `.claude/skills/ship/SKILL.md` com Camada 3 e Camada 5
  - Critério: Passo 8 descreve as 5 camadas; Passo 7 (PR body) tem template novo com 5 seções
- [x] 6. Atualizar `.claude/skills/start/SKILL.md` com retomada de chronicle + flags
  - Critério: lógica de leitura de chronicle 🟡 da branch atual, contagem de checkboxes, flags `--rapido`/`--rigoroso`/`debug`, Modo D (retomar)
- [x] 7. Atualizar `CLAUDE.md` com 4 seções novas
  - Critério: seções Continuidade entre sessões, Formato único do chronicle, `.superpowers/` gitignored, 5 camadas de gate, Snapshot vivo
- [x] 8. Atualizar `.github/workflows/ci.yml` (adicionar build) + `.github/PULL_REQUEST_TEMPLATE.md` (alinhar com 5 camadas)
  - Critério: novo job `build` no CI (docker build sanity); template com 5 seções (Contexto, Plano, Mudanças, Links, Gates de 5 camadas)
- [x] 9. Adicionar `docs/spec/snapshots/**` ao `commit_inference.scope_map` em `project.json`
  - Critério: chaves novas adicionadas: `docs/spec/snapshots/**`, `docs/spec/chronicles/**`, `docs/spec/**`, `.claude/skills/**`, `.github/**` (scopes `spec`, `skills`, `ci`)
- [x] 10. Criar `docs/onboarding/dev.md` (1 página)
  - Critério: arquivo existe com instrução única "decora /start", tabela de cenários, atalhos
- [ ] 11. Commit + push + PR
  - Critério: PR aberto com body de 5 seções, labels corretas
- [ ] 12. Rodar /code-review + /security-review como gates
  - Critério: ambos retornam sem must-fix
- [ ] 13. Self-approve + merge squash
  - Critério: PR mergeado em main, branch deletada
- [ ] 14. Renomear chronicle 🟡 → 🟢 manualmente (sem deploy de prod)
  - Critério: arquivo `🟢-YYYY-MM-DD-HHMM-<sha>-superpowers-integration-v1.md` existe

## Execução / Resultados

- **2026-05-21 15:58** — Branch `feat/superpowers-integration-v1` criada (a partir de main com 174 mudanças pendentes que serão absorvidas no PR conforme decisão do brainstorming).
- **2026-05-21 15:58** — Plan file aprovado via brainstorming. Chronicle 🟡 criado no formato novo (com checkboxes + frontmatter enriquecido).
- **2026-05-21 16:00** — `.claude/skills/snapshot/SKILL.md` criado. Documenta algoritmo: parser de routers FastAPI (ROTAS), parser de migrations SQL cumulativo (ENTIDADES + SCHEMA + MIGRATIONS), cruzamento com project.json (INTEGRACOES). Flags `--check`, `--diff`, `--force`, `--only`. Idempotência via comparação de buffer com strip de timestamp metadata. Preserva blocos `<!-- curated -->`.
- **2026-05-21 16:05** — 7 snapshots iniciais escritos em `docs/spec/snapshots/`: ROTAS.md (~70 endpoints em 13 routers), ENTIDADES.md (12 tabelas + enums), SCHEMA.md (Mermaid ER + indexes + RLS), MIGRATIONS.md (38 migrations cronológicas), INTEGRACOES.md (OpenRouter/OpenAI/ClickSign/Resend/Fireflies/Supabase/Coolify), FLUXOGRAMAS.md (curado humano: Reunião lifecycle, Pendência, ClickSign, Auth, Pipeline IA), ESTRUTURA.md (backend/frontend/supabase com notas humanas).
- **2026-05-21 16:08** — `.claude/skills/deploy/SKILL.md` atualizado: Passo 9.4 invoca `/snapshot` pós-health verde, antes do prepend do CHANGELOG.md. Falha do snapshot é warn-only.
- **2026-05-21 16:09** — `docs/spec/deploy/project.json` atualizado: `commit_inference.scope_map` ganhou entradas `docs/spec/snapshots/**` → spec, `docs/spec/chronicles/**` → spec, `.claude/skills/**` → skills, `.github/**` → ci. Garante que commits `chore(spec):` do snapshot não disparam novo deploy.
- **2026-05-21 16:11** — `.claude/skills/ship/SKILL.md` atualizado: Passo 7 (PR body) tem template novo com 5 seções (Contexto, Plano executado, Mudanças via /snapshot --diff, Links, Gates). Passo 8 reescrito como "5 camadas independentes" (code-review, security-review, requesting-code-review, CI, verification-before-completion). Flag `--hotfix` documentada.
- **2026-05-21 16:13** — `.claude/skills/start/SKILL.md` atualizado: novo Modo D (Retomar) que detecta chronicle 🟡 da branch atual, conta checkboxes, mostra progresso e oferece retomar via `executing-plans`. Modo A invoca `superpowers:brainstorming` por default. Flags `--rapido`, `--rigoroso`, `debug` documentadas. Árvore de aninhamento atualizada.
- **2026-05-21 16:14** — `CLAUDE.md` reescrito (foi deletado nas mudanças pendentes; restaurado via `git show HEAD:CLAUDE.md` + reescrita): 5 seções novas (Continuidade entre sessões, Formato único, .superpowers gitignored, 5 camadas de gate, Snapshot vivo). Remoção de menções obsoletas a REVERSA / `/spec update`. Tabela de gates atualizada (substituindo `/spec update` por `/snapshot`).
- **2026-05-21 16:15** — `.github/workflows/ci.yml`: novo job `build` (docker build sanity check do backend e frontend, sem push, com cache GHA). `paths-ignore` ganhou `.superpowers/**`. `.github/PULL_REQUEST_TEMPLATE.md` reescrito com 5 seções alinhadas ao novo `/ship`.
- **2026-05-21 16:16** — `docs/onboarding/dev.md` criado: 1 página com "decora `/start`", 4 cenários comuns (novo trabalho, com diff, retomar sessão, debug), atalhos, regras, onde achar coisas.

## Implementação / Deploy

_(preenchido após /code-review + /security-review + merge)_
