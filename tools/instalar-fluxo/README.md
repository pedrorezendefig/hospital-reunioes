# Instalar o fluxo em outro projeto

Esta pasta exporta o **fluxo de trabalho** deste repositório para qualquer outro projeto: o painel local de 7 abas (Plano, Issues, Produção, Pendências, Mapa, Domínio, Guia), as skills do pipeline (`/grill-with-docs` até `/ship` e `/onda`), o catálogo de labels, os CIs de higiene e o contrato de deploy. O design system vai idêntico; só a paleta muda.

Não é um prompt solto. É um **roteiro versionado** que um agente Claude Code segue dentro do projeto de destino: explora a base, entrevista quem está instalando (uma pergunta por vez, duas opções, recomendação na frente), copia o que é neutro, adapta o que depende da stack, semeia o domínio e termina com um PR aberto e a primeira pendência humana na fila. Decisão registrada na ADR 0053.

## Arquivos

| Arquivo | O que é |
|---|---|
| `ROTEIRO.md` | O prompt completo, em fases. É o que o agente lê e segue. |
| `MANIFESTO.md` | A lista do que copia igual, do que adapta, do que gera do zero e do que fica de fora, com a nota de adaptação de cada item. |
| `empacotar.sh` | Gera o zip `fluxo-origem-<data>-<sha>.zip` (default em `~/Downloads`) para mandar a quem não vai clonar o repo. O zip traz um `LEIA-ME.md` com o prompt. |

## O prompt que a pessoa cola

Quem vai instalar abre o Claude Code **na raiz do projeto de destino** (um repositório git com remoto no GitHub e `gh` autenticado) e cola:

```
Clone https://github.com/pedrorezendefig/hospital-reunioes em ~/fluxo-origem (se já existir, faça git pull).
Leia ~/fluxo-origem/tools/instalar-fluxo/ROTEIRO.md inteiro e siga as fases na ordem, sem pular a entrevista.
O projeto de destino é este diretório. Não faça merge de nada: o merge é meu.
```

Só isso. O resto está no roteiro.

**Sem clonar:** rode `tools/instalar-fluxo/empacotar.sh` e mande o zip. A pessoa descompacta em `~/fluxo-origem` e cola o prompt do `LEIA-ME.md` que vem dentro (a única diferença é a primeira linha, que aponta a pasta em vez de clonar).

## Como provar que o roteiro funciona

Rode o roteiro num repositório de brinquedo (um projeto pequeno com README, um `package.json` ou `pyproject.toml` e um remoto no GitHub). No fim, o painel tem que subir com as 7 abas cheias, o CI do PR tem que passar e a aba Pendências tem que mostrar a issue "Curar o CONTEXT.md e rodar o primeiro /grill-with-docs".

## Manutenção

Criou, renomeou ou apagou skill do pipeline? Além do `/ask-pedro`, atualize o `MANIFESTO.md` no mesmo commit. O roteiro copia da árvore viva deste repo, então nada aqui duplica arquivo: o manifesto só aponta.
