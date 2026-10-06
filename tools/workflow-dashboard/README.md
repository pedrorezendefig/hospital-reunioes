# Hospital OS

O painel local e **somente leitura** do time (ADR 0062, decisão 1): a ferramenta interna do fluxo de trabalho, não o aplicativo do hospital. Abre direto em **Issues**: o funil das nove fases no topo, cada issue com a fase, quem assumiu e há quanto tempo, e filtros de um clique.

```bash
python3 tools/workflow-dashboard/serve.py   # abre http://localhost:8765
python3 tools/workflow-dashboard/serve.py --no-open --fixture dados.json   # /api/data de um arquivo, sem coletar
```

O `--fixture` serve a saída de `collect.py --json` (editada ou não) no `/api/data`: render repetível no Chrome headless. Os comentários de uma issue (`/api/issue/<n>`) e a linha do tempo das fechadas (`/api/issue/<n>/timeline`) continuam chamando o `gh`.

Zero dependências (só a stdlib do Python). Bind apenas em `127.0.0.1` (ninguém na rede alcança). Nunca escreve na working tree (o `git fetch` da coleta só atualiza referências remotas).

## Rodar como serviço (macOS)

Para o painel ficar sempre de pé (sobe no login, reinicia se cair), instale o LaunchAgent, **a partir da árvore principal do repo**, nunca de um worktree de issue:

```bash
tools/workflow-dashboard/install-launchd.sh            # instala/atualiza → http://localhost:8799
tools/workflow-dashboard/install-launchd.sh uninstall  # remove
```

Porta fixa `8799` (a 8765 fica livre pra rodadas manuais), logs em `~/Library/Logs/workflow-dashboard.log`. O plist vive em `~/Library/LaunchAgents/com.hospital-reunioes.workflow-dashboard.plist` e injeta o PATH do homebrew para o `gh` funcionar sob launchd.

## Abas

Cinco abas, uma fonte por aba (ADR 0062, decisões 2 e 3). Nada no Hospital OS deriva de arquivo o que o GitHub já diz.

| Aba | O que mostra | Fonte |
|---|---|---|
| **Issues** (home) | funil das nove fases, filtros em chips, árvore PRD → fatias com o desenho das ondas, card com a linha do tempo | GitHub ao vivo pelo `gh` (issues, sub-issues, bloqueios, PRs, eventos, branches remotas); a fase Em produção cruza com o `history.json` |
| **PRs** | quadro por fase com uma raia por pessoa e a faixa das tentativas | GitHub ao vivo pelo `gh` (PRs com checks, `mergeStateStatus`, reviews); a coluna Em produção cruza com o `history.json` |
| **Produção** | versão no ar, health de cada serviço e uma linha por versão | `history.json` e `state.json` da `origin/main` (`git fetch` + `git show`) |
| **Mapa** | snapshots factuais da app (rotas, entidades, schema, diagramas) | `docs/spec/snapshots/` do seu clone |
| **Domínio** | ADRs e glossário do hospital | `docs/adr/` e `CONTEXT.md` do seu clone |

**Issues** (home): o **funil** das nove fases no topo, com a contagem de cada uma; clicar numa fase filtra a lista. Abaixo, os filtros em chips: estado, o chip `ready-for-human` com o contador da fila humana (era a aba Pendências), responsável (um chip por pessoa, na cor dela, mais "ninguém assumiu"), PRD aberto, labels agrupadas por prefixo (`type:`, `area:`, `fatia:` e as outras) e busca. Com um responsável filtrado, o funil mostra as contagens dele; não há lead time nem métrica por pessoa (ADR 0061, decisão 5). A lista segue a árvore PRD → fatias; o card fechado mostra fase, pessoa, idade, critérios feitos/total, PR e versão; aberto, a linha do tempo com data e hora, o corpo e os comentários · **PRs**: quadro com as seis fases do PR em colunas (aberto sem CI, CI vermelho, esperando revisor, verde esperando merge, mergeado sem deploy, em produção) e uma raia por pessoa, na cor dela (quem assumiu a issue que o PR fecha; sem assignee, "ninguém assumiu"). O card mostra PR, issue, branch, dias na coluna e o sinal de conflito; a coluna mais cheia e o card parado há mais de 3 dias ganham destaque (Em produção, o fim do caminho, não conta e mostra só a última semana, ou tudo com um PRD filtrado). Tentativas (fechados sem merge) ficam na faixa cinza embaixo. Filtros: pessoa, PRD e só abertos · **Produção**: estado de produção + timeline de deploys · **Mapa**: snapshots factuais da app · **Domínio**: ADRs + glossário.

O método de trabalho (o que era a aba Guia) vive em `docs/onboarding/`.

**Endereço**: aba, item aberto e filtros vivem no hash (`#issues/930`, `#prs/930`, `#producao/v0.161.0`, `#issues?resp=...&fase=...`); copiar a URL e abrir de novo volta ao mesmo ponto, com o card aberto em destaque. Chips de issue, PR e versão navegam dentro do painel; o GitHub é o `↗` de cada card (ADR 0062, decisão 8).

