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
A sequência de chamadas LLM que transforma Transcrição em Ata (extrair fala → casar participantes → resumir → estruturar JSON → gerar Ata em português → PDF). OpenRouter é o provedor único (hoje roteia um modelo OpenAI); sem chave configurada, em desenvolvimento, o Pipeline cai num mock.
_Evitar_: processamento, job de IA.

## Pendências

**Pendência**:
Uma ação atribuída a um responsável, com prazo e máquina de estados própria (`PENDENTE → EM_PROGRESSO → CONCLUIDO`; ramos `ATRASADO`, `CANCELADO` e `REPACTUADA`). Nasce quando o compromisso do responsável se firma, e desde o primeiro segundo é plena (painel, prazo, cobrança). No caminho com assinatura o nascimento é **incremental** (ADR 0030): a assinatura do responsável no ClickSign cria as dele; a assinatura do Facilitador cria as de quem está fora do Envelope; o Aceite interno cria as do aceitante; a finalização do documento cria todo o resto. No caminho sem assinatura, todas nascem na aprovação (**APROVADA**, ADR 0003).
_Evitar_: tarefa, to-do, ação (use "ação" só para a linha da Ata que origina a Pendência).

**Repactuação**:
O ato de o Facilitador remarcar o prazo de uma Pendência. Gera uma **nova** Pendência e mantém a original no histórico (estado `REPACTUADA`). É o caso mais comum a partir de `ATRASADO`.
_Evitar_: adiamento, remarcação, prorrogação.

## Assinatura digital

**Envelope**:
O container da ClickSign que agrupa o PDF da Ata e seus Signatários. Identificado por `envelope_key_clicksign`. Fecha de dois jeitos, e ambos são **finalização**: todos assinam, ou o deadline (30 dias) estoura e a ClickSign fecha com as assinaturas que tiver. Nos dois casos a Reunião vira ASSINADA; quando faltou gente, o banner ganha um selo discreto "N de M assinaram". Recusa ou cancelamento matam o Envelope sem reenvio: a coleta dos compromissos restantes segue por **Aceite interno** (ADR 0030).
_Evitar_: documento, contrato, pacote.

**Aceite interno**:
O equivalente funcional da assinatura, colhido pelo próprio sistema quando o Envelope morre (recusa ou cancelamento). O Signatário pendente com ações recebe email com link público tokenizado, vê a ata completa e clica "Li e aceito": nascem de uma vez todas as Pendências dele, e o aceite conta como o "assinou" dele no desfecho. O Super admin pode registrar o aceite em nome de um signatário (auditado em `audit_log`). Não é assinatura digital: a formalidade ClickSign continua exclusiva do Envelope. Signatário sem ação não recebe link nem trava o desfecho.
_Evitar_: assinatura interna, aceite manual, ciência.

## Controle e custos de IA

Área transversal do Super admin: observa o sistema todo, já que Reuniões, POPs e Auditoria de Pessoal compartilham o mesmo **Pipeline de IA**. O acesso é **mais estreito que o de Super admin**: hoje só o Engenheiro de IA enxerga, não os 6 super admins.

**Controle**:
A área (box) administrativa de observabilidade, dentro de `/admin`. Primeira e, por ora, única subaba: **Custos**. Nasce restrita a um único operador (o Engenheiro de IA), separado do conjunto de Super admin.
_Evitar_: painel, dashboard, admin.

**Custos**:
A subaba que mostra o gasto de IA em dólar (o que debita do crédito no OpenRouter). Tem duas visões: **Visão geral** (indicadores e gráficos por dia, feature, modelo e responsável) e **Interações** (a lista das Chamadas de IA, uma por linha, filtrável). Responde onde o gasto se concentra e quanto custou cada ação.
_Evitar_: billing, faturamento.

**Chamada de IA**:
A unidade atômica de custo: uma das chamadas LLM do Pipeline de IA (ou de um chat, ou a estimativa da transcrição de voz), com custo próprio em dólar, tokens, modelo, o responsável que a disparou e a referência da Reunião ou POP. É o grão que o sistema registra, sempre **sem guardar o conteúdo** do prompt ou da resposta (ADR 0010). O custo é o valor real devolvido pelo OpenRouter, exceto a transcrição de voz, que é estimada e marcada como tal.
_Evitar_: request, log de IA.

