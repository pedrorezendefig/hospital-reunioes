# Hospital OS

> Quando mudar skill do pipeline, atualize `static/fluxo.json` junto com o `/ask-pedro`: é dali que a aba Documentação desenha o fluxo de trabalho.

O painel local e **somente leitura** do time (ADR 0062, decisão 1): a ferramenta interna do fluxo de trabalho, não o aplicativo do hospital. Abre direto em **Issues**, nas abertas: filtros em dropdown no topo, o card grande com tudo que está pendente e a quebra por fase, cada issue com a fase, quem assumiu e há quanto tempo.

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

Quatro abas, uma fonte por aba (ADR 0062, decisões 2 e 3). Nada no Hospital OS deriva de arquivo o que o GitHub já diz.

| Aba | O que mostra | Fonte |
|---|---|---|
| **Issues** (home) | pendente por fase, filtros em dropdown, árvore PRD → fatias com o desenho das ondas, card com a linha do tempo | GitHub ao vivo pelo `gh` (issues, sub-issues, bloqueios, PRs, eventos, branches remotas); a fase Em produção cruza com o `history.json` |
| **PRs** | quadro por fase com uma raia por pessoa e a faixa das tentativas | GitHub ao vivo pelo `gh` (PRs com checks, `mergeStateStatus`, reviews); a coluna Em produção cruza com o `history.json` |
| **Produção** | versão no ar, health de cada serviço e a linha do tempo do repositório (merges e deploys) | merges: GitHub ao vivo pelo `gh` (`mergedBy`, labels); deploys e etapas: `history.json` e `state.json` da `origin/main` (`git fetch` + `git show`) |
| **Documentação** | quatro sub-pills: Fluxo, Mapa, Decisões e Glossário (abaixo) | arquivos do seu clone, uma fonte por sub-pill |

**Issues** (home): no topo, os filtros numa linha de dropdowns do próprio painel (sem `<select>`): responsável (na cor da pessoa, mais "ninguém assumiu"), estado (abre em abertas), PRD aberto, labels agrupadas por prefixo (`type:`, `area:`, `fatia:` e as outras) e busca. Cada opção mostra quantas issues traria com os outros filtros como estão (faceta); opção que traria zero fica esmaecida, mas continua clicável. O botão `limpar` aparece só quando algum filtro saiu do padrão e volta tudo ao padrão (abertas, sem recorte). Abaixo, o **funil**: o card grande, de contorno forte, com tudo que está pendente (issues abertas), e oito cards que destrincham esse número por fase e somam ele; clicar num card filtra a lista. A fila humana (era a aba Pendências) é o card Humana: aberta com `ready-for-human`. Com um responsável filtrado, o funil mostra as contagens dele; não há lead time nem métrica por pessoa (ADR 0061, decisão 5). A lista segue a árvore PRD → fatias; o card do PRD desenha o **fluxo do PRD** (abaixo); o card fechado mostra fase, pessoa, idade, critérios feitos/total, PR e versão; aberto, a linha do tempo com data e hora, o corpo e os comentários · **PRs**: quadro com as seis fases do PR em colunas (aberto sem CI, CI vermelho, esperando revisor, verde esperando merge, mergeado sem deploy, em produção) e uma raia por pessoa, na cor dela (quem assumiu a issue que o PR fecha; sem assignee, "ninguém assumiu"). O card mostra PR, issue (o título dela no title do chip), branch, dias na coluna e o sinal de conflito; a coluna mais cheia e o card parado há mais de 3 dias ganham destaque. Em produção, o fim do caminho, não conta, é compacta (uma linha por PR: número, issue e versão) e mostra só a última semana, ou tudo com um PRD filtrado. Tentativas (fechados sem merge) ficam na faixa cinza embaixo. Filtros: pessoas (várias ao mesmo tempo, uma raia para cada), PRD, só abertos e o `limpar` · **Produção**: estado de produção + linha do tempo do repositório (merges e deploys) · **Documentação**: o fluxo de trabalho desenhado, o mapa da app, as decisões por tema e o glossário.

### Documentação

Uma aba, quatro sub-pills (`#documentacao/fluxo`, `/mapa`, `/decisoes`, `/glossario`; os endereços antigos `#mapa` e `#dominio` caem na sub-pill que herdou o conteúdo). Cada uma tem uma fonte só:

