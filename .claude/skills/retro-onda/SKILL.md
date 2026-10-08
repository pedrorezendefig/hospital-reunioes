---
name: retro-onda
description: Retrospectiva de uma onda da /onda-enxuta. Lê o que a onda deixou (medição, baixas, correções, subida, JSONL) e propõe mudanças no ambiente dos agentes, não no código. Só propõe. Sintaxe `/retro-onda [<nome>-onda<N> | <id de sessão>]`.
disable-model-invocation: true
---

# Retro da onda

Olha para trás numa onda que já terminou e responde: **o que no ambiente deixou o atrito acontecer, e que mudança impede a repetição?** O produto é uma lista de candidatas, da mais grave para a menos, cada uma presa a um momento concreto da onda. Nada é editado aqui: a candidata aceita vira PR de ferramenta pelo `/ship`, com a decisão no corpo do PR (ADR 0068, regra 12).

Fork do `/retro` do Matt Pocock (Skills v1.3), com as fontes e as casas do Hospital. O princípio é o dele: **o padrão mora no revisor, não no implementador** (o implementador tem a pressão de contexto: explora, escreve, depura; o revisor recebe um diff). E **violação mecânica vira check determinístico**, nunca prosa: um check falha, uma frase em skill não.

## Sintaxe

```
/retro-onda [<nome>-onda<N> | <id de sessão>]
```

Sem argumento: a medição mais recente em `~/.claude/onda-enxuta/medicoes/`.

## Fontes, nesta ordem

1. **Medição:** `~/.claude/onda-enxuta/medicoes/<data>-<sessao>-onda<N>.json`. Os sinais: `github.<PR>.ci_falhas`, `revisoes` acima de 1, `por_papel.corretor` (agentes e custo), `contexto_max` acima de 150 mil, `minutos` fora do normal da sessão.
2. **GitHub:** o comentário `## Onda <nome> <N>` no PRD (linha da subida, baixas, linha `retro:`); as issues `ready-for-human` da onda (o comentário de baixa diz gate, achado e hipótese); os comentários do `hr-corretor` nos PRs (achado e commit); o veredito do `hr-revisor`; `docs/spec/deploy/history.json` (a entrada da versão, com `notes`).
3. **JSONL da sessão**, só onde a medição aponta: `~/.claude/projects/<slug>/<sessao>.jsonl` e `<sessao>/subagents/agent-*.jsonl`. Procure o trecho do atrito (a sequência de tool calls antes do erro, a busca longa, a releitura repetida), não a sessão inteira.

## Passos

1. Identifique a onda e leia a medição. Liste os **atritos**: baixa, rollback, conflito na subida, CI vermelho, corretor em `effort: max`, revisão com must-fix, busca longa, contexto alto. Sem atrito, diga que a onda não ensina e pare.
2. Para cada atrito, ache o **momento**: PR, issue, arquivo, trecho do JSONL. Candidata que não aponta para um momento é descartada: conselho genérico para preencher categoria não entra.
3. Classifique e dê a casa:

| Atrito | Casa da mudança |
|---|---|
| Agente demorou a achar arquivo ou fato; dependência escondida entre arquivos | **Ponteiro de navegação** no arquivo que ele já lê (`CLAUDE.md`, a skill, o agente `hr-*`), uma linha |
| Erro que um check pegaria (padrão fixo, API proibida, forma de import, lugar do arquivo, travessão) | **Check** no CI (`.github/workflows/`), regra de `ruff`/ESLint, `lint-adr`, grep de template; gatilho de segurança em `sensivel.py` ou `revisao-sensivel.txt` |
| Revisor deixou passar um juízo (consistência entre arquivos, "parece com o resto", teste vácuo de forma nova) | **Lente** no `hr-revisor.md`, só must-fix, nunca no `hr-implementador` |
| Instrução sem efeito, ou regra que o script já cumpre | **Apagar** (cada regra tem uma casa: script ou skill, nunca as duas) |
| Tool call cara (colagem de log inteiro, releitura de PRD, suíte inteira em vez do arquivo) | **Prompt menor**, ponteiro em vez de colagem, script que resume |
| Informação que o agente não alcançou (log do deploy, estado de outra sessão, decisão só no prompt) | **Acesso**: campo no prompt de disparo, consulta `gh` pronta, log acessível |
| Repo sem guarda-corpo para aquele erro (nenhum check, nenhuma lente) | Achado por si só, com o check mais barato na linguagem do repo |

4. Antes de propor check novo, leia o que já existe (`.github/workflows/`, `pyproject.toml`, ESLint do frontend): check que existe e não está ligado é a candidata, não um check novo.
5. Apresente até 7 candidatas, da mais grave para a menos: **atrito** (momento: PR/issue/trecho), **causa no ambiente**, **mudança** (arquivo e uma linha do que entra ou sai), **tipo** (check, lente, ponteiro, apagar, prompt, acesso). Termine com a linha "nenhuma mudança feita; cada candidata aceita vira `/ship` próprio".

## O que esta skill não faz

- Não edita arquivo, não abre PR, não instala hook. Só propõe; quem escolhe é o humano.
- Não revisa o código da onda (isso é o `hr-revisor`) nem a arquitetura (isso é o `/improve-codebase-architecture`).
- Não é memória: não guarda o que aconteceu, muda o ambiente para não acontecer de novo. Achado que é só "lembrar da próxima vez" vai para a seção 10 do `docs/onboarding/claude-setup.md`, não para esta lista.
- Não audita checks antigos: vê uma onda só. Check que dispara em código bom é sinal para remover, mas isso quem vê é quem roda o CI todo dia.
