---
status: superseded
amends: 0022, 0057, 0061
amended_by: 0064, 0065
superseded_by: 0068
---

# Hospital OS lê o GitHub ao vivo; o rabo grava só a verdade do deploy

Decisão do Pedro (05/out/2026, grilling). O painel local `tools/workflow-dashboard/` cresceu em sete abas (Plano, Issues, Produção, Pendências, Mapa, Domínio, Guia), com um módulo de 230 linhas calculando ondas, tempo típico e caminho crítico, cards de vaidade (total de issues, lead time médio) e um visor com lead time por pessoa que a ADR 0061 (decisão 5) tinha rejeitado. Do outro lado, o `fechar_onda.py` gasta uma rodada inteira de PR por lote só para registrar: snapshot, draft do manual, `history.json`, `state.json` e `CHANGELOG.md`, empurrados numa branch, abertos em PR, esperando três checks e mergeados pela API. O snapshot ainda falha em modo parcial na máquina do sócio (sem venv, `DYLD`), e o CHANGELOG sai com travessão no título. Esta ADR dá nome ao painel, fixa o que ele mostra e de onde lê, e tira do caminho crítico do rabo tudo que não é a verdade do deploy.

## Decisões

1. **O painel se chama Hospital OS.** Na tela, no README, no `CLAUDE.md` e no `/ask-pedro`. O vocabulário dele (fase, funil, raia, tentativa) vive no README do painel; o `CONTEXT.md` segue glossário do hospital (ADR 0061).

2. **Uma fonte por aba.** Issues e PRs leem o GitHub ao vivo pelo `gh` (issues, sub-issues, bloqueios, PRs com checks, `mergeStateStatus`, reviews, timeline de eventos, branches remotas). Produção lê `history.json` e `state.json` da `origin/main`. Mapa e Domínio leem o clone. Nada no painel deriva de arquivo o que o GitHub já diz.

3. **Cinco abas: Issues (home), PRs, Produção, Mapa, Domínio.** Plano sai: as ondas viram um desenho dentro do card de cada PRD aberto (colunas = ondas por dependência, nós = fatias na cor do responsável, setas = `blocked_by`, borda = fase); tempo típico, caminho crítico e comando copiável por fatia saem com o `plano.py`. Pendências sai: vira o filtro `ready-for-human` da aba Issues, com o contador no chip. Guia sai: o conteúdo é o `docs/onboarding/` e o README do painel.

4. **Régua de nove fases por issue, derivada só de fatos do GitHub:** Triagem (`needs-triage`, `needs-info`) · Fila (`ready-for-agent`, sem assignee, sem bloqueio aberto) · Bloqueada · Em andamento (assignee + `in-progress`; sub-estado "branch criada" quando existe branch remota terminada em `-N` sem PR) · PR aberto (com o sinal do PR: CI pendente, vermelho ou verde, revisor comentou, conflito, tentativa anterior se houve PR fechado sem merge) · Mergeada (PR merged, sem versão no `history.json`) · Em produção (versão e data) · Humana (`ready-for-human`) · Encerrada sem PR. "Clonada" significa branch remota, fato que vale para qualquer sócio; worktree é local e não entra.

5. **Aba Issues: funil de fases no topo, filtros em chips.** Os cards de topo (total, abertas, lead time médio, fila) saem; entra a faixa das nove fases com contagem, clicável. Filtros: estado, fase, responsável (chip na cor da pessoa, mais "ninguém assumiu"), PRD, labels agrupadas por prefixo (`type:`, `area:`, `fatia:`), busca. Os `<select>` nativos saem (o popup é pintado pelo sistema, fora do tema). Com responsável filtrado, o funil mostra as contagens dele e nada de lead time: a decisão 5 da ADR 0061 volta a valer e o visor do PR #928 é removido.

6. **Card da issue compacto, linha do tempo sob demanda.** Fechado: fase, pessoa, idade, progresso dos critérios, PR e versão como chips. Expandido: a linha do tempo com data e hora (criada, designada, branch, PR aberto, CI vermelho n vezes, revisor comentou, PR fechado sem merge, novo PR, mergeado, versão em produção). A timeline das abertas vem na coleta, em lote; a das fechadas só ao expandir, como os comentários.

