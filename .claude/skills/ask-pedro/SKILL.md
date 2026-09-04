---
name: ask-pedro
description: Router do pipeline do Hospital Reuniões. Digite /ask-pedro para descobrir qual skill usar agora.
disable-model-invocation: true
---

# Ask Pedro: router do pipeline

Responde "qual skill eu uso agora?" apontando a skill certa e o porquê. Não executa nada; só roteia. Se o pedido do usuário vier junto (`/ask-pedro como subo um fix?`), responda direto com a rota recomendada.

## Fluxo principal (planejar → desenvolver → entregar)

1. **Planejar**: `/grill-with-docs` desafia o plano contra o domínio (uma pergunta por vez, recomendação destacada em cada decisão; atualiza `CONTEXT.md`/ADR via `domain-modeling`). Dúvida factual de serviço externo no meio do grilling → `/research` em background.
2. **Especificar**: `/to-prd` vira PRD (1 issue `ready-for-agent`) → `/to-issues` quebra em fatias verticais com label `fatia:P/M/G`.
3. **Desenvolver**: `/pegar-issue <N>` (claim atômico + branch; sem argumento, lista a fila) → `/tdd` (red → green → refactor).
4. **Entregar**: `/ship` (3 gates → merge humano → deploy). `/deploy` direto para operar produção sem PR novo (status, rollback, setup Coolify).

## Modo AFK

- `/montar-ondas [--exceto #PRD] [--max-sessoes N]`: antes de abrir várias `/onda`, monta o plano: inventário que presta contas de toda issue aberta, triagem rápida das `needs-triage` com decisão cravada na issue, pergunta ao humano as decisões de domínio pendentes (2 opções, recomendação na frente) e crava a resposta, abre a fatia de PRD reprovado na auditoria, agrupamento por arquivo tocado em sessões sem conflito interno, e um prompt pronto por sessão que fica parado até o `vai`. Não executa nada.
- `/onda [#PRD | --all]`: esvazia a fila sozinho em ondas, checkpoint humano de merge por lote, um deploy por onda; com `#PRD`, audita o PRD no fim (reopen se a verificação falhar). A review é do orquestrador, não do sub-agente (ADRs 0022, 0029 e 0035).

## On-ramps (como o trabalho entra)

- `/triage`: criar/triar issues pelos papéis canônicos de label (`docs/agents/triage-labels.md`).
- Bug difícil ou regressão de performance → `/diagnose`.
- Melhorar arquitetura → `/improve-codebase-architecture` (relatório HTML); sanity-check de design → `/prototype`. Vocabulário de módulos em `codebase-design`; glossário e ADRs em `domain-modeling`.

## Pós-entrega

- `/divulgar <PRD> [--so-video | --so-pagina]`: a entrega pro diretor em dois passos, um comando: vídeo de percepção de valor (MP4, gate humano no draft) e página de divulgação publicada na Vercel com o vídeo embutido. Uma pasta por PRD em `docs/comunicacao/<contexto>/` (ADR 0045).
- `/snapshot`: mapa factual da app (roda sozinho no fim do `/deploy`).
- `/atualizar-app`: rebuild local docker-compose (não toca produção).
- **Pendência humana pós-ciclo** (import na virada, credencial, ato externo): vira issue `ready-for-human` ligada ao PRD (`/ship` Passo 10.5); o Pedro acompanha na aba **Pendências** do painel (`python3 tools/workflow-dashboard/serve.py`) e fecha a issue ao concluir.

## Máquina nova

- `/setup-maquina [--nivel N] [--env] [--mapa]`: diagnóstico de quem clonou (clone atualizado, binários, gh, plugins, Coolify, tokens) com o conserto ao lado e o item do 1Password de cada chave; `--mapa` explica cada pasta do repo pelo `README.md` da raiz e como se conectar a cada serviço. O app não roda local: nível 2 (deploy) é o alvo.

## Travessia de sessões

- `/passagem [--bg]`: documento de handoff pra outra janela; `--bg` dispara a continuação em background.
- Conflito de merge/rebase → `/resolver-conflitos`.

## Invariantes (não re-litigar)

- **Subir para prod é decisão humana** (merge = deploy em prod): OK explícito via AskUserQuestion citando o PR#. O gate é a decisão, não a digitação: dado o OK, a sessão executa merge, deploy, bookkeeping e push do registro, e só devolve `! <comando>` depois de ver a negativa de verdade.
- ADRs: consuma só `status: accepted`; supersessão bidirecional travada pelo CI `lint-adr`.
- Estado vive nas GitHub Issues + `docs/spec/deploy/*.json`; proibido criar docs paralelos de estado/processo.
- Nada de travessão nem meia-risca em texto visível ao usuário (ADR 0013).

## Manutenção deste router

Criou, renomeou ou apagou skill do pipeline? Atualize este arquivo no mesmo commit (regra no `CLAUDE.md`).
