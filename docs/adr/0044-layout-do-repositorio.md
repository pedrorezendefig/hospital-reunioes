---
status: accepted
amended_by: 0045, 0046
---

# Layout do repositório: o que fica no git, onde fica, e o que vive fora

Em 5 meses de pipeline com agentes o repositório acumulou 74 GB de worktrees mortas, PDFs de insumo na raiz, três cópias da mesma fonte e do mesmo logo, HTMLs de um formato aposentado, e skills de 50 KB lidas inteiras a cada `/ship`. Uma sessão de limpeza sem regra escrita desfaz o arranjo na sessão seguinte (foi o que motivou o ADR 0043 para as skills). Este ADR fixa o layout.

## Decisões

1. **Histórico é o git.** O que sai do repositório sai de vez. Não existe pasta `_arquivo/`, `_historico/` ou equivalente: o agente lê tudo que está na árvore, e material morto na árvore custa token e induz erro. Quem precisar de uma versão antiga usa `git log`.

2. **`local/` é o único lugar fora do git para insumo humano.** PDFs recebidos, transcrições, atas de migração, rascunhos de spec, dumps de produção: tudo em `local/<assunto>/`, ignorado por uma regra só (`/local/`). Cada máquina cria a sua. O agente lê quando pedido. Nada mais fica solto na raiz além de `CLAUDE.md`, `CONTEXT.md`, `CONTEXT-MAP.md` e `skills-lock.json`.

3. **`docs/comunicacao/` é o material que vai para o diretor e para o usuário funcional.** Dentro: `percepcao/` (vídeos de percepção de valor, ADR 0026), `divulgacao/` (páginas de divulgação publicadas na Vercel) e `_assets/` (uma fonte, um logo). A composição HyperFrames e o HTML são a fonte versionada; MP4, `renders/`, `node_modules/` e `.vercel/` são regeráveis e ficam fora do git. A pasta `docs/manual/` (manual do usuário, #563) nasceu em paralelo a este ADR e permanece onde está até o próximo ciclo de comunicação decidir se entra aqui.

4. **Uma cópia de asset, e o deploy copia.** Fonte e logo vivem só em `docs/comunicacao/_assets/`. Vídeos apontam para lá por link simbólico `assets`. Páginas que a Vercel serve como pasta autossuficiente (divulgação, manual) referenciam `logo-hsm.png` e `HPSimplified_Rg.ttf` relativos, e o passo de deploy da skill copia os dois de `_assets/` para a pasta temporária antes de publicar. Duplicata no git é regressão.

5. **Skill grande carrega o raro em `references/`.** O `SKILL.md` traz o caminho comum. Modos raros (setup do zero, rollback, migração de blueprint), exemplos de saída e integrações opcionais vão para `references/<nome>.md` ao lado, e o `SKILL.md` diz em uma frase quando ler cada um. A `description` no frontmatter tem até 200 caracteres: o que faz, quando usar, sintaxe. Lista de frases-gatilho não entra. O conteúdo do passo a passo não muda de lugar para mudar de sentido: mover é mover.

6. **Um `.env.example` completo por lugar que lê `.env`.** `hospital-reunioes/.env.example` é o molde do `docker-compose` local (backend + `NEXT_PUBLIC_*`). `hospital-reunioes/backend/.env.example` espelha 1:1 a classe `Settings` e é o que o gate `env_example_sync` do `/deploy` confere. `hospital-reunioes/frontend/.env.example` serve o `pnpm dev` sem Docker. `tokens/.env.example` lista as chaves da máquina (Coolify, GitHub, Ana). Cada chave leva um comentário curto. Chave que o código não lê não fica no exemplo.

7. **Scripts de operação vivem em `backend/scripts/`**, fora da imagem de produção, e rodam de dentro de `backend/` com `uv run python -m scripts.<nome>`. Script de uso único não viaja no container.

## Consequências

- Uma faxina futura tem régua: se algo na árvore não é código, doc viva, decisão ou material de comunicação, ou está em `local/` ou sai.
- O sócio clona e roda: os quatro `.env.example` dizem o que preencher, e nenhuma skill depende de pasta global (ADR 0043).
- O custo por sessão cai: descrições curtas de skill e memória do agente podada; o custo por `/ship` cai porque o `SKILL.md` do `/deploy` deixa de carregar os modos que quase nunca rodam.
- O ADR 0026 cita `docs/percepcao/`; o endereço final é o do ADR 0045 (`docs/comunicacao/<contexto>/<PRD>-<slug>/video/`). A decisão dele (vídeo como percepção, composição versionada) não muda.
