# Mapa do repositório: o que é cada pasta, por quê, e como se conectar a cada serviço

Este mapa explica o **porquê** e o **para quê**. A árvore de verdade é o disco: antes de responder sobre uma pasta, rode `ls` nela e confira. Pasta no disco que não está na lista de cobertura no fim deste arquivo é sinal de que o mapa envelheceu: o `/setup-maquina` avisa, e a correção é editar aqui. A regra do layout é o ADR 0044 (e a emenda 0045). O detalhe do app (rotas, tabelas, integrações) é gerado a cada deploy em `docs/spec/snapshots/` e não se repete aqui.

## A regra de uma frase

Tudo que está na árvore é código, doc viva, decisão ou material de comunicação. Insumo humano fica em `local/`, fora do git. Estado de trabalho fica nas GitHub Issues e em `docs/spec/deploy/*.json`, nunca em documento paralelo.

## Raiz

| Pasta ou arquivo | O que é | Por que existe | O que você acha dentro | Para que serve no dia a dia |
|---|---|---|---|---|
| `CLAUDE.md` | Regras do repo para o agente | Mínimo que toda sessão precisa saber | Idioma, tipografia, pipeline, o que é proibido criar | Leia uma vez. O roteamento fino está no `/ask-pedro` |
| `CONTEXT.md` | Glossário do contexto Reuniões (e, por ora, da Ouvidoria) | O agente e o time falam a mesma língua | Termos com definição e "evitar" | Consultar antes de nomear qualquer coisa nova |
| `CONTEXT-MAP.md` | Mapa dos contextos de domínio | Termos homônimos (Setor, Versão) mudam de sentido entre contextos | Tabela contexto x glossário | Saber qual glossário abrir |
| `skills-lock.json` | Origem e hash das 8 skills importadas do Matt Pocock | Rastreabilidade, não instalação | Repo de origem e caminho | Nada a rodar; as skills já vêm no clone |
| `.claude/skills/` | As skills do time, versionadas | Quem clona recebe o workflow inteiro (ADR 0043) | 23 pastas, uma por skill, com `SKILL.md`, `references/` e `scripts/` | `/ask-pedro` diz qual usar |
| `.github/` | CI e templates | Gates automáticos do `/ship` | `ci.yml` (ruff, pytest, lint, tsc, build), `lint-adr.yml`, `higiene-issues.yml`, templates de issue e PR | Não se edita no dia a dia |
| `docs/` | Documentação viva | Ver seção abaixo | | |
| `hospital-reunioes/` | O app | Ver seção abaixo | `backend/`, `frontend/`, `supabase/` | Onde o código mora |
| `local/` | **Fora do git.** Insumo humano | PDFs, transcrições e dumps não podem ir para o GitHub | `insumos/<assunto>/` que cada máquina cria | Colocar aqui o que o hospital manda |
| `tokens/` | Tokens da **máquina**, não do app | O `/deploy` e o `/ship` falam com o Coolify | `.env.example` (versionado) e `.env` (fora do git, permissão 600) | Preencher uma vez por máquina |
| `tools/` | Ferramentas de repo | Gate de ADR no CI e painel local | `lint_adr.py`; `workflow-dashboard/` (painel read-only das issues e do deploy) | `python3 tools/workflow-dashboard/serve.py` |

## `docs/`

