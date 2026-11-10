---
name: todas-issues
description: "Lista no terminal as issues abertas de todos os Projetos de uma vez, por Categoria e por Projeto (a ordem da Ala Projetos do PedroOS), com fase, Responsável e PRD. Com --ondas, monta as Ondas de todos os Projetos, para em \"Posso lançar?\" e, com o \"pode\", abre um Terminal por Projeto com a Onda dele. Funciona em qualquer pasta. Gatilhos: todas as issues, issues de todos os projetos, o que tem aberto em tudo, lança as ondas de tudo, /todas-issues. Sintaxe `/todas-issues [--ondas] [--atualizar]`."
---

# Todas as issues

Mostra numa tela só as issues abertas de todos os Projetos do Pedro e, com `--ondas`, lança as Ondas de todos de uma vez.

A lista vem do servidor do PedroOS (rota `/api/todas-issues`, que junta o Registro e o Coletor), nunca do `gh` repo por repo. O servidor grava a porta e o token em `~/.pedroos/sessao.json` quando sobe, e o script lê dali.

## Sintaxe

```
/todas-issues [--ondas] [--atualizar]
```

Sem argumento, vale a leitura que o PedroOS guardou nos últimos 5 minutos. Com `--atualizar`, o servidor lê o GitHub de novo (demora mais). Sem `--ondas`, a skill é **só leitura**: nada de claim, label, comentário ou merge.

## Fluxo da lista

1. Rode o script, de qualquer pasta, e mostre a saída **como veio**:

   ```bash
   python3 ~/.claude/skills/todas-issues/scripts/todas_issues.py [--atualizar]
   ```

2. Se o script disser que o PedroOS não está rodando (sai com código 2), repasse o aviso e **pare**. Não chame o `gh` em cada repo para compensar: a regra da skill é ler só do PedroOS.

3. Acrescente no máximo **duas linhas** suas, e só se mudarem a decisão (por exemplo: um Projeto que o GitHub não deixou ler, ou um PRD com fatias espalhadas em fases muito diferentes). Nada de recapitular a lista.

4. Pare.

## Fluxo das Ondas (`--ondas`)

1. Monte o plano e mostre a saída **como veio**:

   ```bash
   python3 ~/.claude/skills/todas-issues/scripts/todas_issues.py --plano [--atualizar]
   ```

   O script segue a regra da `montar-ondas-enxutas` com o que o PedroOS já leu: entra a issue `ready-for-agent` sem `in-progress` e sem PR (no Projeto com `designado_tira_da_fila`, o Hospital, o assignee é o dono do card e a Onda de quem roda pega só os cards designados a ele; card de outro dono ou sem dono fica fora), em ondas de até 3, `fatia:P` antes de `M` e `G`; o PRD fica fora (é PRD o pai de outra issue aberta ou o título que começa com "PRD"), porque fecha sozinho quando a última fatia fecha, e PRD ainda sem fatia pede `/to-issues` antes; a bloqueada entra no fim, para a `/onda-enxuta` puxar quando a bloqueadora fechar. Projeto sem issue apta não ganha Onda. O prompt de cada Projeto fica em `$TMPDIR/onda-enxuta/todas-issues/<repo>-onda1.md` (cada `--plano` apaga os do plano anterior, e o `--lancar` só acha o Projeto que tem Onda no último plano) e começa pelo comando `/onda-enxuta --sessao <projeto> --onda 1 --paralelo N`.

2. A saída termina em "Posso lançar?". **Pare ali e espere a resposta.** Sem o "pode", nada é lançado.

3. A resposta é texto livre: "pode", "vai", "sim", "lança" lançam todos; "só o Hospital" lança um; "não" encerra com o comando impresso. Com o sim, rode o comando que o plano imprimiu, só com os Projetos aprovados:

   ```bash
   python3 ~/.claude/skills/todas-issues/scripts/todas_issues.py --lancar <id> [<id> ...]
   ```

   Cada `id` vira um Terminal da Apple na pasta do Projeto (o mesmo caminho do botão Abrir terminal, pela rota `/api/ondas/terminal`), com o `claude` rodando a Onda daquele Projeto. A Onda grava o Estado da Onda e aparece na tela Ondas de todos do PedroOS.

4. Mostre as linhas `Terminal aberto` e pare. Quem roda, revisa e sobe é a `/onda-enxuta` em cada Terminal.

## O que a saída tem

- `## <Categoria>`: Pessoal, Vitta Tech, Globo e Outros, na ordem do `projetos/categorias.json` do PedroOS. Categoria sem nada para mostrar não aparece.
- `### <Projeto> (<repo>): N abertas`: os Projetos da Categoria na ordem da Ala Projetos (o de commit mais recente primeiro). Projeto sem issue aberta não aparece; Projeto que o GitHub não deixou ler aparece com o erro.
- Uma linha por issue: número, título, `[fase]` (a régua do Coletor), Responsável (o assignee; sem assignee, ninguém) e `PRD #N` quando a issue tem a seção Pai.
- No `--plano`, cada Projeto com Onda mostra a sessão, o `--paralelo`, as ondas, as bloqueadas, quantas ficam fora e o caminho do prompt.
