---
name: ask-pedro
description: Router do pipeline do Hospital Reuniões. Digite /ask-pedro para descobrir qual skill usar agora.
disable-model-invocation: true
---

# Ask Pedro: router do pipeline

Responde "qual skill eu uso agora?" apontando a skill certa e o porquê. Não executa nada; só roteia. Se o pedido do usuário vier junto (`/ask-pedro como subo um fix?`), responda direto com a rota recomendada.

## Qual porta? (antes de tudo)

Nem todo trabalho é PRD. Classifique primeiro; o `/grill-with-docs` faz isso no fechamento e o `/express` já nasce na porta C.

| Porta | Quando | Caminho | Por que esse peso |
|---|---|---|---|
| **A. PRD + fatias** | Muda comportamento visível em mais de uma fatia, ou tem migration, ou o diretor precisa saber (bloco "Para o diretor"), ou nasce ou muda página do Manual, ou não cabe numa sessão | `/grill-with-docs` → `/to-prd` → `/to-issues` → `/onda-enxuta` ou `/pegar-issue` | O PRD é o que o diretor lê na aba Tecnologia; a issue é a spec do implementador; o draft do Manual é puxado pelo PRD |
| **B. Issue única, sem PRD** | Uma fatia vertical no app (`hospital-reunioes/`), cabe numa sessão, sem diretor e sem Manual. Várias independentes: `/onda-enxuta --all` ou agentes paralelos na mesma sessão | `/triage` ou `gh issue create` com critérios de aceite → `/pegar-issue N` | PR do app passa pelo `hr-revisor`, e a lente spec × diff precisa dos critérios; os critérios viram os testes do `/tdd`; o funil do OS conta issues |
| **C. PR direto, sem issue** | Ferramenta (`.claude/`, `tools/`, `.github/`, `docs/`) e chore do app que não muda comportamento (texto, lint, config) | Edita na branch → `/ship "<descrição>" --from-diff` → subida. Paralelo: um `Agent` com `isolation: worktree` por mudança, cada um termina no `/ship --skip-review`, e um `fechar_onda.py --prs a b c` no fim | ADR 0068, regra 12: decisão de ferramenta vai no corpo do PR. O OS mostra o PR na aba PRs; sem issue fica fora do funil, e é isso mesmo: o funil é trabalho em aberto |

Teste rápido entre B e C: **alguém precisa conferir que fez o que foi pedido?** Sim: B (precisa de critério escrito). A prova é o diff e o CI: C.

## Fluxo principal (planejar → desenvolver → entregar)

