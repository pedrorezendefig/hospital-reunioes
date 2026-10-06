---
status: accepted
amends: 0062
---

# O bypass da `main` é uma deploy key, usada só no job da Action que não instala nada

Decisão do Pedro (06/out/2026, veredito de segurança do PR #1012, issue #940). A ADR 0062 (decisão 10) deu o bypass do ruleset da `main` ao `github-actions[bot]` (integration 15368) para a Action pós-merge commitar snapshot e draft do Manual. O revisor de segurança mostrou que esse bypass não tem escopo fixo: ele vale para o `GITHUB_TOKEN` de qualquer workflow, de qualquer branch, e em modo `always` pula também o `non_fast_forward`. Quem tem escrita no repo (ou um agente, ou um token com escopo `workflow`) sobe numa branch qualquer um YAML com `contents: write` que faz `git push --force` na `main`, sem PR e sem CI, e o webhook do Coolify põe o código em produção. Além disso, o token com bypass ficava no `.git/config` enquanto o job instalava o lock inteiro do backend e importava o app: um pacote comprometido no PyPI empurraria para a `main`.

## Decisões

1. **O ator do bypass é uma deploy key de escrita (`actor_type: DeployKey`), e só ela.** O `bypass_actors` do `.github/rulesets/main.json` sai da integration 15368. O tipo `DeployKey` cobre todas as deploy keys do repo, então o repo tem uma só com escrita, a da Action. A chave privada vive no secret `POS_MERGE_DEPLOY_KEY` de um Environment `pos-merge`, restrito à branch `main`: job de outra branch, ou de um `workflow_dispatch` nela, não chega ao secret.

2. **A Action tem dois jobs.** O `gerar` faz o que instala e executa código de terceiros (setup do Python e do Node, ffmpeg, `uv sync`, `tirar_draft_manual.py`, `snapshot.py`) com `contents: read` e `persist-credentials: false`, e entrega por artefato um patch só dos três caminhos (`docs/spec/snapshots/`, `docs/ARQUITETURA.md`, `docs/manual/src/content/docs/`). O `commitar` declara o Environment, faz checkout da ponta da `main` com a deploy key, baixa o patch, aplica só o que cai nos três caminhos (`git apply --include`), recusa rename de fora para dentro e modo que não seja de arquivo comum (symlink, gitlink), e no Manual só aceita página que já existe na `main` e volta igual, com o `true` da linha `draft:` trocado por `false`. Commita como `github-actions[bot]` com `[skip ci]` e empurra. Ele não instala nada.

3. **O `[skip ci]` passa a carregar peso.** Push por deploy key dispara workflow, ao contrário do `GITHUB_TOKEN`. O `[skip ci]` no assunto e o `paths-ignore` da própria Action impedem o loop.

## Emendas

- **ADR 0062, decisão 10:** onde se lê "bypass do ruleset só para `github-actions[bot]`" e "Push pelo `GITHUB_TOKEN` não redispara workflow", vale esta ADR: o ator do bypass é a deploy key da Action, o autor do commit continua `github-actions[bot]`, e quem evita o loop é o `[skip ci]` com o filtro de caminhos. A frase da emenda à ADR 0061 ("bypass de escopo fixo") só passa a ser verdade com esta ADR: a regra "subir código é por PR, admin incluído" volta a valer para todo workflow que não seja o job `commitar` na `main`.

## Alternativas descartadas

- **Manter a integration 15368 e só separar os jobs.** Fecha o caminho do PyPI, mas não o YAML de outra branch com `contents: write`.
- **GitHub App própria como ator.** Escopo igual ao da deploy key, com mais peças (app, instalação, troca de token por job) para um único push.
- **Passar os arquivos em vez de um patch.** O artefato não leva arquivo apagado, e sobrescrever os três caminhos apagaria a página do Manual que um PR mergeasse entre os dois jobs.

## Consequências

- Criar a deploy key com escrita, o Environment `pos-merge` (só a branch `main`) e o secret `POS_MERGE_DEPLOY_KEY` é tarefa do admin, na tela do GitHub, junto com aplicar o ruleset (pendência #1011). Deploy key nova com escrita, para qualquer outro fim, ganha o mesmo bypass: o repo fica com uma só.
- O patch vem de um job que roda pacote de terceiros. O `commitar` limita o estrago aos três caminhos e, no Manual, à troca do `draft`: a `.mdx` executa no `pnpm build` de quem roda o `publicar.sh`, então nenhuma outra linha dela vem do patch. Snapshot e `ARQUITETURA.md` aceitam qualquer texto, que ninguém executa; um snapshot adulterado só engana quem lê.
