---
name: mensagem-prd
description: Mensagem de WhatsApp para o diretor e os usuários do módulo contando o que um PRD entregue agrega, em texto corrido e sem jargão, pronta para o Pedro copiar. Sintaxe `/mensagem-prd <PRD>`. Só o que está em produção entra.
---

# Mensagem do PRD

Escreve a mensagem que o Pedro manda no WhatsApp quando um PRD chega em produção: o que mudou, para que serve, como usar, na língua de quem usa o app. É a terceira saída do pós-entrega, ao lado do vídeo e da página do `/divulgar`. Sem ela, a funcionalidade sobe e quem precisava saber descobre por acaso.

## Sintaxe

```
/mensagem-prd <PRD>
```

## Fluxo

1. **Fontes.** Leia o PRD e as sub-issues pelo `gh issue view`. A matéria-prima é o bloco "Para o diretor" de cada uma ("O que muda" e "O que você precisa saber"); o resto do corpo serve para não inventar comportamento. Se o `/divulgar` já publicou, pegue o link da página no último comentário `<!-- automacao -->` do PRD.
2. **Só o que está no ar.** Confira em `docs/spec/deploy/history.json` da `main` (ou no comentário de subida do PRD) quais filhas já foram deployadas. Filha ainda aberta ou sem deploy fica fora da mensagem; se nenhuma subiu, pare e diga isso.
3. **Escreva** no formato abaixo.
4. **Entregue** em bloco de código para copiar num toque, e registre a mesma mensagem como comentário no PRD com `<!-- automacao -->` na primeira linha e o cabeçalho `## Mensagem enviada`, para o histórico saber o que foi dito e quando.

## Formato

Tom semi-formal: é para o diretor e para quem opera o módulo, não para amigos (a regra "Fala galera" do CLAUDE.md global é para mensagens entre colegas e não vale aqui).

- Abertura curta ("Oi, pessoal, tudo bem?") e uma frase dizendo qual parte do app mudou e com que intenção.
- Um parágrafo por funcionalidade, na ordem em que a pessoa encontra na tela. Cada parágrafo diz o que mudou e o benefício em linguagem de uso ("quem vai corrigir um problema de tela vê exatamente o que você viu").
- Texto corrido: sem bullet, sem bold, sem título, sem travessão. WhatsApp é texto puro.
- Sem número de issue, label, nome de tabela, rota ou versão. "Vitta" e os nomes do `CONTEXT.md` (Quadro, Painel, Demanda) podem aparecer porque são os nomes da tela.
- Link da página de divulgação numa linha própria, se existir.
- Um emoji no máximo, só no fecho. Fecho com "me chama".
- Tamanho: cabe numa tela de celular com uma rolada; mais que isso, corte funcionalidade menor, não comprima frase.

Exemplo aprovado (PRD #1056, aba Tecnologia):

```
Oi, pessoal, tudo bem?

Passando pra avisar que a aba Tecnologia do app ganhou uma reforma boa. A ideia foi deixar ela mais limpa e mais útil no dia a dia de quem pede e acompanha as demandas.

O Quadro agora tem só três colunas: Nova, Em andamento e Aguardando. Concluir ou cancelar uma demanda virou um botão dentro do próprio card, e o que foi encerrado sai do quadro na hora.

No lugar de "Minha vez" e "Histórico" entrou o Painel. Ele mostra, numa tela só, o que está esperando por você, o que a Vitta está desenvolvendo e o histórico do que já foi encerrado, com busca.

Agora dá pra anexar prints na demanda: na hora de criar, pelo assistente ou numa resposta da conversa. O print fica só dentro do app, nunca sai pra fora, e é apagado quando a demanda é concluída ou cancelada.

Se tiver qualquer dúvida ou algo parecer estranho, me chama 🙂
```

## O que esta skill não faz

- Não manda a mensagem: o envio é do Pedro.
- Não gera vídeo nem página (`/divulgar`), nem escreve manual (`/manual`).
- Não descreve o que ainda não subiu.
