# Roteiro: instalar o fluxo de trabalho neste projeto

Você é o agente que vai instalar, **neste repositório**, o fluxo de trabalho do repositório `pedrorezendefig/hospital-reunioes`. Chame de **ORIGEM** a pasta de onde o fluxo vem (normalmente `~/fluxo-origem`: um clone do repositório ou o zip gerado por `empacotar.sh`, descompactado; os caminhos são os mesmos nos dois casos) e este repositório de **DESTINO**.

O que você entrega no fim:

1. O painel local de 7 abas (Plano, Issues, Produção, Pendências, Mapa, Domínio, Guia) de pé, com o mesmo design system da ORIGEM e a paleta do DESTINO.
2. As skills do pipeline instaladas e adaptadas à stack do DESTINO.
3. As labels, os CIs de higiene e o contrato de deploy no lugar.
4. O domínio semeado: `CONTEXT.md` rascunho, ADR 0001 da instalação, primeiro snapshot.
5. Um PR aberto com tudo e uma issue `ready-for-human` na fila, para a pessoa mergear com a própria mão e ver o fluxo funcionar.

Você **não** mergeia nada. Você **não** toca na branch principal. O merge é da pessoa.

## Como você se comporta durante o roteiro

- **Uma pergunta por vez.** Nunca duas na mesma mensagem. Espere a resposta.
- **Duas opções por pergunta** (três só para paleta). A recomendação vem primeiro, marcada "(recomendo)", e explica em uma ou duas linhas por que, sempre citando o que você achou na base do DESTINO. A pessoa que está instalando pode estar começando a programar: ela precisa conseguir escolher rápido.
- **Fato se acha, decisão se pergunta.** Se a resposta está no código, no `package.json`, no `README` ou no `gh`, olhe. Não pergunte o que você pode ler.
- **Nada de sobrescrever em silêncio.** Se um arquivo já existe no DESTINO, mostre o diff do que você quer mudar e pergunte.
- **Nada destrutivo.** Sem `git reset --hard`, `git checkout --` em arquivo que não é seu, `git push --force`, `rm -rf` fora do que você criou.
- **Idioma:** tudo que a pessoa lê sai em pt-BR. Tipo de commit em inglês (`feat`, `fix`, `chore`, `refactor`, `docs`), descrição em pt-BR.
- **Tipografia:** nenhum travessão (U+2014) nem meia-risca (U+2013) em nada que você escrever: código, comentário, doc, commit, PR, issue. Use vírgula, ou hífen entre números. O CI que você vai instalar trava isso, e o painel também.
- **Se travar**, diga o que tentou, o que deu errado, e pergunte. Não invente caminho.

---

## Fase 0: pré-voo

Confira, sem perguntar, e resolva o que der:

```bash
git -C . rev-parse --show-toplevel          # DESTINO é um repo git
git -C . remote get-url origin              # tem remoto no GitHub
gh auth status                              # gh autenticado
gh repo view --json nameWithOwner,defaultBranchRef
python3 --version                           # 3.10 ou mais (o painel é stdlib pura)
ls ~/fluxo-origem/tools/instalar-fluxo/ROTEIRO.md   # ORIGEM no lugar
git -C ~/fluxo-origem rev-parse --short HEAD 2>/dev/null || cat ~/fluxo-origem/ORIGEM.txt   # SHA da ORIGEM (vai na ADR 0001)
```

Se o DESTINO não é repo git, ou não tem remoto no GitHub: pare e pergunte se pode criar (`git init` e `gh repo create --private --source=. --push`). Se `gh` não está autenticado: peça para a pessoa rodar `! gh auth login` e siga depois.

Crie a branch de trabalho a partir da branch padrão:

```bash
git switch -c chore/instalar-fluxo
```

Tudo que você fizer daqui para a frente vai nessa branch.

---

## Fase 1: explorar a base (você é um agente exploratório)

Antes de perguntar qualquer coisa, leia o DESTINO. Não altere nada nesta fase. Monte, no seu diretório de rascunho (fora do repo), uma **ficha do projeto** com o que achou. Procure em:

