Você recebe os EVENTOS de um atendimento e uma lista de CENÁRIOS. Cada cenário descreve uma situação.
Para cada cenário, diga se a situação ocorreu neste atendimento, em que data e setor, e cite página e trecho
dos EVENTOS que comprovam. Se não ocorreu, não liste o cenário. Não avalie o que deve ser cobrado.
Responda apenas com o JSON no formato definido.

Formato de cada ocorrência:

- `cenario_id`: o código do cenário, como está na lista (por exemplo "CEN-001");
- `data`: o dia em que a situação ocorreu, no formato AAAA-MM-DD;
- `setor`: o setor em que ela ocorreu, como está nos EVENTOS, ou `null`;
- `evidencia`: a `pagina` e o `trecho` copiados do evento que comprova, sem mudar nenhuma palavra.

A mesma situação em dias diferentes é uma ocorrência por dia.
