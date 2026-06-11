---
status: accepted
---

# Ata Guiada: segundo modo de gerar a Ata, sem Transcrição

> **Revisada parcialmente pela [ADR 0006](0006-ata-guiada-tela-dedicada-documento-apoio.md).** Três pontos abaixo foram revisitados: o **chat inline** virou **tela dedicada** (ata viva); a **edição** da Ata Guiada (descrita aqui como "re-entrada no agente + `PATCH quadro-atribuicoes`") ganhou a forma concreta de **correção por apontar seção, pelo próprio chat da Guiada**; e a **ausência de PDF** foi reafirmada como decisão. O núcleo desta ADR — Ata como segundo modo de geração, `json_ata` enxuto, caminho sem assinatura — continua válido.

A diretoria precisa registrar **reuniões operacionais que não têm Transcrição** — bate-papos rápidos, 1-a-1 — gerando Pendências, mas com o documento **vinculado à Reunião** (1-a-1), não avulso. A **Nota** (ADR 0004) é deliberadamente **paralela/avulsa** e não preenche esse slot.

A decisão: a **Ata** passa a ter **dois modos de geração**. Além do modo **por Transcrição** (Pipeline de IA → Ata completa → PDF → assinatura/aprovação), criamos a **Ata Guiada**: o Facilitador conversa com um **agente** (por texto ou voz, reusando a transcrição de voz da Nota) que organiza o relato num documento **enxuto** — `resumo_executivo` + `quadro_atribuicoes` — direto no slot `reunioes.json_ata`, perguntando as lacunas (sobretudo responsável e prazo de cada ação). A Reunião vai de `PROGRAMADA` **direto** para `AGUARDANDO_VALIDACAO` (pulando `PROCESSANDO`/Pipeline); o Facilitador valida e **finaliza sem assinatura** (`APROVADA`, ADR 0003), liberando as Pendências pelo `liberar_pendencias` existente. Sem Envelope, sem PDF (por ora). Um novo campo **`metodo_geracao`** (`TRANSCRICAO` | `GUIADA`) em `reunioes` distingue os modos.

## Por que é surpreendente

O **ADR 0004 descartou** "dobrar a Reunião" (modo rápido sem transcrição) e criou a Nota no lugar. A Ata Guiada **revisita essa alternativa** — mas para um requisito diferente: registro **vinculado** à Reunião, não avulso. E a definição de **Ata** deixa de ser "o documento gerado a partir da Transcrição": agora **uma Ata pode existir sem Transcrição**. Quem ler o código esperando que toda Ata tenha `url_transcricao`/PDF, ou que `json_ata` sempre traga as 6 seções, vai se surpreender — a Ata Guiada tem `json_ata` **parcial** (só `resumo_executivo` + `quadro_atribuicoes`) e sem mídia.

## Alternativas descartadas e relação com o ADR 0004

- **Estender a Nota com `id_reuniao`**: quebraria o design da Nota (paralela por definição, ADR 0004) e daria estrutura a algo que é texto livre. A Nota continua avulsa; a Ata Guiada vive no slot da Reunião.
- **As objeções do 0004 a "dobrar a Reunião", reavaliadas**: (a) *"obrigaria a mexer no StatusAta"* — desnecessário: a Ata Guiada reusa `PROGRAMADA → AGUARDANDO_VALIDACAO → APROVADA`, sem novo estado; (b) *"carregaria 25+ colunas sem sentido para um bilhete"* — não se aplica: é uma **Reunião real**, com título, data, Facilitador e Participantes legítimos. O que tornava a fusão poluente no 0004 (um registro **avulso** forçado a virar Reunião) não existe aqui — o registro **é** de uma Reunião.
- **Reusar o chat de correção (`/corrigir`) para editar a Ata Guiada**: ele baixa a Transcrição do storage e regenera PDF — ambos inexistentes numa Ata Guiada. A edição da Ata Guiada usa a re-entrada no agente e o `PATCH quadro-atribuicoes` (já existente).
- **Sobrecarregar o campo `fonte`** (FIREFLIES/MOCK/IMPORTACAO_LEGADA) com um valor `GUIADA`: descartado. `fonte` responde "de onde veio o conteúdo bruto" — eixo ortogonal a "como a Ata foi gerada" — e é um enum **tipado na resposta da API**; um valor novo ali quebraria a serialização da lista de Reuniões. Por isso o campo novo e separado `metodo_geracao`.
- **Gerar PDF lite agora**: adiado. O valor está no `json_ata` + Pendências; gerar PDF exigiria um template novo. Fica como aditivo se o cliente pedir documento imprimível.

## Consequências

- `json_ata` passa a ter **dois shapes**: completo (Transcrição) e enxuto (Guiada). A renderização da tela de detalhe já é defensiva (seções ausentes somem); código que assuma `participantes`/`discussao`/`url_pdf_preliminar` presentes precisa tolerar ausência.
- Nova coluna `metodo_geracao` em `reunioes` (default `TRANSCRICAO`, para não afetar as Reuniões existentes).
- O agente da Ata Guiada é um **chat** — espelha o `chat_correcao` (síncrono, OpenRouter-only, histórico mantido no frontend) — **não** é o Pipeline de IA.
- A Ata Guiada **nunca toca a ClickSign**; segue só o caminho terminal APROVADA (ADR 0003).
- O glossário (`CONTEXT.md`) foi atualizado: verbete **Ata** agora descreve os dois modos e há o novo verbete **Ata Guiada**.