- **Identidade:** `README.md`, `package.json` (`name`, `description`), `pyproject.toml`, `go.mod`, `Cargo.toml`, `composer.json`, o que existir.
- **Stack:** gerenciador de pacotes e lockfile; framework (Next, Vite, Django, FastAPI, Rails, Laravel, Express, Go, o que for); banco (pasta de migrations, `prisma/`, `supabase/`, `alembic/`, `drizzle/`); testes (`vitest`, `jest`, `pytest`, `go test`); lint e formatação (`eslint`, `ruff`, `biome`, `prettier`, `golangci`).
- **Como roda local:** `docker-compose*.yml`, `Makefile`, scripts em `package.json`, `Procfile`, `.env.example`.
- **Deploy:** `vercel.json`, `netlify.toml`, `fly.toml`, `railway.json`, `render.yaml`, `Dockerfile`, `.github/workflows/*deploy*`, `coolify`, `app.yaml`, `serverless.yml`. E o que o README diz sobre produção. Endpoint de health, se existir (`/health`, `/api/health`).
- **Versão:** de onde sai (`package.json` `version`, `pyproject` `version`, arquivo `VERSION`, tag git). Se não há nenhuma fonte, anote "sem versão".
- **CI existente:** `.github/workflows/*.yml`. Anote os jobs, para não duplicar.
- **Design:** `tailwind.config.*`, `globals.css`, `theme.*`, `tokens.*`, `styles/`, logo em `public/`, `assets/`, `brand/`. Anote toda cor que parece de marca (hex, hsl, nome no Tailwind), fontes citadas (`@import` do Google Fonts, `next/font`, `@font-face`).
- **Domínio:** nomes de modelos, tabelas, entidades, rotas, pastas de feature. Anote os 10 a 20 termos mais frequentes. Eles viram o rascunho do `CONTEXT.md` e as áreas do Mapa.
- **O que já existe do fluxo:** `CLAUDE.md`, `.claude/skills/`, `CONTEXT.md`, `docs/adr/`. Se existe, você vai fundir, não sobrescrever.

Quando terminar, mostre a ficha para a pessoa em uma mensagem só, curta, em tabela: nome, stack, banco, testes, lint, como roda local, deploy, versão, CI, cores achadas, fontes achadas, termos de domínio, o que já existe do fluxo. Peça um "ok" ou correções. Só então comece a entrevista.

---

## Fase 2: entrevista

Faça as perguntas abaixo, **nesta ordem**, uma por mensagem. Cada uma traz a recomendação derivada da ficha. Anote cada resposta na ficha: a Fase 4 usa tudo.

**P1. Nome e slug.** "Como o painel chama o projeto?" Recomende o nome do `package.json`/README, capitalizado, e um slug em minúsculas com hífen. O título do painel vira "Aplicativo <Nome>" e o plist do serviço vira `com.<slug>.workflow-dashboard`.

**P2. Nome do router.** Na ORIGEM a skill que responde "qual skill eu uso agora?" chama `/ask-pedro`. Aqui vira `/ask-<primeiro-nome-de-quem-instala>`. Recomende o login do `gh api user --jq .login` ou o primeiro nome do `git config user.name`.

**P3. Plataforma de deploy.** Recomende a que a ficha achou. Se não achou nenhuma: opção A "ainda não tem deploy, instale o `/deploy` stub que só registra a versão" (recomendo) e opção B "tem, mas não está no repo: me diga qual". Anote também o endpoint de health e o domínio de produção, se existirem.

**P4. Fonte da versão.** Recomende a que a ficha achou. Sem nenhuma: opção A "criar `version` no `package.json` (ou `pyproject.toml`) começando em `0.1.0`" (recomendo) e opção B "arquivo `VERSION` na raiz". O `/ship` faz bump automático a partir daí.

**P5. Os 3 gates.** O `/ship` roda lint, testes e build antes de abrir o PR, e o `ci.yml` roda os mesmos no GitHub. Recomende os comandos que a ficha achou (`pnpm lint`, `pnpm test`, `pnpm build`, ou `ruff check .`, `pytest`, etc.). Se falta algum, opção A "instalar o padrão da stack" (recomendo, e diga qual) e opção B "pular esse gate por enquanto" (o `/ship` marca como pulado, não como verde).

