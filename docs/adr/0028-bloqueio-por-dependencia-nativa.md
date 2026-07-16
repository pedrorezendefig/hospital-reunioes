---
status: accepted
---

# Bloqueio entre issues por dependência nativa do GitHub

O bloqueio entre issues passa a usar as **issue dependencies nativas** do GitHub ("blocked by", GA desde 08/2025, disponível no plano Free e validado no repo). A convenção anterior, seção `Bloqueada por: #X` no corpo + label `blocked` + varredura manual de destravamento, foi aposentada. A relação nativa é a **única fonte da verdade**; texto remanescente em issues antigas é histórico.

Migração executada em 13/07/2026: 19 dependências criadas via API para as 16 issues abertas que usavam o formato textual (famílias #114-122, #181-184, #214-219), label `blocked` removida das 3 que a tinham e `ready-for-agent` normalizada.

## Por quê

Três ganhos concretos:

1. **A fila vira uma busca server-side.** `gh issue list --label ready-for-agent --search "no:assignee -is:blocked"` substitui parse de corpo + gestão de label em `/pegar-issue`, `/onda` e no protocolo do issue-tracker.
2. **Destravamento automático.** Quando a última bloqueadora fecha, `is:blocked` deixa de casar e a dependente reaparece na fila sozinha. A varredura manual (remover `blocked`, adicionar `ready-for-agent`), um passo que podia ser esquecido entre sessões, deixa de existir.
3. **Estado estrutural, não textual.** A UI mostra o ícone "Blocked" e o painel de dependências; webhooks ficam disponíveis para automação futura.

## Considered options

- **Migração híbrida** (nativa manda, corpo mantém a linha como leitura humana): rejeitada. Duas fontes que podem divergir; a UI do GitHub já mostra a relação de forma proeminente.
- **Não migrar agora** (esperar `gh` >= 2.94.0, que traz `--add-blocked-by`): rejeitada. A escrita já funciona hoje via `gh api` POST (custo de um GET extra para resolver número → id global), e a leitura da fila (`-is:blocked` no `gh issue list --search`) funciona na versão instalada.
- **Manter o esquema textual**: rejeitada. Era a origem da varredura manual e do risco de fila mentirosa.

## Consequences

- A fatia bloqueada **nasce com `ready-for-agent`**: quem esconde ela da fila é o `-is:blocked`, não a ausência de label. O `/to-issues` cria a dependência nativa no publish (uma por bloqueadora, em ordem de dependência).
- O endpoint de escrita exige o **id global** da bloqueadora (`gh api .../dependencies/blocked_by -F issue_id=<id>`), não o número. Com `gh` >= 2.94.0, simplificar para `gh issue edit <N> --add-blocked-by <X>`.
- Automação que use o REST **legado** `GET /search/issues` precisa de `advanced_search=true`, senão `is:blocked` é ignorado em silêncio (falso "nada bloqueado"). O `gh issue list --search` não sofre disso.
- A label `blocked` está aposentada (`docs/agents/triage-labels.md`); a Action de higiene pode continuar tentando removê-la em fechamentos, sem efeito.
- Limite nativo de 50 dependências por relação: folgado para o padrão espinha → fatias.