**Operação**:
A ação de negócio que o Facilitador ou elaborador enxerga (gerar uma Ata por Transcrição, uma sessão de Ata Guiada, elaborar um POP) e que agrupa uma ou mais Chamadas de IA. É o nível em que o custo é lido de forma agregada. O que o dono chamou de "interação" costuma ser uma Operação.
_Evitar_: interação, aquisição (ambíguos entre a Chamada de IA e a Operação).

**Responsável (por uma Chamada de IA)**:
Quem disparou a ação naquele request, o usuário autenticado, e não o dono do artefato. Se a Secretária sobe a Transcrição da Reunião de outro Facilitador, a Chamada de IA é contada para a Secretária; a Reunião fica só como referência.
_Evitar_: autor, dono.

## Dados do Atendimento (Ana)

Área nascida no ADR 0031 (14/ago/2026): o app vira a casa dos dados que alimentam a **Ana**, e ganha a primeira API de serviço para outro sistema.

**Ana**:
A agente de IA de atendimento e agendamento de pacientes via WhatsApp do mesmo hospital: produto irmão, com repo e roadmap próprios (`~/PedroDev/Ana`). Consome dados deste app pela [API da Ana]; não loga, não tem conta, não é usuária.
_Evitar_: tratar a Ana como feature deste app (é cliente de serviço).

**Dados do Atendimento**:
O módulo da área admin com as tabelas que alimentam a Ana: consultas particulares (preços e diferenciais), exames, estimativas de cirurgias e convênios por especialidade. Super admins e secretárias editam; facilitadores leem. Edição vale imediatamente para a Ana (leitura direta, sem cache). Substitui a planilha do NocoDB (aposentado pelo ADR 0031).
_Evitar_: "tabelas do NocoDB" (a casa agora é aqui); cache entre a edição e a API.

**Protocolo de ouvidoria**:
O número que a Ana informa ao paciente ao registrar uma manifestação de ouvidoria, formato `ANO-NNNN` (ex.: 2026-0007), gerado por sequence do Postgres, nunca pela aplicação nem por IA; NNNN contínuo, não reinicia por ano. O app guarda só o **índice** da manifestação (categoria, setor, resumo, status, prazo, `conversa_id`): nome, CPF e relato do manifestante vivem na conversa do Chatwoot da Ana e **nunca entram neste banco**. O painel de ouvidoria mostra os protocolos e permite mudar o status (aberto/respondido).
_Evitar_: dado pessoal do manifestante em qualquer coluna; compor ou estimar número fora da sequence; reiniciar a numeração.

**API da Ana**:
Os endpoints de serviço `/api/ana/*`: leitura das tabelas do Dados do Atendimento, registro e consulta de protocolo de ouvidoria. Autenticação por **API key de serviço** dedicada (header), fora do fluxo JWT do Supabase Auth; a chave vive no vault da plataforma da Ana e o escopo é restrito a esses endpoints. Nos endpoints de escrita, campo crítico é NOT NULL e validado (o cliente tem falha silenciosa conhecida que enviaria vazio com HTTP 200; o banco recusa).
_Evitar_: reusar a key para outros consumidores; endpoint anônimo; expor esses endpoints no fluxo JWT comum.

**Modo de resposta (API da Ana)**:
O degrau de detalhe que a [API da Ana] escolhe **pelo tamanho** da resposta, para caber no teto de leitura do cliente (a plataforma da Ana corta toda resposta de tool em 4.000 caracteres, sem aviso). São três, do mais rico ao mais magro: `completo` (todos os campos), `resumo` (a vitrine: nome e valor) e `indice` (só os nomes, cada item em texto e não em objeto, porque repetir o nome do campo em cada linha é o que faz o degrau mais magro estourar; no convênio o nome é o par convênio e especialidade). O endpoint monta o `completo`; se passar de 3.500 caracteres, desce um degrau, e depois outro. Tirar campo é permitido, **tirar linha nunca**: cortar a lista é o defeito que a regra existe para matar (ADR 0032). O corpo sempre declara o `modo` e a `dica` do gesto seguinte. Cada GET de tabela aceita um filtro por termo (`?exame=`, `?especialidade=`, `?procedimento=`, `?convenio=`), com termo vazio valendo como sem filtro.
_Evitar_: paginação; cortar a lista para caber; supor que a mesma chamada devolve sempre a mesma forma.

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