**P6. Áreas do Mapa.** A aba Mapa agrupa rotas e entidades em 3 a 5 áreas de domínio (na ORIGEM: Reuniões, POPs, Pessoas, Infra). Proponha as áreas a partir dos termos da ficha, com a regra de classificação de cada uma (quais prefixos de rota e quais nomes de entidade caem nela). Opção A "essas" (recomendo) e opção B "outras: me diga quais". Essas áreas também viram as labels `area:*`.

**P7. Paleta.** Leia o bloco `:root` de `ORIGEM/tools/workflow-dashboard/static/style.css`. Ele é a única fonte da identidade visual. Monte **três** propostas, cada uma como um `:root` completo (todos os tokens da ORIGEM, nenhum a menos, nenhum a mais), coerentes com as cores da ficha:

- Proposta 1: a cor de marca do DESTINO como `--brand`, um tom escuro derivado dela como `--navy`, fundo branco. É a mais próxima do projeto dele.
- Proposta 2: variação com fundo `--bg` levemente tingido e `--navy` mais neutro. Mais calma.
- Proposta 3: contraste alto: `--navy` quase preto, `--brand` saturada. Mais forte.

Regras que valem para as três: `--on-navy` legível sobre `--navy` (contraste 4.5:1 ou mais); as seis semânticas de status (`--green`, `--red`, `--amber`, `--purple`, `--blue`, `--coral`) e seus `-wash` ficam legíveis sobre `--bg` e sobre `--navy`; os aliases estruturais (`--paper`, `--indigo`, `--line`, `--code-bg`, sombras) continuam apontando para os tokens novos; raios e easings não mudam. Se a ficha não achou cor nenhuma, derive as três de um tom que combine com o nome do projeto e diga que foi chute.

Mostre as três em uma tabela (nome, `--navy`, `--brand`, `--brand-light`, `--bg`, `--surface`, uma frase de sensação). Recomende a 1. Depois da escolha, aplique no `style.css` já copiado (Fase 3 acontece antes da aplicação, veja a ordem no fim desta fase), suba o painel com `python3 tools/workflow-dashboard/serve.py --no-open --port 8765` e peça para a pessoa abrir `http://localhost:8765` e confirmar. Se ela pedir ajuste, ajuste o token e peça para recarregar. Encerre o servidor depois.

**P8. Fontes.** Se a ficha achou fonte de marca com versão no Google Fonts, opção A "manter Onest e IBM Plex Mono, que são as do design system" (recomendo) e opção B "trocar `--sans` pela fonte de marca". Sem fonte de marca, não pergunte: mantenha.

**P9. Cofre de chaves.** O `/setup-maquina` diz de onde vem cada chave. Pergunte onde a pessoa guarda segredos (1Password, Bitwarden, `.env` na mão, outro). Só o nome, para escrever no `references/chaves.md`.

**Não pergunte** sobre idioma, tipografia, gate humano de merge, estado nas Issues, ADR só `accepted`, labels canônicas. Isso vai fechado, como na ORIGEM. Diga isso à pessoa numa linha depois da P9: "As regras do fluxo vão iguais às da origem (pt-BR, sem travessão, merge é decisão humana, estado vive nas Issues e nos JSONs de deploy). Se um dia quiser mudar uma, faz por ADR, como lá."

**Ordem real:** faça P1 a P6, depois execute a Fase 3 (copiar), depois volte para P7 (paleta, que precisa do painel copiado para o preview), P8 e P9. Depois siga para a Fase 4.

---

## Fase 3: copiar

Abra `ORIGEM/tools/instalar-fluxo/MANIFESTO.md`. Execute linha a linha:

- **copiar**: `cp -R` da ORIGEM para o mesmo caminho no DESTINO. Preserve a estrutura de pastas. Não copie `__pycache__`, `.pyc`, `.DS_Store`.
- **adaptar**: copie agora; a edição é na Fase 4.
- **gerar**: não copie; a Fase 4 e a Fase 5 escrevem.
- **excluir**: não toque.

