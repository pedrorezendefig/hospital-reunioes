# Labels de triage

As skills falam em **5 papéis canônicos** de triage. Esta tabela mapeia cada papel para a label real no GitHub deste repo. Mantemos os nomes técnicos em inglês (identificadores estáveis que as skills aplicam); o significado é descrito em pt-BR.

| Papel (mattpocock/skills) | Label no nosso tracker | Significado |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Precisa de avaliação antes de virar trabalho |
| `needs-info` | `needs-info` | Aguardando mais informação de quem reportou |
| `ready-for-agent` | `ready-for-agent` | Especificada por completo; um agente AFK pega sem precisar de contexto humano |
| `ready-for-human` | `ready-for-human` | Precisa de implementação/decisão humana (HITL) |
| `wontfix` | `wontfix` | Não será tratada |

Quando uma skill mencionar um papel (ex.: "aplique a label de AFK-ready"), use a label correspondente da coluna do meio.

## Labels de apoio ao paralelismo

| Label | Significado |
| --- | --- |
| `in-progress` | Uma sessão deu claim e está trabalhando — sai da fila `ready-for-agent` |
| `blocked` | Tem dependência aberta (`Bloqueada por: #X`); não entra no pool paralelo até a dependência fechar |

## Label do loop do revisor (ADR 0007)

| Label | Significado |
| --- | --- |
| `revisor-comentou` | Um login de `REVIEWER_LOGINS` comentou na issue; curadoria pendente — o agente lê, classifica e age (HITL), e remove a label ao final |

Aplicada automaticamente pela Action de higiene (`.github/workflows/higiene-issues.yml`) em `issue_comment.created`. A Action **só sinaliza** — nunca reabre nem edita. Comentários de automação não disparam o loop: a Action ignora comentários em PRs, comentários com o disclaimer do `/triage` e comentários com o marcador `<!-- automacao -->`. O protocolo de curadoria vive na skill `/triage`; o acesso do revisor e a config `REVIEWER_LOGINS` estão em `docs/agents/issue-tracker.md`.

## Labels ortogonais (mantidas do fluxo anterior)

Estas convivem com as de triage — descrevem **o que** é a mudança, não o estado dela:

- `type:feature` · `type:fix` · `type:chore` · `type:refactor` · `type:docs` — natureza da mudança (alimenta o PR e o CHANGELOG).
- `area:backend` · `area:frontend` · `area:supabase` · `area:infra` · `area:docs` · `area:skills` · `area:spec` — onde a mudança incide.
