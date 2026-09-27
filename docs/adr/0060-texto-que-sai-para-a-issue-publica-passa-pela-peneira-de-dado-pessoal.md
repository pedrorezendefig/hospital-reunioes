---
status: accepted
amends: 0054
---

# Texto que sai para a issue pública passa pela peneira de dado pessoal

Decisão do diretor na triagem da issue #772 (27/set/2026). Estende ao dado de paciente a regra que a review do PR #688 fixou para o nome de quem pede: "nome civil nenhum sai daqui". O repositório das issues é público.

## Contexto

- O "Levar para desenvolvimento" (ADR 0054, decisão 1) publica o título e a descrição da Demanda numa issue do repositório público, e toda resposta da Conversa de uma Demanda vinculada vira comentário na issue (decisão 4). O único tratamento do texto era o escape de `<` e de estrutura de Markdown.
- Desde o #730 a descrição pode ser a transcrição, feita pelo modelo de visão, de um print de sistema hospitalar: nome de paciente, leito, prontuário. O prompt do print manda omitir dado pessoal e a tela avisa quem anexa, mas as duas barreiras dependem do modelo e da pessoa. E o diretor também digita: dado de paciente digitado vaza igual.
- Na varredura de 27/09 nenhuma issue do repositório tinha sido criada pelo botão. Esta decisão é prevenção, e precisa estar em produção antes do primeiro uso real.

## Decisões

1. **Todo texto da Tecnologia que sai para o GitHub passa pela peneira, sempre.** Título e descrição da issue criada, e o texto do comentário espelhado, no envio e na correção. Sempre, e não só quando a descrição veio de print: não há coluna que diga a origem, e o texto digitado vaza igual.
2. **A peneira é o `pseudonimizar` da Ouvidoria, como está.** Os mesmos marcadores (`[CPF]`, `[CNS]`, `[RG]`, `[TELEFONE]`, `[EMAIL]`, `[DATA_NASCIMENTO]`, `[NOME]`, `[REDE_SOCIAL]` e os demais) e as mesmas garantias e limites, já testados com fuzz nas issues #412 e #441. Não existe uma segunda peneira, e esta fatia não muda o comportamento do módulo para quem mais o usa.
3. **A peneira roda sobre o texto cru, e o escape vem por último.** Assim o escape é a última palavra sobre a saída: nenhum `<` e nenhuma estrutura em coluna zero sobrevive, venha do autor ou da peneira. O escape também põe uma barra antes do colchete do marcador quando ele encosta em `:`, `(` ou `[`, porque `[NOME]: [TELEFONE]` na coluna zero é uma definição de link de referência e o GitHub some com a linha, e `[TELEFONE](x)` vira link. A barra não se repete numa segunda passada. O título da issue fica sem a barra: lá o GitHub mostra texto puro, sem link a desligar, e a barra apareceria.
4. **Só o que sai é peneirado.** A Demanda no app e a linha da Conversa guardam o texto original. O bloco "Para o diretor", que volta ao card lido da issue, pode voltar com marcadores, e isso é aceito.
5. **No comentário espelhado, a peneira roda nos trechos entre as menções do app.** A menção escolhida no autocomplete continua virando `@login` ou "Pessoa do hospital" (emenda de 11/09 da ADR 0054), e esse rótulo não passa pela peneira. O `@` digitado à mão, esse sim, passa: a peneira o lê como perfil de rede social, e ele sai `[REDE_SOCIAL]` em vez do `@ fulano` que a emenda de 11/09 descrevia. Pode ser o perfil do paciente. O espaço depois do `@` continua valendo para o que a peneira não pega, o `@` seguido de dígito.
6. **A peneira é camada a mais, não substituta.** A regra do prompt do print e o aviso na tela continuam.

## Consequências

- Perde contexto, nunca vaza pessoa. A regra de desenho do `pseudonimizar` lê duas palavras capitalizadas seguidas como nome, e nomes de tela e de fornecedor saem como `[NOME]` ("Painel de Reuniões", "Assistente de Tecnologia", "Global Health"). Sigla com três letras e quatro dígitos tem o desenho de placa e sai `[PLACA]` (`RFC7231`, `ISO8601`). No corpo, a barra do marcador aparece dentro de bloco de código e no "O que muda" do card, que o Markdown não lê. Versão, código de erro, porta, stack trace, identificador e número de issue saem intactos.
- O `@login` do GitHub digitado à mão pela Vitta numa resposta sai `[REDE_SOCIAL]`: a peneira não distingue login de perfil de paciente. Quem quer chamar alguém usa a menção do app.
- Nome fora da base de nomes, em minúsculas e sem pista, atravessa: é o limite conhecido do módulo, documentado no próprio `pseudonimizar`. Por isso o prompt e o aviso continuam de pé.

Rejeitado:

- **Confirmação no botão, ou o print sair só como link.** As opções (b) e (c) da issue #772 pediam migration e mudavam o fluxo; a peneira fecha o vazamento sem isso.
- **Peneirar só quando a descrição veio de print.** Não há como saber a origem sem migration, e o texto digitado vaza igual.
- **Afrouxar o `pseudonimizar` para o texto técnico.** Mudaria o comportamento da Ouvidoria, que manda o mesmo texto para uma IA externa.
