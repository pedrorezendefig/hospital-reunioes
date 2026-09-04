---
name: setup-maquina
description: Diagnostica a máquina de quem clonou (clone atualizado, binários, gh, plugins, Coolify, tokens), diz o que falta e de onde vem cada chave, e explica cada pasta do repo (README.md). Sintaxe `/setup-maquina [--nivel N] [--env] [--mapa]`.
---

# Setup de máquina nova

Quem clona o repositório precisa de pouca coisa para trabalhar no pipeline (planejar, desenvolver, abrir PR, mergear, subir para produção). O app **não** roda na máquina de quem desenvolve: sobe para produção e se testa lá. Esta skill diz, em uma tabela, o que já está pronto, o que falta e de onde vem cada chave.

## Níveis

| Nível | Para quê | O que exige |
|---|---|---|
| 1 Pipeline | `/grill-with-docs`, `/to-prd`, `/to-issues`, `/pegar-issue`, `/ship` até o PR | clone com a `main` igual à `origin/main`, git, gh autenticado com WRITE, jq, Claude Code, os plugins de `references/plugins.txt`, `git config user.*` |
| 2 Deploy e testes | `/tdd` (pytest e ruff do backend), `/ship` com merge e deploy, `/deploy`, `/onda` | CLI do Coolify com contexto `hsm`, `tokens/.env`, python3 3.9+, uv + `.venv` do backend, Pango, `hospital-reunioes/.env` com três valores fictícios (o snapshot importa o app) |
| 3 App local | `/atualizar-app`, `vitest` e `tsc` do frontend na máquina | Docker, Supabase CLI, Node, corepack com pnpm 9, chaves de sandbox. **Opcional: hoje ninguém usa; teste de frontend confia no CI.** |
| 4 Divulgar | `/divulgar` | ffmpeg, Chrome, skills globais de HyperFrames, time da Vercel. **Opcional.** |

O padrão é conferir os níveis 1 e 2. `--nivel 3` ou `--nivel 4` acrescenta os opcionais.

## Como rodar

```bash
bash .claude/skills/setup-maquina/scripts/diagnostico.sh            # níveis 1 e 2
bash .claude/skills/setup-maquina/scripts/diagnostico.sh --nivel 4  # tudo
```

Saída: uma linha por checagem, com `OK`, `FALTA` (conta e dá exit 1), `AVISO` (não conta) ou `OPC` (opcional ausente, não conta), e o comando de conserto ao lado. **O script nunca imprime valor de chave**, só o nome e se está preenchida. O script recebe só `--nivel`; `--env` é modo desta skill (item 4 abaixo) e não vai para o script.

## O que fazer com o resultado

1. Rode o script e mostre a tabela ao usuário.
2. Para cada `FALTA`, execute o conserto indicado **um por vez, com confirmação**, nunca com `sudo`. Clone atrasado é `git pull --ff-only origin main` na `main` (se a árvore tiver mudança não commitada, avise e não puxe). Instalação de binário é `brew install`; plugin é `claude plugin install`; token é humano. O `hospital-reunioes/.env` é só três valores fictícios: o comando do script cria, sem chave real e sem 1Password.
3. Para chave de `.env`, consulte `references/chaves.md`: a tabela diz o nível, se a chave é por pessoa ou compartilhada, e o item do 1Password (cofre `VITTA TECH`) onde ela vive. Chave que só o Pedro tem vira a frase "peça ao Pedro: `NOME_DA_CHAVE`, serve para X".
4. Com `--env`, gere os arquivos que faltam a partir dos `.env.example`:
   - `tokens/.env`: `COOLIFY_ACCESS_TOKEN` é por pessoa (gerado no painel do Coolify, conta criada pelo Pedro); `ANA_API_KEY` vem do 1Password; `GITHUB_PERSONAL_ACCESS_TOKEN` só se for usar Actions locais.
   - `hospital-reunioes/.env`: o script já dá o comando que cria o arquivo com os três valores fictícios. Chave real só entra se o usuário for rodar o app local (nível 3).
   - O humano abre o 1Password e copia o valor à mão. A skill diz só o item e o campo. Nunca use a CLI do 1Password nem peça o valor no chat.
   - Nunca sobrescreva um `.env` existente: escreva `.env.novo` ao lado e mostre a diferença de chaves.
   - Depois de gravar, rode `git check-ignore -q <arquivo>` em cada um. Se algum não estiver ignorado, pare e avise.
5. Feche com a lista do que ficou pendente de humano (conta no Coolify, acesso ao cofre).

## O que esta skill nunca faz

- Nunca imprime, ecoa ou cola valor de segredo, nem em log.
- Nunca commita `.env`, `tokens/.env` ou `~/.claude/settings.json`.
- Nunca toca produção: zero `coolify deploy`, zero migration, zero escrita de env no Coolify.
- Nunca instala sem confirmação e nunca usa `sudo`.
- Nunca acessa o 1Password (nem `op`, nem pedir o valor no chat). Quem copia a chave é o humano.

## Explicar o repositório (`/setup-maquina --mapa`, ou qualquer pergunta "o que é a pasta X")

Leia o `README.md` da raiz (ADR 0046): cada pasta com o que é, por que existe, o que tem dentro e para que serve; onde as chaves de produção moram (Coolify); e, em `references/chaves.md`, como o sócio se conecta a cada serviço (GitHub, Coolify, Supabase, Resend, ClickSign, OpenRouter, Vercel, 1Password). Antes de responder sobre uma pasta, rode `ls` nela: o disco manda, o mapa explica. O script já avisa quando aparece pasta que o mapa não conhece; aí a resposta certa é atualizar o README, não inventar.

Para o detalhe do app (rotas, tabelas, integrações) aponte `docs/spec/snapshots/`, que é gerado a cada deploy. Para o porquê do layout, o ADR 0044.

## Onboarding em prosa

`docs/onboarding/claude-setup.md` é o passo a passo humano. Esta skill é a checagem automática do mesmo conteúdo. Quando o script acusa algo que o documento não explica, a correção é no documento.
