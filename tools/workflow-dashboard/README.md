# Dashboard do workflow — Fluxo vivo

Painel local e **somente leitura** do projeto. Junta o que o workflow já produziu e mostra de forma didática — para acompanhar o trabalho e para quem está chegando aprender o fluxo.

```bash
python3 tools/workflow-dashboard/serve.py   # abre http://localhost:8765
```

Zero dependências (só a stdlib do Python). Bind apenas em `127.0.0.1` (ninguém na rede alcança). Nunca escreve na working tree (o `git fetch` da coleta só atualiza referências remotas).

## Abas

**Aprender** — Começar aqui (setup passo a passo, copia-e-cola, por sistema operacional) · Workflow (o pipeline do brainstorm ao deploy, com números vivos) · Bastidores (como este painel funciona).

**Acompanhar** — Agora (estado de produção) · Issues · Deploys · Mapa da app (snapshots) · Domínio (ADRs + glossário).

## De onde vêm os dados (ao vivo vs. do último `git pull`)

- **Ao vivo (rede):** issues, PRs e comentários via `gh`; produção, deploys e releases da `origin/main` (`git fetch` + `git show` — os ships rodam em worktrees paralelos, então a verdade pós-ship vive no remoto); e o seu `git` local (branch, commits).
- **Do seu clone (último `git pull`):** mapa da app (`docs/spec/snapshots/`), decisões e glossário (`docs/adr/` + `CONTEXT.md`).

Recoleta a cada request (cache de 60s; o botão ⟳ força). O painel recoleta sozinho a cada 60s. Requer `gh` autenticado para a parte de issues — sem ele, o resto continua funcionando (o painel mostra como resolver).

## Estrutura

- `serve.py` — servidor HTTP (stdlib), só leitura, bind 127.0.0.1.
- `collect.py` — agrega `gh` + arquivos de `docs/spec` + `git` num único `/api/data`.
- `static/` — front vanilla em ES modules (sem build):
  - `app.js` — SPA, render de cada aba.
  - `ui.js` — componentes (tooltip, copiar, recolhível, count-up).
  - `content/` — textos das abas didáticas (setup, workflow, bastidores, glossário).
  - `style.css` — identidade visual (papel/indigo/coral; Fraunces + IBM Plex).
  - `vendor/marked.min.js` — render de Markdown ([marked](https://github.com/markedjs/marked), licença MIT).
