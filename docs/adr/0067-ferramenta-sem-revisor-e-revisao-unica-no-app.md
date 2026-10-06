---
status: accepted
amends: 0064
---

# PR de ferramenta sem revisor, revisão única no app e agente que nunca para para perguntar

Decisão do Pedro (06/out/2026, depois de medir os PRDs #938 e #963). Implementar uma fatia leva de 10 a 25 min; a revisão até o verde leva mediana de 28 min, com cauda de 1h a 3h, e é a fase ativa mais cara. Em 05 e 06/10, 12 dos 13 PRs de implementação não tocavam `hospital-reunioes/` e mesmo assim passaram por 2 a 7 rodadas de revisão; o PR #1012 (só workflow) teve 4 rodadas de segurança, uma delas executando o passo de commit do workflow, e a sessão parou 42 min oferecendo opções A, B e C a um humano que não estava olhando. Cada rodada nova achava algo novo fora do que a correção mexeu. Esta ADR corta o laço.

## Decisões

1. **PR de ferramenta não tem revisor.** PR sem nenhum arquivo em `hospital-reunioes/` (skills, agentes, `tools/`, `.github/`, docs) não dispara `hr-revisor`, spec×diff nem `hr-revisor-seguranca`. O CI é o gate. Emenda a decisão 1 da 0064, que rejeitou "ficar só com CI": a régua vale para o app, onde o custo de um bug é o hospital; para ferramenta interna, o bug aparece no CI ou no uso e se corrige para frente. O ruleset da `main` (PR obrigatório e CI verde) continua igual.

2. **No app, uma revisão, uma correção, sem re-revisão.** O `hr-revisor` (e o `hr-revisor-seguranca`, quando o PR toca rota sem login ou migration) roda uma vez. Must-fix vai ao `hr-corretor` uma vez; depois dele, quem confere é o CI. Não existe rodada 2. Corretor que termina com must-fix pendente é baixa (`ready-for-human`) e o lote segue. Revisor que não dá veredito também é baixa, sem redisparo.

3. **Revisor só olha o que o diff muda.** Achado em linha que o diff não toca é descartado: não vira must-fix nem issue. O revisor de segurança julga lendo, sem executar código, workflow ou ataque simulado. A segurança do resto continua com o `hr-auditor-prd`, uma vez, no fechamento do PRD (0064, decisão 4).

4. **Agente nunca para para perguntar.** Na sessão de fundo, dúvida, impasse ou decisão que o prompt não traz vira baixa com uma linha de motivo; ninguém oferece opções nem espera resposta.

Rejeitado: manter a re-revisão com teto (o teto da 0064 já existia e as sessões fizeram de 3 a 7 rodadas mesmo assim); revisão de ferramenta só por amostragem (é regra a mais para o orquestrador decidir); revisor que abre issue com o achado fora do diff (é o mesmo trabalho novo, só adiado).

## Consequências

- Uma fatia de ferramenta vai do claim ao merge em cerca de 20 min (implementar mais CI).
- Bug em ferramenta interna passa a ser pego pelo CI, pelo CI de push na `main` ou pelo uso.
- Uma correção do app pode entrar sem olho de revisor sobre ela; o CI e o auditor do PRD são a rede.
