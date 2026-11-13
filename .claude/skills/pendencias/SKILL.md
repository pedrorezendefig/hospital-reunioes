---
name: pendencias
description: "Varre todos os repositórios de ~/PedroDev de uma vez: mudanças pendentes, commits que não subiram, branches fora da main e PRs abertos. Resume o que é cada coisa, por repositório, e sugere o que fazer (subir com PR e merge, mergear o PR que já existe, esperar, ignorar ou descartar). Para em \"Posso seguir?\" e só age com o \"pode\". Funciona em qualquer pasta. Gatilhos: /pendencias, o que tá pendente, mudanças pendentes, o que falta subir, commits parados, faz o merge do que tá pronto, limpa os repositórios. Sintaxe `/pendencias [Pasta ...] [--sem-fetch]`."
---

# Pendências

Mostra o que está parado em cada repositório de `~/PedroDev`, diz o que é cada coisa e sugere o merge certo. Até o "pode", é **só leitura**.

## Sintaxe

```
/pendencias                    todos os repositórios
/pendencias OS Hospital        só essas pastas de ~/PedroDev
/pendencias --sem-fetch        sem git fetch (mais rápido)
```

## Passo 1: ler

```bash
python3 ~/.claude/skills/pendencias/scripts/pendencias.py [Pasta ...] [--sem-fetch]
```

O script faz `git fetch` e mostra, por repositório: branch, mudanças pendentes (com a idade do arquivo mais novo), commits que não subiram, commits da branch fora da main, PR aberto da branch, branches locais velhas e as linhas `velha?` e `conflito?`. Velha quer dizer: a mudança mais antiga tem mais de 7 dias, ou a main recebeu commits depois dela. Conflito quer dizer: juntar o que está ali (commits e arquivos mexidos) com a main dá conflito nos arquivos listados. O script simula o merge sem mexer em arquivo, índice ou branch; "não deu para simular" aparece com git anterior ao 2.38. Não mostre a saída crua para o Pedro; ela é a sua matéria-prima.

## Passo 2: entender cada pendência

Para cada repositório com algo, descubra **o que é** a mudança. Leia o mínimo:

- `git -C <pasta> diff --stat` e depois `git -C <pasta> diff -- <arquivo>` nos arquivos que importam (corte em ~200 linhas por arquivo).
- Arquivo novo: olhe o nome e as primeiras linhas.
- Commit parado: `git -C <pasta> show --stat <sha>`.
- PR aberto: `gh pr view <n> -R <repo> --json title,body,statusCheckRollup,mergeable`.

Com 4 ou mais repositórios com diff grande, dispare um agente `Explore` por repositório, em paralelo, e peça de volta 2 linhas: o que é e se parece completo.

### Um assunto, vários repositórios

A mesma mudança aparece em mais de um repositório quando vem de uma fonte comum. Junte numa linha só: mesmo assunto e mesma lista de arquivos (ou quase) é uma linha da tabela, com os repositórios dentro dela. O Pedro lê uma vez e responde uma vez.

O caso mais comum é o **Pacote do fluxo**: arquivos em `.claude/skills/` e `.claude/agents/` de um Projeto que tem `.claude/fluxo.json`. Eles vêm do PedroOS pelo instalador (ADR 0007 do PedroOS) e ninguém escreve neles à mão. Para saber se a cópia de um repositório é a versão atual:

```bash
git -C ~/PedroDev/OS pull --ff-only     # a fonte em dia; pule se o OS tem mudança pendente
~/PedroDev/OS/scripts/instalar-skills.sh --conferir --projeto <nome>
```

O `<nome>` é o de `~/PedroDev/OS/projetos/<nome>.json`. Nada impresso: a cópia é a versão atual, e a mudança vai para a caixa Pronta. Linha impressa: a cópia já está atrás da fonte. Diga quais skills, e a sugestão é rodar o instalador sem `--conferir` para aquele Projeto e depois subir.

Classifique cada pendência numa destas caixas:

| Caixa | Sinal | Sugestão |
|---|---|---|
| **Em uso** | arquivo mexido há menos de 15 min (o script marca "ATENÇÃO") ou é a pasta desta sessão com trabalho dela | Não mexer. Esperar. |
| **Pronta** | mudança coerente e completa, de um assunto só, com `conflito? não` | Subir: branch, commit, PR, merge. |
| **Com conflito** | `conflito? sim` | Esperar. Dizer os arquivos. A `/resolver-conflitos` só com o Pedro pedindo. |
| **PR pronto** | PR aberto, `mergeable=MERGEABLE`, estado `CLEAN` | Mergear o PR. |
| **Meio feita** | `wip`, código pela metade, teste quebrado, mistura de assuntos | Esperar. Dizer o que falta. |
| **Lixo** | build (`dist/`, `.astro/`, `.vercel/`), prints do `.playwright-cli/`, `.bak`, planilha solta na raiz | Pôr no `.gitignore` ou apagar. Nunca commitar. |
| **Dado pessoal** | arquivo de finanças, vault, planilha de cliente | Não subir sem o Pedro dizer. |
| **Branch velha** | branch local sem PR, sem commit há mais de 7 dias, ou com o remoto apagado | Só listar o número. Faxina é a Ala Faxina do PedroOS. |

Branch com o remoto apagado quase sempre é PR já mergeado por squash. Não sugira merge dela.

### Relação: o que essa mudança tem a ver com o que já subiu

Para cada pendência das caixas Pronta, PR pronto e Meio feita, leia o **assunto** dela (nome dos arquivos, o diff, a mensagem do commit) e procure se o Pedro já mexeu nesse assunto em outro lugar:

- na main do mesmo repositório: `git -C <pasta> log origin/main --since=<início da mudança> --oneline -- <arquivos>` e `git -C <pasta> log origin/main -i --grep=<palavra do assunto> --oneline -n 10`;
- nos PRs: `gh pr list -R <repo> --state all --search "<palavra do assunto>" --limit 10 --json number,title,state,mergedAt`;
- nos outros repositórios de `~/PedroDev`, quando o assunto é compartilhado (skill, fluxo, `.claude/`): `git -C ~/PedroDev/<outro> log origin/main -i --grep=<palavra> --oneline -n 5`.

Para conferir se o diff já está na main: `git -C <pasta> diff origin/main -- <arquivo>` vazio quer dizer que a mudança já subiu.

Responda com uma destas quatro:

| Relação | Quando | Sugestão |
|---|---|---|
| **nada parecido** | nenhum commit nem PR sobre o assunto depois dela | segue a caixa |
| **já subiu em X** | o mesmo conteúdo já está na main (diff vazio ou PR mergeado igual) | Descartar. Só com o "apaga" do Pedro. |
| **superada por X** | a main ou um PR mergeado resolveu o mesmo assunto de outro jeito | Comparar antes. Dizer em uma linha o que a pendência tem a mais. |
| **completa X** | um PR aberto ou commit recente é do mesmo assunto e esta mudança é a parte que falta | Subir junto, no mesmo PR ou logo depois. |

X é o PR (`#123`) ou o commit (`abc1234`) que você achou. Sem evidência, a resposta é "nada parecido": não chute relação.

## Passo 3: mostrar o plano

Uma tabela, um assunto por linha (vários repositórios na mesma linha quando é o mesmo assunto), na ordem: o que sobe agora primeiro, depois o que espera, depois o lixo.

A coluna **Sobe agora?** diz "sim" só quando as três coisas valem: caixa Pronta ou PR pronto, `conflito? não` e relação "nada parecido" ou "completa X". Nos outros casos diz "não" e a Sugestão diz o motivo.

```
| Assunto | Onde | Velha? | Conflito? | Relação | Sobe agora? | Sugestão |
|---|---|---|---|---|---|---|
| Pacote do fluxo (lentes da revisão, painel de voz) | Ana, Diduccio, IAE | não | não | nada parecido | sim | Subir um PR em cada |
| PR #29 glossário, verde | Diduccio | não | não | nada parecido | sim | Mergear o PR #29 |
| botões "abrir todos" nas Alas (7 arquivos, mexido há 37 min) | OS | não | não | nada parecido | não | Esperar: em uso |
| ADR 0073 de contas médicas, 1 commit | Hospital | sim, 10 dias e main andou 217 | sim, 3 arquivos | superada por #1290 | não | Comparar antes: a ADR tem a regra de quem analisa |
| carimbo de dados + nota de finanças + planilha IBMS solta | Pedro | sim, 11 dias | não | já subiu em 147fa6c (carimbo) | não | Descartar o carimbo; nota fica; planilha fora |
```

Depois da tabela, no máximo 3 linhas: os riscos que mudam a decisão (por exemplo, branch 127 commits atrás da main, que vai dar conflito). Repositório limpo: uma linha só com os nomes.

Termine com a pergunta **"Posso seguir?"** e pare. Sem o "pode", nada é feito.

## Passo 4: com o "pode"

A resposta é texto livre: "pode" faz tudo o que a tabela sugeriu; "só o Diduccio" faz um; "não" encerra.

Antes de mexer num repositório, leia o `CLAUDE.md` dele. Se ele tem `.claude/skills/ship/SKILL.md`, siga as regras da `/ship` dele (nome da branch, tipo de commit, gates). Senão, o caminho padrão:

**Subir mudança pendente que está na main:**

```bash
cd ~/PedroDev/<Pasta>
git switch -c <tipo>/<assunto-curto>
git add <só os arquivos da caixa Pronta>      # nunca git add -A
git commit -m "<tipo>: <o que muda>"           # com as linhas de atribuição da sessão
git push -u origin HEAD
gh pr create --fill                            # corpo passa pelo humanizer
gh pr checks --watch                           # espera o CI
gh pr merge --squash --delete-branch
git switch main && git pull --ff-only
```

**Mergear PR aberto:** `gh pr checks <n> -R <repo>` verde, depois `gh pr merge <n> -R <repo> --squash --delete-branch`. Se o clone local estava na branch do PR e não tem mudança pendente, volte para a main e `git pull --ff-only`. Com mudança pendente na branch, deixe o clone onde está e avise.

**Commit parado sem PR:** `git push -u origin HEAD`, `gh pr create --fill`, e segue igual.

**Lixo:** acrescente a pasta no `.gitignore` e suba isso como `chore`. Só apague arquivo com o Pedro dizendo "apaga".

## Regras

- Nunca `git push --force`, `git reset --hard`, `git checkout -- <arquivo>`, `git clean` ou `git stash drop`.
- Nunca mexa num repositório marcado "Em uso".
- CI vermelho ou conflito: pare aquele repositório, diga o motivo em uma linha e siga com os outros. Conflito com a main: a skill `/resolver-conflitos`, só se o Pedro pedir.
- Um assunto por PR. Mudança que mistura dois assuntos vira dois PRs ou espera.
- Sem travessão em commit, PR ou resposta.

## Passo 5: fechar

Uma linha por repositório: o que foi feito e o link do PR. Depois, numa linha, o que ficou esperando e por quê.
