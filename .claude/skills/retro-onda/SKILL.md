---
name: retro-onda
description: 'Retrospectiva de uma onda da /onda-enxuta. Lê o que a onda deixou (medição, baixas, correções, subida, JSONL) e propõe mudanças no ambiente dos agentes, não no código. Grava a Retro com as Candidatas aceitas e imprime a linha `Candidata:` de cada uma. Com `--todas`, a Análise das Retros: todas as Retros pendentes de uma vez, uma Candidata comum por causa. Sintaxe `/retro-onda [<nome>-onda<N> | <id de sessão> | --todas]`.'
disable-model-invocation: true
---

# Retro da onda

Olha para trás numa onda que já terminou e responde: **o que no ambiente deixou o atrito acontecer, e que mudança impede a repetição?** O produto é uma lista de candidatas, da mais grave para a menos, cada uma presa a um momento concreto da onda. Aqui só a Retro é gravada, no Estado da Onda: a candidata aceita vira PR de ferramenta pelo `/ship`, com a decisão e a linha `Candidata:` no corpo do PR (decisão do fluxo, regra 12).

Fork do `/retro` do Matt Pocock (Skills v1.3), com as fontes e as casas do pacote do fluxo (a mesma em todo Projeto; as regras só de um Projeto estão em `fluxo.py notas retro-onda`). O princípio é o dele: **o padrão mora no revisor, não no implementador** (o implementador tem a pressão de contexto: explora, escreve, depura; o revisor recebe um diff). E **violação mecânica vira check determinístico**, nunca prosa: um check falha, uma frase em skill não.

## Sintaxe

```
/retro-onda [<nome>-onda<N> | <id de sessão> | --todas]
```

Sem argumento: a medição mais recente em `~/.claude/onda-enxuta/medicoes/`. Com `--todas`: a Análise das Retros (seção própria abaixo), no lugar das Fontes e dos Passos.

## Fontes, nesta ordem

1. **Medição:** `~/.claude/onda-enxuta/medicoes/<data>-<sessao>-onda<N>.json`. Os sinais: `github.<PR>.ci_falhas`, `revisoes` acima de 1, `por_papel.corretor` (agentes e custo), `contexto_max` acima de 150 mil, `minutos` fora do normal da sessão.
2. **GitHub:** o comentário `## Onda <nome> <N>` no PRD (linha da subida, baixas, linha `retro:`); as issues `ready-for-human` da onda (o comentário de baixa diz gate, achado e hipótese); os comentários do `onda-corretor` nos PRs (achado e commit); o veredito do `onda-revisor`; `docs/spec/deploy/history.json` (a entrada da versão, com `notes`).
3. **JSONL da sessão**, só onde a medição aponta: `~/.claude/projects/<slug>/<sessao>.jsonl` e `<sessao>/subagents/agent-*.jsonl`. Procure o trecho do atrito (a sequência de tool calls antes do erro, a busca longa, a releitura repetida), não a sessão inteira.

## Passos

1. Identifique a onda e leia a medição. Liste os **atritos**: baixa, rollback, conflito na subida, CI vermelho, corretor em `effort: max`, revisão com must-fix, busca longa, contexto alto. Sem atrito, diga que a onda não ensina e pare.
2. Para cada atrito, ache o **momento**: PR, issue, arquivo, trecho do JSONL. Candidata que não aponta para um momento é descartada: conselho genérico para preencher categoria não entra.
3. Classifique e dê a casa:

| Atrito | Casa da mudança |
|---|---|
| Agente demorou a achar arquivo ou fato; dependência escondida entre arquivos | **Ponteiro de navegação** no arquivo que ele já lê (`CLAUDE.md`, a skill, o agente `onda-*`), uma linha |
| Erro que um check pegaria (padrão fixo, API proibida, forma de import, lugar do arquivo, travessão) | **Check** no CI (`.github/workflows/`), regra de lint, grep de template; gatilho de segurança em `sensivel.py` ou `revisao-sensivel.txt` |
| Revisor deixou passar um juízo (consistência entre arquivos, "parece com o resto", teste vácuo de forma nova) | **Lente** no `onda-revisor.md`, só must-fix, nunca no `onda-implementador` |
| Instrução sem efeito, ou regra que o script já cumpre | **Apagar** (cada regra tem uma casa: script ou skill, nunca as duas) |
| Tool call cara (colagem de log inteiro, releitura de PRD, suíte inteira em vez do arquivo) | **Prompt menor**, ponteiro em vez de colagem, script que resume |
| Informação que o agente não alcançou (log do deploy, estado de outra sessão, decisão só no prompt) | **Acesso**: campo no prompt de disparo, consulta `gh` pronta, log acessível |
| Repo sem guarda-corpo para aquele erro (nenhum check, nenhuma lente) | Achado por si só, com o check mais barato na linguagem do repo |

