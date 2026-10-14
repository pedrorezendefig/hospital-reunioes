---
name: manual
description: Produz o Manual do usuário em docs/manual/. `/manual <módulo>` escreve a seção, `/manual #PRD` as páginas do PRD em draft, `/manual publicar` publica. Prints por roteiro, vídeo pelos gates do Estilo do manual.
---

# Manual

Escreve o Manual do usuário da plataforma (ADR 0057, emendada pela 0072) no
site que vive em `docs/manual/`: um endereço só, organizado como o menu do
app, em que quem travou numa tela abre a página da tarefa, segue os passos com
os prints e faz. Cada módulo abre com um Vídeo de visão geral do caminho
principal (o Admin fica sem).

**O leitor é o usuário do hospital**, não o time de tecnologia. Se a página
falar de tela, botão e prazo, acertou. Se falar de rota, tabela ou versão,
errou, e o lint trava.

## Três modos

| Comando | O que faz |
| --- | --- |
| `/manual <módulo>` | Escreve a seção inteira de um módulo: Visão geral, Páginas de tarefa, Como funciona e Novidades, com prints e o Vídeo de visão geral na abertura. |
| `/manual #PRD` | Só as páginas que aquele PRD cria ou muda, todas em `draft: true`, mais a entrada de Novidades, e o Vídeo de visão geral refeito só quando a issue pede (o PRD mudou o caminho principal). É a receita da Fatia de manual. Veja `references/prd-e-novidades.md`. |
| `/manual publicar` | Tira o draft que a Action deixou (abertura com vídeo), roda o `publicar.sh` e registra o link. É do humano, depois do deploy que fecha PRD com Fatia de manual. Veja `references/publicar.md`. |

