---
status: accepted
---

> Emenda em prosa à decisão 1 do ADR 0034. Sem ponteiro `amends` no frontmatter: o 0034 já está emendado pelo 0036 (Ponto de escuta) e o lint de ADR aceita um único ponteiro por campo, como o próprio 0034 fez com o 0031.

# O tipo da manifestação é lista fechada, e é ele que decide o sigilo

A decisão 1 do ADR 0034 diz que denúncia e relato de conduta nascem com sigilo reforçado. Na implementação, "denúncia" era uma **palavra digitada**: a regra procurava os termos `denuncia` e `relato de conduta` dentro de um campo de texto livre. Quatro revisões independentes (PRs #328, #337, #348 e #351) mostraram as quatro faces do mesmo buraco, e a issue #372 as fechou.

O caso classificado como "Assédio moral" não casava com termo nenhum, não elevava o sigilo, e o email de acionamento chegava ao setor acusado com o nome de quem manifestou. Nenhuma rota elevava o sigilo depois da criação, e nenhuma o abaixava: a manifestação vinda do QR, que nasce fail-closed, ficava invisível para facilitador, secretária e super admin **para sempre**, mesmo depois de o ouvidor classificá-la como elogio. E a consulta de protocolo da API da Ana devolvia o índice de qualquer caso pelo número, que é sequencial e enumerável.

## Decisões

1. **Tipo é lista fechada, no banco**: `denuncia`, `reclamacao`, `sugestao`, `elogio`, `relato_de_conduta` (coluna `tipo_manifestacao`, CHECK na migration 077). É o tipo que decide o sigilo. O texto livre continua existindo na coluna `categoria`, como rótulo humano do caso, e não decide mais nada. `categoria` não foi renomeada: renomear exigiria app e banco subindo no mesmo instante, e o ganho seria só o nome.

2. **Sigiloso por natureza**: `denuncia` e `relato_de_conduta`, nos três canais, sem ato humano. A regra automática é **piso, nunca teto**: o ouvidor pode elevar o sigilo de um caso que a lista não previu, e não pode retirar o de um tipo sigiloso por natureza.

3. **Sem tipo é fail-closed**: `tipo_manifestacao` nulo significa "ainda não classificado", e o caso não classificado é tratado como sigiloso. Vale para o formulário público, para o QR e **também para o canal da Ana**, que antes entrava aberto: o `resumo` do índice é texto gerado a partir da conversa com quem manifestou e frequentemente já identifica a pessoa. A saída é a classificação, não afrouxar a entrada.

4. **A Ana não manda o tipo**: o campo entra na lista de decisões do ouvidor que o POST da API de serviço recusa, junto de estado, desfecho e sigilo. Mantém a decisão 10 do ADR 0034: a Ana registra manifestação, não classifica caso. Aceitar o tipo dela seria deixar a IA decidir quem enxerga o caso.

5. **A porta do sigilo é a classificação**: uma rota (`POST /ouvidoria/manifestacoes/{id}/classificacao`) que grava tipo, rótulo e sigilo, atrás de `require_perfil_ouvidoria`, com movimento na trilha e registro no log de acesso. A validação e acionamento aplica a **mesma** regra, pela mesma função: quem classifica ali não precisa de uma segunda tela. Sem pedido explícito de sigilo, o sigilo de hoje é mantido: descer é ato consciente, não efeito colateral de reclassificar.

6. **Consulta de protocolo sigiloso devolve só o andamento**: `protocolo`, `status` e a data. Sem resumo, sem categoria, sem setor. O caso não sigiloso segue com o contrato de hoje, sem mudança: o time da Ana só perde campos no caso sigiloso.

## Consequências

- Casos que já estavam no banco receberam tipo por backfill, pelo mesmo critério que a regra antiga reconhecia, para nenhum caso hoje sigiloso ficar aberto. O rótulo "A classificar" do canal aberto continua sem tipo, porque ele de fato não foi classificado.
- Enquanto o ouvidor não classifica, o caso da Ana some do painel de quem está fora da Ouvidoria. É a troca aceita: antes ele aparecia com um resumo que identificava quem relatou.
- A reabertura por reincidência só **eleva** o sigilo, e por isso não usa a mesma função: reabrir não é classificar, então não devolve caso nenhum ao índice geral.
- O time da Ana precisa ser avisado da mudança no contrato da consulta, depois do deploy.
