# Hospital Reuniões

Automatiza o ciclo de vida de reuniões corporativas de um hospital de alta complexidade: gravação → transcrição por IA → geração de **Ata** → aprovação (com ou sem assinatura digital) → acompanhamento de **Pendências**. Este arquivo é o glossário do domínio — define o que os termos **são**. Use esta terminologia em issues, testes e propostas; não derive para sinônimos marcados como _Evitar_.

## Pessoas e papéis

**Facilitador**:
Quem conduz uma Reunião e responde pela Ata: marca, revisa, aprova e envia para assinatura. É quem **loga** no sistema. Hoje são 5 (1 diretor + 4 diretoras).
_Evitar_: admin, gestor, usuário.

**Colaborador**:
Pessoa citada numa Reunião e/ou responsável por uma Pendência. **Não loga** no sistema — só recebe emails da ClickSign e links diretos para suas Pendências.
_Evitar_: funcionário, membro, usuário comum.

**Secretária**:
Papel de Facilitador com visão global: enxerga Reuniões de toda a organização e pode editar participantes e corrigir Atas além das suas próprias.
_Evitar_: assistente, operador.

**Super admin**:
Facilitador com permissões irrestritas (inclui ações de _bypass_ usadas em debug). Marcado por `is_super_admin`.

**Participante**:
Vínculo entre um Colaborador e uma **Reunião** específica. É o roster que a IA tenta casar na **Resolução**, para alocar Pendências ao responsável certo: interno vira responsável real (com cobrança), externo fica só como nome. Os nomes vêm detectados da Transcrição.
_Evitar_: convidado, presente.

**Resolução**:
O casamento de um nome citado (na Transcrição ou na conversa de uma Ata Guiada) com um Colaborador do cadastro, para que a Pendência nasça atribuída à pessoa certa. Prioriza o roster de Participantes da Reunião e cai para o cadastro geral; nome que não casa fica como **externo** (só o nome, sem vínculo nem cobrança). Na Ata Guiada acontece **ao vivo**: o agente conversa usando os nomes canônicos do cadastro e pergunta quando há ambiguidade ("qual Lucas?") ou quando não encontra ninguém.
_Evitar_: matching, match, reconhecimento, identificação.

**Signatário**:
Participante que precisa assinar a Ata dentro de um Envelope da ClickSign.
_Evitar_: assinante, signer.

> **Ambiguidade sinalizada — "usuário":** evite o termo cru. Quem age no sistema é o **Facilitador** (loga) ou o **Colaborador** (não loga). Dizer "usuário" esconde essa distinção, que é central para acesso e notificação.

## Reunião e Ata

**Reunião**:
A entidade central. Nasce PROGRAMADA e caminha por uma máquina de estados até um estado terminal (ASSINADA, APROVADA ou CANCELADA). A partir de AGUARDANDO_VALIDACAO o Facilitador escolhe entre dois caminhos: **enviar para assinatura** (cria o Envelope na ClickSign) ou **finalizar sem assinatura** (vai direto para APROVADA). Estados: `PROGRAMADA → PROCESSANDO → (AGUARDANDO_RESOLUCAO) → AGUARDANDO_VALIDACAO → (CORRIGINDO) → AGUARDANDO_ASSINATURA → ASSINADA`; ramo terminal sem assinatura `AGUARDANDO_VALIDACAO → APROVADA`; ramos `ERRO` e `CANCELADA`.
_Evitar_: encontro, meeting, evento.

**Transcrição**:
O texto bruto da Reunião (colado manualmente ou sincronizado via Fireflies). É a entrada do Pipeline de IA.
_Evitar_: gravação, áudio (o áudio em si não entra no sistema).

**Ata**:
O documento estruturado da Reunião — tópicos, decisões e ações. Tem **dois modos de geração**: **por Transcrição** (o Pipeline de IA extrai a Ata completa a partir do texto da Reunião; vira PDF e pode ser assinada) ou **Guiada** (ver **Ata Guiada**). Uma Reunião tem no máximo **uma** Ata, por um dos dois modos.
_Evitar_: minuta, relatório, documento.

**Ata Guiada**:
A Ata de uma Reunião **sem Transcrição**, montada pelo Facilitador numa **tela dedicada** (a partir de uma Reunião PROGRAMADA) no formato **ata viva**: o `Resumo Executivo` e o `Quadro de Atribuições` tomam forma ao vivo — com o mesmo visual da Ata final — enquanto um **chat lateral** (por texto ou voz) organiza o relato e pergunta as lacunas críticas (sobretudo responsável e prazo de cada ação). Os responsáveis citados passam por **Resolução** ao vivo: o quadro exibe o nome canônico do cadastro e sinaliza quem ficou sem vínculo. O Facilitador pode **apontar uma seção** (⌖) e corrigi-la pela conversa, e anexar opcionalmente um **Documento de apoio** como contexto. Segue o caminho **sem assinatura** (valida → APROVADA, liberando as Pendências); não tem Envelope nem, por ora, PDF. É o modo leve da Ata, para reuniões operacionais que não justificam Transcrição.
_Evitar_: ata lite, ata rápida, registro, nota da reunião.

