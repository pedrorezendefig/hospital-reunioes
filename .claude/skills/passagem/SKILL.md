---
name: passagem
description: Compacta a conversa atual num documento de passagem (handoff) que outra sessão Claude com janela fresca consegue pegar e continuar de onde parou. Use quando o trabalho precisa migrar de sessão por contexto cheio ("passagem", "tô estourando contexto", "passa pro próximo Claude"), ou quando o usuário quer registrar o estado para retomar depois ("salva onde paramos", "quero retomar amanhã numa janela limpa"). Salva no diretório temporário do OS (não no workspace), redige info sensível e referencia artefatos existentes por path em vez de duplicar. Com `--bg`, dispara a sessão de continuação em background automaticamente.
argument-hint: No que a próxima sessão vai focar?
---

# passagem

Escreva um documento de passagem que resume a conversa atual pra que um agente novo (sessão Claude com janela fresca) consiga continuar o trabalho sem repetir descoberta.

## Onde salvar

Salve no **diretório temporário do OS do usuário**, não no workspace atual. Em macOS/Linux use `$TMPDIR` ou `/tmp`; em Windows use `%TEMP%`. Nome do arquivo: `passagem-<YYYY-MM-DD-HHMM>-<slug-curto>.md`.

Por quê: o documento é descartável e específico desta sessão. Não polui o repositório nem entra acidentalmente num commit.

Ao terminar, imprima o **caminho absoluto** do arquivo gerado pra que o usuário possa copiar e colar na próxima sessão (`leia <path>`).

## O que entra no documento

Estruture com estas seções (omita as que não se aplicarem):

```markdown
# Passagem — <título curto>

**Data:** <ISO-8601>
**Sessão originada em:** <cwd / projeto>
**Foco da próxima sessão:** <argumento do usuário, se houver>

## Objetivo
[1-3 frases: o que estávamos tentando fazer]

## Estado atual
[onde paramos: branch, working tree, último teste rodado, último erro]

## Decisões tomadas
[escolhas feitas nessa sessão que a próxima precisa respeitar — não re-litigue]

## Próximos passos
[checklist objetivo do que falta]

## Artefatos referenciados
[paths/URLs dos arquivos que importam, NÃO duplique conteúdo]
- issue #N / PRD #M no GitHub: spec e critérios de aceite
- `<path>:<linha>`: local exato de mudança em andamento
- PR #N, commit <sha>, ADR relevante

## Armadilhas conhecidas
[becos sem saída que já testamos, suposições erradas que já caíram]

## Skills sugeridas
[skills que a próxima sessão deve invocar pra retomar]
- `/pegar-issue <N>` se a próxima sessão continua uma fatia da fila
- `/tdd` se há testes RED pendentes ou implementação em andamento
- `/diagnose` se a próxima fase é debugging
- `/onda` se a fila ready-for-agent deve rodar em modo AFK
- outras conforme contexto
```

## Princípios

**Não duplique artefatos.** Se a conversa já gerou um PRD ou issue no GitHub, um PR, um commit, um diff, um ADR: referencie por path ou URL. Repetir conteúdo gera divergência: a fonte da verdade evolui, o resumo apodrece.

**Redija informação sensível.** Nunca escreva chaves de API, senhas, tokens, secrets, PII (nomes, emails, telefones, CPFs) no documento. Se precisar mencionar que existe uma credencial, escreva `<REDACTED>` ou `<API_KEY_DA_INTEGRACAO_X>` indicando o papel sem revelar o valor. O arquivo vai pro tmp do OS mas pode ser copiado pra qualquer lugar depois.

**Capture o "porquê", não o "o quê".** O código e os commits já dizem o que mudou. O documento de passagem precisa dizer por que escolhemos um caminho, que alternativas descartamos, que hipóteses ainda não validamos. Esse é o conhecimento que se perde quando a sessão fecha.

**Argumentos do usuário viram foco.** Se o usuário invocou com argumento (ex: "/passagem amanhã quero focar no fix do bug X"), use isso pra calibrar o nível de detalhe: o que é relevante pro foco vai pro topo, o resto pode ser sucinto ou omitido.

**Seja conciso.** Um bom documento de passagem cabe em 1 tela. Listas curtas, paths exatos, decisões em uma frase. Se tá ficando longo, é sinal de que você tá duplicando conteúdo que já existe em outro artefato — referencie e corte.

## Modo --bg (opcional)

Se o usuário invocar com `--bg` (ex.: `/passagem --bg amanhã foco no bug X`), depois de salvar o documento dispare a sessão de continuação em background:

```bash
claude --bg --name '<slug-curto>' 'leia <path absoluto do documento> e continue de onde parou'
```

Antes de disparar, redobre a checagem de informação sensível no documento: a sessão de background vai ler o arquivo inteiro sem supervisão humana. O default (sem `--bg`) fica intacto: só salvar e imprimir o path.

## Formato de saída no chat

Depois de escrever o arquivo, responda no chat só com:

```
Passagem salva em: <path absoluto>

Para retomar numa sessão nova:
  leia <path absoluto>
```

Se rodou com `--bg`, acrescente uma linha: `Sessão de continuação disparada em background: <slug>`.

Sem resumo da passagem inline (o usuário acabou de viver a conversa, não precisa relê-la). O valor está no arquivo persistido.
