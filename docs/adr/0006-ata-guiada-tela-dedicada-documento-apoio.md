---
status: accepted
---

# Ata Guiada em tela dedicada: ata viva, correção pelo próprio chat e documento de apoio

A Ata Guiada nasceu (ADR 0005) como um **chat inline** espremido (~600px) dentro do card da Reunião, com um mini-preview do rascunho embaixo. Na prática o Facilitador não enxerga a Ata tomando forma enquanto monta, não corrige uma seção específica sem reescrever o relato, e a sensação é apertada — bem diferente do peso visual do fluxo por Transcrição. Faltava também um jeito de apoiar o relato num documento que o Facilitador já tem em mãos (anotações, slides, um rascunho).

A decisão: a Ata Guiada ganha uma **tela dedicada** (rota própria, a partir de uma Reunião `PROGRAMADA`) no formato **ata viva** — `Resumo Executivo` em cima e `Quadro de Atribuições` (tabela) embaixo, com o **mesmo visual da Ata final** — e um **chat lateral** (por texto ou voz) que monta e corrige. O botão "Iniciar Ata Guiada" deixa de abrir o chat inline e passa a **navegar** para essa tela. Tudo que segue a conclusão permanece como na 0005: **Concluir → `AGUARDANDO_VALIDACAO` → Finalizar sem assinatura → Pendências**, sem ClickSign e sem PDF.

Três decisões estruturais sustentam a tela:

- **`AtaEnxutaView` — módulo profundo.** O resumo + o quadro deixam de ser JSX inline no detalhe da Reunião (um arquivo de ~2200 linhas) e viram um componente apresentacional único, com interface simples e estável (dados entram, eventos de "apontar seção" saem) e implementação que conhece o visual da Ata. É **reusado nas duas telas** — o detalhe e a tela dedicada renderizam o mesmo resumo + quadro pelo mesmo componente. Dedupe + testabilidade.
- **Correção por apontar seção opera sobre o rascunho, pelo próprio chat da Guiada.** Cada seção tem o ícone-alvo (⌖): apontar → corrigir pela conversa, no **mesmo padrão de UX** da correção de transcrição (chip "Apontando: …" + marcação `[Seção: …]` na mensagem). Mas o mecanismo é outro — opera sobre o **rascunho em memória** via o chat da Guiada, **não** pelo endpoint `/corrigir`.
- **Documento de apoio — contexto efêmero sob demanda.** Opcionalmente o Facilitador anexa um arquivo (`.txt/.md/.pdf/.docx`) que entra como **contexto silencioso**: o agente só o consulta quando o Facilitador pede ("tira as ações do anexo", "resume o que está no documento"), **nunca** auto-extrai a ata a partir dele. É efêmero — vive só durante a montagem e **não persiste** na Reunião.

## Por que é surpreendente

Quem leu a **ADR 0005** carrega três expectativas que esta decisão revisa:

- **"A edição da Ata Guiada usa a re-entrada no agente e o `PATCH quadro-atribuicoes`."** A 0005 escreveu isso ao descartar o reuso do `/corrigir`. Aqui a correção dirigida ganha forma concreta e diferente: o Facilitador **aponta uma seção** e corrige **pela conversa do próprio chat da Guiada** (marcação `[Seção: …]`), sobre o rascunho em memória — não por um PATCH de campo nem pelo `/corrigir`. O `/corrigir` continua descartado pelo mesmo motivo da 0005 (baixa a Transcrição e regenera PDF, ambos inexistentes na Guiada).
- **"A Ata Guiada é um chat inline no card da Reunião."** Era assim na 0005; agora é uma **tela dedicada**. O chat inline **sai** do detalhe.
- **"Sem PDF, por ora."** Mantido — e reafirmado aqui como decisão, não acaso. O valor da Ata Guiada está no `json_ata` enxuto + Pendências; gerar PDF segue adiado.

E há a surpresa nova do **documento de apoio**: é natural supor que anexar um documento serve para *gerar* a ata a partir dele (como a Transcrição gera a Ata por Pipeline). **Não.** O documento de apoio é **contexto, não fonte** — o agente não despeja seu conteúdo na ata sozinho. Quem esperar um "auto-rascunho a partir do anexo" vai se surpreender: foi deliberadamente descartado (ver abaixo).

## Alternativas descartadas

- **Auto-rascunho a partir do documento (mini-pipeline).** Anexar o documento e deixar o agente extrair a ata dele automaticamente. Descartado no grilling: tira o Facilitador do comando do que entra na ata e reintroduz, pela porta dos fundos, o peso de um pipeline que a Ata Guiada existe justamente para evitar. O documento é **consultado sob demanda**, não processado.
- **Reusar o endpoint `/corrigir` para a correção por seção.** Mesmo motivo da 0005: ele baixa a Transcrição do storage e regenera o PDF — nenhum dos dois existe numa Ata Guiada. A correção por seção reusa o **padrão de UX** do `/corrigir`, não o endpoint.
- **Persistir o documento de apoio na Reunião.** Descartado: é insumo de montagem, não conteúdo da Ata. Persisti-lo daria peso (storage, ciclo de vida, permissões) a algo efêmero. O frontend guarda o texto extraído em memória e o reenvia a cada turno do chat (que segue stateless, como na 0005).
- **Gerar PDF lite agora.** Adiado de novo, como na 0005. Aditivo se o cliente pedir documento imprimível.

