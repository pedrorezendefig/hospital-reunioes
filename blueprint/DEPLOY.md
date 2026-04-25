# Deploy — Hospital Reuniões

Visão de produção em 5 minutos. A skill `/deploy` (CLI no Claude Code) é a única dona desse fluxo.

## Como ver o estado agora

Abra **`blueprint/dashboard.html`** no navegador (file:// direto). É um dashboard auto-gerado, regerado pela skill `/deploy` a cada ship. Mostra saúde dos serviços, gates do pre-flight, configurações, banco e histórico, com drill-down via side drawer.

Para snapshot rápido sem abrir o browser:

```
/deploy status
```

## Estrutura do blueprint

| Arquivo | O que é | Quem edita |
|---|---|---|
| `dashboard.html` | Dashboard visual auto-gerado | skill `/deploy` (passo final do ship) |
| `deploy/state.json` | Snapshot atual de produção | skill `/deploy` |
| `deploy/history.json` | Últimos 50 deploys | skill `/deploy` (prepend a cada ship) |
| `deploy/coolify.md` | UUIDs, domínios, repo, GitHub App | humano (raramente) + setup |
| `deploy/env-vars.md` | Listas de variáveis backend/frontend/supabase | humano |
| `deploy/secrets.md` | 3 segredos auto-gerados + comandos | humano |
| `deploy/gates.md` | Pre-flight, rollback policy, excludes, comandos MCP | humano |

## Como rodar

| Comando | Quando |
|---|---|
| `/deploy` | Ship diário: pre-flight, push, Coolify, migrations, health, auto-rollback |
| `/deploy setup` | 1ª vez no projeto (cria projeto, apps, Supabase no Coolify) |
| `/deploy status` | Só reporta estado, sem alterar nada |
| `/deploy rollback` | Reverte para último SHA saudável |
| `/deploy migrate-blueprint` | Migra blueprint legado (`DEPLOY.md` único) para a estrutura atual. 1×. |

## Princípios

- **Silencioso quando passa, vocal quando falha.** Pre-flight só reporta o que quebrou; `--verbose` expõe tudo.
- **Migrations destrutivas pedem confirmação explícita.** DROP, TRUNCATE, DELETE-sem-WHERE e ALTER-DROP/ALTER-COLUMN-TYPE.
- **Idempotência.** Rodar 2× sem mudança = mesmo resultado. JSONs são reescritos inteiros (não há merge parcial).
- **Segredos nunca vazam.** Valores nunca vão para log, commit, JSON ou HTML. Só nomes + presente/faltando.

## Doc legado

`DEPLOY.md.legacy` mantém o documento único anterior (211 linhas) durante 1 release como rede de segurança. Pode ser removido após o primeiro `/deploy` ship rodar contra a nova estrutura.
