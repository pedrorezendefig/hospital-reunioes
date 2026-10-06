# Prompts de disparo da /onda-enxuta

Use literalmente, preenchendo `<...>`. Cada agente já tem o contrato no próprio arquivo em `.claude/agents/`; o prompt só entrega os dados do caso. Quanto menos você escrever, menos o agente relê a cada turno.

**A primeira linha de todo prompt é `[papel: <nome>]`** (`mapeador`, `implementador`, `corretor`, `revisor`, `revisor-seguranca`, `auditor-prd`): é por ela que o `medir_onda.py` atribui o custo de cada sub-agente ao papel certo.

## hr-mapeador

```
[papel: mapeador]
PRD #<PRD>. Escreva o Mapa do terreno como comentário no PRD e devolva a URL.
Fatias abertas nesta sessão: #<a>, #<b>, #<c>.
```

## hr-implementador / hr-implementador-xhigh

```
[papel: implementador]
Issue #<N> do PRD #<PRD>. Mapa do terreno: <URL do comentário>.
<Se a passagem traz o PRD em "Mergeado na onda anterior": "Mergeado na onda anterior: PRs #a #b.">
Tentativa <k> de 3.
<Se houver decisão de triagem que o corpo não traz: uma linha.>
<Se a issue cria migration: "o número é <0XX>; a <0XX-1> já existe em origin/main".>
<Se não há PRD: "Sem Mapa: explore só o necessário e registre a receita do ambiente no relatório.">
```

## hr-revisor

```
[papel: revisor]
PR #<PR>, issue #<N>. Ache problemas, não aprove, não edite. Revisão única: ninguém revisa a correção.
```

## hr-revisor-seguranca

```
[papel: revisor-seguranca]
PR #<PR>, issue #<N>. Motivo: <arquivos de rota sem login ou de migration tocados, um por linha>.
```

## hr-corretor / hr-corretor-max

```
[papel: corretor]
PR #<PR>, issue #<N>. Motivo: <revisao|ci|conflito|retomar>.
<revisao: cole o comentário do veredito inteiro.>
<ci: cole as últimas 60 linhas de `gh run view <id> --log-failed`.>
<conflito: "A main andou; rebase pela skill resolver-conflitos. Arquivos em conflito: <lista da linha do rabo>. Tentativa <k> de 3.">
<retomar: "Branch <branch> tem commits wip. Termine a fatia e abra o PR.">
```

## hr-auditor-prd

```
[papel: auditor-prd]
PRD #<PRD>. Versão em produção: v<X.Y.Z>. Audite os critérios do PRD contra o app no ar, passe a lente de segurança no diff acumulado dos PRs do PRD e comente o veredito.
```

Issue sem PRD, ou PR sem issue (o PR já em produção):

```
[papel: auditor-prd]
PR #<PR> (issue sem PRD). Versão em produção: v<X.Y.Z>. Passe só a lente de segurança no diff desse PR e comente o veredito no PR.
```

## Passagem (prompt da próxima sessão)

Salve em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md`. A primeira linha precisa ser o comando, para a skill disparar.

```
/onda-enxuta --sessao <nome> --onda <N+1> --paralelo <P>

## Passagem
Sessão <nome>, onda <N> com os PRs verdes em <data hora ISO>.
Em deploy: PRs #a #b (issues #x #y), versão esperada v<antiga> -> v<nova>, rabo na chave <nome>-onda<N>.
Ondas anteriores: <cada uma com os PRs e o estado deles no GitHub (mergeados ou abertos), ou "nenhuma">.

Fila-alvo FIXA desta sessão (o que sobrou):
- Onda <N+1>: #d, #e
- Onda <N+2>: #f, depois da #e
Dependências: <a de cada issue, como o plano original escreveu>. A onda é toda issue desta fila já desbloqueada, até o --paralelo.
Não toque nas issues #.., #.. (outra sessão está rodando).

Mapas do terreno já escritos: PRD #<X> (<URL>).
Mergeado na onda anterior: PRD #<X>: PRs #a #b.
Estrutura mudou: PRD #<X>: <sim|não>.
Auditorias de PRD desta sessão: <quando #f fechar, audite o PRD #X>.
Decisões de triagem: <as mesmas linhas do plano original>.
Baixas até aqui (ready-for-human): <issue e motivo, ou "nenhuma">.
Prod hoje: v<antiga>; a onda <N> leva a v<nova>. Última migration: <0XX>, contando a da onda em deploy.
```

A fila leva a dependência de cada issue ("#945, depois da #944"), nunca arquivo em comum: o único separador de ondas é a dependência (ADR 0066). A próxima sessão roda toda issue já desbloqueada (`blocked_by` todo fechado), mesmo a que está numa onda posterior da lista. `<P>` é o número de issues da fila desbloqueadas quando você escreve a passagem, com teto 3; bloqueio por issue da linha `Em deploy` não conta (passo 1 da skill).

A passagem sai com os PRs verdes, e a sessão que a escreve sobe a onda depois: `Em deploy` diz o que o rabo dela ainda leva à `main` e a versão que o `fechar_onda.py --dry-run` calculou. Fatia da fila bloqueada por uma das issues dessa linha fica na onda e espera a bloqueadora fechar (passo 3 da skill); as outras começam na hora, da `origin/main` do momento. A passagem é escrita uma vez só e não muda depois do lançamento: o que acontece com o rabo da onda <N> fica no comentário dela, e entre as duas sessões só existem o semáforo, que ordena os deploys (o rabo que quebrou deixa a trava parada e o seu sai com 8), e o GitHub, que diz o que está bloqueado (issue reaberta por rollback volta a bloquear as dependentes).

O Mapa do terreno é um por PRD e atravessa as ondas: a passagem leva o que mudou depois dele. A linha `Mergeado na onda anterior` acumula desde o Mapa: os PRs da passagem que você recebeu mais os da sua onda, que ainda estão em deploy quando a passagem sai (por isso o implementador confere em `origin/main`); Mapa refeito nesta sessão zera a conta.

`Estrutura mudou` é por PRD: `sim` quando algum PR mergeado na onda apagou ou renomeou arquivo que não é teste (`gh api --paginate repos/{owner}/{repo}/pulls/<PR>/files --jq '.[] | select(.status == "removed" or .status == "renamed") | .filename'`); arquivo novo ou editado é `não`, porque o implementador recebe a lista do `Mergeado na onda anterior` e confere o que ela tocou. Só `sim` faz a próxima sessão disparar o `hr-mapeador` (passo 2 da skill).
