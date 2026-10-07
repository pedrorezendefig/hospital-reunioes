<!--
PR template preenchido automaticamente pelo /ship a partir da Issue vinculada (gh issue view).
Pode editar manualmente. No modelo Pocock o contexto vive na Issue, não em chronicle/plano.
-->

## 💬 Resumo funcional

<!--
Para quem não é dev, em duas frases curtas, sem jargão técnico (sem endpoint, branch, componente).
Aparece em destaque no hover do card do PR no Hospital OS, então é o que o funcional lê primeiro.
O que é: o que muda, do ponto de vista de quem usa ou opera. Valor: o ganho (mais rápido, mais seguro, agora possível).
-->

**O que é:** <uma frase>
**Valor:** <uma frase>

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

## 🔎 Evidência

<!--
Antes e depois, nunca só "testes verdes". O teste exato que falhava e agora passa (nome e assert, em
pseudocódigo), a saída de comando que mudou, ou print quando a mudança é visual. PR de ferramenta: a
saída do script ou do comando antes e depois.
-->

- **Antes:**
- **Depois:**

## ⚠️ Perigo do merge

<!--
Porta de uma via (o rollback da imagem não desfaz): migration, envio externo (email, ClickSign, WhatsApp),
escrita ou apagamento em dado de produção, mudança em .github/ ou nas skills da subida (ship, onda-enxuta,
agentes hr-*). O resto é porta de duas vias: a subida faz rollback automático.
Raio: quem sente se der errado (uma tela, um módulo, todos os logins, o próprio deploy).
-->

**Porta:** <uma via | duas vias>, porque <motivo em uma linha>

**Raio:** <uma palavra ou expressão curta>

## 🔗 Links

- Issue: #N
- Snapshot atual: [`docs/spec/snapshots/`](./docs/spec/snapshots/)

## 🤖 Gates (ADR 0068)

- [ ] Ferramenta (nada em `hospital-reunioes/`): CI verde
- [ ] App: `hr-revisor` uma vez (com `Sensível:` se o `sensivel.py` acusar rota sem login ou migration) e CI verde

## Closes

<!-- Closes #N (vincula e fecha a Issue do GitHub no merge) -->