Módulos: `primeiros-passos`, `reunioes`, `ouvidoria`, `pops`, `contas-medicas`,
`admin`. A aba
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
nasce em `draft: true` e uma Action no push da `main` tira o draft quando ela
sobe (ADR 0068). A Action não publica: o site só muda com o
`/manual publicar`, que o humano roda da máquina com os MP4 e que também tira
o draft das aberturas com Vídeo de visão geral (o MP4 não vem no clone; issue
#951).

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
busca: [boleto, fatura]    # palavras do dia a dia que acham a página na busca
proximas: [<slug>, <slug>] # até 3 tarefas do mesmo módulo que vêm depois
sidebar:
  order: 2
---

## Quando usar
## Passo a passo
1. Clique em **Novo Usuário**.
   ![<o que o print mostra>](../../../assets/<modulo>/<print>.png)
2. Preencha ...

:::caution[Não tem volta]
<o aviso, uma ou duas frases, antes do passo que dispara a ação>
:::

3. Clique em **Criar**.
## Se der errado
```

O selo é desenhado pelo tema a partir do frontmatter: **não repita isso no
Markdown**. Página de tarefa não leva vídeo, nem pelo campo nem embutido. O Print de passo fica **dentro do item da lista**, com três
espaços de recuo, logo abaixo do passo que ele ilustra: é assim que o tema o
acomoda sob o número grande. O Aviso destacado é no máximo um por página e só
para o irreversível.

`busca:` lista as palavras que a pessoa digitaria e que o texto não usa (ela
procura "boleto", a página fala "guia"). Elas entram no índice da busca sem
aparecer na tela; palavra que já está no texto não precisa estar aqui.
`proximas:` aponta até três tarefas do mesmo módulo, pelo nome do arquivo sem
extensão, e o tema desenha "Tarefas próximas" no fim da página. O lint reprova
nome que não existe no módulo, de outro módulo ou mais de três; tarefa em
draft não vira link até subir. O módulo da página aparece sozinho no resultado
da busca, sem campo nenhum.

As outras páginas do módulo: `index.md` é a Visão geral (as palavras que a
pessoa vê o tempo todo e o caminho de ponta a ponta), a abertura do módulo, e
é a única que leva `video: <slug>` (o Vídeo de visão geral; ausente, publica
sem vídeo e sem aviso). A página inicial (`index.mdx`) leva o mesmo `video:`
de Primeiros passos. O grupo `como-funciona/`
guarda o que não é ação de ninguém (como o prazo é contado, o que o sistema
apaga sozinho) e `novidades.md` é a linha do tempo das entregas, com o link
para a página de divulgação de cada entrega no lugar do vídeo. Nenhuma delas
leva `papel`.

## A régua de linguagem

- **"Você", verbo no imperativo.** "Clique em Enviar", não "o usuário deve clicar".
- **A palavra da tela em negrito**, escrita igualzinha ao app: **Enviar manifestação**.
- **Até 6 passos numerados.** Passou disso, a tarefa é outra.
- **"Se der errado" no fim**, em até 3 casos, cada um começando pelo que a
  pessoa vê: "**O botão está apagado:** o relato está vazio."
- **Um Print de passo por mudança de tela**, com balão numerado igual ao
  passo; passos na mesma tela dividem um print. Página de tarefa sem nenhuma
  imagem está incompleta.
- **Teto de 250 palavras** por Página de tarefa (o lint avisa acima disso; o
  texto alternativo das imagens não conta).
- **Sem travessão e sem meia-risca** (ADR 0013) e sem jargão em texto visível:
  a lista que trava está em `tools/lint_manual.py`.
- **Humanizer antes do lint, em toda página** (ADR 0071): escrita a página
  (Visão geral, Página de tarefa, Como funciona ou Novidades), chame a Skill
  tool com `humanizer` em modo embutido e só depois rode o
  `tools/lint_manual.py`. A amostra de voz é uma Página de tarefa já publicada
  do módulo: ela manda no tom, o humanizer só tira os cacoetes. O molde não
  muda (passos, teto de palavras, a palavra da tela em negrito), e o que está
  em frontmatter, caminho de print e bloco de código fica igual.

## Prints e vídeo

- **Print** é tela real do app local, capturada pelo Roteiro de prints do
  módulo (`docs/manual/prints/<modulo>.py`, Playwright). Print novo entra no
  roteiro, nunca à mão; o balão numerado também é do roteiro. Receita em
  `references/prints.md`.
- **Fluxograma de caminho** só em Visão geral e em Como funciona com estados
  ou desvios, um por página: fonte Mermaid em `docs/manual/fluxogramas/`, SVG
  gerado pelo script do site em `src/assets/<modulo>/fluxo-<slug>.svg`
  (`node docs/manual/scripts/gerar-fluxogramas.mjs`, ou
  `node docs/manual/scripts/gerar-fluxogramas.mjs --so <modulo>/<slug>` para
  refazer um só). Nunca em Página de tarefa.
- **Vídeo de visão geral**: um por módulo, na abertura, mostrando o caminho
  principal do módulo. Composição HyperFrames versionada em
  `docs/manual/video/<modulo>/<slug>/`, MP4 fora do git, 90 a 120 s, mudo,
  com legendas e carimbo de geração, no **Estilo do manual**
  (`docs/manual/video/_estilo/`: `DESIGN.md`, tokens gerados do app e os cinco
  cards). Até 8 MB depois do reencode, e a soma do Manual até 40 MB (o
  `publicar.sh` trava). Passa pelo gate de strips e ganha um `VERIFY.md`. Os
  gates limpos levam direto ao render final, sem esperar OK humano; nota que o
  Pedro mandar depois vira regra no PR do conserto. O Admin fica sem vídeo, e
  Página de tarefa não tem vídeo. Receita em
  `references/video-de-visao-geral.md`.

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
4. `video` só na abertura do módulo (e na página inicial), com composição
   versionada com carimbo, e o MP4 ficou fora do git.
5. O render final saiu depois dos gates limpos e o MP4 foi copiado para os masters.
6. Vídeo novo ou refeito: `tools/strips_video_manual.py` sem achado, `VERIFY.md`
   ao lado da composição e cada nota recebida virou regra.
7. Os quatro comandos acima passam.
