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

## Labels de tamanho de fatia (Plano vivo)

Família **descritiva de tamanho** (não de estado), aplicada pelo `/to-issues` no momento da quebra do PRD — uma por fatia, nunca no PRD pai:

| Label | Significado |
| --- | --- |
| `fatia:P` | Pequena — poucas horas, escopo contido (1 camada dominante, poucos critérios) |
| `fatia:M` | Média — meio período típico (fatia vertical completa, escopo conhecido) |
| `fatia:G` | Grande — dia cheio ou mais; maior risco/incerteza (muitas camadas, UI nova, integração externa) |

O dashboard usa esses labels para calcular o **tempo típico** de cada fatia: a mediana do **lead time real** (claim → fechamento; sem claim identificável, abertura → fechamento) das fatias fechadas do mesmo tamanho. Bucket com menos de 3 amostras cai na mediana geral. Nunca é estimativa a priori — o número melhora sozinho a cada fatia fechada. Não retro-rotulamos issues antigas; a amostra cresce daqui pra frente. Vocabulário do Plano (onda, caminho crítico) no README de `tools/workflow-dashboard/`.

## Labels ortogonais (mantidas do fluxo anterior)

Estas convivem com as de triage — descrevem **o que** é a mudança, não o estado dela:

- `type:feature` · `type:fix` · `type:chore` · `type:refactor` · `type:docs` — natureza da mudança (alimenta o PR e o CHANGELOG).
- `area:backend` · `area:frontend` · `area:supabase` · `area:infra` · `area:docs` · `area:skills` · `area:spec` — onde a mudança incide.