1. **Planejar**: `/grill-with-docs` desafia o plano contra o domínio (uma pergunta por vez, recomendação destacada em cada decisão; atualiza `CONTEXT.md`/ADR via `domain-modeling`). Modo lote (`--lote`, "responde tudo"): todas as lacunas já decididas de uma vez, fecha com "ok" ou "N: correção". Dúvida factual de serviço externo no meio do grilling → `/research` em background.
2. **Especificar**: `/to-prd` vira PRD (1 issue `ready-for-agent`, com a seção "Manual: páginas que nascem ou mudam") → `/to-issues` quebra em fatias verticais com label `fatia:P/M/G` e, em PRD com tela, fecha com a **Fatia de manual** (`docs: manual do PRD #N`, bloqueada pelas fatias de código; ADR 0057).
3. **Desenvolver**: `/pegar-issue <N>` (claim atômico + branch; sem argumento, lista a fila) → `/tdd` (red → green → refactor).
4. **Entregar**: `/ship` leva até o **PR verde** (ferramenta, nada em `hospital-reunioes/`: só o CI; app: `hr-revisor` uma vez, com a lente de segurança se o `sensivel.py` acusar e spec × diff se houver issue, mais o CI; must-fix ou CI vermelho chamam o `hr-corretor`) e roda a subida sozinho, sem parada até produção, exceto migration. **Subida única** (ADR 0068): `python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <N>` mergeia PR a PR pela API (squash), define a versão pelo tipo dos commits sem commit (`APP_VERSION` no Coolify e tag), um build, health e registro gravado pela Action pós-merge (só `history.json` e `state.json`); nenhum push. Serve a um PR avulso ou ao lote de uma onda; quem roda é o `/ship` do autor do PR ou o fechamento da onda. Conflito na subida chama o `hr-corretor` com a `/resolver-conflitos` e conta tentativa; a terceira falha vai para `ready-for-human`. `/deploy` só opera produção (status, rollback, setup Coolify); `/deploy ship` aponta para a subida e sai. O snapshot e o `draft` das páginas do Manual dos PRDs que subiram saem numa Action no push da `main`, depois do registro. A Action não publica: ela avisa no PRD fechado o que saiu e o que ficou em draft, e o humano roda `/manual publicar` da máquina com os MP4, que tira o draft das páginas com Vídeo de tarefa e republica o site (issue #951).

## Modo AFK

- `/minhas-issues [@login]`: check de um minuto antes de escolher o que fazer: semáforo do Actions, o que está em andamento e onde parou, fila por PRD com idade, e plano de até 3 passos com comando pronto (o passo de ondas devolve o `/montar-ondas-enxutas` com recorte). "Minha" = atribuída, ou criada sem ninguém atribuído. Não executa nada.
- `/montar-ondas-enxutas [--exceto #PRD] [--max-sessoes N]`: antes de abrir várias `/onda-enxuta`, monta o plano: inventário que presta contas de toda issue aberta, triagem rápida das `needs-triage` com decisão cravada na issue, pergunta ao humano as decisões de domínio pendentes (2 opções, recomendação na frente) e crava a resposta, agrupamento pela dependência (não pelo arquivo) em sessões sem conflito interno, e um arquivo de prompt mais um comando de lançamento por sessão (sessão de fundo, zero MCP). Para cada PRD que fecha no plano, escreve também o prompt do `/divulgar` e a linha do `/mensagem-prd` e diz quando colar (terminal próprio, nunca dentro da `/onda-enxuta`); entrega a agenda das intervenções humanas no meio das ondas (migration, segredo no Coolify, restart). Não executa nada.
- `/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]`: esvazia a fila sozinho em ondas, uma sessão de fundo por onda (`scripts/lancar_sessao.sh`), implementador que morre no PR, corretor fresco, merge PR a PR pela API dos PRs verdes de cada lote e um build por onda pelo `fechar_onda.py` (as paradas humanas são as da regra 9 da ADR 0068). A review é do agente `hr-revisor`, disparado pelo orquestrador (ADR 0068). A `/onda` e a `/montar-ondas` originais não existem mais.
- `/retro-onda [<nome>-onda<N> | <id de sessão>]`: o último passo do modo AFK, quando o relatório da onda terminou em `retro: recomendada`. Lê o que a onda deixou (medição em `~/.claude/onda-enxuta/medicoes/`, baixas, comentários do corretor, saída da subida, JSONL da sessão) e propõe mudanças no **ambiente** dos agentes, não no código: ponteiro de navegação, check no CI, lente nova no `hr-revisor`, gatilho no `sensivel.py`, instrução sem efeito para apagar. Mecânico vira check; juízo vira lente. Só propõe; cada candidata aceita vira PR de ferramenta pelo `/ship`.

## On-ramps (como o trabalho entra)

- Ideia pequena, "dá pra fazer X?", print com uma vontade → `/express`: uma rodada só, olha o código, propõe a ponte mínima, e com o "siga" implementa e verifica. É a entrada da porta C; se a conversa pedir 5 decisões encadeadas, ele mesmo manda para o `/grill-with-docs`.

- `/triage`: criar/triar issues pelos papéis canônicos de label (`docs/agents/triage-labels.md`).
- Bug difícil ou regressão de performance → `/diagnose`.
- Esforço grande demais para caber num grilling de uma sessão (névoa multi-sessão) → `/wayfinder`: mapa de tickets de decisão no GitHub (label `wayfinder:map`), um ticket por sessão, até a rota clarear; o handoff no fim é `/to-prd` + `/to-issues`. A porta da frente do planejamento continua sendo `/grill-with-docs` (ADRs 0027 e 0049).
- Melhorar arquitetura → `/improve-codebase-architecture` (relatório HTML); sanity-check de design → `/prototype`. Vocabulário de módulos em `codebase-design`; glossário e ADRs em `domain-modeling`.

## Pós-entrega

- `/divulgar <PRD> [--so-video | --so-pagina]`: a entrega pro diretor em dois passos, um comando: vídeo de percepção de valor (MP4, gate humano no draft) e página de divulgação publicada na Vercel com o vídeo embutido. Uma pasta por PRD em `docs/comunicacao/<contexto>/` (ADR 0045).
- `/mensagem-prd <PRD>`: a mensagem de WhatsApp que o Pedro manda ao diretor e aos usuários do módulo quando o PRD sobe: o que mudou e para que serve, texto corrido sem jargão, só o que já está em produção, com o link da página do `/divulgar` quando existir. Sai em bloco para copiar e fica registrada como comentário no PRD. O envio é do Pedro.
- `/manual <módulo | #PRD | publicar>`: o Manual do usuário em `docs/manual/`. Com módulo, escreve a seção inteira; com `#PRD`, só as páginas daquele PRD em `draft` (é a receita da Fatia de manual, que para no draft do vídeo); com `publicar`, tira o draft que a Action deixou e chama o `publicar.sh` (ADR 0057; passo do humano depois do deploy, issue #951).
- `/montar-manual [--max-sessoes N]`: antes de abrir vários terminais de `/manual`, monta o plano do passivo do manual: inventário por módulo (página que falta, print, vídeo, Novidades por PRD entregue, draft esquecido de PRD que já subiu), cada lacuna em um balde só, e um prompt por terminal, um por módulo, com as pastas que aquele terminal pode tocar e teto de 3. A publicação na Vercel fica fora dos prompts: é um passo só, depois dos merges. Não executa nada.
- `/snapshot`: mapa factual da app (roda sozinho numa Action no push da `main`, depois do registro da subida, ADR 0068).
- `/atualizar-app`: rebuild local docker-compose (não toca produção).
- **Pendência humana pós-ciclo** (import na virada, credencial, ato externo): vira issue `ready-for-human` ligada ao PRD (`/ship` Passo 10); o Pedro acompanha no card **Humana** da aba Issues do **Hospital OS** (`python3 tools/workflow-dashboard/serve.py`) e fecha a issue ao concluir.

## Máquina nova

- `/setup-maquina [--nivel N] [--env] [--mapa]`: diagnóstico de quem clonou (clone atualizado, binários, gh, plugins, Coolify, tokens) com o conserto ao lado e o item do 1Password de cada chave; `--mapa` explica cada pasta do repo pelo `README.md` da raiz e como se conectar a cada serviço. O app não roda local: nível 2 (deploy) é o alvo. Quem vai produzir ou publicar o Manual roda `--nivel 4`: ele confere Node >= 22.12 (o site não builda com menos), `ffmpeg` e Playwright.

## Travessia de sessões

- `/passagem [--bg]`: documento de handoff pra outra janela; `--bg` dispara a continuação em background.
- Conflito de merge/rebase → `/resolver-conflitos`.

## Invariantes (não re-litigar)

- **Subir para prod não espera humano, fora as quatro paradas da regra 9** (ADR 0068): o gate é CI, revisores agentes, health e rollback automático. O `/ship` e o fechamento da onda rodam a subida (`fechar_onda.py`) sozinhos; ela faz o merge pela API (a `main` é protegida), o deploy e o registro, que a Action pós-merge grava na `main` sem PR. O humano só é chamado nas quatro paradas da regra 9 da ADR 0068: migration, draft do vídeo da fatia de manual, rollback que a subida não fechou sozinha (`/deploy rollback`) e baixa `ready-for-human`. Cada sócio sobe o próprio PR (ADR 0068).
- ADRs: consuma só `status: accepted`; supersessão bidirecional travada pelo CI `lint-adr`.
- Estado vive nas GitHub Issues + `docs/spec/deploy/*.json`; proibido criar docs paralelos de estado/processo.
- Nada de travessão nem meia-risca em texto visível ao usuário (ADR 0013).
- **O Manual só mostra o que está no ar** (ADR 0057): página de funcionalidade que ainda não subiu nasce em `draft`, e quem tira o draft é a Action do push da `main`, depois do registro da subida (ADR 0068), nunca a mão no frontmatter. A página com Vídeo de tarefa (o MP4 não vem no clone) sai do draft pelo `/manual publicar` que o humano roda da máquina com os MP4, e é só esse modo que republica o site (issue #951). A Fatia de manual roda depois das fatias de código, não no mesmo PR.

## Manutenção deste router

Criou, renomeou ou apagou skill do pipeline? Atualize este arquivo no mesmo commit (regra no `CLAUDE.md`).

Skill do Matt Pocock (`mattpocock-skills`) entra no pipeline **forkada** em `.claude/skills/`, em pt-BR, apontando `CONTEXT.md` (o upstream renomeou o glossário para `GLOSSARY.md` na v1.3; aqui o nome não muda) e com as fontes e destinos do Hospital escritos. O plugin fica como referência de leitura, não como skill ativa do fluxo; o fork sombreia o nome. Instrução operativa que manda rodar outra skill diz "chame a Skill tool com `nome`", nunca `/nome` em prosa (convenção do upstream: o `/nome` solto é o que mais falha em disparar); `/nome` fica só onde um humano escolhe, como neste router.