| Sub-pill | O que mostra | Fonte |
|---|---|---|
| **Fluxo** (padrão) | o fluxo de trabalho do pedido à produção: as três portas (PRD + fatias, issue única, PR direto), os gates, a subida `fechar_onda.py` e as paradas humanas em âmbar; clicar num passo abre a regra dele e, em passo de skill, o link para o `SKILL.md`; abaixo, a legenda e a tabela das três portas | `static/fluxo.json`, desenhado à mão e mantido junto com o `/ask-pedro`; o front não tem texto do fluxo hardcoded, e o `diagramas.js` desenha (tipo `fluxo`, ADR 0025: sem mermaid.js) |
| **Mapa** | snapshots factuais da app: capa ER interativa e uma pill por documento (rotas, entidades, schema, diagramas) | `docs/spec/snapshots/` do seu clone |
| **Decisões** | ADRs agrupadas pelo tema do índice, só as `accepted` por padrão, com a frase da decisão em cada card; `ver histórico (N)` mostra as `superseded` esmaecidas com "substituída pela NNNN"; busca no título e no corpo | `docs/adr/*.md` e o índice `docs/adr/README.md` (parseado no `collect.py`; sem índice, agrupa pelo prefixo do título) |
| **Glossário** | o `CONTEXT.md` renderizado, com um índice de termos em chips no topo; cada `**Termo**` vira a âncora `#documentacao/glossario/<slug>` | `CONTEXT.md` do seu clone |

O método de trabalho (o que era a aba Guia) vive em `docs/onboarding/`.

**Endereço**: aba, item aberto e filtros vivem no hash (`#issues/930`, `#prs/930`, `#producao/v0.161.0`, `#issues?resp=...&fase=...`); copiar a URL e abrir de novo volta ao mesmo ponto, com o card aberto em destaque. Chips de issue, PR e versão navegam dentro do painel; o GitHub é o `↗` de cada card (ADR 0062, decisão 8).

**Produção**: no topo, a versão no ar e cada serviço com o último health, do `state.json` (ADR 0062, decisão 2). O semáforo do mast tem três estados: verde só com todo serviço `healthy` e checado; âmbar quando algum está `warning` ou sem verificação e ninguém está fora; vermelho só com serviço `down`/`unhealthy` ou HTTP fora de 2xx. O supabase não tem HTTP próprio: a subida deriva o status dele do health do backend a cada deploy (o `/api/health` só responde ok com o banco respondendo), e o card diz "via backend" (ou "sem verificação"). Abaixo, a **linha do tempo do repositório**, uma trilha vertical do mais recente ao mais antigo com duas fontes costuradas pelo número do PR: os **merges** vêm do GitHub ao vivo (`gh pr list` com `mergedBy` e labels) e os **deploys** do `history.json` da `origin/main`. Cada deploy é um card: versão, subject, resultado, responsável (quem rodou a subida, campo `responsavel` da entrada; nas entradas antigas, quem mergeou os PRs do lote), data, chips de PR (com a bolinha de quem mergeou) e de issue, migrations e a barra empilhada das etapas: `aberto` (createdAt ao mergedAt do PR mais antigo do lote) e `fila até produção` (último merge ao deploy) derivadas do GitHub; `merge`, `build` e `health` medidas pela subida (campo `etapas` da entrada, só nas entradas novas; as antigas mostram só aberto, fila e o total). A largura dos segmentos é logarítmica, para o build de um minuto não sumir ao lado de dias de PR aberto. Merge que não entrou em deploy nenhum é um nó pequeno, tracejado na cor da pessoa: "só merge · ferramenta" quando o PR é de ferramenta (nenhum deploy o inclui e a label não é `type:feature`/`type:fix`), "mergeado · sem deploy" quando é do app e espera o próximo. Janela: os últimos 60 dias ou os últimos 40 deploys, o que for maior; o `history` inteiro continua no payload. Filtro por pessoa no mesmo dropdown da aba Issues (recorta merges e deploys), que vai para o hash (`#producao?resp=...`). Aberto, o deploy mostra commit, escopo, duração da subida, env e notas.

## Vocabulário