7. **Aba PRs: quadro por fase com raias por pessoa.** Colunas = fase do PR (aberto sem CI, CI vermelho, esperando revisor, verde esperando merge, mergeado sem deploy, em produção); uma raia por sócio, na cor fixa da pessoa; card = PR com issue, branch e há quantos dias está na coluna. Coluna cheia e card velho ganham destaque: o gargalo aparece sem métrica. PRs fechados sem merge (tentativas) ficam numa faixa cinza, com data e issue. Filtros: pessoa, PRD, só abertos.

8. **Navegação interna por URL.** Aba, item e filtros vivem no hash (`#issues/930`, `#prs/930`, `#producao/v0.161.0`, `#issues?resp=...&fase=...`). Chip de issue, PR ou versão abre o card certo na aba certa; o GitHub é o link secundário `↗` em todo card. Produção lista versões; cada versão expande PRs, issues, migration, health e build, e cada card de issue ou PR mostra a versão em que subiu como chip de volta.

9. **O rabo grava só `history.json` e `state.json`.** É a verdade que o GitHub não tem (health, duração do build, migration aplicada, env, rollback). O PR de docs por lote continua, com dois JSONs e sem script rodando antes. `history.json` perde o teto de 50 (`HISTORY_MAX`) e guarda tudo. `CHANGELOG.md` é apagado: a timeline é render do `history.json` no Hospital OS, e `CLAUDE.md`, `/ask-pedro` e as skills param de citá-lo. *Emendada pela ADR 0064 (decisão 6b; issue #1000): o PR de docs sai. O rabo monta a entrada nova do `history.json` e o `state.json` e dispara a Action da decisão 10 na `main` por `workflow_dispatch`, com os dois no input `registro`; ela os grava na `main` pela deploy key (ADR 0065), conferidos contra o input, no mesmo run do snapshot e do draft. O rabo espera a entrada no `history.json` da `main`.*

10. **Snapshot e draft do manual saem do rabo para uma Action no push da `main`.** A Action roda o `snapshot.py` (ambiente completo, sem o modo parcial do macOS) e o `tirar_draft_manual.py`, e commita direto na `main` com bypass do ruleset **só para `github-actions[bot]`**. Ela dispara no merge do PR de docs, quando o `history.json` com a versão nova já está na `main`, então o fato que o draft precisa (versão em produção) existe no momento certo. Push pelo `GITHUB_TOKEN` não redispara workflow: sem loop. *Emendada pela ADR 0065: o bypass do `github-actions[bot]` valia para qualquer workflow de qualquer branch; o ator passa a ser uma deploy key, usada só no job da Action que não instala nada.* *Emendada também pela ADR 0064 (decisão 6b): o run que traz a versão nova ao `history.json` é o que o rabo dispara por `workflow_dispatch` com o registro, e não o merge de um PR de docs; o `history.json` e o `state.json` entram no `paths-ignore` do push, junto com o resto do que a Action escreve.*

## Emendas

- **ADR 0022:** o Plano vivo do painel (PRD #101, ondas, prompts copiáveis, tempo típico) deixa de existir como aba; o que resta é o desenho das ondas dentro do PRD.
- **ADR 0057:** quem tira a página do `draft` passa a ser a Action do push da `main`, não o `fechar_onda.py`. O critério não muda (só sai do draft o que está em produção, lido do `history.json`).
- **ADR 0061:** a emenda de 02/10 recusou bypass do ruleset para quem roda o rabo (uma pessoa). Esta ADR abre um bypass de escopo fixo para `github-actions[bot]`, um ator que não é pessoa e só executa o workflow versionado no repo; a regra "subir código é por PR, admin incluído" continua intacta. A decisão 5 (sem métrica por pessoa) volta a valer no painel.

## Alternativas descartadas

- **Rabo publicar GitHub Release por versão e o painel ler só GitHub.** Mais aderente, mas health, build e migration não têm forma estruturada no Release, e Coolify e rollback leem o `state.json`.
- **Manter snapshot e manual no rabo como best-effort.** Já era best-effort (#844) e continuava custando tempo e falhando em silêncio.
- **Action abrir PR automático com auto-merge.** Zero bypass, mas dois commits de bookkeeping por versão e mais um PR por deploy.
- **Snapshot não commitado, gerado ao abrir o Mapa.** `docs/ARQUITETURA.md` e o Manual perderiam a fonte.
- **Manter o CHANGELOG escrito pelo rabo.** Duas fontes para a mesma timeline e um arquivo a mais para o CI vigiar travessão.
- **Aba PRs como lista com filtros ou como grafo issue, PR, deploy.** A lista repete a Issues; o grafo não responde "o que está parado com quem".
- **Três abas (sem Mapa e Domínio).** Custam zero coleta e o ER interativo (ADR 0025) é o único lugar onde o schema é legível.
- **Manter lead time por pessoa no visor.** Decidido contra na ADR 0061; compara gente.

## Consequências

- Nasce um PRD com as fatias: coletor (campos novos de PR, timeline em lote, branches remotas, fases), aba Issues (funil, chips, card, timeline, desenho das ondas no PRD), aba PRs, Produção por versão com navegação interna, remoção de Plano, Pendências, Guia e `plano.py`, rabo enxuto (sem snapshot, manual e CHANGELOG, `history.json` sem teto), Action do bot com o bypass no ruleset, e a troca de nome em `CLAUDE.md`, `/ask-pedro`, README e skills que citam o painel ou o CHANGELOG.
- Os testes de `tools/workflow-dashboard/tests/` que cobrem Plano, Pendências e o visor por responsável saem com o código.
- O `lint-adr` e o grep de travessão do CI deixam de ter o CHANGELOG no escopo.
- Quem roda o rabo deixa de precisar de venv, WeasyPrint e `DYLD` locais para o snapshot: a Action tem o ambiente.

## Emenda de 06/10/2026: responsável é só quem assumiu (issue #942)

A triagem do PRD #938 deixou em aberto qual regra de responsável vale no Hospital OS: a da decisão 5 desta ADR ("ninguém assumiu" = sem assignee) ou a da emenda de 05/10/2026 da ADR 0061 (sem ninguém designado, conta quem criou a issue, PR #930). O Pedro decidiu na triagem da #942 (comentário de 06/10/2026 na issue).

**Decisão:** no painel, responsável é só quem está designado (assignee). O filtro de responsável, a cor da pessoa nos nós das ondas e nas raias da aba PRs e o "ninguém assumiu" leem só o assignee; issue sem assignee é "ninguém assumiu", tenha o autor que tiver. O autor pode continuar no card como informação (`✎ criada por fulano`), sem contar como responsável em lugar nenhum.

Revoga a emenda de 05/10/2026 da ADR 0061 ("responsável cai em quem criou"). O visor da pessoa que separava assumidas de só criadas já tinha saído com a decisão 5 desta ADR.

> **Desfeita no filtro** pela issue #1039 (decisão do Pedro de 06/10/2026, registrada no PR, ADR 0068): o chip da pessoa volta a trazer também as issues que ela criou e que ninguém assumiu, com a marca `✎ criou` no card, e o funil filtrado conta igual. Quem assumiu manda; "ninguém assumiu" segue = sem assignee; a cor dos nós das ondas e as raias da aba PRs continuam só pelo assignee.
>
> **Ampliada** em 06/10/2026 (decisão do Pedro, registrada no PR): a pessoa tem também o que criou e outro assumiu, e o funil conta só issues abertas (o pendente), com um card grande do total e os cards das fases somando ele. A decisão 5 muda junto: os filtros viram dropdowns do próprio painel no topo (o motivo de tirar o `<select>`, popup pintado pelo sistema, continua valendo) e o chip `ready-for-human` sai, porque o card Humana é a mesma fila.