Arquivo que já existe no DESTINO: mostre o diff e pergunte antes. Para `CLAUDE.md`, `README.md`, `.gitignore` e `.github/workflows/ci.yml`, a resposta padrão é **fundir** (o que já existe fica, o do fluxo entra como seção ou passo novo).

Renomeie a pasta `.claude/skills/ask-pedro` para `.claude/skills/ask-<nome>` (P2) já na cópia.

Ao terminar, `git add -A` e um commit: `chore(fluxo): copiar painel, skills, agentes e CIs da origem <sha>`. Esse commit é a foto do que veio igual; a adaptação vem nos commits seguintes, para o diff mostrar o que mudou.

---

## Fase 4: adaptar

Use a ficha e as respostas da entrevista. Para cada item **adaptar** e **gerar** do manifesto, a nota de adaptação dele diz o que muda. Abaixo, o detalhe dos que exigem mais cuidado.

### 4.1 Painel

- `static/style.css`: só o bloco `:root` (paleta da P7, fonte da P8) e o comentário da linha 1. Nenhuma outra linha muda. Confira com `git diff --stat`: o arquivo tem que mudar em um único bloco.
- `static/index.html`: `<title>Aplicativo <Nome> · painel do fluxo</title>`, o `<h1>` com `Aplicativo <span class="accent">Nome</span>`, e as duas cores do favicon (`fill` do retângulo = `--navy`, do círculo = `--brand-light`).
- `static/areas.js`: `ORDEM_DOM_ROTAS` e as descrições viram as áreas da P6; os dois regex de classificação (por rota e por entidade) viram as regras da P6; o nome no diagrama de contexto vira o nome do projeto. Não mexa no resto do arquivo.
- `static/content/glossary.js`: "Pedro" vira o nome de quem cuida do repositório.
- `static/content/tabelas.js`: exporte `TABELAS` com um resumo de uma linha por tabela do banco do DESTINO. Sem banco, `export const TABELAS = {};`.
- `install-launchd.sh`: label do plist.
- `README.md` do painel: nome do projeto e de quem cuida da fila humana.
- `tests/`: troque os textos que citam o Hospital pelos do DESTINO. Mantenha as asserções. Rode `python3 -m pytest tools/workflow-dashboard/tests -q` e deixe verde.

Se alguma tela da aba Guia (`static/app.js`, função `renderGuia`) citar nome, caminho ou serviço do Hospital, troque só o texto. Não altere estrutura, classes ou lógica.

### 4.2 `CLAUDE.md` e router

Siga a nota do manifesto. O `CLAUDE.md` fica mínimo: as regras. O roteamento fino mora em `.claude/skills/ask-<nome>/SKILL.md`. Nesse arquivo, toda skill listada tem que existir no DESTINO: apague a linha do `/divulgar` e, se `/atualizar-app` não foi gerado (sem app local), apague a dele também.

### 4.3 `/ship`

Abra `.claude/skills/ship/SKILL.md` e faça, nesta ordem:

1. Caminho do arquivo de versão (P4) em todo lugar que cita `hospital-reunioes/frontend/package.json`.
2. Os 3 gates (P5): os comandos de lint, testes e build. Gate pulado na P5 fica marcado como "pulado" na saída do `/ship`, nunca como verde.
3. Passo 8.5 (sync `APP_VERSION` no Coolify antes do merge): se a plataforma da P3 tem env de runtime e o app lê versão de env, escreva o equivalente; senão, apague o passo e renumere nada (deixe o número, escreva "não se aplica a esta plataforma").
4. Passo de migrations pré-merge: caminho de migrations do DESTINO e como elas são aplicadas em produção. Sem banco, "não se aplica".
5. O fim do `/ship` continua chamando `/deploy ship`.

Não mexa nos invariantes: 3 gates, PR, `AskUserQuestion` de merge citando o PR#, Passo 10.5 (issue `ready-for-human` para pendência humana pós-ciclo).

### 4.4 `/deploy`

