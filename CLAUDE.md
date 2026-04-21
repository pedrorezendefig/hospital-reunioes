# Regras do Projeto — Hospital Reuniões

## Deploy e blueprint

- **Toda operação de deploy passa por `/deploy`** (skill unificada). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Fonte única de verdade de produção:** `blueprint/DEPLOY.md` (versionado na raiz). Seções `config-*` são editadas por você; `status`, `historico` são preenchidas automaticamente pela skill via marcadores HTML.
- **Demais docs do blueprint** (`README`, `ARQUITETURA`, `FLUXOS`, `AMBIENTES`) são atualizados após cada commit pelo hook `post-commit` que invoca `/blueprint-sync`.
- **Não criar** pasta `implementacoes/` nem logs por tarefa. O histórico vive em `git log` + `blueprint/DEPLOY.md`.
- **Não criar** `PRODUCAO.md` ou `deploy-history.md` — substituídos pelo blueprint.

## Hook post-commit (`.githooks/post-commit`)

Ao clonar o repo, ativar o hook com:

```bash
git config core.hooksPath .githooks
```

Sem isso, os `.md` do blueprint não são atualizados automaticamente. Para pular o hook em um commit específico: `BLUEPRINT_SYNC=off git commit ...` ou `git commit --no-verify`.

## Planos

Quando o usuário pedir planejamento, criar o plano como `.md` na raiz do projeto (ex: `plano-nova-feature.md`) para visualização fora do terminal (VS Code, GitHub). Não usar `.claude/plans/`.
