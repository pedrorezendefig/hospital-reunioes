# Aplicativo Hospital — painel do fluxo

Painel local e **somente leitura** do projeto. Abre direto em **Issues**: o funil das nove fases no topo, cada issue com a fase, quem assumiu e há quanto tempo, e filtros de um clique.

```bash
python3 tools/workflow-dashboard/serve.py   # abre http://localhost:8765
python3 tools/workflow-dashboard/serve.py --no-open --fixture dados.json   # /api/data de um arquivo, sem coletar
```

O `--fixture` serve a saída de `collect.py --json` (editada ou não): render repetível no Chrome headless, sem depender do `gh`.

Zero dependências (só a stdlib do Python). Bind apenas em `127.0.0.1` (ninguém na rede alcança). Nunca escreve na working tree (o `git fetch` da coleta só atualiza referências remotas).

## Rodar como serviço (macOS)

Para o painel ficar sempre de pé (sobe no login, reinicia se cair), instale o LaunchAgent — **a partir da árvore principal do repo**, nunca de um worktree de issue:

```bash
tools/workflow-dashboard/install-launchd.sh            # instala/atualiza → http://localhost:8799
tools/workflow-dashboard/install-launchd.sh uninstall  # remove
```

Porta fixa `8799` (a 8765 fica livre pra rodadas manuais), logs em `~/Library/Logs/workflow-dashboard.log`. O plist vive em `~/Library/LaunchAgents/com.hospital-reunioes.workflow-dashboard.plist` e injeta o PATH do homebrew para o `gh` funcionar sob launchd.

## Abas

**Issues** (home): o **funil** das nove fases no topo, com a contagem de cada uma; clicar numa fase filtra a lista. Abaixo, os filtros em chips: estado, o chip `ready-for-human` com o contador da fila humana (era a aba Pendências), responsável (um chip por pessoa, na cor dela, mais "ninguém assumiu"), PRD aberto, labels agrupadas por prefixo (`type:`, `area:`, `fatia:` e as outras) e busca. Com um responsável filtrado, o funil mostra as contagens dele; não há lead time nem métrica por pessoa (ADR 0061, decisão 5). A lista segue a árvore PRD → fatias; o card fechado mostra fase, pessoa, idade, critérios feitos/total, PR e versão; aberto, a linha do tempo com data e hora, o corpo e os comentários · **PRs**: em construção (quadro por fase, uma raia por pessoa) · **Produção**: estado de produção + timeline de deploys · **Mapa**: snapshots factuais da app · **Domínio**: ADRs + glossário.

O método de trabalho (o que era a aba Guia) vive em `docs/onboarding/`.

**Endereço**: aba, item aberto e filtros vivem no hash (`#issues/930`, `#prs/930`, `#producao/v0.161.0`, `#issues?resp=...&fase=...`); copiar a URL e abrir de novo volta ao mesmo ponto, com o card aberto em destaque. Chips de issue, PR e versão navegam dentro do painel; o GitHub é o `↗` de cada card (ADR 0062, decisão 8).

**Produção** lê só `history.json` e `state.json` (ADR 0062, decisão 2): no topo, a versão no ar e cada serviço com o último health; abaixo, uma linha por versão do `history.json` inteiro, a mais recente primeiro (deploys da mesma versão juntos). Aberta, a versão mostra cada deploy dela: health, duração do build, commit, env e notas; PRs, issues e migration ficam à mostra no card.

## Vocabulário

- **Fase**: em que pé está a issue, derivado só de fatos do GitHub (ADR 0062, decisão 4): Triagem, Fila, Bloqueada, Em andamento, PR aberto, Mergeada, Em produção, Humana, Encerrada sem PR. Quem calcula é o `fases.py`; o front só desenha.
- **Funil**: a faixa das nove fases com a contagem de cada uma, no total ou de um responsável.
- **Responsável**: quem assumiu a issue (assignee). Quem só criou aparece no card como informação, mas não conta; "ninguém assumiu" são as issues sem assignee.
- **Tentativa**: PR fechado sem merge; o próximo PR da mesma issue aparece na linha do tempo como "novo PR".
- **Cor da pessoa**: os três sócios têm cor fixa; quem mais aparecer ganha a próxima cor da paleta (`static/pessoas.js`).
- **Onda**: rodada de execução de um PRD; a fatia entra uma onda depois da bloqueadora aberta do mesmo PRD. O card de cada PRD aberto desenha as ondas em colunas: o nó é a fatia na cor de quem assumiu, a borda é a fase, a seta é o `blocked_by` aberto, e clicar no nó abre o card da fatia.

## De onde vêm os dados (ao vivo vs. do último `git pull`)

- **Ao vivo (rede):** issues, PRs, comentários e a linha do tempo via `gh`; produção e deploys (`history.json` e `state.json`) da `origin/main` (`git fetch` + `git show`; o rabo `fechar_onda.py` pusha de um worktree próprio, então a verdade pós-merge vive no remoto); e o seu `git` local (branch, commits).
- **Do seu clone (último `git pull`):** mapa da app (`docs/spec/snapshots/`), decisões e glossário (`docs/adr/` + `CONTEXT.md`).

Recoleta a cada request (cache de 60s; o botão ⟳ força). O painel recoleta sozinho a cada 60s. Requer `gh` autenticado para Issues; sem ele, o resto continua funcionando (o painel mostra como resolver).

## Estrutura

- `serve.py` — servidor HTTP (stdlib), só leitura, bind 127.0.0.1.
- `collect.py` — agrega `gh` + arquivos de `docs/spec` + `git` num único `/api/data`.
- `fases.py`: módulo puro das fases: fase por issue e por PR, linha do tempo, ondas por PRD e contagens do funil (o front não calcula nada).
- `areas.py`: parse dos snapshots de área para as capas interativas (degrada para `None`, nunca quebra).
- `diagramas.py`: parse do subset Mermaid dos snapshots (ADR 0025).
- `tests/`: pytest dos módulos e do front (`cd tools/workflow-dashboard && python3 -m pytest tests -q`; o front roda no Node).
- `static/` — front vanilla em ES modules (sem build):
  - `app.js` — SPA, render de cada aba.
  - `ui.js` — componentes (tooltip, copiar, recolhível).
  - `pessoas.js`: a cor fixa de cada pessoa (`corDaPessoa`), reusada por chips, raias e nós.
  - `router.js`: o router de hash (`#aba/item?filtros`), único módulo que lê e grava o `location.hash`.
  - `ondas.js`: o desenho das ondas no card do PRD (SVG próprio, um gancho só no `issueCard`).
  - `content/`: textos estáveis (glossário, verbetes das tabelas).
  - `style.css` — identidade visual (papel/indigo/coral; Fraunces + IBM Plex).
  - `vendor/marked.min.js` — render de Markdown ([marked](https://github.com/markedjs/marked), licença MIT).