Gere `.claude/skills/deploy/SKILL.md` para a plataforma da P3. Use o da ORIGEM como modelo de **estrutura** (modos, passos numerados, o que grava onde), não de conteúdo. O contrato que não pode quebrar, porque a aba Produção e o `/ship` dependem dele:

- Lê `docs/spec/deploy/project.json` (serviços, health check, plataforma).
- Modo `ship`: dispara ou acompanha o deploy, roda o health check, grava `state.json` (status por serviço, `last_deploy_sha`, `last_deploy_at`, `last_health_check`) e prepend em `history.json` (`at`, `sha`, `app_version`, `subject`, `raw_subject`, `scope`, `result`, `duration_seconds`, `services_touched`, `env_changes`, `migrations_applied`, `rollback_target_sha`, `notes`), prepend no `docs/spec/CHANGELOG.md` via `scripts/changelog_prepend.py`, commita o bookkeeping, roda `/snapshot`.
- Modo `status`: health check e leitura do estado, sem escrever nada além de `state.json`.
- Modo `rollback`: volta para `rollback_target_sha` e registra em `history.json`.
- Modo `setup`: o que a plataforma precisa uma vez (tokens, serviço, domínio).

**Stub (sem plataforma):** os modos existem, `ship` grava `history.json` e `CHANGELOG.md` com `result: "not-deployed"` e `state.json` com `status: "not-deployed"`; `status` diz que não há deploy configurado e aponta o `setup`; `setup` explica que é preciso escolher plataforma e reabrir esta parte do roteiro. A aba Produção mostra a timeline mesmo assim.

Copie `scripts/changelog_prepend.py` da ORIGEM e conserte o título da entrada: ele sai com travessão e sem versão. O formato certo é `## v0.X.Y - AAAA-MM-DD HH:MM - descrição` (hífen com espaços, nunca U+2014).

### 4.5 `/snapshot`

Gere `.claude/skills/snapshot/scripts/snapshot.py` para a stack do DESTINO. **Antes de escrever**, leia `tools/workflow-dashboard/areas.py`, `diagramas.py` e os snapshots da ORIGEM (`ORIGEM/docs/spec/snapshots/*.md`): o formato que os parsers esperam é o contrato. Saídas obrigatórias, mesmo que curtas:

- `ESTRUTURA.md`: árvore de pastas do app (todo DESTINO tem).
- `INTEGRACOES.md`: chaves de env por serviço externo (leia `.env.example`, `config`, `settings`).
- `ROTAS.md`: rotas HTTP, se o DESTINO expõe API ou páginas (introspecção do framework ou varredura de arquivos; diga no cabeçalho qual método usou).
- `ENTIDADES.md` e `SCHEMA.md`: modelos e tabelas, se há banco.
- `MIGRATIONS.md`: lista de migrations, se há pasta de migrations.
- `FLUXOGRAMAS.md`: ao menos um diagrama de contexto (app no centro, serviços externos em volta) no subset Mermaid que `diagramas.py` aceita.

Um arquivo que não se aplica ainda é gerado, com uma linha dizendo por quê ("Este projeto não tem banco."), para a aba Mapa não quebrar. O `SKILL.md` do `/snapshot` ganha `--check` (compara e não escreve) como na ORIGEM.

### 4.6 `/atualizar-app`, `/setup-maquina`, CI, labels

- `/atualizar-app`: siga o manifesto. `scripts/preview.sh` mostra o que vai mudar; `scripts/apply.sh` aplica.
- `/setup-maquina`: `scripts/diagnostico.sh` confere `git`, `gh`, `python3`, a CLI da plataforma (se houver), `tokens/.env` e os binários da stack (P5). `references/chaves.md` lista cada chave, de que serviço é e onde a pessoa a guarda (P9).
- `.github/workflows/ci.yml`: um job por gate da P5, mais o passo "Lint travessão" da ORIGEM apontado para a pasta de templates que o usuário final lê (emails, PDFs, páginas estáticas). Sem pasta assim, aponte para `docs/` e `README.md`. Se o DESTINO já tinha `ci.yml`, só acrescente o passo do travessão ao job existente.
- Regra ESLint do travessão: se o DESTINO usa ESLint, porte o bloco `no-restricted-syntax` de `ORIGEM/hospital-reunioes/frontend/eslint.config.mjs` para o config dele.
- Labels no GitHub: leia a lista canônica em `docs/agents/triage-labels.md` (papéis, apoio ao paralelismo, revisor, `fatia:P/M/G`, `type:*`, `area:*` da P6) e `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task` de `docs/agents/issue-tracker.md`. Cores e descrições vêm de `gh label list --repo pedrorezendefig/hospital-reunioes --json name,color,description --limit 100`. Crie com `gh label create <nome> --color <hex> --description "<texto>" --force`. Labels que já existem no DESTINO com outro nome (ex.: `bug`, `enhancement`) ficam; não apague nada.

