<!--
PR template preenchido automaticamente pelo /ship a partir da Issue vinculada (gh issue view).
Pode editar manualmente. No modelo Pocock o contexto vive na Issue — não em chronicle/plano.
-->

## 🎯 Contexto

<!-- Por que esta mudança importa pro Hospital, pros usuários, pra operação. Vem do corpo da Issue. -->

## ✅ Critérios de aceite

<!-- Copiados da seção "Critérios de aceite" da Issue. Marcados conforme foram entregues (viram os testes do /tdd). -->

- [ ] critério 1
- [ ] critério 2

## 📊 Mudanças

<!--
Preenchido automaticamente por `/snapshot --diff <base>..HEAD`. Mostra o delta em rotas,
entidades, migrations e integrações. Se nada relevante mudou no snapshot, vem "_sem mudanças_".
-->

_gerado por `/snapshot --diff`_

## 🔗 Links

- Issue: #N
- Snapshot atual: [`docs/spec/snapshots/`](./docs/spec/snapshots/)

## 🤖 Gates (3)

- [ ] Gate 1: `hr-revisor` (só PR do app)
- [ ] Gate 2: `sensivel.py` (rota sem login ou migration vira `Sensível:` no revisor)
- [ ] Gate 3: CI verde

## Closes

<!-- Closes #N (vincula e fecha a Issue do GitHub no merge) -->
