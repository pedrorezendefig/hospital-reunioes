---
name: mensagem-prd
description: Mensagem informal de WhatsApp para o diretor dizendo o que um PRD entregue colocou no ar e o que ele já consegue fazer no app, em tópicos e sem jargão, pronta para o Pedro copiar. A /onda-enxuta roda sozinha no fim da onda que fecha o PRD; à mão, `/mensagem-prd <PRD>`. Só o que está em produção entra.
---

# Mensagem do PRD

Escreve a mensagem que o Pedro manda no WhatsApp quando um PRD chega em produção: o que subiu e o que o diretor já consegue fazer no app, na língua de quem usa. A `/onda-enxuta` chama esta skill sozinha quando a subida fecha a última filha do PRD (nota `onda-enxuta` do `.claude/fluxo-notas.md`). É a terceira saída do pós-entrega, ao lado do vídeo e da página do `/divulgar`. Sem ela, a funcionalidade sobe e quem precisava saber descobre por acaso.

## Sintaxe

```
/mensagem-prd <PRD>
```

## Fluxo

1. **Fontes.** Leia o PRD e as sub-issues pelo `gh issue view`. A matéria-prima é o bloco "Para o diretor" de cada uma ("O que muda" e "O que você precisa saber"); o resto do corpo serve para não inventar comportamento. Se o `/divulgar` já publicou, pegue o link da página no último comentário `<!-- automacao -->` do PRD.
2. **Só o que está no ar.** Confira em `docs/spec/deploy/history.json` da `main` (ou no comentário de subida do PRD) quais filhas já foram deployadas. Filha ainda aberta ou sem deploy fica fora da mensagem; se nenhuma subiu, pare e diga isso.
3. **Escreva** no formato abaixo.
4. **Humanizer** (ADR 0071): passe a mensagem pela Skill tool com `humanizer` em modo embutido antes de entregar. A amostra de voz é o exemplo abaixo e a regra 6 do CLAUDE.md global: elas mandam no tom informal, o humanizer só tira os cacoetes. Link e nomes da tela não mudam.
5. **Entregue** em bloco de código para copiar num toque, e registre a mesma mensagem como comentário no PRD com `<!-- automacao -->` na primeira linha e o cabeçalho `## Mensagem para o diretor`, para o histórico saber o que foi dito e quando.

## Formato

Informal, na voz da regra 6 do CLAUDE.md global: é o Pedro falando com o diretor no WhatsApp. A pergunta que a mensagem responde é "o que subiu e o que eu consigo fazer agora no app?".

- Abertura com "Fala <nome do diretor>" e uma frase dizendo o que subiu e em que tela está. O nome não fica no repositório (ele é público): use o do prompt ou da memória; sem nome, "Fala, tudo bem?".
- "O que você já consegue fazer:" e depois um tópico por coisa que dá para fazer, na ordem em que a pessoa encontra na tela. Cada tópico é uma linha curta com a ação (sem marcador, sem bold) e, logo abaixo, duas ou três frases de como funciona na tela, com os textos que aparecem nela entre aspas.
- Restrição que muda o uso (quem não vê, quando ainda não aparece) entra numa linha "Só um detalhe:" antes do fecho.
- Texto puro: sem bullet, sem bold, sem título, sem travessão.
- Sem número de issue, label, nome de tabela, rota ou versão. Os nomes do `CONTEXT.md` (Fila, Painel, Quadro, Demanda) podem aparecer porque são os nomes da tela.
- Link da página de divulgação numa linha própria, se existir.
- Um emoji no máximo. Fecho com "Qualquer coisa me chama."
- Tamanho: até seis tópicos. Se tiver mais, junte os pequenos ou corte, sem espremer as frases.

Exemplo (PRD #1415, acompanhamento do processamento em Contas médicas):

```
Fala <nome>, subiu agora no app a parte de acompanhar as contas enquanto a IA lê. Tá tudo na aba Envios de Contas médicas 🙌

O que você já consegue fazer:

Ver em que etapa a conta está
A conta que a IA está lendo mostra "Processando" e a etapa, tipo "IA lendo o prontuário, parte 3 de 7". Se travou e o sistema tentou de novo, aparece "tentativa 2 de 3". A tela se atualiza sozinha e avisa quando a conta cai na Fila.

Saber quanto falta
Cada conta mostra quanto falta pra ficar pronta, tipo "faltam ~8 min". A que ainda espera a vez mostra a posição e a que horas começa e termina.

Ver como a fila tá andando
No topo da aba aparecem quantas contas estão sendo lidas e quantas esperam, o tempo médio do envio até a Fila, o tempo médio só de leitura e a hora que a espera deve acabar.

Pegar conta demorando
Se uma conta passa do dobro do tempo normal, ela fica amarela com "demorando mais que o normal".

Ver o tempo e o custo de cada conta
Clicando no cartão abre um painel com as cinco etapas, quanto tempo cada uma levou e quanto a IA gastou naquela conta. O custo só aparece pra quem tem o painel completo, secretária e faturistas não veem essa parte.

Mais coisa no cartão
O cartão mostra a operadora, quantos dias durou a internação e quantas páginas escaneadas o prontuário tem, que são as que deixam a leitura mais lenta. Quando a conta fica pronta, a linha dela na Fila mostra quantos itens e eventos a IA achou.

Só um detalhe: a previsão de tempo precisa de pelo menos 5 contas prontas pra comparar, antes disso ela não aparece.

Qualquer coisa me chama.
```

## O que esta skill não faz

- Não manda a mensagem: o envio é do Pedro.
- Não gera vídeo nem página (`/divulgar`).
- Não descreve o que ainda não subiu.
