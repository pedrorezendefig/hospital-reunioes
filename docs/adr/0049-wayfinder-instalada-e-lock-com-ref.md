---
status: accepted
amends: 0027, 0043
---

# A wayfinder entra instalada no clone, e o `skills-lock.json` fixa o commit de origem

O ADR 0027 deixou a `wayfinder` **preparada, não instalada**: a seção "Wayfinding operations" entrou em `docs/agents/issue-tracker.md`, e a skill em si só entraria quando aparecesse o primeiro épico com névoa multi-sessão. O gatilho ainda não apareceu. A skill entra assim mesmo, por decisão do Pedro, e o motivo que sustentava o adiamento deixou de valer.

## Por quê

O custo que o 0027 queria evitar era **context load permanente**: uma skill a mais competindo pela atenção do modelo em toda sessão. A versão upstream da `wayfinder` declara `disable-model-invocation: true`, igual ao `/ask-pedro` e ao `/improve-codebase-architecture`. Com isso ela não é carregada por iniciativa do modelo: só entra quando o humano digita `/wayfinder`. O custo passa a ser o de um arquivo no repositório, não o de um item permanente no contexto.

O segundo motivo é de disponibilidade. O gatilho do 0027 é "o primeiro épico com névoa", e é exatamente na hora desse épico que ninguém quer parar para importar, traduzir e adaptar uma skill. Adaptada e versionada agora, ela está pronta quando o caso chegar.

A porta da frente do planejamento **não muda**: continua sendo `/grill-with-docs`. A `wayfinder` é on-ramp situacional, para o que não couber numa sessão de grilling. O `/ask-pedro` roteia com essa ressalva escrita.

## O que a adaptação preservou

Conforme o 0027 já determinava: narração e corpo de issue em pt-BR, labels `wayfinder:map` e `wayfinder:<tipo>` em inglês, handoff final para `/to-prd` e `/to-issues` (não o `to-spec`/`to-tickets` do upstream), e tickets wayfinder fora da máquina de estados do `/triage`, sem `ready-for-agent`, para que as duas filas não colidam.

## O `skills-lock.json` passa a fixar `ref`

Auditoria do lock contra o upstream mostrou que 3 dos 8 `skillPath` registrados respondiam **404**: o upstream renomeou `diagnose` para `diagnosing-bugs` (12/06/2026) e unificou `to-prd` e `to-issues` em `to-spec` e `to-tickets` (08/07/2026). O lock não guardava o commit de origem, então os caminhos eram resolvidos contra o `main` de hoje, onde as pastas não existem mais.

A decisão: **cada entrada do lock guarda o `ref`**, o commit de origem da importação. Com o `ref`, o caminho volta a ser válido (`git show <ref>:<skillPath>`), o rename vira histórico em vez de link quebrado, e o `computedHash` passa a descrever uma árvore identificável. Os hashes das 8 entradas existentes foram conferidos contra o upstream e batem exatamente com a árvore do `ref` registrado, então nenhum valor foi reescrito: só o `ref` foi acrescentado.

Quatro skills que vieram do mesmo upstream estavam fora do lock (`codebase-design`, `domain-modeling`, `research` e `resolver-conflitos`, esta última do upstream `resolving-merge-conflicts`) e entram com o `ref` da data em que chegaram ao repositório.

O lock continua sendo **rastreabilidade, não instalação** (ADR 0043): as skills vêm no clone, adaptadas em pt-BR, e o lock diz de onde cada uma saiu.

## Consequências

- `npx skills add mattpocock/skills --copy`, o comando citado em `docs/ARQUITETURA.md` e no onboarding, traz hoje os **nomes novos** do upstream. Rodá-lo cria pastas paralelas (`diagnosing-bugs`, `to-spec`, `to-tickets`) em vez de atualizar as nossas. Atualizar uma skill do Pocock é trabalho manual: comparar com o `ref` do lock, trazer o que interessa, manter a adaptação em pt-BR e regravar `ref` e `computedHash`.
- A divergência com o upstream é **intencional e permanente** (ADR 0043). O lock mede a distância; não existe meta de zerá-la.
- A `wayfinder` não mergeia e não sobe nada: o invariante "subir para produção é decisão humana" não é tocado.
