'use strict';

/* Conteúdo da aba "Workflow".
   Adaptação interativa de docs/onboarding/dev.md (pipeline + cenários + regras).
   Os NÚMEROS de cada etapa são vivos (calculados no app.js a partir de /api/data);
   aqui mora só o texto didático estável. Se dev.md mudar, reflita aqui.

   step.live = chave do número vivo (resolvida no renderWorkflow). */

export const WORKFLOW_STEPS = [
  {
    cmd: '/grill-with-docs', title: 'A ideia apanha do domínio', tip: 'ADR', live: 'adrs', go: 'dominio',
    summary: 'Antes de escrever qualquer código, a ideia é desafiada contra o glossário (CONTEXT.md) e as decisões já tomadas. Os termos viram precisos; cada trade-off real vira um ADR.',
    how: 'Abra uma sessão Claude Code e descreva a ideia. A skill faz perguntas, afia os termos e atualiza CONTEXT.md/ADR ali mesmo. Quando o plano fica redondo, ela encadeia o /to-prd.',
    run: '/grill-with-docs',
  },
  {
    cmd: '/to-prd', title: 'O plano vira PRD', tip: 'PRD', live: 'prds', go: 'issues',
    summary: 'O plano validado é publicado como um PRD — uma issue no GitHub com problema, solução, histórias de usuário e critérios de aceite. É a especificação do QUE construir.',
    how: 'Depois do grill, rode /to-prd. Ele transforma a conversa numa issue com a label ready-for-agent.',
    run: '/to-prd',
  },
  {
    cmd: '/to-issues', title: 'O PRD vira fatias verticais', tip: 'fatia vertical', live: 'slices', go: 'issues',
    summary: 'O PRD é cortado em fatias independentes — cada uma entregável de ponta a ponta (banco + API + tela + testes) e vinculada como sub-issue nativa do PRD, com bloqueios explícitos.',
    how: 'Rode /to-issues logo após o /to-prd. Ele lê o PRD e cria N issues filhas, prontas para a fila.',
    run: '/to-issues',
  },
  {
    cmd: '/pegar-issue', title: 'Claim atômico na fila', tip: 'claim atômico', live: 'ready', go: 'issues', label: 'ready-for-agent',
    summary: 'Quem vai desenvolver pega uma issue da fila. O claim é atômico: tira da fila e marca você como dono num passo só. Várias pessoas trabalham em paralelo, 1 worktree por issue, sem colisão.',
    how: 'Sem argumento, lista a fila. Com o número, dá o claim, cria a branch determinística e carrega a spec no contexto.',
    run: '/pegar-issue 42',
  },
  {
    cmd: '/tdd', title: 'Red → green → refactor', tip: 'fatia vertical', live: 'prog', go: 'issues', label: 'in-progress',
    summary: 'Cada critério de aceite da issue vira um teste que falha primeiro (red), depois o código mínimo para passar (green), depois a limpeza (refactor). Os testes são a especificação.',
    how: 'Rode /tdd depois do /pegar-issue. Os critérios de aceite da issue são a sua lista de testes — um por vez.',
    run: '/tdd',
  },
  {
    cmd: '/ship', title: 'Três gates até o merge', tip: 'gate', live: 'merged', go: 'deploys', security: true,
    summary: 'Commit, Pull Request e 3 gates: code-review (sempre), security-review (quando toca login, banco, env ou webhooks) e CI. Passou tudo, faz squash-merge com Closes #N e a issue fecha sozinha.',
    how: 'Rode /ship com a issue verde. Ele cuida de branch, PR, gates, bump de versão (semver) e merge — e chama o /deploy no fim.',
    run: '/ship "descrição da mudança" --issue 42',
  },
  {
    cmd: '/deploy', title: 'Coolify, health e rollback', tip: 'rollback', live: 'deploys', go: 'deploys', deploy: true,
    summary: 'Sobe a versão no Coolify, aplica as migrations, faz health check com version match e, se algo falhar, reverte sozinho. No fim reescreve state.json, history.json e o CHANGELOG.',
    how: 'O /ship chama o /deploy no final. Para ver a produção sem mexer em nada: /deploy status. Para reverter à versão anterior: /deploy rollback.',
    run: '/deploy status',
  },
  {
    cmd: '/snapshot', title: 'O mapa factual se regenera', tip: 'snapshot', live: 'snapshots', go: 'mapa',
    summary: 'Depois de cada deploy verde, ROTAS, ENTIDADES, SCHEMA, MIGRATIONS e INTEGRACOES são regerados a partir do código. O mapa da app (aba "Mapa da app") nunca fica velho.',
    how: 'Roda sozinho no fim do /deploy. Para conferir manualmente o que mudaria: /snapshot --check.',
    run: '/snapshot --check',
  },
];

/* As duas portas de entrada + retomada + bug (dev.md, "Como trabalhar") */
export const WORKFLOW_SCENARIOS = [
  { tag: 'A', title: 'Tenho uma ideia nova', text: 'Lapida a ideia e a transforma em issues prontas para a fila.', run: '/grill-with-docs\n/to-prd\n/to-issues' },
  { tag: 'B', title: 'Vou pegar trabalho da fila', text: 'Pega uma issue, desenvolve com testes e sobe para produção.', run: '/pegar-issue 42\n/tdd\n/ship' },
  { tag: 'C', title: 'Sessão fechou, retomo depois', text: 'O contexto vive na Issue, não em arquivo. A branch é determinística pelo nº.', run: 'git checkout fix/algum-slug-42\ngh issue view 42\n/tdd' },
  { tag: 'D', title: 'Bug feio que não sei resolver', text: 'Loop disciplinado: reproduz → isola → hipótese → corrige → teste de regressão.', run: '/diagnose' },
];

/* Regras de ouro (dev.md, "Regras importantes") */
export const WORKFLOW_RULES = [
  { icon: '🔒', text: 'Nunca commitar na main direto. Toda mudança entra por um Pull Request via /ship.' },
  { icon: '✅', text: 'Self-approval é OK — os 3 gates (code-review, security-review e CI) já validam. Cada um aprova o próprio PR.', tip: 'self-approval' },
  { icon: '🛡', text: 'Nunca pular o security-review quando a mudança toca login, banco de dados, variáveis de ambiente ou webhooks.', tip: 'security-review' },
  { icon: '📌', text: 'O contexto do trabalho vive na Issue, não num arquivo de plano. Os critérios de aceite viram seus testes no /tdd.' },
  { icon: '🔀', text: 'Uma issue por vez, uma branch por issue. Em paralelo (vários terminais), 1 worktree por issue evita que duas sessões colidam.', tip: 'worktree' },
];
