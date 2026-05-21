<!--
PR template preenchido automaticamente pelo /ship a partir do chronicle 🟡 vinculado.
Pode editar manualmente. Mantenha as 5 seções pra rastreabilidade.
-->

## 🎯 Contexto

<!-- Por quê esta mudança importa pro Hospital, pros usuários, pra operação. Vem da seção "Contexto" do chronicle 🟡. -->

## ✅ Plano executado

<!-- Checkboxes copiadas da seção "Plano" do chronicle 🟡. Marcadas conforme tarefas foram concluídas. -->

- [ ] tarefa 1
- [ ] tarefa 2

## 📊 Mudanças

<!--
Preenchido automaticamente por `/snapshot --diff <base>..HEAD`. Mostra delta em rotas,
entidades, migrations, integrações. Se nada relevante mudou no snapshot, vem "_sem mudanças_".
-->

_gerado por `/snapshot --diff`_

## 🔗 Links

- Issue: #N
- Chronicle: [🟡-... / 🟢-... / 🔴-...](./docs/spec/chronicles/...)
- Snapshot atual: [`docs/spec/snapshots/`](./docs/spec/snapshots/)

## 🤖 Gates (5 camadas independentes)

- [ ] Camada 1 — `/code-review` passou
- [ ] Camada 2 — `/security-review` passou
- [ ] Camada 3 — `superpowers:requesting-code-review` passou (subagent independente)
- [ ] Camada 4 — CI verde (lint + tests + build no GitHub Actions)
- [ ] Camada 5 — `superpowers:verification-before-completion` passou (comando real verificado)

Self-approval acontece só se todas as 5 derem verde. Pós-merge, `/deploy ship` regenera `docs/spec/snapshots/` automaticamente.

## Closes

<!-- Closes #N (vincula Issue do GitHub Projects) -->
