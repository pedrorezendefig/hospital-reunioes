---
status: accepted
amends: 0082, 0039
---

# O agente de triagem da Ouvidoria lê toda manifestação e toda avaliação na chegada

Decisão do diretor no Planejamento da Demanda (PRD #1527, decisões 5 e 18) e do Pedro no grill técnico de 11/11/2026. A especificação da Diretoria pede que um agente escreva o assunto de cada caso, aponte os casos para o Núcleo de Segurança do Paciente e marque as avaliações graves. Duas ADRs aceitas impediam: a 0082 (nenhuma IA com custo roda sem ação humana) e a 0039, decisão 4 (a IA da Ouvidoria recebe o agregado, nunca o relato).

## Decisões

1. **Exceção à decisão 1 da ADR 0082.** O agente roda sozinho na chegada de toda manifestação, de qualquer canal, e de toda avaliação com comentário. Quem dispara é o envio, não um relógio: não há job, não há retentativa. É uma chamada em segundo plano, uma vez por caso.

2. **Só sugere.** O agente escreve o **assunto** (uma linha, sem nome de pessoa nem dado clínico identificável), o **apontamento ao Núcleo** (com uma justificativa simples, para o ouvidor, e uma técnica, para o Núcleo) e a marca **Para revisar** na avaliação cujo comentário sugere gravidade. Nunca grava tipo, gravidade, sigilo nem área (ADR 0037), e nada do que ele escreve sai para o paciente ou para um setor sem confirmação de uma pessoa.

3. **Se o agente falhar, nada trava.** O caso entra na fila sem assunto e sem alerta, e o ouvidor lê e decide sozinho sobre o Núcleo. As listas mostram que o assunto não foi gerado.

4. **O agente lê todos os relatos, inclusive os sigilosos (emenda a decisão 4 da ADR 0039).** Uma denúncia também pode descrever risco ao paciente. Antes de sair do app, o relato passa pelo `pseudonimizar` de `app/services/ouvidoria_pseudonimizacao.py`, como manda a ADR 0034 (pseudonimização antes de IA externa): nome, CPF, telefone, e-mail e os outros identificadores viram marcador, e o relato cru nunca vai para a Anthropic. O assunto e o alerta do Núcleo não dependem de nome. O texto pseudonimizado vai para a API da Anthropic com a retenção padrão (até 30 dias) e sem uso para treino, como na ADR 0074, que também desidentifica antes de enviar. O relatório mensal continua recebendo só o agregado.

5. **Modelo, custo e teto.** O agente usa `claude-sonnet-5-5`, com custo estimado em cerca de US$ 0,01 por caso. O teto é de 300 chamadas por dia no app inteiro (no máximo cerca de US$ 3 por dia, contra quem enche o formulário). Passado o teto, o agente pula o caso, com log e registro na trilha, e o caso segue o caminho da decisão 3.

6. **A salvaguarda da resposta não precisa de exceção.** No caso com o selo "Em análise pelo NSP", o agente lê a resposta ao manifestante antes do envio e aponta frases que admitem ou negam falha. Quem dispara é o clique do ouvidor, o que já cabe na ADR 0082.

7. **A saída passa pelo sanitizador** (ADR 0013), como todo texto gerado.

## Alternativas consideradas

- **Botão "Triar" com estimativa, como manda a ADR 0082**: rejeitada. O assunto e o alerta do Núcleo só servem se estiverem lá quando o ouvidor abre a fila.
- **Não mandar o relato sigiloso**: rejeitada pelo diretor. A denúncia de maus-tratos é justamente a que mais precisa do alerta.

## Consequências

- O custo da Ouvidoria passa a variar com o volume do canal público, limitado pelo teto diário.
- Job novo que chame IA continua precisando de ADR que emende a 0082. Esta exceção vale só para a chegada de caso e de avaliação.
