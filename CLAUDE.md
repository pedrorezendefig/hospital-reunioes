# Regras — Hospital Reuniões

## Idioma
Todo conteúdo voltado ao time é em **pt-BR**: PRDs, issues (título + corpo), user stories ("Como `<papel>`, quero `<ação>`, para `<valor>`"), critérios de aceite, comentários de PR, ADRs, `CONTEXT.md`, mensagens ao usuário. Tipo de commit em inglês (`feat`/`fix`/`chore`/`refactor`/`docs`) com descrição em pt-BR. Termos técnicos consagrados (commit, merge, deploy, endpoint) ficam em inglês.

## Tipografia
**Sem travessão (U+2014) nem meia-risca (U+2013)** em nada que o usuário vê (telas, PDFs de Ata/POP, emails): são marca de texto gerado por IA. Use vírgula, ou hífen entre números (ADR 0013). O CI trava: ESLint no front (string e texto de JSX) + grep nos templates HTML do backend. O sanitizador determinístico cobre o texto que a IA gera.

## Fluxo de trabalho
Pipeline GitHub-issue-centric (skills do Matt Pocock + deploy próprio):
- **Planejar:** `/grill-with-docs` (desafia o plano contra o domínio — uma pergunta por vez, com recomendação destacada em cada decisão; atualiza `CONTEXT.md`/ADR) → `/to-prd` (vira PRD = 1 issue `ready-for-agent`) → `/to-issues` (quebra em fatias verticais independentes). Esse estilo vale inclusive sob o plan mode nativo do Claude Code — ele hospeda o fluxo, não o substitui.
- **Desenvolver:** `/pegar-issue <N>` (claim + branch) → `/tdd` (red → green → refactor) → `/ship` (3 gates → merge → deploy). **Modo AFK:** `/onda` esvazia a fila sozinho em ondas com checkpoint por lote (ADR 0022).
- **Deploy:** `/ship` chama `/deploy` no fim; ou `/deploy` direto (Coolify + health + rollback). Estado em `docs/spec/deploy/*.json`.
- **Debug:** `/diagnose`. **Arquitetura:** `/improve-codebase-architecture`. **Passar contexto p/ outra sessão:** `/passagem`.
- **Dev local:** `/atualizar-app` (rebuild docker-compose, não toca produção). **Mapa da app:** `/snapshot` (roda sozinho no fim do `/deploy`).

> Roteamento detalhado e o "como fazer" vivem nas **descrições das skills**. Mantenha este arquivo mínimo.

## Agent skills
- **Issue tracker:** GitHub Issues via `gh`. Veja `docs/agents/issue-tracker.md` (inclui o protocolo de claim para sessões paralelas).
- **Triage labels:** 5 papéis canônicos (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) + `in-progress`/`blocked`. Veja `docs/agents/triage-labels.md`.
- **Domain docs:** single-context — `CONTEXT.md` (glossário) + `docs/adr/`. Veja `docs/agents/domain.md`.

## Desenvolvimento paralelo
Várias sessões Claude Code rodam issues `ready-for-agent` distintas ao mesmo tempo — **1 git worktree por issue**, claim atômico via label/assignee. Bloqueios entre issues usam o campo "Bloqueada por: #X"; só entram no pool issues sem bloqueio aberto. Protocolo completo em `docs/agents/issue-tracker.md`.

## Proibido criar
- Docs de estado/processo paralelos (`PRODUCAO.md`, `deploy-history.md`, `dashboard.html`, pastas `planos/`, `implementacoes/`, `blueprint/`, chronicles): estado vive em `docs/spec/deploy/*.json` e o trabalho nas **GitHub Issues**.
- Exceção: `tools/workflow-dashboard/` — painel local **read-only** desses JSONs + `gh` (`python3 tools/workflow-dashboard/serve.py`).

## Docs vivos
- `CONTEXT.md` + `docs/adr/` — domínio e decisões (curado por humano). ADR: consuma só `status: accepted` (`superseded`/`deprecated` = histórico); supersessão é bidirecional (`supersedes`/`superseded_by`, `amends`/`amended_by`), travada pelo CI `lint-adr`.
- `docs/spec/snapshots/` — mapa **factual** da app, auto-gerado a cada deploy.
- `docs/spec/deploy/` — contrato e estado de deploy (`project.json` · `state.json` · `history.json`).
- `docs/spec/CHANGELOG.md` — timeline de deploys · `docs/spec/VERSIONING.md` — versão semântica.
