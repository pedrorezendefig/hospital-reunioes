# Prompts de disparo da /onda-enxuta

Use literalmente, preenchendo `<...>`. Cada agente já tem o contrato no próprio arquivo em `.claude/agents/`; o prompt só entrega os dados do caso. Quanto menos você escrever, menos o agente relê a cada turno.

**A primeira linha de todo prompt é `[papel: <nome>]`** (`mapeador`, `implementador`, `corretor`, `revisor`, `revisor-seguranca`, `auditor-prd`): é por ela que o `medir_onda.py` atribui o custo de cada sub-agente ao papel certo.

## hr-mapeador

```
[papel: mapeador]
PRD #<PRD>. Escreva o Mapa do terreno como comentário no PRD e devolva a URL.
Fatias abertas nesta sessão: #<a>, #<b>, #<c>.
```

## hr-implementador

```
[papel: implementador]
Issue #<N> do PRD #<PRD>. Mapa do terreno: <URL do comentário>.
Tentativa <k> de 3.
<Se houver decisão de triagem que o corpo não traz: uma linha.>
<Se a issue cria migration: "o número é <0XX>; a <0XX-1> já existe em origin/main".>
<Se não há PRD: "Sem Mapa: explore só o necessário e registre a receita do ambiente no relatório.">
```

## hr-revisor

```
[papel: revisor]
PR #<PR>, issue #<N>. Ache problemas, não aprove, não edite. Rodada <1|2>.
```

## hr-revisor-seguranca

```
[papel: revisor-seguranca]
PR #<PR>, issue #<N>. Motivo: <arquivos sensíveis tocados, um por linha | pedido do revisor padrão: "<motivo>">.
```

## hr-corretor / hr-corretor-max

```
[papel: corretor]
PR #<PR>, issue #<N>. Motivo: <revisao|ci|conflito|retomar>.
<revisao: cole o comentário do veredito inteiro. Se o "vai" do humano pré-autorizou should-fix: "Pré-autorizado pelo humano: corrija também <itens>.">
<ci: cole as últimas 60 linhas de `gh run view <id> --log-failed`.>
<conflito: "A main andou; rebase e resolva. Arquivos em conflito: <lista>.">
<retomar: "Branch <branch> tem commits wip. Termine a fatia e abra o PR.">
```

## hr-auditor-prd

```
[papel: auditor-prd]
PRD #<PRD>. Versão em produção: v<X.Y.Z>. Audite os critérios do PRD contra o app no ar e comente o veredito.
```

## Passagem (prompt da próxima sessão)

Salve em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md`. A primeira linha precisa ser o comando, para a skill disparar.

```
/onda-enxuta --sessao <nome> --onda <N+1> --paralelo <P>

## Passagem
Sessão <nome>, onda <N> fechada em <data hora>: v<antiga> -> v<nova>, PRs #a #b, build ok, health ok.
Ondas anteriores: <lista curta ou "nenhuma">.
Chave do semáforo: <nome>. Está solta.

Fila-alvo FIXA desta sessão (o que sobrou):
- Onda <N+1>: #d, #e
- Onda <N+2>: #f
Ordem obrigatória: <as mesmas regras do plano original>.
Não toque nas issues #.., #.. (outra sessão está rodando).

Mapas do terreno já escritos: PRD #<X> (<URL>).
Auditorias de PRD desta sessão: <quando #f fechar, audite o PRD #X>.
Decisões de triagem: <as mesmas linhas do plano original>.
Baixas até aqui (ready-for-human): <issue e motivo, ou "nenhuma">.
Prod hoje: v<nova>. Última migration em origin/main: <0XX>.
```

## Mensagem de checkpoint (fim do turno da sessão de fundo)

```
Onda <N> da sessão <nome> pronta para o seu OK.

| issue | PR | status | fatia | should-fix | migration |
| ... |

Para aprovar, num terminal:
  claude attach <id>
e escreva uma destas linhas:
  vai #a #b                        (mergeia e deploya o lote inteiro)
  vai #a                           (só um subconjunto)
  vai #a #b, corrigir o should-fix da #b e mergear se voltar limpo
  abortar
Migration <0XX> no lote: aplique no Studio antes do "vai".
```
