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
- `dados_do_google`: monta o payload da tela Dados do Google (#817), com todos
  os relatórios dela numa ida só à GA4.
- `provedor_instagram`: o provedor de dados do Instagram, o ÚNICO ponto do app
  que fala com a Graph API do Instagram (#819). Seguidores e crescimento,
  Alcance, Visualizações, Interações e as partes, Contas que engajaram e as
  Principais publicações. Na tela diz-se sempre "Instagram".
- `instagram`: monta o payload da tela do Instagram (#819).
- `cache`: o cache com frescor de 1 hora, em memória do processo, com o último
  valor bom quando a fonte cai (#815). O Ao vivo nunca passa por ele.
- `telas`: o registro das telas lidas pelo cache, uma chave por tela e
  período, com o frescor no payload e o Atualizar agora (#815). Tela nova
  entra no registro e ganha os três.

O que ainda vem, cada um no seu módulo: a tela de Objetivos e o conector MCP.
"""
