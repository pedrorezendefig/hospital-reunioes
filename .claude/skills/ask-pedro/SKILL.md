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

- `/onda [#PRD | --all]`: esvazia a fila sozinho em ondas, checkpoint humano de merge por lote, um deploy por onda; com `#PRD`, audita o PRD no fim (reopen se a verificação falhar) (ADRs 0022 e 0029).

## On-ramps (como o trabalho entra)

- `/triage`: criar/triar issues pelos papéis canônicos de label (`docs/agents/triage-labels.md`).
- Bug difícil ou regressão de performance → `/diagnose`.
- Melhorar arquitetura → `/improve-codebase-architecture` (relatório HTML); sanity-check de design → `/prototype`. Vocabulário de módulos em `codebase-design`; glossário e ADRs em `domain-modeling`.

## Pós-entrega

- `/perceber <N>`: vídeo de percepção de valor pro diretor.
- `/divulgar <PRD>`: documentação de divulgação da seção (HTML enxuto com abas Funcionalidade + Demonstração por Vídeo, embute o MP4 da /perceber; publica na Vercel via HITL).
- `/snapshot`: mapa factual da app (roda sozinho no fim do `/deploy`).
- `/atualizar-app`: rebuild local docker-compose (não toca produção).

## Travessia de sessões

- `/passagem [--bg]`: documento de handoff pra outra janela; `--bg` dispara a continuação em background.
- Conflito de merge/rebase → `/resolver-conflitos`.

## Invariantes (não re-litigar)

- **Merge/push na main é ação humana** (merge = deploy em prod): OK explícito via AskUserQuestion citando o PR#.
- ADRs: consuma só `status: accepted`; supersessão bidirecional travada pelo CI `lint-adr`.
- Estado vive nas GitHub Issues + `docs/spec/deploy/*.json`; proibido criar docs paralelos de estado/processo.
- Nada de travessão nem meia-risca em texto visível ao usuário (ADR 0013).

## Manutenção deste router

Criou, renomeou ou apagou skill do pipeline? Atualize este arquivo no mesmo commit (regra no `CLAUDE.md`).
