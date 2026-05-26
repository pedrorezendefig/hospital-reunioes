# Hospital Reuniões

Automatiza o ciclo de vida de reuniões corporativas de um hospital de alta complexidade: gravação → transcrição por IA → geração de **Ata** → assinatura digital → acompanhamento de **Pendências**. Este arquivo é o glossário do domínio — define o que os termos **são**. Use esta terminologia em issues, testes e propostas; não derive para sinônimos marcados como _Evitar_.

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
Vínculo entre um Colaborador (ou nome detectado na transcrição) e uma Reunião específica. É o que a IA tenta casar na etapa de resolução.
_Evitar_: convidado, presente.

**Signatário**:
Participante que precisa assinar a Ata dentro de um Envelope da ClickSign.
_Evitar_: assinante, signer.

> **Ambiguidade sinalizada — "usuário":** evite o termo cru. Quem age no sistema é o **Facilitador** (loga) ou o **Colaborador** (não loga). Dizer "usuário" esconde essa distinção, que é central para acesso e notificação.

## Reunião e Ata

**Reunião**:
A entidade central. Nasce PROGRAMADA e caminha por uma máquina de estados até ASSINADA ou CANCELADA. Estados: `PROGRAMADA → PROCESSANDO → (AGUARDANDO_RESOLUCAO) → AGUARDANDO_VALIDACAO → (CORRIGINDO) → AGUARDANDO_ASSINATURA → ASSINADA`; ramos `ERRO` e `CANCELADA`.
_Evitar_: encontro, meeting, evento.

**Transcrição**:
O texto bruto da Reunião (colado manualmente ou sincronizado via Fireflies). É a entrada do Pipeline de IA.
_Evitar_: gravação, áudio (o áudio em si não entra no sistema).

**Ata**:
O documento estruturado que a IA gera a partir da Transcrição — tópicos, decisões e ações. Vira PDF e é o que se assina.
_Evitar_: minuta, relatório, documento.

**Pipeline de IA** (ou **Pipeline**):
A sequência de chamadas LLM que transforma Transcrição em Ata (extrair fala → casar participantes → resumir → estruturar JSON → gerar Ata em português → PDF). LLM primário via OpenRouter, com fallback automático para OpenAI.
_Evitar_: processamento, job de IA.

## Pendências

**Pendência**:
Uma ação atribuída a um responsável, criada quando uma Reunião vira ASSINADA com ações. Tem prazo e máquina de estados própria: `PENDENTE → EM_PROGRESSO → CONCLUIDO`; ramos `ATRASADO`, `CANCELADO` e `REPACTUADA`.
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
> **Dev:** Se o prazo de uma Pendência estoura?
> **Facilitador:** Vira ATRASADO. Normalmente eu faço uma Repactuação: o sistema cria uma Pendência nova com prazo novo e guarda a antiga no histórico.
