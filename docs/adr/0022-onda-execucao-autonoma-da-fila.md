---
status: accepted
---

# Onda: execução autônoma da fila em ondas com checkpoint por lote e deploy único

Adaptação do "loop engineering" (artigo "Getting started with loops", Claude Code, 30/06/2026) ao nosso pipeline `grill → to-prd → to-issues → pegar-issue → tdd → ship → deploy`. Em vez de uma sessão humana por issue, um comando único (`/onda`) executa a fila de forma autônoma: seleciona issues **desbloqueadas**, roda 2-3 em paralelo (1 worktree por issue) até cada uma virar um PR com os 3 gates verdes, e para **uma vez** para o gate humano de merge. Aprovado o lote, mergeia sequencialmente e faz **um** deploy no fim da onda. Depois reabastece com as issues recém-destravadas e repete até a fila esvaziar.

Compõe os primitivos de loop do artigo: cada issue é um loop **goal-based** (para quando o PR fica verde, teto de 3 tentativas); a onda inteira é um loop **proactive** com um checkpoint humano; o executor coordena via **agentes em worktrees isolados**.

## Por quê

O gargalo do nosso fluxo era humano: cada issue exigia uma sessão dedicada, e o merge exige OK explícito por PR (merge = deploy em prod). O loop tira de nós a parte mecânica (claim, tdd, gates, PR) e nos devolve como **revisores de um lote pronto**, não babás do processo. Um único toque humano por onda preserva a regra de que push na main é ação humana (o gate continua real), e o deploy único por onda evita N rebuilds do Coolify (`watch_paths=null` rebuilda tudo a cada push).

## Considered options

- **Branches empilhadas (stacked PRs)** para 1 único OK cobrindo a fila inteira, incluindo dependentes: rejeitado. Rebases em cascata quando a base muda e concentração das corridas conhecidas de migration/bump/lockfile. As ondas com checkpoint dão o mesmo resultado (fila inteira, um OK por onda) sem a fragilidade da pilha.
- **Branch de integração** (merge autônomo em staging, humano só aprova staging→main) para ter literalmente 1 deploy por N issues: rejeitado. Mudaria o contrato de deploy (Coolify assiste a `main`) e adicionaria uma branch de longa duração. O deploy único **por onda** já entrega "poucos deploys pra muitas issues" sem tocar no contrato.
- **Aprovação por PR** (pausa a cada merge): rejeitado. Devolve o humano ao papel de gargalo N vezes por rodada, matando a autonomia que é o objetivo.
- **Revogar o gate de merge** (autonomia total até prod): rejeitado. Confiaria só nos 3 gates + health + rollback, mas o rollback nunca foi exercitado em produção e a `/security-review` lê o diff errado em worktree. O risco não vale a economia de um clique.
- **Paralelismo total na onda** (todas as destravadas de uma vez): rejeitado a favor de 2-3. Concentra as corridas de migration/lockfile/bump no checkpoint e cria pico de custo de tokens; 2-3 dá paralelismo real com merge sequencial re-conferido.

## Consequences

- **Política de falha "marcar e seguir":** issue que não fecha os gates em 3 tentativas é rotulada `ready-for-human` com o estado comentado (branch, o que falhou, hipótese) e a onda segue. A fila nunca trava por uma issue ruim; as baixas aparecem no checkpoint.
- **Merge sequencial obrigatório** mesmo com execução paralela: segue o playbook manual (bump um a um, `APP_VERSION` antes do deploy, re-conferir `origin/main` antes de cada push). Ver [[project_deploy_ops_manual_ship]] e [[project_bump_race_sessoes_paralelas]].
- **Gate de segurança em worktree é frágil:** a `/security-review` lê o diff da árvore principal, não do worktree (ver [[project_security_review_diff_errado]]). O agente de cada issue precisa escopar o diff explicitamente e o checkpoint sinaliza quando o escopo não pôde ser confirmado.
- **`/onda` não substitui** o fluxo interativo (`/pegar-issue` + `/tdd` em terminais separados continua válido para trabalho que quer acompanhamento fino); é o modo AFK de esvaziar a fila.
