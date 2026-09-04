# Aplicativo Hospital — painel do fluxo

Painel local e **somente leitura** do projeto. Abre direto no **Plano**: o mapa vivo do trabalho pendente, na ordem certa, com o comando de cada passo pronto para copiar.

```bash
python3 tools/workflow-dashboard/serve.py   # abre http://localhost:8765
```

Zero dependências (só a stdlib do Python). Bind apenas em `127.0.0.1` (ninguém na rede alcança). Nunca escreve na working tree (o `git fetch` da coleta só atualiza referências remotas).

## Rodar como serviço (macOS)

Para o painel ficar sempre de pé (sobe no login, reinicia se cair), instale o LaunchAgent — **a partir da árvore principal do repo**, nunca de um worktree de issue:

```bash
tools/workflow-dashboard/install-launchd.sh            # instala/atualiza → http://localhost:8799
tools/workflow-dashboard/install-launchd.sh uninstall  # remove
```

Porta fixa `8799` (a 8765 fica livre pra rodadas manuais), logs em `~/Library/Logs/workflow-dashboard.log`. O plist vive em `~/Library/LaunchAgents/com.hospital-reunioes.workflow-dashboard.plist` e injeta o PATH do homebrew para o `gh` funcionar sob launchd.

## Abas

**Plano** (home) — a leva atual: as fatias do PRD ativo em **ondas** de execução, com tamanho, tempo típico, estado e o comando copiável para pegar cada uma; issues **avulsas** abertas (fora de PRD) fecham a aba em seção própria, com os mesmos estados · **Issues** — tudo que aconteceu (PRD → fatias → PR → deploy); as fatias de cada PRD nascem **colapsadas** atrás de um toggle `▸ N fatias · M fechadas` (filtro/busca ativos forçam a exibição do que bate) · **Produção** — estado de produção + timeline de deploys e releases · **Pendências**, a fila humana: issues abertas com o label `ready-for-human` (ações que só o Pedro pode fazer, criadas no fim de um ciclo pelo `/ship` Passo 10.5), cada card com o rastro do PRD pai e o corpo com o passo a passo; fecha a issue, some do painel · **Mapa** — snapshots factuais da app · **Domínio** — ADRs + glossário · **Guia** — o método em 6 passos, num desenho · **Repositório** — cada pasta e arquivo que o git conhece, com o resumo lido da fonte (tabela do `README.md` da raiz, frontmatter, docstring, `<title>`, título do markdown), o conteúdo aberto na própria aba (markdown, texto, HTML em quadro isolado) e os links GitHub e Vercel (este só quando a URL está na fonte); embaixo, o botão **Rodar diagnóstico** roda o `/setup-maquina` sob demanda e mostra os cartões OK, AVISO e FALTA com o conserto copiável. Só o que está no `git ls-files` aparece: `.env`, `tokens/.env` e `local/` nunca entram.

## Vocabulário do Plano

- **Leva** — o conjunto de fatias de um PRD aberto; o painel desenha uma leva por PRD ativo.
- **Onda** — camada de fatias sem dependência entre si: tudo na mesma onda anda **em paralelo** (1 worktree por issue, claim atômico). A onda seguinte destrava quando as dependências fecham.
- **Fatia P/M/G** — label de tamanho aplicado pelo `/to-issues` na quebra do PRD (catálogo em `docs/agents/triage-labels.md`).
- **Tempo típico** — mediana do lead time real (claim → fechamento) das fatias fechadas do mesmo tamanho; bucket com menos de 3 amostras cai na **mediana geral** (o card avisa). Nunca é estimativa a priori.
- **Caminho crítico** — soma dos tempos típicos no caminho mais longo de dependências: o tempo mínimo até a leva fechar, mesmo com paralelismo máximo.

## De onde vêm os dados (ao vivo vs. do último `git pull`)

- **Ao vivo (rede):** issues, PRs e comentários via `gh` (o Plano nasce daí); produção, deploys e releases da `origin/main` (`git fetch` + `git show` — os ships rodam em worktrees paralelos, então a verdade pós-ship vive no remoto); e o seu `git` local (branch, commits).
- **Do seu clone (último `git pull`):** mapa da app (`docs/spec/snapshots/`), decisões e glossário (`docs/adr/` + `CONTEXT.md`).

Recoleta a cada request (cache de 60s; o botão ⟳ força). O painel recoleta sozinho a cada 60s. Requer `gh` autenticado para issues e para o Plano — sem ele, o resto continua funcionando (o painel mostra como resolver).

## Estrutura

- `serve.py` — servidor HTTP (stdlib), só leitura, bind 127.0.0.1.
- `collect.py` — agrega `gh` + arquivos de `docs/spec` + `git` num único `/api/data`.
- `plano.py` — módulo puro do Plano: ondas, caminho crítico, tempo típico e copiáveis por fatia (o front não calcula nada).
- `areas.py`: parse dos snapshots de área para as capas interativas (degrada para `None`, nunca quebra).
- `diagramas.py`: parse do subset Mermaid dos snapshots (ADR 0025).
- `tests/` — pytest do módulo plano e da estrutura do shell (`python3 -m pytest tests/`).
- `static/` — front vanilla em ES modules (sem build):
  - `app.js` — SPA, render de cada aba.
  - `ui.js` — componentes (tooltip, copiar, recolhível).
  - `content/` — textos estáveis (guia, setup, glossário).
  - `style.css` — identidade visual (papel/indigo/coral; Fraunces + IBM Plex).
  - `vendor/marked.min.js` — render de Markdown ([marked](https://github.com/markedjs/marked), licença MIT).
