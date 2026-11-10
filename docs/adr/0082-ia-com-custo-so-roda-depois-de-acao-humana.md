---
status: accepted
amends: 0081
---

# IA com custo só roda depois de uma ação humana; a Validação e o segundo agente de Contas médicas viram botão

Decisão do Pedro (09/11/2026), depois do pico de custo de IA dos dias 8 e 9 de novembro. Emenda as decisões 13 e 14 da ADR 0081.

## Contexto

- No dia 9/11 (UTC) a conta da Anthropic marcou US$ 99,79 em Opus 5.5, e no dia 8, US$ 44. Tudo saiu de Contas médicas: no dia 9, US$ 76,27 vieram de 131 chamadas da Prova da regra, US$ 18,40 da análise de 12 contas (Passo A e Passo B) e US$ 5,12 do Auditor.
- A Prova veio do job `validacao_decidida_contas_medicas`, que entrou com a #1491 (PR #1510): a cada 30 minutos ele pegava até 5 Temas da Validação sem recomendação e, em cada Regra pendente, refazia o Passo B nas últimas Contas concluídas da operadora. Em dois dias ele provou as 53 Regras pendentes que a importação das memórias tinha deixado na fila, uma a cada 5 minutos, sem ninguém pedir.
- O relógio não estava na ADR 0081, no PRD #1484 nem no card #1491. Eles pediam só que a fila chegasse decidida para aprovar em lote. A escolha do job de 30 minutos foi do agente que implementou o card, com o motivo de que a prova "não cabe no tempo de um pedido".
- A ADR 0081 estimava US$ 1 por prova de 10 Contas. Saiu cerca de US$ 2,40 por prova de 4 Contas: o Passo B devolve uns 21 mil tokens de saída por Conta, e o Coolify tem `CM_IA_MODELO_PASSO_A` e `CM_IA_MODELO_PASSO_B` em Opus.
- O segundo agente (decisão 14 da ADR 0081) estava agendado para todo domingo às 03:00, 10 Contas por rodada, no modelo do Passo B. Ainda não tinha rodado.

## Decisões

1. **Chamada de IA com custo relevante só roda depois de uma ação humana.** Vale para o app inteiro: nenhum job do APScheduler dispara IA por conta própria. Quem clica vê antes quanto vai ser feito e o custo estimado. Fica de fora o que custa centavos e já roda hoje, como as sugestões de ação do relatório quinzenal e mensal da Ouvidoria, que continua automático. A fila de análise de Contas médicas também segue como está, porque só processa a conta que alguém enviou.

2. **A Validação chega decidida quando alguém pede (emenda a decisão 13 da ADR 0081).** Sai o job de 30 minutos. A tela de Validação ganha o botão "Pedir recomendação ao Auditor", com o número de Temas abertos sem recomendação, quantos levam Prova da regra e o custo estimado. Confirmado, o servidor recomenda todos esses Temas em segundo plano, sem o teto de 5 por rodada, e a tela mostra que está calculando. Um pedido por vez. O resto da decisão 13 continua: a pessoa aprova o lote ou corrige o item N.

3. **A recomendação da Validação roda no Sonnet.** A Prova da regra e o Auditor pedidos por esse botão usam `CM_IA_MODELO_VALIDACAO`, padrão `claude-sonnet-5-5`, que custa metade do Opus. A Prova pedida na conversa da Operadora e o resto do módulo seguem nos modelos do Passo A e do Passo B.

4. **O segundo agente roda quando alguém pede (emenda a decisão 14 da ADR 0081).** Sai o job de domingo. O Painel ganha, para quem tem "painel completo", o botão "Reler contas concluídas", com quantas Contas serão relidas (até 10 ainda não revisadas) e o custo estimado. O que ele acha continua entrando como Faltou isto de origem AGENTE.

## Consequências

- O custo de IA de Contas médicas passa a ter dono: cada rodada de recomendação e de releitura tem alguém que clicou e viu a estimativa antes.
- A fila de Validação pode ficar sem recomendação até alguém pedir. O lote só aplica o que tem recomendação, então nada muda para quem decide pelo cartão.
- Se ninguém clicar, o segundo agente não relê nada e o Painel não ganha Faltou isto de origem AGENTE naquela semana.
- O pedido roda em segundo plano no mesmo processo. Um deploy no meio da rodada a interrompe; os Temas que faltaram continuam sem recomendação e o próximo clique termina o trabalho.
- Job novo que chame IA precisa de uma ADR que emende esta.
