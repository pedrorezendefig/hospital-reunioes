---
status: accepted
---

# Wayfinder: on-ramp situacional para planejamento multi-sessão, sob demanda

Adoção **preparada, não instalada** da skill `wayfinder` (mattpocock/skills v1.1) para esforços grandes demais para uma sessão de planejamento: um **mapa** compartilhado no GitHub (issue `wayfinder:map`) cujos **tickets** são sub-issues, cada um resolvendo uma decisão ou investigação. O protocolo operacional (mapa, tickets, frontier, claim, resolução) vive na seção "Wayfinding operations" de `docs/agents/issue-tracker.md`; a skill em si só será instalada quando aparecer o primeiro épico com névoa multi-sessão que não caiba num grilling.

## Por quê

Hoje, planejamento que atravessa sessões vira uma cadeia de grillings + `/passagem`, e o estado morre num documento efêmero no tmp do OS, invisível para o revisor. O mapa como GitHub Issue dá persistência, retomada por qualquer sessão e visibilidade pro diretor (loop do revisor, ADR 0020). Ao mesmo tempo, o histórico do projeto mostra que quase tudo coube no fluxo atual (PRDs #113, #180 e #210 saíram de grillings de uma sessão), então instalar já seria pagar contexto por um caso raro.

A preparação antecipada tem um motivo técnico: a wayfinder v1.1 procura a seção "Wayfinding operations" no doc de issue tracker apontado pelo `CLAUDE.md`; sem ela, a skill cai num fallback de tracker local em markdown, exatamente o tipo de doc de estado paralelo que o `CLAUDE.md` proíbe.

## Considered options

- **Instalar a skill agora**: rejeitado. Paga context load permanente por um caso que ainda não apareceu; a porta da frente continua sendo a cadeia liderada pelo grill (posição do próprio upstream: "situational on-ramp, not the new main entry flow").
- **Não preparar nada e instalar quando precisar**: rejeitado. Sem a seção no issue-tracker.md, a primeira invocação criaria o tracker markdown paralelo proibido; o custo da preparação é uma seção de doc.
- **Usar /passagem para planejamento multi-sessão**: mantido para travessia de contexto de UMA linha de trabalho, mas rejeitado como mapa de épico: o doc é efêmero, local e invisível pro revisor.

## Consequences

- Tickets wayfinder **nunca** recebem `ready-for-agent` nem entram na máquina de estados do `/triage`: `/pegar-issue` e `/onda` continuam enxergando só a fila de execução; as filas não colidem.
- Quando o mapa limpar (nada mais a decidir), o handoff é para `/to-prd` + `/to-issues` (não o to-spec/to-tickets do upstream). Tickets tipo grilling usam `/grill-with-docs`, com o gate de uma pergunta por vez e recomendação destacada.
- O wayfinder planeja e não mergeia: o invariante "push na main é ação humana" não é tocado.
- Ao instalar a skill (gatilho: primeiro épico com névoa), traduzir narração e corpos de issue para pt-BR, manter os labels `wayfinder:*` em inglês e trocar o handoff final, conforme a seção do issue-tracker.md.
