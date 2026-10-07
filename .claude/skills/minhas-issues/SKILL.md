---
name: minhas-issues
description: "Check de um minuto das minhas issues abertas: semáforo do Actions, onde parou, fila por PRD e plano com comandos. Gatilhos: minhas issues, onde parei, o que tem pra mim, check das minhas issues, status do Actions. Só leitura. Sintaxe `/minhas-issues [@login]`."
---

# Minhas issues: check de um minuto

Mostra numa tela só o que está aberto com quem pede, onde cada coisa parou, se o GitHub Actions está de pé e por onde seguir. **Só leitura**: nada de push, rerun, claim, merge ou comentário; toda ação sai como comando pronto, e quem roda é o humano (issue #956).

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

3. Pare. Não execute nenhum comando do plano sem o humano pedir.

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
