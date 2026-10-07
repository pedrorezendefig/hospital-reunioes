# Prompts de disparo da /onda-enxuta

Use literalmente, preenchendo `<...>`. Cada agente já tem o contrato no próprio arquivo em `.claude/agents/`; o prompt só entrega os dados do caso. Quanto menos você escrever, menos o agente relê a cada turno.

**A primeira linha de todo prompt é `[papel: <nome>]`** (`implementador`, `corretor`, `revisor`): é por ela que o `medir_onda.py` atribui o custo de cada sub-agente ao papel certo.

## hr-implementador

```
[papel: implementador]
Issue #<N> do PRD #<PRD>.
Tentativa <k> de 3.
<Se houver decisão de triagem que o corpo não traz: uma linha.>
<Se a issue cria migration: "o número é <0XX>; a <0XX-1> já existe em origin/main".>
```

## hr-revisor

```
[papel: revisor]
PR #<PR>, issue #<N>. Ache problemas, não aprove, não edite. Revisão única: ninguém revisa a correção.
<Se o sensivel.py acusou: "Sensível: <arquivos de rota sem login ou de migration, um por linha>".>
```

## hr-corretor

```
[papel: corretor]
PR #<PR>, issue #<N>. Motivo: <revisao|ci|conflito|retomar>.
<revisao: cole o comentário do veredito inteiro.>
<ci: cole as últimas 60 linhas de `gh run view <id> --log-failed`.>
<conflito: "A main andou; rebase chamando a Skill tool com resolver-conflitos. Arquivos em conflito: <lista da linha da subida>. Tentativa <k> de 3.">
<retomar: "Branch <branch> tem commits wip. Termine a fatia e abra o PR.">
```

## Passagem (prompt da próxima sessão)

Salve em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md`. A primeira linha precisa ser o comando, para a skill disparar.

```
/onda-enxuta --sessao <nome> --onda <N+1> --paralelo <P>

## Passagem
Sessão <nome>, onda <N> com os PRs verdes em <data hora ISO>.
Em deploy: PRs #a #b (issues #x #y), versão esperada v<antiga> -> v<nova>, subida na chave <nome>-onda<N>.
Ondas anteriores: <cada uma com os PRs e o estado deles no GitHub (mergeados ou abertos), ou "nenhuma">.

Fila-alvo FIXA desta sessão (o que sobrou):
- Onda <N+1>: #d, #e
- Onda <N+2>: #f, depois da #e
Dependências: <a de cada issue, como o plano original escreveu>. A onda é toda issue desta fila já desbloqueada, até o --paralelo.
Não toque nas issues #.., #.. (outra sessão está rodando).

Decisões de triagem: <as mesmas linhas do plano original>.
Baixas até aqui (ready-for-human): <issue e motivo, ou "nenhuma">.
Prod hoje: v<antiga>; a onda <N> leva a v<nova>. Última migration: <0XX>, contando a da onda em deploy.
```

A fila leva a dependência de cada issue ("#945, depois da #944"), nunca arquivo em comum (ADR 0068). `<P>` é o número de issues da fila desbloqueadas, com teto 3. A passagem é escrita uma vez e não muda: o resultado da subida vai no comentário da onda.
