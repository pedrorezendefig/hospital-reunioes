# Regras do Projeto — Hospital Reuniões

## Deploy e blueprint

- **Toda operação de deploy passa por `/deploy`** (skill unificada). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Fonte única de verdade de produção:** `blueprint/DEPLOY.md` (versionado na raiz). Seções `config-*` são editadas por você; `status`, `historico` são preenchidas automaticamente pela skill via marcadores HTML.
- **`blueprint/README.md`** é mantido manualmente — visão geral do sistema em um único doc.
- **`/blueprint-sync`** é manual (não dispara em commit). Só gera changelog humano em `blueprint/historico/YYYY-MM.md` a partir dos commits recentes.
- **Não criar** pasta `implementacoes/` nem logs por tarefa. O histórico vive em `git log` + `blueprint/DEPLOY.md` + `blueprint/historico/`.
- **Não criar** `PRODUCAO.md` ou `deploy-history.md` — substituídos pelo blueprint.

## Planos

Quando o usuário pedir planejamento, criar o plano em **`planos/`** (pasta versionada na raiz do projeto), com nome no formato:

```
plano-HHMMh-nome-do-plano-DD-MM-AA.md
```

O horário (`HHMM` + sufixo `h`) aparece logo após o prefixo `plano-` para ficar visualmente evidente. O ano usa 2 dígitos. O timestamp reflete a **última atualização** do arquivo. Ao editar um plano existente, **renomear** para refletir o novo timestamp — fluxo:

1. `Edit` / `Write` no arquivo atual.
2. `mv planos/plano-1800h-foo-23-04-26.md planos/plano-1900h-foo-23-04-26.md` (com a data/hora do momento do save).

Cada arquivo tem **duas seções obrigatórias**:

- `## Plano` — escopo, passos, critérios de sucesso, riscos.
- `## Execução / Resultados` — registro do que foi feito, resultados, desvios, itens pendentes. Atualizar essa seção conforme o plano vai sendo executado.

Não usar `.claude/plans/`. Não criar `.md` de plano na raiz do projeto.
