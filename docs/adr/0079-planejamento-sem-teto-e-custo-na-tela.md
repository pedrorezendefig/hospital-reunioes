---
status: accepted
amends: 0077
---

# Planejamento da Demanda sem teto de perguntas, e o custo da conversa na tela

Decisão do Pedro (06/11/2026, grill no terminal a partir do áudio do diretor). O diretor usou o Planejamento da Demanda e gostou do formato (uma pergunta por vez, com a recomendada destacada), mas a conversa bateu no teto de 12 perguntas: o agente encerrou no meio do assunto, o chat deixou de aceitar pergunta nova e o resumo saiu com quatro a seis itens em "Ficou em aberto". O teto era código (`TETO_DE_PERGUNTAS = 12`), não critério do modelo, e o prompt mandava parar "quando já tiver o bastante", o que empurrava lacuna para o resumo. Esta ADR troca a regra de parada e mostra o custo para que o diretor saiba quanto a entrevista custa enquanto decide continuar.

## Decisões

1. **Sem teto de perguntas na melhoria.** Não existe limite de número de perguntas, nem visível nem escondido. O que segura o tamanho da conversa é o custo na tela (decisão 6) e o "Fechar e resumir", que segue à mão. Emenda a decisão 4 da ADR 0077. Rejeitado: teto alto invisível como proteção (volta a cortar o diretor no meio, só que mais tarde).

2. **A regra de parada é "nada em aberto".** O agente só encerra quando o "Ficou em aberto" sairia vazio. Enquanto houver lacuna do lado do negócio, a próxima pergunta é sobre ela. "Ficou em aberto" deixa de ser a saída normal da conversa e passa a existir só quando o diretor fecha antes. Rejeitado: manter "pare quando já tiver o bastante para a Vitta começar" (é o que gerou as pendências).

3. **A conversa nunca trava antes do card.** Depois do encerramento ou do resumo, o campo livre continua ativo até "Criar o card": o diretor escreve, e o agente volta a perguntar. Quem decide que acabou é o diretor.

4. **Fechar cedo deixa a lacuna à vista.** Se o diretor clica "Fechar e resumir" com lacuna, o resumo mostra "Ficou em aberto" com o botão "Continuar respondendo", que retoma as perguntas por essas lacunas. "Criar o card" com lacuna continua permitido. Rejeitado: bloquear o card enquanto houver lacuna (prende o diretor).

5. **Título e tipo na lista.** Na melhoria, o agente dá o título já na primeira resposta e o afina a cada turno, como já fazia no bug; o título provisório deixa de ficar até o resumo. Cada linha da lista lateral ganha um selo "Bug" ou "Melhoria" ao lado da Etapa, sem agrupar nem filtrar. Retomar a conversa continua sendo abrir a linha: ela volta na última pergunta sem resposta.

6. **O custo da conversa aparece no cabeçalho dela.** "Opus 5.5 · US$ 1,84 até agora", atualizado a cada turno, somando todas as chamadas de IA daquela conversa (classificação, perguntas, leitura de código, imagem, resumo). Fica só na conversa aberta, não na lista. Se alguma chamada saiu sem preço na tabela (gravada com custo zero), aparece "custo não medido", nunca um valor que finge ser real. Emenda a decisão 9 da ADR 0077 (e a decisão 7 da ADR 0075, que é histórico), que mantinham o custo fora da tela do diretor. Quem vê a aba continua sendo só o Super admin (ADR 0050). Rejeitado: custo só num painel interno da Vitta (o diretor não dimensionaria a entrevista).

7. **O Roteiro do bug não muda.** Continua com no máximo cinco perguntas, uma por campo fixo (onde, o que aconteceu, o que esperava, como repetir, print). Cinco campos não deixam lacuna.

## Consequências

- Uma conversa de melhoria pode ficar bem mais longa e mais cara; o risco é aceito porque o diretor vê o número enquanto conversa.
- O Kit `tecnologia.md` deixa de falar em "no máximo 12 perguntas" e passa a explicar o custo no cabeçalho, no mesmo PR da mudança.
- Repetição sem fim do modelo não tem trava de número: a defesa é o prompt (não perguntar o que já foi respondido) e o diretor, que vê o custo e pode fechar.
