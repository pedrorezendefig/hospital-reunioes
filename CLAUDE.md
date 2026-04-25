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
plano-AA-MM-DD-HHMMh-nome-do-plano.md
```

A data vem primeiro (`AA-MM-DD`) para que sort cronológico funcione naturalmente. O horário (`HHMM` + sufixo `h`) vem em seguida e o ano usa 2 dígitos. O timestamp reflete a **última atualização** do arquivo. Ao editar um plano existente, **renomear** para refletir o novo timestamp — fluxo:

1. `Edit` / `Write` no arquivo atual.
2. `mv planos/plano-26-04-23-1800h-foo.md planos/plano-26-04-23-1900h-foo.md` (com a data/hora do momento do save).

> Para ver os mais recentes no topo do explorer, deixar o VS Code com `"explorer.sortOrder": "modified"` (sort por data de modificação, recente primeiro).

Cada arquivo tem **duas seções obrigatórias**:

- `## Plano` — escopo, passos, critérios de sucesso, riscos.
- `## Execução / Resultados` — registro do que foi feito, resultados, desvios, itens pendentes. Atualizar essa seção conforme o plano vai sendo executado.

Não usar `.claude/plans/`. Não criar `.md` de plano na raiz do projeto.
