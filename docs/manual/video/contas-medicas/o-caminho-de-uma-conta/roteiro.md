# Roteiro: O caminho de uma conta (Contas médicas)

Vídeo de visão geral do módulo Contas médicas, na abertura da seção
(`contas-medicas/index.md`). Piloto do estilo narrado em Remotion (ADR 0076,
issue #1368 do PRD #1365).

## Briefing (skill `copy`)

- **Quem vê:** a faturista do São Matheus na primeira semana com o módulo,
  com o MV aberto ao lado, e quem divide a conta com ela: o Apoio ao
  faturamento, a coordenadora, a gestão de contas médicas.
- **O que deve pensar ao final:** "sei o caminho inteiro da conta e onde eu
  entro nele".
- **A única ideia:** a conta faz um caminho só, do PDF do MV ao Painel, e cada
  papel tem a sua parada nele.
- **A prova:** a abertura do módulo ("O caminho de ponta a ponta"), as Páginas
  de tarefa (Enviar contas e prontuários, Corrigir uma conta pelo guia,
  Devolver uma conta à fila, Decidir na Validação, Cadastrar um cenário e
  conferir os lembretes, Ler o Painel), o Como funciona "Quando a conta dá
  erro" e o `novidades.md`.

## Ganchos

1. Detalhe específico: "Dois PDFs do MV viram a lista do que corrigir."
   **Escolhido:** o objeto concreto (os dois PDFs que a faturista já exporta)
   e o resultado (a lista) cabem em 3 s, e o primeiro quadro mostra os dois
   PDFs virando a lista, então funciona no mudo.
2. Situação: "A conta está pronta para a operadora. Ou quase."
3. Começo no meio: "Você arrasta a conta do MV e a conferência começa."

Virada (responde o gancho): "Dois PDFs entraram, e a conta sai para a
operadora já conferida."

## Nota da copy

| Critério | Nota |
| --- | --- |
| Gancho | 2 |
| Uma ideia | 2 |
| Ouvido | 2 |
| Repetição | 1 (conta e prontuário repetem de propósito: são o assunto) |
| Cena casada | 2 |
| Virada | 2 |
| Verdade | 2 |
| **Total** | **13 de 14** |

Humanizer (ADR 0071) passado na narração e no texto de tela: saíram o "sem
você digitar nada" (virou o que o sistema faz), o par de perguntas soltas do
Não procede e a repetição de "código" no Copiar para a TI. Varredura
anti-técnica (migration, endpoint, API, PR, deploy, RLS, schema, backend,
frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt)
e de travessão: sem achado.

## Narração

O texto que a voz A lê está em `narracao.txt`, um parágrafo por frase.

## Cenas

Uma cena por tela do app. As frases da mesma tela dividem a cena: a câmera
anda de um alvo ao outro na palavra que cita o alvo, e a legenda troca de
frase. Cada corte entre telas usa uma transição diferente do catálogo.
Destaque é o contorno azul com o resto da tela velado; cursor é a seta
branca, com o anel no clique.

TABELA_DE_CENAS

## Como refazer

1. Telas: `python3 docs/manual/prints/contas-medicas.py --semear` e
   `python3 docs/manual/prints/contas-medicas.py --video` (o app local na
   versão de produção). Saem `video-*.png` e `video-alvos.json` em
   `docs/manual/src/assets/contas-medicas/`.
2. Projeto de trabalho: o da receita
   (`.claude/skills/manual/references/video-de-visao-geral.md`), com os
   arquivos de `cena/projeto/` por cima do modelo da skill `motion` (fonte HP
   Simplified, paleta azul-marinho, sem grão, `swangle`).
   `cp docs/manual/src/assets/contas-medicas/video-*.png "$W/public/"`,
   `cp docs/manual/src/assets/contas-medicas/video-alvos.json "$W/src/videos/ContasMedicas/alvos.json"`
   e a logo branca da `marca-hsm` em `public/logo-hsm-branca.png`.
3. Narração: `python3 ~/.claude/voz/narrar.py --file narracao.txt --output "$W/public/narracao.wav"`.
4. Tempos: `node cena/projeto/tempos-da-narracao.mjs "$W/public/narracao.json" narracao.txt "GRUPOS" > "$W/src/videos/ContasMedicas/tempos.json"`.
5. `npx tsc --noEmit`, stills, draft e render (receita), composição `ContasMedicas`.
