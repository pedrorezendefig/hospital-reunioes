# Versionamento

Como a versão do Hospital Reuniões é decidida, exibida e documentada.

## TL;DR

- **Versão semântica** (`vMAJOR.MINOR.PATCH`, ex: `v0.2.1`) é o identificador da app.
- **Fonte da verdade**: o `last_app_version` do `docs/spec/deploy/state.json`, conferido com a maior tag `vX.Y.Z` do repositório (vale a maior).
- **A versão não vira commit** (issue #967): o rabo (`fechar_onda.py`) grava `APP_VERSION` no backend e no frontend do Coolify antes do merge e cria a tag `vX.Y.Z` no squash depois. O `hospital-reunioes/frontend/package.json` fica congelado.
- **Rodapé da app** exibe `v0.2.1` em todas as páginas.
- **A versão sobe sozinha** a cada entrega de app, pelo tipo dos commits.

## Esquema de versão

Seguimos [Semantic Versioning 2.0](https://semver.org/lang/pt-BR/).

```
v0.2.1
 │ │ └─ PATCH — bug fix, refactor, chore, docs, style, test, build, ci
 │ └─── MINOR — feature nova (feat:)
 └───── MAJOR — breaking change (BREAKING CHANGE: no body do commit, ou feat!: / fix!:)
```

Hoje estamos em `v0.x.y` (pré-1.0). Quando `v1.0.0` for batido, a app entra em modo "API estável" — toda mudança breaking exige major bump explícito.

## Regra da versão nova

O rabo lê os commits dos PRs do lote e decide pelo tipo dominante (BREAKING > feat > fix/chore/refactor). Lote só de ferramenta (nada em `hospital-reunioes/`) não muda a versão:

| Tipo de commit | Bump |
|---|---|
| `BREAKING CHANGE:` no body OU `feat!:`, `fix!:` etc. | major (`0.1.0` → `1.0.0`) |
| `feat:` ou `feat(<scope>):` | minor (`0.1.0` → `0.2.0`) |
| `fix:`, `refactor:`, `perf:`, `chore:`, `docs:`, `style:`, `test:`, `build:`, `ci:` | patch (`0.1.0` → `0.1.1`) |

Se o PR tem 1 `feat:` + 3 `fix:`, **vale o mais alto**: minor.

Nenhum commit de versão entra no PR: o CI verde do PR vale para o merge, e dois PRs não disputam a mesma linha do `package.json`.

## Marco editorial

Para ir de `v0.x.y` direto pra `v1.0.0`, marque o commit do PR como breaking (`feat!:` ou `BREAKING CHANGE:` no corpo): o rabo sobe o major.

## Como a versão chega na app rodando

**Frontend (build-time, inlined no bundle)**:
- O `Dockerfile` recebe `APP_VERSION` como `ARG` do build, e o `frontend/next.config.ts` a injeta em `process.env.NEXT_PUBLIC_APP_VERSION`. Sem ela (build local, CI), cai no `package.json`.
- `Footer.tsx` lê `process.env.NEXT_PUBLIC_APP_VERSION` e renderiza `v0.2.1`.
- O `generateBuildId` é a versão + timestamp do build → invalida cache do Service Worker (`@serwist/next`) a cada nova versão.

**Backend (runtime, env var)**:
- `Settings.app_version` (em `backend/app/config.py`) lê `APP_VERSION` de env. Default `"0.1.0"` se a env não estiver setada.
- `/api/health` retorna `{ "version": "0.2.1", ... }`.

**Coolify (gravado pelo rabo)**:
- Antes do merge (que dispara o build pelo webhook), o `fechar_onda.py` roda `coolify app env update <uuid> APP_VERSION --value "<versão nova>"` no backend e no frontend. A chave é **posicional**: `--key` é o flag de rename, não serve pra apontar a variável.
- Pós-health, valida que `GET /api/health` retorna a versão esperada. Mismatch (ou health ruim) → rollback automático (issue #968): o rabo devolve o `APP_VERSION` antigo aos dois apps, volta cada app do lote à imagem anterior (`coolify app rollback run`), confere o health na versão antiga e sai com 6. Se o rollback também falhar, sai com 4 e o semáforo fica preso para o `/deploy rollback`.

## Release notes

A lista completa de versões é o **`docs/spec/deploy/history.json`**: o rabo (`fechar_onda.py`) grava uma entrada por deploy, sem teto (ADR 0062), com versão, SHA, PRs, PRDs, serviços, duração, migrations, resultado e health. O painel local desenha essa timeline na aba Produção.

Detalhes ricos de cada mudança vivem na **GitHub Issue + PR** (contexto, critérios de aceite, discussão).

## Mapeamento versão ↔ SHA

Cada versão (`v0.2.1`) = 1 commit no `main` (o squash, com a tag `v0.2.1`) = 1 registro no `docs/spec/deploy/history.json`. O SHA do commit é o identificador único técnico; a versão é o identificador semântico humano.