| Pasta | O que é | Por que existe | O que tem | Quando abrir |
|---|---|---|---|---|
| `adr/` | Decisões de arquitetura e domínio | Decisão sem registro é re-litigada | `README.md` (índice por tema) e um `.md` por decisão, com `status` no frontmatter | Antes de propor mudança de regra. Só `accepted` vale |
| `agents/` | Protocolo do agente | Sessões paralelas precisam do mesmo contrato | `issue-tracker.md` (claim, labels, revisor), `triage-labels.md`, `domain.md` | Ao pegar issue ou triar |
| `onboarding/` | Setup humano | Máquina nova | `claude-setup.md` (setup), `dev.md` (dia a dia) | Primeiro dia. `/setup-maquina` confere o mesmo conteúdo |
| `spec/deploy/` | Contrato e estado do deploy | O `/deploy` lê daqui, nunca de memória | `project.json` (contrato: serviços, chaves, gates), `state.json` (versão em prod agora), `history.json` (todos os deploys, com notas) | `/deploy status`; ler as notas antes de planejar |
| `spec/snapshots/` | Mapa factual do app, gerado | O código muda, o mapa acompanha sozinho | `ROTAS.md`, `ENTIDADES.md`, `SCHEMA.md`, `MIGRATIONS.md`, `INTEGRACOES.md`, `ESTRUTURA.md` | Para saber o que existe hoje sem abrir o código |
| `spec/CHANGELOG.md`, `spec/VERSIONING.md` | Linha do tempo dos deploys e regra de versão | Cada ship tem entrada | Versão, data, PR, ADRs | Ver o que subiu quando |
| `pops/` | Glossário do contexto POPs | Segundo contexto de domínio (ADR 0007) | `CONTEXT.md` e `materiais-reais/` (POPs reais como referência) | Trabalhando em POPs |
| `comunicacao/` | Material para o diretor e o usuário funcional | Vídeo e página nascem juntos por PRD (ADR 0045) | `<contexto>/<PRD>-<slug>/video/` (composição) e `index.html` (página); `_assets/` (uma fonte, um logo) | `/divulgar <PRD>`. MP4 fica fora do git |
| `manual/` | Manual do usuário por módulo | Publicado na Vercel para o time interno | `ouvidoria/index.html`, `img/`, `README.md` (como publicar) | Ao entregar módulo novo |
| `ARQUITETURA.md` | Visão de arquitetura | Um lugar para o desenho geral | Os 3 contextos, fluxos, blocos gerados pelo `/snapshot` | Primeira leitura técnica |

## `hospital-reunioes/` (o app)

A árvore do app (routers, services, componentes, migrations) é gerada a cada deploy em `docs/spec/snapshots/ESTRUTURA.md`, com blocos curados por humano. Não se repete aqui. O que o mapa acrescenta é o porquê:

| Pasta | Por que existe assim | Quando abrir |
|---|---|---|
| `backend/` | FastAPI em subpacotes por área (`routers/pops/` é o modelo); regra de negócio em `services/`; scripts de operação fora da imagem (`scripts/`, e `scripts/oneshot/` para o que já rodou) | Toda issue de API, prazo, email, PDF ou IA |
| `frontend/` | Next.js com rota por domínio e `layout.tsx` aplicando o gate no servidor; regra sem React em `lib/<dominio>/` com teste ao lado | Toda issue de tela |
| `supabase/` | Migrations numeradas, RLS ligado na criação da tabela; produção aplica à mão no Studio | Issue que muda tabela |
| `.env.example` | Uma cópia só para docker-compose e uvicorn; o backend lê `hospital-reunioes/.env` | `/setup-maquina --env` |

## Variáveis de ambiente e como se conectar a cada serviço

Tudo em `references/chaves.md`: onde cada variável mora (máquina, app local, Coolify de produção, CI), de onde vem cada valor, e a tabela "Serviços" com o que o sócio precisa para GitHub, Coolify, Supabase, app em produção, Resend, ClickSign, OpenRouter, Global Health, Ana, Vercel e 1Password.

## O fluxo, em uma linha por etapa

1. Ideia: `/grill-with-docs` afia contra `CONTEXT.md` e ADRs. 2. `/to-prd` e `/to-issues` viram issues. 3. `/pegar-issue N` faz o claim e abre a branch. 4. `/tdd` escreve o teste primeiro. 5. `/ship` abre o PR, roda os 3 gates e pede o OK de merge. 6. O merge dispara o build no Coolify; `/deploy ship` acompanha e registra em `docs/spec/deploy/`. 7. Testa em produção. 8. `/divulgar` conta a entrega ao diretor.

## Cobertura (o `/setup-maquina` confere esta lista)

Toda pasta de nível 1 e 2 que o git conhece precisa estar aqui. O script compara linha a linha e avisa o que falta. Pasta nova no repo: acrescente a linha e explique acima, no mesmo commit. Ficam fora da conferência, por serem descritas por padrão e não uma a uma, o conteúdo de `.claude/skills/`, `docs/adr/`, `docs/comunicacao/` e `docs/manual/`.

<!-- cobertura:start -->
```
.claude
.claude/skills
.github
.github/ISSUE_TEMPLATE
.github/workflows
docs
docs/adr
docs/agents
docs/comunicacao
docs/manual
docs/onboarding
docs/pops
docs/spec
hospital-reunioes
hospital-reunioes/backend
hospital-reunioes/frontend
hospital-reunioes/supabase
tokens
tools
tools/workflow-dashboard
```
<!-- cobertura:end -->

Não aparecem aqui, por não estarem no git: `local/` (insumo humano), `tokens/.env`, `.claude/worktrees/`, `.vscode/` e os caches de ferramenta. Todas explicadas nas tabelas acima.
