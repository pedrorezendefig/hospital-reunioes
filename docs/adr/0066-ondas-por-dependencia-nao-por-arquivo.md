---
status: accepted
amends: 0063, 0064
---

# Ondas se separam por dependência, não por arquivo

Decisão do Pedro (06/out/2026). No PRD #938 (Hospital OS), as fatias #943 e #944 só compartilhavam `tools/workflow-dashboard/static/app.js`, em pontos diferentes, e o plano as pôs em ondas diferentes pela regra "arquivo em comum não roda junto". Sem essa regra, a fila de 5 ondas virou 3. Cada onda a mais é uma sessão, um rabo e um deploy em série, e o conflito que a regra evitava já tem dono: desde a ADR 0064 (decisão 3) o rabo mergeia PR a PR, e conflito tira só aquele PR, que o `hr-corretor` rebaseia (motivo `conflito`, skill `resolver-conflitos`) enquanto os outros sobem.

## Decisão

1. **O único separador de ondas é a dependência.** As ondas se montam pelo grafo de bloqueio: o `blocked_by` nativo (ADR 0028) mais o "rodar depois da #N" escrito na issue, que vira nativo no plano. Arquivo em comum, dentro de uma sessão ou entre sessões, não separa onda nem sessão. Sessões se separam por tema ou PRD.
2. **Mesmo ponto é dependência, e vira `blocked_by` explícito.** O mesmo ponto é a mesma entrada: as duas fatias editam a mesma rota, o mesmo item de menu ou a mesma função, ou uma usa o que a outra cria. Cada fatia acrescentar a própria linha de `include_router` no `main.py` ou o próprio item no `AdminSidebar.tsx` não é mesmo ponto: as duas rodam juntas, e o rabo PR a PR resolve o conflito de texto. Exemplo: as fatias 1 e 2 criam as rotas `/pops` e `/ouvidoria`, cada uma com o próprio `include_router` no `main.py`, e andam na mesma onda; a fatia 3 muda a rota `/pops` que a 1 cria e anda depois da 1, com o `blocked_by` dela. Quando é mesmo ponto, a de depois ganha o `blocked_by` nativo da de antes. Nunca uma regra implícita de "arquivo em comum".
3. **A onda é toda issue desbloqueada da fila fixa**, até o `--paralelo`, mesmo que o plano ou a passagem a tenha posto numa onda posterior. A fila do prompt e da passagem lista, além das ondas, a dependência de cada issue ("#945, depois da #944"), e o `--paralelo` da próxima sessão é o número de issues desbloqueadas quando a passagem é escrita, com teto 3.

Rejeitado: manter o arquivo como separador. Custava ondas em série por um conflito que o rabo PR a PR já resolve sem parar a onda, e escondia a dependência real atrás do nome do arquivo.

## Emenda à ADR 0064

- **Decisão 5 (a).** "Fatias da mesma onda não compartilham arquivo de costura" passa a "fatias que só compartilham o arquivo de costura andam na mesma onda; o mesmo ponto de registro é dependência, com `blocked_by`". O resto da decisão continua.

## Emenda à ADR 0063

- **Fluxo sem humano no merge.** A regra derivada dela no `/montar-ondas-enxutas` ("arquivo em comum entre sessões também não roda junto, porque o conflito só apareceria no rabo") sai: o conflito aparece no rabo e é resolvido lá, PR a PR, pelo `hr-corretor`.

## Consequências

- Mudam `/montar-ondas-enxutas` (passo 1, balde "Bloqueada"; passo 4; template da fila), `/to-issues` (paralelismo real, quiz e ondas previstas no PRD), `/onda-enxuta` (passos 1 e 7) e a passagem em `references/prompts.md`.
- Mais conflitos no rabo, cada um custando uma rodada do `hr-corretor` e uma tentativa da fatia (teto de 3, ADR 0022), contra uma onda inteira a menos.
