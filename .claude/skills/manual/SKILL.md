---
name: manual
description: Produz o Manual do usuário em docs/manual/. `/manual <módulo>` escreve a seção, `/manual #PRD` as páginas do PRD em draft, `/manual publicar` publica. Prints por roteiro, vídeo com OK humano.
---

# Manual

Escreve o Manual do usuário da plataforma (ADR 0057) no site que vive em
`docs/manual/`: um endereço só, organizado como o menu do app, em que quem
travou numa tela abre a página da tarefa, vê um vídeo curto e faz.

**O leitor é o usuário do hospital**, não o time de tecnologia. Se a página
falar de tela, botão e prazo, acertou. Se falar de rota, tabela ou versão,
errou, e o lint trava.

## Três modos

| Comando | O que faz |
| --- | --- |
| `/manual <módulo>` | Escreve a seção inteira de um módulo: Visão geral, Páginas de tarefa, Como funciona e Novidades, com prints e Vídeos de tarefa. |
| `/manual #PRD` | Só as páginas que aquele PRD cria ou muda, todas em `draft: true`, mais a entrada de Novidades. É a receita da Fatia de manual. Veja `references/prd-e-novidades.md`. |
| `/manual publicar` | Roda o `publicar.sh` e registra o link. Veja `references/publicar.md`. |

Módulos: `primeiros-passos`, `reunioes`, `ouvidoria`, `pops`, `admin`. A aba
Tecnologia fica fora de propósito (a divulgação do #634 cobre).

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **O código do frontend** da tela: texto de botão, rótulo, ordem dos campos,
   mensagem de erro. A palavra que a página põe em negrito sai daqui, nunca de
   memória.
2. **`docs/spec/snapshots/`** (`ROTAS.md`, `FLUXOGRAMAS.md`): o caminho de
   navegação real até a tela e a ordem dos passos.
3. **`CONTEXT.md`** e o CONTEXT do módulo: vocabulário canônico. Sempre o termo
   do glossário, nunca sinônimo inventado.
4. **A Visão geral já escrita** do módulo e as páginas vizinhas: o manual não
   se contradiz nem repete o que a página do lado já explica.
5. **Os PRDs fechados do módulo e o `docs/spec/deploy/history.json`**: são a
   matéria-prima de Novidades, com a data de cada entrega.

O manual só mostra **o que está no ar**. Funcionalidade que ainda não subiu
nasce em `draft: true` e o `/deploy ship` tira o draft quando ela sobe.

## O molde da Página de tarefa

Uma página é **uma tarefa**, com título no infinitivo ("Registrar uma
manifestação pelo formulário"). Se não cabe em uma tela de celular, são duas
tarefas.

```markdown
---
title: <verbo no infinitivo>
description: <uma frase, o que a pessoa consegue fazer>
prd: [731]                 # PRDs que criaram ou mudaram a página
draft: true                # sai quando o PRD sobe para produção
papel: [Ouvidoria]         # quem faz: Ouvidoria, Gestor do setor, Facilitador,
                           # Secretária, Só admin, Qualquer pessoa
login: false               # só na tela aberta por link ou QR, sem entrar no app
video: <slug do vídeo>     # ausente = a página mostra "Vídeo em produção"
sidebar:
  order: 2
---

## Quando usar
## Passo a passo
![<o que o print mostra>](../../../assets/<modulo>/<print>.png)
## Se der errado
```

Selo e vídeo são desenhados pelo tema a partir do frontmatter: **não repita
isso no Markdown**.

As outras páginas do módulo: `index.md` é a Visão geral (as palavras que a
pessoa vê o tempo todo e o caminho de ponta a ponta), o grupo `como-funciona/`
guarda o que não é ação de ninguém (como o prazo é contado, o que o sistema
apaga sozinho) e `novidades.md` é a linha do tempo das entregas. Nenhuma delas
leva `papel`.

## A régua de linguagem

- **"Você", verbo no imperativo.** "Clique em Enviar", não "o usuário deve clicar".
- **A palavra da tela em negrito**, escrita igualzinha ao app: **Enviar manifestação**.
- **Até 6 passos numerados.** Passou disso, a tarefa é outra.
- **"Se der errado" no fim**, em até 3 casos, cada um começando pelo que a
  pessoa vê: "**O botão está apagado:** o relato está vazio."
- **Teto de 250 palavras** por Página de tarefa (o lint avisa acima disso).
- **Sem travessão e sem meia-risca** (ADR 0013) e sem jargão em texto visível:
  a lista que trava está em `tools/lint_manual.py`.

## Prints e vídeo

- **Print** é tela real do app local, capturada pelo Roteiro de prints do
  módulo (`docs/manual/prints/<modulo>.py`, Playwright). Print novo entra no
  roteiro, nunca à mão. Receita em `references/prints.md`.
- **Vídeo de tarefa**: composição HyperFrames versionada em
  `docs/manual/video/<modulo>/<slug>/`, MP4 fora do git, 30 a 60 s, mudo, com
  carimbo de geração. Vai a draft e **só o Pedro aprova**; o render final vem
  depois do OK. Receita em `references/video-de-tarefa.md`.

## Antes de entregar

```bash
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
```

Checklist:

1. Cada página tem `prd`, `draft` e (sendo tarefa) `papel` no frontmatter.
2. Toda palavra em negrito existe na tela, com a mesma grafia do frontend.
3. Todo print veio do roteiro do módulo, e o roteiro roda de ponta a ponta.
4. Todo `video` do frontmatter tem composição versionada com carimbo, e o MP4
   ficou fora do git.
5. O draft do vídeo foi entregue ao Pedro e o OK veio antes do render final.
6. Os quatro comandos acima passam.
