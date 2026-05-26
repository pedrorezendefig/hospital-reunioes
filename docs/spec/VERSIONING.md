# Versionamento

Como a versão do Hospital Reuniões é decidida, exibida e documentada.

## TL;DR

- **Versão semântica** (`vMAJOR.MINOR.PATCH`, ex: `v0.2.1`) é o identificador da app.
- **Fonte da verdade**: `hospital-reunioes/frontend/package.json` campo `version`.
- **Backend espelha** via env `APP_VERSION` (injetada pelo `/deploy ship` antes do build).
- **Rodapé da app** exibe `v0.2.1` em todas as páginas (clicável → abre este CHANGELOG.md no GitHub).
- **Bump é automático** a cada PR via `/ship`, baseado no tipo do commit.

## Esquema de versão

Seguimos [Semantic Versioning 2.0](https://semver.org/lang/pt-BR/).

```
v0.2.1
 │ │ └─ PATCH — bug fix, refactor, chore, docs, style, test, build, ci
 │ └─── MINOR — feature nova (feat:)
 └───── MAJOR — breaking change (BREAKING CHANGE: no body do commit, ou feat!: / fix!:)
```

Hoje estamos em `v0.x.y` (pré-1.0). Quando `v1.0.0` for batido, a app entra em modo "API estável" — toda mudança breaking exige major bump explícito.

## Regra de bump automático

A skill `/ship` lê os commits do PR (`git log main..HEAD`) e decide o bump pelo tipo dominante (BREAKING > feat > fix/chore/refactor):

| Tipo de commit | Bump |
|---|---|
| `BREAKING CHANGE:` no body OU `feat!:`, `fix!:` etc. | major (`0.1.0` → `1.0.0`) |
| `feat:` ou `feat(<scope>):` | minor (`0.1.0` → `0.2.0`) |
| `fix:`, `refactor:`, `perf:`, `chore:`, `docs:`, `style:`, `test:`, `build:`, `ci:` | patch (`0.1.0` → `0.1.1`) |

Se o PR tem 1 `feat:` + 3 `fix:`, **vale o mais alto**: minor. O CHANGELOG da versão lista todas as mudanças.

A skill `/ship` adiciona um último commit `chore(release): bump v0.2.0` no PR antes do `gh pr create`. O squash merge consolida tudo num commit só no main.

## Bump manual em marcos editoriais

Se você quiser marcar um marco (ex: chegou um módulo grande novo, vai de `v0.x.y` direto pra `v1.0.0`), edite à mão no PR:

1. `hospital-reunioes/frontend/package.json` campo `version`
2. Commit `chore(release): bump v1.0.0 — primeiro release oficial`

A skill `/ship` respeita: sempre lê a versão atual de `package.json` e incrementa a partir dela. Bump manual ≠ versão "fora do controle".

## Como a versão chega na app rodando

**Frontend (build-time, inlined no bundle)**:
- `frontend/next.config.ts` importa `package.json` e injeta `process.env.NEXT_PUBLIC_APP_VERSION` na build.
- `Footer.tsx` lê `process.env.NEXT_PUBLIC_APP_VERSION` e renderiza `v0.2.1`.
- O `generateBuildId` é a versão + timestamp do build → invalida cache do Service Worker (`@serwist/next`) a cada nova versão.

**Backend (runtime, env var)**:
- `Settings.app_version` (em `backend/app/config.py`) lê `APP_VERSION` de env. Default `"0.1.0"` se a env não estiver setada.
- `/api/health` retorna `{ "version": "0.2.1", ... }`.

**Coolify (injetado pelo `/deploy ship`)**:
- Antes do `mcp__coolify__deploy`, a skill faz `mcp__coolify__bulk_env_update` no UUID do backend setando `APP_VERSION=<versão atual do package.json>`.
- Pós-health, valida que `GET /api/health` retorna a versão esperada. Mismatch → rollback automático.

## Release notes

O **`docs/spec/CHANGELOG.md`** é a lista completa de versões, prepended automaticamente pelo `/deploy ship` a cada deploy. Formato:

```markdown
## v0.2.0 — 2026-05-21 — feat(app): acrescentar versionamento visível
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `abc1234`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (142s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/abc1234
```

Detalhes ricos de cada mudança vivem na **GitHub Issue + PR** (contexto, critérios de aceite, discussão) e no **`docs/spec/deploy/history.json`** (registro factual de cada deploy: SHA, serviços, duração, resultado, health).

## Mapeamento versão ↔ SHA

Cada versão (`v0.2.1`) = 1 entrada no `CHANGELOG.md` = 1 commit no `main` = 1 registro no `docs/spec/deploy/history.json`. O SHA do commit é o identificador único técnico; a versão é o identificador semântico humano.

Quem clica no rodapé da app vai pro `CHANGELOG.md` no GitHub e vê todas as versões com link pro commit de cada uma.