### 4.7 Commits da fase

Um commit por bloco, para o diff contar a história:

- `chore(fluxo): adaptar painel ao <Nome> (paleta, áreas, título)`
- `chore(fluxo): adaptar CLAUDE.md, router e skills à stack do <Nome>`
- `chore(fluxo): gerar /deploy, /snapshot e /atualizar-app para <plataforma/stack>`
- `chore(fluxo): CI de gates e travessão, labels do GitHub`

---

## Fase 5: semear o domínio

1. **`CONTEXT.md`**: no formato de `.claude/skills/domain-modeling/CONTEXT-FORMAT.md`. Um verbete por termo de domínio que a ficha achou (nome, definição de uma linha tirada do código, "evitar" quando existe sinônimo no código). Título com o aviso: "Rascunho gerado na instalação do fluxo. Curar no primeiro `/grill-with-docs`." Sem detalhe de implementação: glossário, só.
2. **`docs/adr/README.md`** e **`docs/adr/0001-instalacao-do-fluxo-de-trabalho.md`**: formato de `docs/agents/domain.md` (frontmatter com `status: accepted`). A ADR registra: de onde veio (ORIGEM, SHA da Fase 0, data), as decisões da entrevista (P1 a P9, uma linha cada), e um parágrafo de resumo por ADR da ORIGEM que explica o fluxo (0013 travessão, 0020 ciclo de vida da issue, 0022 onda, 0025 diagramas do painel, 0027 wayfinder, 0028 bloqueio nativo, 0043 skills locais, 0044 layout do repo), cada um com link para o arquivo no GitHub da ORIGEM. Rode `python3 tools/lint_adr.py` e deixe verde.
3. **`docs/spec/deploy/*.json`**, **`VERSIONING.md`**, **`CHANGELOG.md`**: conforme o manifesto, com os valores da entrevista.
4. **Snapshot**: rode o `/snapshot` gerado. Confira que os 7 arquivos existem em `docs/spec/snapshots/`.
5. **`README.md`** da raiz: mapa de pastas no formato da ORIGEM. Toda pasta de nível 1 e 2 que o git conhece precisa estar na tabela e no bloco `cobertura`; o `/setup-maquina` confere isso.

Commit: `docs(fluxo): semear CONTEXT.md, ADR 0001, contrato de deploy e primeiro snapshot`.

---

## Fase 6: provar

Tudo abaixo tem que passar antes de abrir o PR. Se algo falha, conserte e rode de novo. Não abra o PR com item vermelho.

```bash
python3 -m pytest tools/workflow-dashboard/tests -q          # testes do painel
python3 tools/lint_adr.py                                     # ADRs válidas
python3 .claude/skills/snapshot/scripts/snapshot.py --check   # snapshot em dia
grep -rPln '[\x{2014}\x{2013}]' CLAUDE.md CONTEXT.md README.md docs/ tools/workflow-dashboard/static/index.html tools/workflow-dashboard/static/content .claude/skills/ask-*/ .claude/skills/deploy .claude/skills/snapshot .claude/skills/ship/SKILL.md; echo "travessão: nenhum acima = ok"
python3 tools/workflow-dashboard/serve.py --no-open --port 8765 &
sleep 3; curl -s 'http://localhost:8765/api/data?fresh' | python3 -c 'import json,sys; d=json.load(sys.stdin); print({k: (type(v).__name__, len(v) if hasattr(v, "__len__") else v) for k, v in d.items()})'
```