4. Antes de propor check novo, leia o que já existe (`.github/workflows/`, `tools/lint_skills.py`, o lint da pasta do app (`app` no `fluxo.py`) quando existir): check que existe e não está ligado é a candidata, não um check novo.
5. Apresente até 7 candidatas, numeradas de 1 em diante, da mais grave para a menos: **atrito** (momento: PR/issue/trecho), **causa no ambiente**, **mudança** (arquivo e uma linha do que entra ou sai), **tipo** (check, lente, ponteiro, apagar, prompt, acesso).
6. Pergunte quais Candidatas o humano (o `humano` do `fluxo.py`) aceita, pelos números. Com a resposta, grave a Retro da raiz do Projeto da onda, com a `<sessao>` e o `<N>` da medição:

   ```bash
   python3 .claude/skills/onda-enxuta/scripts/estado_onda.py retro --sessao <sessao> --onda <N> --candidata <n> "<título>"
   ```

   Um `--candidata <n> "<título>"` por aceita: o número dela na lista e o título curto. Com nenhuma aceita a Retro também está feita: rode sem `--candidata`. Rodar de novo substitui o que estava gravado.
7. Para cada aceita, imprima uma linha neste formato fixo:

   ```
   Candidata: <slug>/<sessao>-onda<N> #<n>
   ```

   `<slug>` é o `slug` do `fluxo.py`, `<sessao>-onda<N>` é a onda desta Retro e `<n>` é o número da Candidata. A linha vai como está no pedido do `/ship` da correção, e o PR que entra na main com ela dá a Candidata por corrigida. Termine com a linha "só a Retro foi gravada; cada Candidata aceita vira `/ship` próprio, com a linha `Candidata:` no pedido".

## Modo --todas: a Análise das Retros

Todas as Retros pendentes, de todos os Projetos, de uma vez. O humano aceita as Candidatas uma vez só, e cada Onda fica com a Retro gravada com as Candidatas da causa dela. A tabela de casas, o "momento concreto" e o check antes do check novo valem como nos Passos.

1. **Liste as Retros pendentes** (linha `retro:` "recomendada" e nada gravado), de todos os Projetos, nos Estados da Onda em `~/.pedroos/ondas/`:

   ```bash
   jq -r 'select(.contrato == 1 and .registro_retro == null and ((.retro // "") | test("^(retro:\\s*)?recomendada"; "i"))) | [.slug, .id, .sessao, .onda, .repo, .prd, .pasta, .retro] | @tsv' "${PEDROOS_ONDAS:-$HOME/.pedroos/ondas}"/*/*.json
   ```

   Sem nenhuma, diga que não há Retro pendente e pare.
2. **Leia o atrito de cada uma**: a linha `retro:` (o motivo entre parênteses) e o comentário `## Onda <sessao> <N>` no PRD da Onda (`gh issue view <prd> --repo <repo> --comments`: subida, baixas, erros). A medição e o JSONL só onde a causa não fecha com isso.
3. **Agrupe por causa no ambiente**, não por sintoma: o mesmo Teste instável em três Projetos é uma causa só. Onda sem atrito que ensine (a pendência acabou fora da Onda, erro de rede, nada a mudar no ambiente) não entra em causa nenhuma.
4. **Delegue a investigação de cada causa grande** (a que pega 3 Ondas ou mais) a um subagente, um por causa e em paralelo: ele recebe as Ondas da causa e devolve o momento concreto, a casa e a mudança, em até 10 linhas. Causa pequena você mesmo investiga.
5. **Apresente uma Candidata por causa**, numeradas de 1 em diante, da que pega mais Ondas para a que pega menos: **causa**, quantas Ondas ela pegou e quais (`<slug>/<sessao>-onda<N>`), **mudança** (arquivo e uma linha) e **tipo**. No fim, as Ondas sem Candidata, com o porquê numa linha. Dê o id da Análise: `analise-<AAAA-MM-DD>` com a data de hoje (se o id já aparece em algum Estado da Onda, acrescente `-2`, `-3`).
6. **Pergunte quais Candidatas o humano aceita, pelos números.** Só grave depois da resposta.
7. **Grave a Retro de toda Onda da lista**, na raiz do clone do Projeto dela (a `pasta` sem o trecho `/.claude/worktrees/...`), com as Candidatas aceitas da causa dela, cada uma com o número da lista:

   ```bash
   python3 .claude/skills/onda-enxuta/scripts/estado_onda.py retro --sessao <sessao> --onda <N> --analise <id> --candidata <n> "<título>"
   ```

   Onda sem Candidata aceita (a causa dela foi recusada, ou ela não tinha atrito que ensine) também tem a Retro gravada: rode sem `--candidata`. Se o script do Projeto não conhece o `--analise`, o pacote do fluxo daquele Projeto está velho: sincronize (`scripts/instalar-skills.sh` do PedroOS) e rode de novo.
8. Para cada aceita, imprima a linha da Candidata comum, uma só para todas as Ondas que ela cobre:

   ```
   Candidata: <id> #<n>
   ```

   `<id>` é o id da Análise e `<n>`, o número da Candidata. O PR que entra na main com essa linha dá a Candidata por corrigida em todas as Ondas que a têm. Termine com a linha "só as Retros foram gravadas; cada Candidata aceita vira `/ship` próprio, com a linha `Candidata:` no pedido".

## O que esta skill não faz

- Grava só a Retro (`estado_onda.py retro`): não edita arquivo de código, não abre PR, não instala hook. Quem escolhe as Candidatas é o humano.
- Não revisa o código da onda (isso é o `onda-revisor`) nem a arquitetura (isso é o `/improve-codebase-architecture`).
- Não é memória: não guarda o que aconteceu, muda o ambiente para não acontecer de novo. Achado que é só "lembrar da próxima vez" não entra nesta lista.
- Não audita checks antigos: vê uma onda só. Check que dispara em código bom é sinal para remover, mas isso quem vê é quem roda o CI todo dia.
