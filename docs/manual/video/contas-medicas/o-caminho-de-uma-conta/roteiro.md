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

| Cena | Tempo (s) | Fala | Tela | Entrada |
| --- | --- | --- | --- | --- |
| 1 | 0.0 a 3.9 | Dois PDFs do MV viram a lista do que corrigir. | tipografia: dois PDFs viram a lista | (abre) |
| 2 | 3.9 a 14.7 | Em Contas médicas, arraste a conta e o prontuário do mesmo atendimento. O sistema lê o número do atendimento nos PDFs e junta os dois. | video-01-contas, video-02-ultimo-envio | pontoAbre |
| 3 | 14.7 a 31.3 | Quem é do Apoio ao faturamento também envia e acompanha tudo em Meus envios. Cada conta vira um cartão com dois quadrados, um da conta e outro do prontuário. Faltou um arquivo? O botão do cartão pede só o que falta. | video-03-meus-envios | fusao |
| 4 | 31.3 a 40.6 | Com o guia pronto, a conta entra na Fila, a mesma para todas as faturistas. Clique em Abrir, e a conta passa a ser sua. | video-01-contas | chicoteLuz |
| 5 | 40.6 a 51.3 | No topo do guia ficam a nota de entrada e quanto falta ajustar em reais. As linhas vêm por dia e por setor, e cada uma começa pelo verbo. | video-04-guia | estica |
| 6 | 51.3 a 60.2 | Copie o código, corrija no MV e marque Feito. Ver evidência mostra a página do prontuário que prova a linha. | video-05-guia-linhas | flash |
| 7 | 60.2 a 67.4 | Se a correção não cabe, marque Não procede e diga o motivo. Se o MV não deixa lançar, Bloqueado. | video-06-nao-procede | flood |
| 8 | 67.4 a 72.3 | No fim, Concluir e abrir a próxima já traz a conta seguinte. | video-07-concluir | peliculaGira |
| 9 | 72.3 a 81.7 | Vai sair mais cedo? Devolver à fila solta a conta com o que você marcou. Outra faturista continua de onde você parou. | video-04-guia, video-08-fila-devolvida | retangulo |
| 10 | 81.7 a 98.6 | Quando a análise não termina, a conta fica em Erro, com o motivo e um código. Analisar de novo refaz a análise com os PDFs que já estão no sistema. Se a falha voltar, Copiar para a TI leva o detalhe para quem resolve. | video-03-meus-envios | glitchRGB |
| 11 | 98.6 a 111.0 | A linha Validar, o item bloqueado e a observação da faturista seguem para a Validação. Lá a gestão decide por tema, e a decisão vale para todas as contas dele. | video-09-validacao | tunel |
| 12 | 111.0 a 122.6 | Na Coordenação, a coordenadora faz a segunda checagem pelos lembretes. Cada lembrete aponta o insumo que o prontuário pede e a conta não trouxe. | video-10-coordenacao | pulsoJanela |
| 13 | 122.6 a 134.3 | O Painel mostra à gestão a nota da semana e onde a perda nasce. Farmácia, cadastro, enfermagem ou o próprio faturamento, cada causa com o valor dela. | video-11-painel | corteBatida |
| 14 | 134.3 a 138.4 | Dois PDFs entraram, e a conta sai para a operadora já conferida. | tipografia: a lista conferida e a logo | despenca |

Parada planejada: de 139,0 s ao fim (141,8 s), a logo do hospital inteira e parada na assinatura. Fora dela, nada fica parado: a câmera empurra devagar dentro de cada tela e a grade do fundo corre.

## Como refazer

1. Telas: `python3 docs/manual/prints/contas-medicas.py --semear` e
   `python3 docs/manual/prints/contas-medicas.py --video` (o app local na
   versão de produção). Saem `video-*.png` e `video-alvos.json` em
   `docs/manual/src/assets/contas-medicas/`.
2. Projeto de trabalho: o da receita
   (`.claude/skills/manual/references/video-de-visao-geral.md`), mais
   `patch -p1 -d "$W" < cena/projeto/identidade.patch` (fonte HP Simplified,
   paleta azul-marinho, sem grão, `swangle`, as transições sem o verde do
   modelo e a composição registrada no `Root.tsx`), as cenas
   (`mkdir -p "$W/src/videos/ContasMedicas" && cp cena/*.tsx tempos.json "$W/src/videos/ContasMedicas/"`),
   as telas (`cp docs/manual/src/assets/contas-medicas/video-*.png "$W/public/"`
   e `cp docs/manual/src/assets/contas-medicas/video-alvos.json "$W/src/videos/ContasMedicas/alvos.json"`),
   o roteiro dos tempos (`cp cena/projeto/tempos-da-narracao.mjs "$W/scripts/"`)
   e a logo branca da `marca-hsm` em `public/logo-hsm-branca.png`.
3. Narração: `python3 ~/.claude/voz/narrar.py --file narracao.txt --output "$W/public/narracao.wav"`.
4. Tempos: `node cena/projeto/tempos-da-narracao.mjs "$W/public/narracao.json" narracao.txt "1|2,3|4,5,6|7,8|9,10|11,12|13|14|15,16|17,18,19|20,21|22,23|24,25|26" > tempos.json`, e copie de novo para `$W/src/videos/ContasMedicas/`.
5. `npx tsc --noEmit`, stills, draft e render (receita), composição `ContasMedicas`.