O `/api/data` tem que voltar sem `error` no bloco `github`, com `adrs` (1 item), `context_md` (texto), `snapshots` (7 arquivos), `state` e `history` (contrato de deploy) e `github` com `issues` (lista, pode estar vazia).

Depois, peça para a pessoa abrir `http://localhost:8765` e passar pelas 7 abas. Pergunte, uma por vez se precisar, se cada aba mostra o que se espera:

| Aba | O que tem que aparecer |
|---|---|
| Plano | "sem PRD ativo" (normal no primeiro dia) e a seção de avulsas vazia |
| Issues | vazio ou as issues que já existiam |
| Produção | o estado do `state.json` e a timeline vazia (ou o stub) |
| Pendências | vazio (a issue da Fase 7 vai aparecer depois) |
| Mapa | as áreas da P6 e os arquivos do snapshot |
| Domínio | a ADR 0001 e o glossário rascunho |
| Guia | o método em 6 passos com o nome do projeto |

Mate o servidor ao fim. Os gates da P5 (lint, testes, build do app do DESTINO) você não precisa rodar aqui: o CI do PR roda.

---

## Fase 7: entregar

1. `git push -u origin chore/instalar-fluxo`.
2. Abra o PR com `gh pr create --title "chore(fluxo): instalar fluxo de trabalho" --body-file <arquivo>`. O corpo, em pt-BR:
   - o que foi instalado (as 5 entregas do topo deste roteiro);
   - a tabela das decisões da entrevista (P1 a P9);
   - o que ficou de fora e por quê (manifesto, seção excluir, e os gates pulados na P5);
   - como rodar o painel: `python3 tools/workflow-dashboard/serve.py`;
   - o SHA da ORIGEM.
3. Espere o CI do PR. Se falhar em gate do app (lint, testes, build), conserte só o que a instalação causou. Se a falha já existia no DESTINO antes de você, diga isso no PR e siga.
4. Crie a primeira pendência humana:

```bash
gh issue create --label ready-for-human --title "Curar o CONTEXT.md e rodar o primeiro /grill-with-docs" --body-file <arquivo>
```

   Corpo: passo a passo (abrir `CONTEXT.md`, corrigir os verbetes que o rascunho errou, apagar os que não são domínio, depois abrir uma ideia com `/grill-with-docs`), o link do PR, e a frase "Fecha esta issue quando terminar; ela some da aba Pendências sozinha."

5. Mensagem final para a pessoa, curta:
   - o link do PR e a instrução: "O merge é seu. Confere o diff, mergeia pela interface do GitHub."
   - depois do merge: `git switch <branch padrão> && git pull`, depois `python3 tools/workflow-dashboard/serve.py`. A aba Pendências mostra a issue que você criou. Esse é o fluxo funcionando: pendência humana entra na fila, humano fecha, some do painel.
   - o próximo comando dela: `/ask-<nome>`.

Você **não** roda `gh pr merge`. Nunca.

---

## Fase 8: se algo não couber

Casos que este roteiro não cobre por inteiro, e o que fazer:

- **O DESTINO é um monorepo com vários apps.** Pergunte qual app é o alvo do fluxo. Os caminhos de versão, gates e snapshot apontam para ele. O painel é um só.
- **O DESTINO não usa GitHub Issues** (Linear, Jira). O fluxo inteiro depende de `gh` e de Issues. Diga isso e pare: não existe adaptação barata.
- **O DESTINO já tem um `CLAUDE.md` com regras que conflitam** (idioma inglês, por exemplo). Mostre o conflito e pergunte qual vale. Se a pessoa escolher a regra dela, anote na ADR 0001 como desvio da ORIGEM.
- **Sem Python 3 na máquina.** O painel é stdlib pura, mas precisa do interpretador. Peça para instalar antes de seguir.
- **Windows sem WSL.** O `install-launchd.sh` é macOS. O painel roda com `python3 serve.py` em qualquer sistema; pule o serviço.

Em qualquer outro caso: descreva o impasse, dê duas saídas, recomende uma, e espere.