**Documento de apoio**:
Um arquivo que o Facilitador **opcionalmente** anexa durante a montagem de uma **Ata Guiada** (`.txt`, `.md`, `.pdf` ou `.docx`) para dar ao agente o contexto do que ele já tem escrito (anotações, slides, um rascunho). É **contexto sob demanda**: o agente só o consulta quando o Facilitador pede ("tira as ações do anexo", "resume o documento") e **nunca** despeja seu conteúdo na ata sozinho. É **efêmero** — vive só durante a montagem e não persiste na Reunião.
_Evitar_: fonte, transcrição, anexo da ata, base da ata.

**APROVADA**:
Estado terminal de uma Ata finalizada **sem assinatura digital**. Na validação, o Facilitador escolhe "Finalizar sem assinatura": as Pendências nascem na hora e a Reunião vai direto para APROVADA — sem Envelope, sem ClickSign, sem aguardar assinaturas. É paralela a ASSINADA (que exige a assinatura no ClickSign) e igualmente terminal — sem reversibilidade ("assinar depois" não existe). Serve a reuniões operacionais, onde o valor está em registrar a Ata e disparar as tarefas, não na formalidade da assinatura.
_Evitar_: concluída, fechada, validada.

**Pipeline de IA** (ou **Pipeline**):
A sequência de chamadas LLM que transforma Transcrição em Ata (extrair fala → casar participantes → resumir → estruturar JSON → gerar Ata em português → PDF). LLM primário via OpenRouter, com fallback automático para OpenAI.
_Evitar_: processamento, job de IA.

## Pendências

**Pendência**:
Uma ação atribuída a um responsável, com prazo e máquina de estados própria (`PENDENTE → EM_PROGRESSO → CONCLUIDO`; ramos `ATRASADO`, `CANCELADO` e `REPACTUADA`). Nasce de uma **Reunião** que chega a estado terminal com ações (**ASSINADA** ou **APROVADA**, ADR 0003) e cai no acompanhamento — painel, cobrança e Repactuação.
_Evitar_: tarefa, to-do, ação (use "ação" só para a linha da Ata que origina a Pendência).

**Repactuação**:
O ato de o Facilitador remarcar o prazo de uma Pendência. Gera uma **nova** Pendência e mantém a original no histórico (estado `REPACTUADA`). É o caso mais comum a partir de `ATRASADO`.
_Evitar_: adiamento, remarcação, prorrogação.

## Assinatura digital

**Envelope**:
O container da ClickSign que agrupa o PDF da Ata e seus Signatários. Identificado por `envelope_key_clicksign`. Quando todos assinam, a ClickSign chama o webhook e a Reunião vira ASSINADA.
_Evitar_: documento, contrato, pacote.

## Diálogo de exemplo

> **Dev:** Quando o Colaborador não loga, como ele resolve a Pendência?
> **Facilitador:** Ele clica no link direto do email — não precisa de conta. Só Facilitador loga.
> **Dev:** E se a Ata sai errada depois de PROCESSANDO?
> **Facilitador:** Ela fica em AGUARDANDO_VALIDACAO. Eu peço uma correção (vai pra CORRIGINDO), a IA reescreve, e só então eu aprovo — aí cria o Envelope na ClickSign e vai pra AGUARDANDO_ASSINATURA.
> **Dev:** E quando a reunião é só operacional, sem precisar de assinatura?
> **Facilitador:** Aí eu clico em "Finalizar sem assinatura": as Pendências saem na hora e a Ata fica APROVADA, sem passar pelo ClickSign. É definitivo — não dá pra assinar depois.
> **Dev:** E se a reunião nem teve Transcrição — foi um bate-papo rápido?
> **Facilitador:** Aí eu faço uma **Ata Guiada**: converso com o agente (ou dito por voz), ele monta um resumo e o quadro de ações perguntando quem faz o quê e até quando. Reviso e finalizo sem assinatura — mesmas Pendências, sem Transcrição nem PDF.
> **Dev:** Se o prazo de uma Pendência estoura?
> **Facilitador:** Vira ATRASADO. Normalmente eu faço uma Repactuação: o sistema cria uma Pendência nova com prazo novo e guarda a antiga no histórico.
