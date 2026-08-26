---
status: accepted
amends: 0031
amended_by: 0038
---

# A resposta da API da Ana é dimensionada pelo teto de leitura do cliente

O ADR 0031 criou a API da Ana devolvendo cada tabela inteira, com todos os campos. A plataforma que hospeda a Ana (fazer.ai agents) corta o corpo de **toda** resposta de HTTP tool em **4.000 caracteres** antes de entregar ao modelo: limite fixo no runtime dela (`maxResponseChars` em `src/graph/tools/http.ts`), sem env nem configuração. O que passa do teto o modelo não lê, e o corte é mudo: a Ana afirma que o item não existe, ou repete a chamada em loop.

A medição de 18/ago/2026 contra a produção mostrou o tamanho do problema: exames 7.698 chars, convênios 4.970, consultas 5.008, cirurgias 3.347 (única que cabe, com 1.089 chars por linha, ou seja, a 4ª cirurgia cadastrada estoura). Na prática a Ana já não enxergava Pediatria nem Urologia, e desativar a Dermatologia no admin encolhia a resposta e fazia a Pediatria reaparecer: hoje editar um item muda quais **outros** itens a agente consegue ver.

O teto é do cliente, não deste app, e nenhum acordo verbal o segura. Ele vira, então, uma regra do servidor.

## Decisões

**1. Filtro por termo em cada GET de tabela.** `?especialidade=` (consultas), `?exame=` (exames), `?procedimento=` (cirurgias), `?convenio=` e `?especialidade=` combináveis (convênios). Parâmetro **ausente ou string vazia significa sem filtro**: o cliente interpola variável não preenchida como string vazia, em silêncio, e a API não pode ler isso como busca por vazio.

**2. Comparação normalizada.** O termo casa ignorando caixa, acento e pontuação, e exige que todas as palavras dele apareçam no nome do registro (`obstetricia` acha "Obstetrícia"; `raio x` acha "Raio-X (RX)"). O filtro roda na aplicação, sobre as linhas já lidas (3 a 20 por tabela), sem extensão nova no Postgres.

**3. Três degraus de resposta, escolhidos pelo tamanho.** O endpoint monta a resposta **completa**; se ela passar de **3.500 caracteres** (o teto de 4.000 com folga), cai para o **resumo** (nome e valor de vitrine); se ainda passar, cai para o **índice** (só os nomes). O degrau é sempre decidido no servidor, com ou sem filtro: nenhuma resposta da API da Ana sai maior que 3.500 caracteres.

**4. Item nunca some.** A degradação tira campo, jamais linha. Cortar a lista é exatamente o defeito que esta decisão existe para matar.

**5. O degrau é declarado no corpo.** Toda resposta traz `modo` (`completo`, `resumo` ou `indice`) e `dica`, a frase que ensina o gesto seguinte ("chame de novo com `?exame=NOME` para os detalhes"). Sem isso o modelo lê campo ausente como dado inexistente e responde errado.

**6. O aviso obrigatório não se perde no resumo.** As cirurgias carregam `caveat_obrigatorio_ana`, que a Ana precisa dizer junto do valor. No resumo ele sai da linha e entra uma vez no envelope, com o texto vindo do banco (é conteúdo editável pelas secretárias, não literal no código).

**7. Filtro sem resultado devolve 200 com lista vazia e `disponiveis`**, os nomes que existem, sem valor. O modelo vê que não achou, vê o nome certo e reencaminha, em vez de insistir na mesma chamada. Sem preço junto, não há como confundir a lista com resultado.

**8. A regra vale para todo endpoint futuro de `/api/ana/*`** que devolva lista, e é provada por teste com a tabela inflada a 3x o volume de hoje, não só com os dados atuais.

## Considered options

- **Só o filtro, sem regra de tamanho:** rejeitado pela medição. Termo curto casa quase tudo (`?exame=a` devolve 9 exames, 6.878 chars) e o estouro volta em silêncio.
- **Paginação (`?limite=`, `?pagina=`):** rejeitado. Transfere ao modelo a responsabilidade de saber que existe página 2, e a falha é a mesma de hoje: ele conclui a partir do que veio.
- **Cortar a lista no servidor até caber:** rejeitado pela decisão 4. Seria reproduzir o corte da plataforma com outro nome.
- **Pedir limite configurável à plataforma:** já registrado do lado da Ana como report ao fornecedor, mas não é dependência: a correção não pode esperar terceiro.
- **Resumo só quando não houver filtro, sem degrau no meio:** rejeitado. Convênios com 46 linhas (6 convênios por 8 especialidades, tamanho plausível já em 2026) passa de 3.500 mesmo resumido, e sem o terceiro degrau a resposta estouraria.

## Consequências

- A forma da resposta passa a depender do volume dos dados: a mesma chamada devolve `completo` hoje e `resumo` depois de o hospital cadastrar mais linhas. É intencional, e por isso o `modo` é explícito no corpo.
- Um registro sozinho maior que 3.500 caracteres cairia para resumo mesmo filtrado, e aí o detalhe pedido não chega. Não acontece hoje (maior registro: 1.181 chars, uma cirurgia); se acontecer, o caminho é encurtar o texto no admin, não subir o teto.
- O consumidor precisa acompanhar: do lado da Ana, cada tool ganha o campo opcional de filtro no `input_schema` e uma linha na descrição. Enquanto isso não é feito, a Ana enxerga a tabela inteira em vitrine (nome e valor), o que é melhor que a cegueira atual.
- O teto de 4.000 é fato externo e pode mudar quando a plataforma da Ana mudar. Ele vive numa constante única, comentada com a origem, e é o único ponto a ajustar.