**Produção** lê só `history.json` e `state.json` (ADR 0062, decisão 2): no topo, a versão no ar e cada serviço com o último health; abaixo, uma linha por versão do `history.json` inteiro, a mais recente primeiro (deploys da mesma versão juntos). Aberta, a versão mostra cada deploy dela: health, duração do build, commit, env e notas; PRs, issues e migration ficam à mostra no card.

## Vocabulário

- **Fase**: em que pé está a issue, derivado só de fatos do GitHub (ADR 0062, decisão 4): Triagem, Fila, Bloqueada, Em andamento, PR aberto, Mergeada, Em produção, Humana, Encerrada sem PR. Quem calcula é o `fases.py`; o front só desenha.
- **Funil**: a faixa das nove fases com a contagem de cada uma, no total ou de um responsável.
- **Responsável**: quem assumiu a issue (assignee) e, sem assignee, quem criou (issue #1039); quem assumiu manda, então a issue criada por um e atribuída a outro é só do outro. A issue que entra pelo autor mostra a marca `✎ criou` no card. "ninguém assumiu" são as issues sem assignee: a mesma issue pode aparecer no chip do autor e em "ninguém assumiu", de propósito. O funil filtrado segue a mesma regra; a cor dos nós das ondas e as raias da aba PRs seguem só o assignee.
- **Branch criada**: sub-estado de Em andamento; existe branch remota da issue (convenção `<type>/<slug>-<N>`) e ainda não há PR. É fato do GitHub, vale para qualquer sócio; worktree é local e não entra.
- **Raia**: a linha de uma pessoa no quadro da aba PRs, na cor dela. O PR cai na raia de quem assumiu a issue que ele fecha; sem assignee, na raia "ninguém assumiu".
- **Tentativa**: PR fechado sem merge; o próximo PR da mesma issue aparece na linha do tempo como "novo PR".
- **Cor da pessoa**: os três sócios têm cor fixa; quem mais aparecer ganha a próxima cor da paleta (`static/pessoas.js`).
- **Onda**: rodada de execução de um PRD; a fatia entra uma onda depois da bloqueadora aberta do mesmo PRD. O card de cada PRD aberto desenha as ondas em colunas: o nó é a fatia na cor de quem assumiu, a borda é a fase, a seta é o `blocked_by` aberto, e clicar no nó abre o card da fatia.

## De onde vêm os dados (ao vivo vs. do último `git pull`)

- **Ao vivo (rede):** issues, PRs, comentários e a linha do tempo via `gh`; produção e deploys (`history.json` e `state.json`) da `origin/main` (`git fetch` + `git show`; o rabo `fechar_onda.py` pusha de um worktree próprio, então a verdade pós-merge vive no remoto); e o seu `git` local (branch, commits).
- **Do seu clone (último `git pull`):** mapa da app (`docs/spec/snapshots/`), decisões e glossário (`docs/adr/` + `CONTEXT.md`).

Recoleta a cada request (cache de 60s; o botão ⟳ força). O painel recoleta sozinho a cada 60s. Requer `gh` autenticado para Issues; sem ele, o resto continua funcionando (o painel mostra como resolver).

## Estrutura

- `serve.py`: servidor HTTP (stdlib), só leitura, bind 127.0.0.1.
- `collect.py`: agrega `gh` + arquivos de `docs/spec` + `git` num único `/api/data`.
- `fases.py`: módulo puro das fases: fase por issue e por PR, linha do tempo, ondas por PRD e contagens do funil (o front não calcula nada).
- `areas.py`: parse dos snapshots de área para as capas interativas (degrada para `None`, nunca quebra).
- `diagramas.py`: parse do subset Mermaid dos snapshots (ADR 0025).
- `tests/`: pytest dos módulos e do front (`cd tools/workflow-dashboard && python3 -m pytest tests -q`; o front roda no Node).
- `static/`: front vanilla em ES modules (sem build):
  - `app.js`: SPA, render de cada aba.
  - `ui.js`: componentes (tooltip, copiar, recolhível).
  - `pessoas.js`: a cor fixa de cada pessoa (`corDaPessoa`), reusada por chips, raias e nós.
  - `prs.js`: o quadro da aba PRs (colunas por fase, raias por pessoa, faixa das tentativas e filtros).
  - `router.js`: o router de hash (`#aba/item?filtros`), único módulo que lê e grava o `location.hash`.
  - `ondas.js`: o desenho das ondas no card do PRD (SVG próprio, um gancho só no `issueCard`).
  - `content/`: textos estáveis (glossário, verbetes das tabelas).
  - `style.css`: identidade visual (papel/indigo/coral; Fraunces + IBM Plex).
  - `vendor/marked.min.js`: render de Markdown ([marked](https://github.com/markedjs/marked), licença MIT).
