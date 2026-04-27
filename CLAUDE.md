# Regras do Projeto — Hospital Reuniões

## Deploy e blueprint

- **Toda operação de deploy passa por `/deploy`** (skill universal). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Painel humano:** `blueprint/PROJETO.md` — visão consolidada para leigo (estado de prod, variáveis OK, integrações, alertas, planos abertos, histórico recente). Regerado pela skill `/blueprint update` (executada automaticamente ao final de cada `/deploy ship`).
- **Fonte da verdade da infra:** `blueprint/deploy/project.json` (manual; ampliado com `description`, `stack`, `integrations`, `next_actions`). `state.json` e `history.json` são auto-gerados pela `/deploy`.
- **Implementações:** `blueprint/implementacoes/<timestamp>-<sha>-<resultado>.md` — 1 MD por `/deploy ship` (sucesso ou falha), gerado automaticamente. Cronologia humana de produção.
- **Histórico mensal:** `blueprint/historico/YYYY-MM.md` — gerado por `/blueprint historico` (changelog humano de commits, manual).
- **Não criar** `PRODUCAO.md`, `deploy-history.md`, `dashboard.html` — substituídos pelo `PROJETO.md`.

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
