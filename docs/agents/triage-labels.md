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

> **Aposentada:** a label `blocked` (e a convenção `Bloqueada por: #X` no corpo) saiu de uso em 13/07/2026. Bloqueio entre issues agora é a **dependência nativa** do GitHub ("blocked by"); a fila filtra com `-is:blocked` e o destravamento é automático. Ver ADR 0068 e `docs/agents/issue-tracker.md`.

## Label do loop do revisor (ADR 0068)

| Label | Significado |
| --- | --- |
| `revisor-comentou` | Um login de `REVIEWER_LOGINS` comentou na issue, ou o app espelhou a resposta de um revisor sem login (marcador `<!-- revisor-app`); curadoria pendente: o agente lê, classifica e age (HITL), e remove a label ao final |

Aplicada automaticamente pela Action de higiene (`.github/workflows/higiene-issues.yml`) em `issue_comment.created`, por **dois gatilhos**: o login do autor estar em `REVIEWER_LOGINS`, ou o corpo do comentário **começar** pelo marcador `<!-- revisor-app autor="Pessoa do hospital" demanda="id" -->` em linha própria (ADR 0054, decisão 4 e emenda de 11/09: nome civil nenhum sai para o GitHub), que vale independente do login. Citar o marcador no meio de um texto não acende a label (issue #680): só o app o escreve como primeira linha, e o texto do autor chega com `<!--` neutralizado. O caminho do marcador não fica sem filtro: o `if:` do job só deixa passar comentário com `author_association` OWNER, MEMBER ou COLLABORATOR, e o comentário espelhado pelo app sai pelo token de um colaborador. A Action **só sinaliza**, nunca reabre nem edita. Comentários de automação não disparam o loop: a Action ignora comentários em PRs e, nos comentários **sem** o marcador de revisor, os que trazem o disclaimer do `/triage` ou o marcador `<!-- automacao -->`. O protocolo de curadoria vive na skill `/triage`; o acesso do revisor e a config `REVIEWER_LOGINS` estão em `docs/agents/issue-tracker.md`.

## Labels de tamanho de fatia (Plano vivo)

Família **descritiva de tamanho** (não de estado), aplicada pelo `/to-issues` no momento da quebra do PRD — uma por fatia, nunca no PRD pai:

| Label | Significado |
| --- | --- |
| `fatia:P` | Pequena — poucas horas, escopo contido (1 camada dominante, poucos critérios) |
| `fatia:M` | Média — meio período típico (fatia vertical completa, escopo conhecido) |
| `fatia:G` | Grande — dia cheio ou mais; maior risco/incerteza (muitas camadas, UI nova, integração externa) |

O Hospital OS agrupa esses labels no filtro `fatia:` da aba Issues, e a `/onda-enxuta` escolhe por eles o esforço do implementador. Tempo típico, lead time por tamanho e caminho crítico saíram com o Plano (ADR 0068). O vocabulário do painel (fase, funil, raia, tentativa) fica no README de `tools/workflow-dashboard/`.

## Labels ortogonais (mantidas do fluxo anterior)

Estas convivem com as de triage — descrevem **o que** é a mudança, não o estado dela:

- `type:feature` · `type:fix` · `type:chore` · `type:refactor` · `type:docs`: natureza da mudança (alimenta o tipo do PR e do commit).
- `area:backend` · `area:frontend` · `area:supabase` · `area:infra` · `area:docs` · `area:skills` · `area:spec` — onde a mudança incide.
