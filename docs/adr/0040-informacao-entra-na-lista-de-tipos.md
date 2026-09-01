---
status: accepted
amends: 0037
---

# `informacao` entra na lista de tipos; os nomes atuais ficam

O diagnóstico da Diretoria Executiva de 31/08/2026 (D-11, RN-57) apontou a divergência entre a aplicação (5 tipos, ADR 0037) e a Especificação da Diretoria, que previa `informacao` e não previa `relato_de_conduta`. A RN-57 unifica as duas listas em seis tipos. O cartaz do ponto de escuta, já em arte final, promete quatro naturezas ao manifestante, e uma delas é informação (RN-88): sem o tipo no banco, o formulário público não cumpre o que o papel promete.

## Decisões

1. **Sexto tipo: `informacao`**, sem sigilo por natureza. Entra no CHECK do banco (migration nova sobre a 077) e nas taxonomias espelhadas do backend (`ouvidoria_taxonomia.py`) e do frontend (`taxonomia.ts`). Todas as demais regras do ADR 0037 permanecem: fail-closed sem tipo, porta única do sigilo, Ana não manda tipo.

2. **`relato_de_conduta` não é renomeado.** A RN-57 escreveu `relato_conduta`, mas renomear valor em uso em produção é migration de dado com risco e sem ganho funcional. A divergência de grafia é registrada na resposta à Diretoria; a Especificação é atualizada com o valor real.

3. **O formulário público ganha o seletor das quatro naturezas como sugestão** (RN-88): elogio primeiro, escolha opcional, gravada em campo próprio (`natureza_informada`). Não classifica, não decide sigilo, não muda estado: o que o manifestante diz que o caso é não é o que o caso é. O ouvidor vê a sugestão no dossiê e segue soberano na classificação, como já acontece com a `classificacao_ia` da Ana.

## Consequências

- A lista fechada do ADR 0037 passa de 5 para 6 valores; este ADR o emenda.
- A Especificação da Diretoria deve ser atualizada na mesma versão (a própria RN-57 exige).
- O cartaz impresso fica honrado: as quatro naturezas que ele promete existem na tela de destino com igual destaque.