- **Fase**: em que pé está a issue, derivado só de fatos do GitHub (ADR 0062, decisão 4): Triagem, Fila, Bloqueada, Em andamento, PR aberto, Mergeada, Em produção, Humana, Encerrada sem PR. Quem calcula é o `fases.py`; o front só desenha.
- **Funil**: o pendente (issues abertas) e a quebra dele pelas oito fases que uma issue aberta pode ter, no total ou de um responsável. Issue fechada não entra.
- **Responsável**: quem assumiu (assignee) manda; sem ninguém designado, a issue é de quem criou, com a marca `✎ criou` no card (ADR 0062, emenda de 06/10/2026). O que a pessoa criou e outro assumiu é do outro. "ninguém assumiu" são as issues sem assignee: a mesma issue aparece no chip do autor e em "ninguém assumiu", de propósito. O funil filtrado segue a mesma regra; a cor dos nós do fluxo e as raias da aba PRs seguem só o assignee.
- **Branch criada**: sub-estado de Em andamento; existe branch remota da issue (convenção `<type>/<slug>-<N>`) e ainda não há PR. É fato do GitHub, vale para qualquer sócio; worktree é local e não entra.
- **Raia**: a linha de uma pessoa no quadro da aba PRs, na cor dela. O PR cai na raia de quem assumiu a issue que ele fecha; sem assignee, na raia "ninguém assumiu".
- **Tentativa**: PR fechado sem merge; o próximo PR da mesma issue aparece na linha do tempo como "novo PR".
- **Cor da pessoa**: os três sócios têm cor fixa; quem mais aparecer ganha a próxima cor da paleta (`static/pessoas.js`).
- **Onda**: rodada de execução de um PRD; a fatia entra uma onda depois da bloqueadora aberta do mesmo PRD. No **fluxo do PRD** (card de cada PRD aberto) as ondas são faixas, uma linha por fatia.
- **Fluxo do PRD**: o desenho no card do PRD aberto: cada fatia numa linha (bolinha na cor de quem assumiu, borda na cor da fase), a seta para o PR dela (borda na cor da fase do PR no quadro da aba PRs) e, no ar, a versão; a seta vermelha no corredor da esquerda é o `blocked_by` aberto, da bloqueadora para a bloqueada. Clicar na fatia abre o card dela; PR e versão levam às abas PRs e Produção.

## De onde vêm os dados (ao vivo vs. do último `git pull`)

- **Ao vivo (rede):** issues, PRs, comentários e a linha do tempo via `gh`; produção e deploys (`history.json` e `state.json`) da `origin/main` (`git fetch` + `git show`; a subida `fechar_onda.py` pusha de um worktree próprio, então a verdade pós-merge vive no remoto); e o seu `git` local (branch, commits).
- **Do seu clone (último `git pull`):** mapa da app (`docs/spec/snapshots/`), decisões e glossário (`docs/adr/` + `CONTEXT.md`); o fluxo de trabalho é um arquivo do próprio painel (`static/fluxo.json`).

Recoleta a cada request (cache de 60s; o botão ⟳ força). O painel recoleta sozinho a cada 60s. Requer `gh` autenticado para Issues; sem ele, o resto continua funcionando (o painel mostra como resolver).

## Estrutura

- `serve.py`: servidor HTTP (stdlib), só leitura, bind 127.0.0.1.
- `collect.py`: agrega `gh` + arquivos de `docs/spec` + `git` num único `/api/data`.
- `fases.py`: módulo puro das fases: fase por issue e por PR, linha do tempo, ondas por PRD e contagens do funil (o front não calcula nada).
- `areas.py`: parse dos snapshots de área para as capas interativas (degrada para `None`, nunca quebra).
- `diagramas.py`: parse do subset Mermaid dos snapshots (ADR 0025).
- `tests/`: pytest dos módulos e do front (`uv run --no-project --python ">=3.12" --with pytest python -m pytest tools/workflow-dashboard/tests -q`; o front roda no Node). O CI não roda esta pasta (o `manual.yml` ignora o painel): o `/ship` roda local.
- `static/`: front vanilla em ES modules (sem build):
  - `app.js`: SPA, render de cada aba.
  - `ui.js`: componentes (tooltip, copiar, recolhível).
  - `pessoas.js`: a cor fixa de cada pessoa (`corDaPessoa`), reusada por chips, raias e nós.
  - `prs.js`: o quadro da aba PRs (colunas por fase, raias por pessoa, faixa das tentativas e filtros).
  - `router.js`: o router de hash (`#aba/item?filtros`), único módulo que lê e grava o `location.hash`.
  - `fluxo.json`: o fluxo de trabalho desenhado à mão (nós numa grade, raias, arestas, regra de cada passo, legenda e as três portas); fonte da sub-pill Fluxo.
  - `ondas.js`: o desenho das ondas no card do PRD (SVG próprio, um gancho só no `issueCard`).
  - `content/`: textos estáveis (glossário, verbetes das tabelas).
  - `style.css`: identidade visual (papel/indigo/coral; Fraunces + IBM Plex).
  - `vendor/marked.min.js`: render de Markdown ([marked](https://github.com/markedjs/marked), licença MIT).
