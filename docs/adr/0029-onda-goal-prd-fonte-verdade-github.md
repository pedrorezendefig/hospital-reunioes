---
status: accepted
amends: 0022
---

# Onda escopada em PRD: goal de conclusão, fonte de verdade no GitHub e orquestrador magro

O ADR 0022 definiu a onda com goal "fila-alvo vazia + deploys verdes". Na prática, uma `/onda #PRD` podia terminar com todas as fatias mergeadas e deployadas sem ninguém conferir se o **PRD inteiro** funciona (integração entre fatias), e o orquestrador confiava num retorno estruturado que o sub-agente às vezes não emite (caso conhecido: parar no `/code-review` esperando os review-agents e notificar "completed" sem wrap-up, ver [[project_onda_subagente_async_sem_json]]). Este ADR registra três refinamentos ao contrato da onda; tudo o mais do 0022 permanece.

## Decisões

1. **Goal de conclusão do PRD (auditoria pós-fechamento).** Com `/onda #PRD`, após a última onda e deploy verde, um sub-agente fresco lê o PRD, verifica os critérios de aceite **do PRD** ponta a ponta contra o app deployado (smoke via API/UI, incluindo a integração entre fatias, não só os critérios de cada fatia) e comenta o resultado no PRD. Nesse momento o PRD normalmente **já está fechado**: a Action de higiene (ADR 0020) fecha o PRD sozinha quando a última fatia fecha. A verificação é, portanto, uma **auditoria pós-fechamento**: tudo verde, o comentário com a evidência encerra o assunto; qualquer falha, o sub-agente **reabre** o PRD com `ready-for-human` e o que falhou. O invariante do 0022 não muda: merge e push na main continuam atrás do checkpoint humano; a autonomia nova é comentar/reabrir a issue do PRD (reversível), não deploy.

2. **GitHub como fonte de verdade da conclusão do sub-agente.** O status estruturado que o sub-agente retorna (`{issue, pr, verde, tentativas, notas}`) passa a ser dica, não contrato. A cada notificação de término, o orquestrador confere o estado real via `gh` (PR aberto? gates verdes? labels corretas?) e re-engaja o agente via `SendMessage(nome)` quando o estado real não bate com o notificado.

3. **Orquestrador magro por design.** O orquestrador não lê código, diff nem spec inteira; mantém apenas a tabela da fila e o status por issue. Toda leitura pesada (PRD, critérios de aceite, diffs) acontece dentro dos sub-agentes, que já nascem com contexto fresco. Isso protege a sessão orquestradora do inchaço de contexto em PRDs com muitas ondas.

## Considered options

- **Fechamento condicional pela /onda (fechar só se a verificação passar):** foi a redação original desta decisão, rejeitada na revisão do PR #242. A Action de higiene (ADR 0020, `higiene-issues.yml`) fecha o PRD quando a última fatia fecha, antes de a verificação rodar; o fechamento condicional era inalcançável e o "sem fechar" em falha, impossível de honrar. A auditoria pós-fechamento com reopen entrega a mesma garantia sem colidir com a automação.
- **Action pular PRDs (a /onda fecharia):** rejeitado. Altera o contrato do ADR 0020 e deixa PRDs entregues fora da onda abertos à toa.
- **Verificar antes do último merge:** rejeitado. Verificaria contra um app sem a última fatia deployada, quebrando o propósito do smoke ponta a ponta.
- **Só comentar a verificação e deixar o humano reagir:** rejeitado. Reabrir com `ready-for-human` é reversível, auditável (o comentário fica no PRD) e evita que uma falha de integração durma num PRD fechado.
- **Não verificar o PRD inteiro:** rejeitado. Os critérios por fatia via `/tdd` não cobrem a integração entre fatias; é exatamente a lacuna que o goal de PRD fecha.
- **Endurecer o contrato de retorno no prompt do sub-agente:** rejeitado como mecanismo principal. Já falhou na prática; prompt não é garantia. O contrato continua no prompt, mas a confiança migra para o estado verificável no GitHub.
- **Sessões independentes de verdade (claude -p headless, /passagem --bg por issue) no lugar dos sub-agentes:** rejeitado. O Agent tool já entrega contexto fresco por issue e worktree isolado; sessões separadas perderiam o checkpoint de merge centralizado e multiplicariam o custo de coordenação (estado só via GitHub).
- **Passagem entre ondas para conter o inchaço do orquestrador:** rejeitado. Quebraria o fluxo do checkpoint humano e adicionaria uma engrenagem por onda; o orquestrador magro + sumarização nativa de contexto bastam.

## Consequences

- O relatório final da onda escopada em PRD ganha o **veredito do PRD** (verificado com evidência comentada, ou reaberto `ready-for-human` com o que falhou).
- O orquestrador precisa de verificação ativa via `gh` a cada término de sub-agente; o custo é pequeno e elimina a dependência do wrap-up.
- A regra do orquestrador magro vira restrição operacional da skill: se o orquestrador precisar de um fato do código, delega a leitura a um sub-agente.
