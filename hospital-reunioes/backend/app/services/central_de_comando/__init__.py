"""Central de Comando: os números do Site e do Instagram do hospital (ADR 0058).

A Central era um app à parte (`pedroribbe/central-de-comando-hsm`) e mora aqui
desde o PRD #809, só para Super admin, sem tabela nenhuma: tudo o que ela mostra
é lido da fonte na hora (stateless). Os testes de `src/lib` de lá são a
especificação do porte: cada regra portada tem o seu teste equivalente aqui.

Um módulo por assunto, para as fatias do PRD acrescentarem sem reescrever:

- `periodo`: os períodos de 7, 28 e 90 dias e o período anterior de mesmo
  tamanho, em UTC, terminando ontem. Regra pura, sem I/O.
- `variacao`: a variação relativa contra o período anterior. Regra pura.
- `provedor_google`: o provedor de dados do Google, o ÚNICO ponto do app que
  fala com o Google Analytics. Cada número do Site é uma função dele.
- `visao_geral`: monta o payload da tela Visão Geral. Cada bloco da tela é uma
  chave do payload.

O que ainda vem, cada um no seu módulo: o cache com frescor (#815), o provedor
de dados do Instagram (#819), as telas de Dados do Google, Instagram e
Objetivos, e o conector MCP.
"""
