# Regras do Projeto — Hospital Reuniões

## Deploy e blueprint

- **Toda operação de deploy passa por `/deploy`** (skill unificada). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Fonte única de verdade de produção:** `blueprint/DEPLOY.md` (versionado na raiz). Seções `config-*` são editadas por você; `status`, `historico` são preenchidas automaticamente pela skill via marcadores HTML.
- **`blueprint/README.md`** é mantido manualmente — visão geral do sistema em um único doc.
- **`/blueprint-sync`** é manual (não dispara em commit). Só gera changelog humano em `blueprint/historico/YYYY-MM.md` a partir dos commits recentes.
- **Não criar** pasta `implementacoes/` nem logs por tarefa. O histórico vive em `git log` + `blueprint/DEPLOY.md` + `blueprint/historico/`.
- **Não criar** `PRODUCAO.md` ou `deploy-history.md` — substituídos pelo blueprint.

## Planos

Quando o usuário pedir planejamento, criar o plano como `.md` na raiz do projeto (ex: `plano-nova-feature.md`) para visualização fora do terminal (VS Code, GitHub). Não usar `.claude/plans/`.
