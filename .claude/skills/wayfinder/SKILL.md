---
name: wayfinder
description: Planeja esforço grande demais para uma sessão como mapa de tickets de decisão no GitHub, resolvidos um por vez até a rota ficar clara. Sintaxe `/wayfinder [mapa]`. Instalada sob demanda (ADRs 0027 e 0049).
disable-model-invocation: true
---

# Wayfinder: mapa de decisões para esforço com névoa

Uma ideia grande chegou, não cabe numa sessão de planejamento e ainda está no escuro: o caminho daqui até o **destino** não é visível. Esta skill não corre atrás do destino; ela desenha a rota como um **mapa** de tickets de decisão no GitHub e resolve um ticket por vez, até não sobrar nada a decidir.

> **Quando usar:** só quando o esforço não couber num `/grill-with-docs` de uma sessão. A porta da frente do planejamento continua sendo o grilling (ADR 0027). Se o grilling der conta, use o grilling.

> **Idioma:** corpo das issues, comentários e narração em **pt-BR**. Os labels técnicos (`wayfinder:map`, `wayfinder:<tipo>`) ficam em inglês, como commit e merge.

O protocolo operacional deste repositório (mapa, tickets, frontier, claim, resolução) está na seção **"Wayfinding operations"** de `docs/agents/issue-tracker.md`. Leia essa seção antes de criar qualquer issue. Nunca caia no fallback de tracker em markdown local: `CLAUDE.md` proíbe doc de estado paralelo.

## Planejar, não executar

O wayfinder produz **decisões**, não entregas. Cada ticket resolve uma pergunta. O mapa acaba quando a rota está clara e alguém pode ir construir. A vontade de "já ir fazendo" é o sinal de que você chegou na borda do mapa e é hora do handoff.

**Handoff final:** mapa limpo vira `/to-prd` e depois `/to-issues`. Não use `to-spec` nem `to-tickets` (nomes do upstream; aqui o PRD é issue do GitHub).

## Chame pelo nome

Mapa e ticket são issues, então cada um tem um **nome**: o título. Na narração e no índice do mapa, cite pelo nome, nunca por número solto. Uma parede de `#42, #43, #44` não se lê. O link vive dentro do nome.

## O mapa

Uma issue com o label `wayfinder:map`. Os tickets são sub-issues dela (mesmo `gh api .../sub_issues` do vínculo PRD para fatias).

O mapa é **índice, não depósito**. A decisão mora no ticket; o mapa guarda uma linha e o link. Tickets abertos não são listados: eles são achados por consulta.

Corpo do mapa:

```markdown
## Destino

<o que encerra este mapa: um PRD para escrever, uma decisão para cravar, uma mudança para fazer. Uma ou duas linhas.>

## Notas

<domínio, skills que toda sessão deve chamar, preferências fixas deste esforço>

## Decisões até agora

- [<título do ticket fechado>](link): <resumo de uma linha da resposta>

## Ainda sem forma

<a névoa: pergunta que você sente vir mas ainda não sabe formular>

## Fora de escopo

<o que foi conscientemente descartado deste esforço, com o porquê>
```

## Tickets

Sub-issue do mapa. O corpo é a pergunta, do tamanho de uma sessão:

```markdown
## Pergunta

<a decisão ou investigação que este ticket resolve>
```

Cada ticket leva um label `wayfinder:<tipo>`. Bloqueio entre tickets usa a dependência nativa do GitHub ("blocked by"), que desenha o frontier na própria interface.

**Claim:** assinar a issue para si **antes** de qualquer trabalho. O assignee é o lock. Ticket aberto e sem assignee está livre.

**Frontier** = filhas abertas, desbloqueadas e sem assignee.

> **Invariante das duas filas:** ticket wayfinder **nunca** recebe `ready-for-agent` e nunca entra na máquina de estados do `/triage`. A fila de execução (`/pegar-issue`, `/onda`) enxerga só issues de build. As filas não colidem.

## Tipos de ticket

Todo ticket é **HITL** (o humano participa e fala por si) ou **AFK** (o agente resolve sozinho). Num ticket HITL, o agente nunca responde no lugar do humano.

| Tipo | Modo | Para quê | Skill que resolve |
|---|---|---|---|
| `research` | AFK | Fato externo que trava a decisão (doc oficial, API de terceiro) | `/research` |
| `prototype` | HITL | "Como isso deveria parecer ou se comportar?" Faz um artefato barato para reagir | `/prototype` |
| `grilling` | HITL | Conversa. O caso padrão | `/grill-with-docs` (que já puxa `domain-modeling`) |
| `task` | HITL ou AFK | Trabalho manual que precisa acontecer antes de decidir (criar conta, liberar acesso, mover dado) | nenhuma; é execução |

