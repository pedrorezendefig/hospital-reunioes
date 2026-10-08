---
name: minhas-issues
description: "Check de um minuto das minhas issues abertas: semáforo do Actions, onde parou, fila por PRD, plano com comandos e passo a passo das humanas. Gatilhos: minhas issues, onde parei, o que tem pra mim, check das minhas issues, status do Actions. Só leitura. Sintaxe `/minhas-issues [@login]`."
---

# Minhas issues: check de um minuto

Mostra numa tela só o que está aberto com quem pede, onde cada coisa parou, se o GitHub Actions está de pé e por onde seguir. **Só leitura**: nada de push, rerun, claim, merge ou comentário; toda ação sai como comando pronto, e quem roda é o humano (issue #956). A única coisa que a skill roda além do script são checagens de leitura (`gh issue view`, `curl`) para montar o passo a passo das humanas.

## Sintaxe

```
/minhas-issues [@login]
```

Sem argumento, a pessoa é o login do `gh api user`. Com `@login`, mostra a fila de outra pessoa (cobrar alguém, cobrir férias).

"Minha" é o que a pessoa tem que fazer: atribuída a ela; sem ninguém atribuído, quem criou. O painel filtrado pela pessoa mostra também o que ela criou e outro assumiu, então lá o total pode ser maior.

## Fluxo

1. Rode o script e mostre a saída **como veio**, sem reescrever:

   ```bash
   python3 .claude/skills/minhas-issues/scripts/minhas_issues.py [@login]
   ```

2. Acrescente no máximo **duas linhas** suas, e só se mudarem a decisão (por exemplo: o mesmo arquivo em dois PRs do plano, ou um PR verde cuja issue já fechou). Nada de recapitular a tabela.

3. Se o plano tem **Tarefa humana**, acrescente a seção **4. Humanas: passo a passo** (abaixo). É a única exceção ao limite de duas linhas.

4. Pare. Não execute nenhum comando do plano sem o humano pedir. No fim, ofereça em uma linha rodar o passo que o agente consegue fazer sozinho (ex.: "Quer que eu rode o `--dry-run` da #891?").

## 4. Humanas: passo a passo

Para cada `ready-for-human` da pessoa, leia a issue antes de escrever (`gh issue view <N> --json body,comments`, corpo + últimos 3 comentários). Uma issue por bloco, nesta forma:

```
#<N> <tema curto>
Por que é humana: <uma linha: o que só a pessoa tem ou decide>
Já pode estar feito? <checagem de 1 comando, quando houver; rode-a, é leitura>
Passo a passo:
  1. <comando ou skill exata, com argumento>
  2. ...
Pronto quando: <critério de aceite verificável, de preferência um comando>
O agente faz: <os passos que esta sessão roda se a pessoa disser "vai"> · Só você: <o resto>
```

Regras:

- **Motivo real, não o label.** Classifique pelo que trava de fato. Os motivos que se repetem:
  - *conta pessoal* (projeto Vercel, chave ou máquina que só uma pessoa tem): diga qual conta e confira se esta máquina tem o vínculo (ex.: `docs/manual/.vercel/project.json`);
  - *decisão de domínio* (pacote grande, perguntas abertas na triagem, emenda de ADR): o caminho é `/grill-with-docs #<N> --lote`, e o passo 1 é juntar o insumo externo que falta (organograma, número, resposta do diretor) antes de abrir o grill;
  - *divulgação* (`type:divulgacao`): a pessoa aprova vídeo e página; o resto é `/divulgar`;
  - *as quatro paradas da regra 9 da ADR 0068* (migration no Studio, draft do vídeo do Manual, rollback, baixa `ready-for-human`): siga as memórias do projeto (migration pelo caminho clicável, segredo só na tela do Coolify).
- **Confira se já foi feito** antes de mandar fazer: `curl` no endereço público procurando a frase velha, `gh pr list --search <N>`, estado do deploy. Se já foi, o passo a passo vira "fechar com `gh issue close <N> --comment ...`".
- **O caminho mais curto**: reaproveite o que a issue já traz (bloco `O que fazer`, perguntas da triagem com recomendação). Prefira `--dry-run` primeiro quando o script tiver. Não invente passo que a issue não pede.
- **Separe o que é do agente.** Quase sempre só uma parte é humana (aprovar, decidir, logar numa conta); o resto o agente roda nesta máquina. Diga qual parte é qual.
- Máximo 6 passos por issue; sem travessão nem meia-risca.

## O que sai

1. **Semáforo** (1 linha), só Actions: componente Actions da status page do GitHub mais os últimos 10 runs do repositório.
   - verde: `operational` e nenhum job cancelado com `not acquired by Runner`: desenvolve, mergeia e deploya.
   - amarelo: `degraded_performance`, status page sem resposta ou algum cancelamento por runner: desenvolve e abre PR; a subida espera.
   - vermelho: `partial_outage` ou `major_outage`: só código local, não abre onda.
2. **Em andamento**: issue com claim, PR, ou worktree nesta máquina. "Onde parou" diz PR verde esperando a subida, CI cancelado ou vermelho, conflito, must-fix aberto, sem revisão, commit só local e worktree travado.
3. **Na fila**: uma linha por PRD ou grupo de avulsas, com a idade ("parada há N dias"). `needs-triage` entra só na contagem, com `/triage`.
4. **Plano**: até 3 passos, um por nível, nesta ordem fixa:
   1. PR verde esperando a subida (`fechar_onda.py --prs <N> --dry-run`);
   2. trabalho que pode se perder (commit sem push);
   3. PR travado (rerun, log do CI, conflito, must-fix, revisão);
   4. `priority:high` na fila (`/pegar-issue <N>`);
   5. `ready-for-human` que só a pessoa faz;
   6. fila de agente em ondas: devolve `/montar-ondas-enxutas` com `--exceto #PRD` para o PRD que já tem fatia andando. Esta skill não monta ondas.

   A estimativa é a mediana de PR aberto até o merge pelo tamanho da fatia (`fatia:P/M/G`), calculada na hora sobre os últimos 45 dias. O lead time abertura-fechamento não entra: mede espera na fila, não esforço. **Melhor** é o passo 1 (a ordem já põe primeiro o que destrava mais); **mais rápido** é o de menor estimativa; quando coincidem, sai numa linha.

## Limites

- Worktree e commit sem push só aparecem para a máquina onde roda; claim sem PR nem worktree aqui sai como "claim sem PR nem worktree nesta máquina".
- Os testes estão em `tools/test_minhas_issues.py`.
