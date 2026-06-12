---
status: accepted
---

# Resolução de responsável ao vivo na Ata Guiada: LLM conversa, backend vincula

Na Ata Guiada, o responsável de cada ação era texto livre de ponta a ponta: o agente escrevia no quadro o nome como ouvido ("Lucas", "Pedro"), sem enxergar nem o roster da Reunião nem o cadastro. O vínculo com um Colaborador só era tentado depois, dentro de `liberar_pendencias`, por um `ILIKE %nome%` que pega o primeiro resultado — invisível para o Facilitador e frágil a homônimos. Pior: mesmo a edição manual na validação (`PATCH quadro-atribuicoes`, combobox) recebia o `responsavel_participante_id`, usava-o para copiar nome/cargo canônicos e **descartava o id**. Em nenhum ponto da cadeia o vínculo existia de fato. E com a finalização num clique (#66, evolução da ADR 0006), o fluxo guiado nem passa mais pela tela de validação — a conversa é a única revisão antes de a Pendência nascer.

A decisão, em quatro movimentos:

- **Resolução ao vivo, híbrida: o LLM conversa, o backend vincula.** A lista de candidatos (roster da Reunião anotado + cadastro de participantes ativos, com cargo/setor) entra no prompt do chat — o agente passa a falar e escrever os nomes canônicos e a perguntar quando há ambiguidade ("qual Lucas — Lucas Silva, de TI, ou Lucas Mendes, do RH?") ou quando não encontra o nome ("não achei Fernanda no cadastro — é alguém de fora?"). Mas o `responsavel_id` é resolvido **deterministicamente pelo backend a cada turno**, com a cascata do `participant_matcher` (a mesma do Pipeline de Transcrição; auto-match no threshold padrão). O LLM nunca decide FK.
- **Candidatos: roster primeiro, cadastro geral como fallback** — a mesma regra da extração de Pendências da Nota (`extracao_pendencias_service`). Quem não casa fica **externo**: só o nome, sem id, sinalizado no quadro, sem insistência depois da primeira pergunta.
- **O vínculo viaja no quadro, fim a fim.** O item do `quadro_atribuicoes` ganha `responsavel_id` (nullable): anotado a cada turno no rascunho, persistido pelo `concluir` no `json_ata`, gravado (e limpo, quando texto livre) pelo `PATCH quadro-atribuicoes` — que hoje o descarta — e **honrado por `liberar_pendencias`**, que só cai na Resolução por nome quando o id está ausente (atas antigas, externos).
- **Upsert no roster ao concluir.** Responsável casado fora do roster é adicionado a `reuniao_participantes` no `concluir` — espelha o que o Pipeline de Transcrição já faz com os participantes detectados e mantém o invariante do combobox da validação (responsável escolhível ⊆ roster). Sem efeito de assinatura: Ata Guiada nunca vai à ClickSign. Durante o chat nada persiste — o rascunho segue efêmero (ADR 0006).

## Por que é surpreendente

- **O backend recalcula o que o LLM acabou de escrever.** Com a lista no prompt, o agente já devolve "Lucas Silva" — parece redundante rodar o matcher de novo. Não é: FK decidida por modelo generativo é erro plausível e silencioso (id de outro Lucas, id inexistente), exatamente o tipo de falha que a feature existe para eliminar. O nome é conversa; o id é dado — e dado vem de código determinístico.
- **A FK vive dentro de um JSON.** `responsavel_id` dentro do `json_ata` não tem integridade referencial do banco. Aceito de propósito: o quadro é rascunho dentro da Reunião (shape enxuto da ADR 0005), e a Pendência — onde o vínculo vira cobrança — tem FK real (`pendencias.responsavel_id`). O `concluir` revalida os ids server-side (existente e ativo no cadastro); id inválido cai para Resolução por nome.
- **O ✓ do quadro é promessa, não decoração:** o que o Facilitador vê vinculado na conversa é exatamente o que `liberar_pendencias` grava — zero rematch surpresa no fim.

## Alternativas descartadas

- **LLM decide a FK** (devolve `responsavel_id` direto no rascunho): menos código, mas id alucinado/trocado é silencioso e mina a confiança que a feature quer construir.
- **Backend cego, sem lista no prompt** (matcher pós-turno apenas): vincula certo, mas a conversa não muda — o agente seguiria dizendo "Lucas" sem saber perguntar "qual Lucas?"; a segurança não apareceria na interação, que era o pedido.
- **Sem id no quadro; rematch melhor na liberação** (trocar o ILIKE pela cascata): o vínculo exibido na conversa não seria garantido na Pendência — desambiguações feitas pelo Facilitador na conversa poderiam ser desfeitas pelo rematch final.
- **Id resolvido só na conclusão**: sem ✓ confiável ao vivo nem base determinística para as perguntas de desambiguação durante a montagem.
- **Combobox de participantes no quadro ao vivo**: corrigir durante a montagem segue conversacional (⌖) — editar à mão um rascunho que o LLM reescreve a cada turno exigiria protocolo de proteção por item, para um ganho que a conversa já cobre. O ajuste manual com dropdown continua onde existe: na validação (fallback da Guiada e fluxo por Transcrição).

## Consequências

- O prompt do chat guiado ganha o bloco de candidatos (roster + cadastro ativo, com cargo/setor). O cadastro é pequeno (dezenas); se crescer, esse bloco é o primeiro candidato a filtro.
- Novo campo opcional `responsavel_id` no shape do item do quadro (rascunho e `json_ata`) — aditivo; atas existentes seguem válidas.
- `liberar_pendencias` honra `responsavel_id` quando presente; o fallback por nome continua para atas antigas e itens sem vínculo. Quando há vínculo, o cargo exibido/persistido é o canônico do cadastro, não o ouvido na conversa.
- `PATCH quadro-atribuicoes` passa a gravar/limpar o `responsavel_id` que hoje valida e descarta.
- `concluir` revalida os vínculos server-side e faz o upsert do roster.
- Glossário (`CONTEXT.md`) atualizado: novo verbete **Resolução**; **Participante** referencia a Resolução; **Ata Guiada** menciona a Resolução ao vivo.