O `task` é o único tipo que **faz** em vez de decidir, e só entra no mapa quando destrava uma decisão. Resolvido, o comentário registra o que foi feito e os fatos que os tickets seguintes usam (onde ficou a credencial, qual URL nova, quantas linhas).

## Névoa

O mapa é incompleto **de propósito**. Não desenhe o que você ainda não enxerga. Além dos tickets vivos fica a névoa: decisões que você sente vir mas não consegue formular, porque dependem de perguntas ainda abertas. Ela mora em **"Ainda sem forma"**.

Resolver um ticket dissipa a névoa à frente dele. O que virou formulável vira ticket novo, e sai de "Ainda sem forma".

**Teste de névoa ou ticket:** vale se você consegue **enunciar** a pergunta agora, não se consegue respondê-la agora.

- **Ticket** quando a pergunta já está afiada, mesmo bloqueada.
- **Ainda sem forma** quando você não consegue enunciar direito. Não pique a névoa em pedaços de tamanho de ticket: um pedaço pode virar três tickets ou nenhum.

## Fora de escopo

A névoa só se junta **na direção do destino**. O que passa do destino não é névoa: é **fora de escopo**, e tem seção própria.

Fora de escopo nunca se gradua. Volta só se o destino for redesenhado, e aí como esforço novo.

Se um ticket que já existe se revelar além do destino, **feche** o ticket e deixe uma linha em "Fora de escopo" com o motivo e o link. Não entra em "Decisões até agora", que registra a rota realmente andada.

## Invocação

Dois modos. Nos dois, **nunca resolva mais de um ticket por sessão**, com exceção dos `research`.

### Modo 1: cartografar (`/wayfinder`, com a ideia solta)

1. **Nomeie o destino.** Chame `/grill-with-docs` para cravar o que este mapa está procurando: o PRD, a decisão, a mudança. O destino fixa o escopo, então vem primeiro.
2. **Mapeie o frontier.** Grille de novo, agora **em largura**: varra o espaço inteiro em vez de fundo numa linha só. Se **não aparecer névoa** (a rota já está clara e cabe numa sessão), você não precisa de mapa. Pare e diga isso ao usuário: o caminho é `/grill-with-docs` direto.
3. **Crie o mapa** (label `wayfinder:map`): destino e notas preenchidos, decisões vazio, névoa esboçada em "Ainda sem forma".
4. **Crie os tickets que já dá para enunciar** como sub-issues, e ligue os bloqueios num **segundo passo** (issue precisa existir para ser referenciada).
5. **Dispare os `research` em paralelo**, um sub-agente por ticket, chamando `/research`. O achado vira comentário no ticket.
6. **Pare.** Cartografar é o trabalho de uma sessão. Não resolva ticket agora.

### Modo 2: andar o mapa (`/wayfinder <issue do mapa>`)

Ticket é opcional: sem ele, quem escolhe o próximo é você, não o usuário.

1. Carregue o **mapa** (a visão de baixa resolução), não o corpo de todo ticket.
2. Escolha o ticket: o que o usuário nomeou, ou o primeiro do frontier. **Faça o claim** antes de trabalhar.
3. Resolva. Puxe o corpo de tickets relacionados ou fechados sob demanda; chame as skills que a seção "Notas" indicar. Na dúvida, `/grill-with-docs`.
4. Registre: resposta como comentário, **feche** a issue, e acrescente uma linha em "Decisões até agora" no mapa.
5. Gradue a névoa que a resposta liberou (crie e depois ligue), e limpe o pedaço graduado de "Ainda sem forma". Se a resposta mostrar que um ticket está além do destino, mande para "Fora de escopo" em vez de resolver. Se a decisão invalidar partes do mapa, atualize ou apague esses tickets.

Outras sessões podem estar andando tickets desbloqueados em paralelo. Espere o tracker mudar debaixo de você.

## Quando o mapa limpa

Sem ticket aberto e sem névoa, a rota está clara. Handoff: `/to-prd` para escrever o PRD e `/to-issues` para quebrar em fatias. O mapa fecha com um comentário apontando o PRD.

O wayfinder planeja e não mergeia. O invariante "subir para produção é decisão humana" não é tocado aqui.