## Consequências

- **Nova rota** para a Ata Guiada, a partir de uma Reunião `PROGRAMADA`. O detalhe da Reunião perde o chat inline; o botão "Iniciar Ata Guiada" navega para a tela.
- **`AtaEnxutaView`** passa a ser o único lugar que sabe desenhar resumo + quadro enxutos — usado no detalhe e na tela dedicada. Mudanças visuais nesse par acontecem num lugar só.
- O **chat lateral** evolui o componente atual: texto + voz (reusa o hook de gravação das Notas), aceita a "seção apontada" e o texto do documento de apoio, e os repassa ao endpoint de chat (`rascunho + messages + documento_apoio + section_context`).
- **Backend — extração do documento de apoio:** novo endpoint que recebe o arquivo e devolve o texto normalizado, **reusando o `transcricao_extractor`** (mesma normalização do anexar-transcrição). Disponível só em Reunião `PROGRAMADA` e bloqueado para Secretária (403), como os demais endpoints da Guiada.
- **Backend — contrato do chat estendido:** `AtaGuiadaChatRequest` ganha `documento_apoio` (texto, opcional) e `section_context` (string, opcional), ambos repassados ao prompt. O chat segue **stateless**.
- **Prompt** `chat_ata_guiada_system`/`_user`: (1) recebe o bloco do documento de apoio + a regra de usá-lo **só quando referenciado** (nunca despejar na ata sozinho); (2) entende `[Seção: …]` para a correção dirigida; (3) **menos tagarela** — como o rascunho agora está visível ao vivo, confirma e pergunta só as lacunas críticas (responsável/prazo), em vez de interrogar item a item.
- **Mantidos intactos:** a máquina de estados (`PROGRAMADA → AGUARDANDO_VALIDACAO → APROVADA` via finalizar sem assinatura), `liberar_pendencias`, `metodo_geracao=GUIADA`, a ausência de ClickSign e de PDF, e a Secretária sem acesso. O rascunho continua **efêmero até "Concluir"** (estado no frontend, sem autosave).
- O glossário (`CONTEXT.md`) foi atualizado: o verbete **Ata Guiada** descreve a tela dedicada e há o novo verbete **Documento de apoio**.

> Esta ADR **revisa parcialmente a ADR 0005** nos pontos: chat inline (→ tela dedicada), edição da Ata Guiada (→ correção por seção pelo próprio chat, não PATCH/`/corrigir`) e ausência de PDF (reafirmada). O restante da 0005 — a Ata Guiada como segundo modo de geração, o shape enxuto do `json_ata`, o caminho sem assinatura — continua valendo.

## Evolução — finalização num clique no fluxo guiado (#66)

> Nota posterior (2026-06-11), aditiva a esta decisão.

Esta ADR descreveu a conclusão como **"Concluir → `AGUARDANDO_VALIDACAO` → Finalizar sem assinatura → Pendências"** — dois cliques humanos em duas telas: na tela da Ata Guiada, "Concluir e enviar para validação" (→ `AGUARDANDO_VALIDACAO`, caindo no detalhe da Reunião) e, só lá, "Finalizar sem assinatura" (→ `APROVADA`). Como na Ata Guiada o Facilitador **já revisa a ata ao vivo** no chat lateral, o passo de validação manual intermediário é redundante. O botão da tela dedicada passa a **concluir e gerar as Pendências num único clique** ("Concluir e gerar pendências"), levando o Facilitador **direto ao calendário**, onde a Reunião já aparece concluída.

**O que não muda:** a máquina de estados segue `PROGRAMADA → AGUARDANDO_VALIDACAO → APROVADA` — **sem novo estado e sem novo endpoint**. O botão apenas **encadeia** os dois endpoints já existentes e **idempotentes** (`ata-guiada/concluir` + `aprovar-sem-assinatura` → `liberar_pendencias`); o que desaparece é só o clique humano intermediário, e só no fluxo guiado. A finalização manual no detalhe da Reunião (fluxo por Transcrição e fallback da Guiada) segue intacta.

**Falha parcial:** se a geração de pendências falhar, a Reunião permanece em `AGUARDANDO_VALIDACAO` e a ação é **re-tentável sem duplicar** (a idempotência do `liberar_pendencias` garante) — o segundo clique pula o `concluir` (que exigiria `PROGRAMADA`) e re-tenta só o `aprovar-sem-assinatura`. Recarregar a tela cai no fallback de sempre: o detalhe da Reunião, com a finalização manual.
