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

**Role (faixa hierárquica)**:
Etiqueta interna de administração (`diretor`, `gerente`, `coordenador`, `presidente`), derivada do cargo, com poder de permissão quase nulo (a permissão real vive em `access_profile` e `perfil_pop`). **Nunca aparece para o próprio Facilitador**; só o Super admin a vê, no painel de usuários (ADR 0033, risco trabalhista). O texto público de identificação de uma pessoa nas telas é o **cargo**.
_Evitar_: exibir role em tela de usuário final; confundir role com perfil de acesso.

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

**Manifestação**:
O caso de ouvidoria completo, que vive neste app desde o ADR 0034: relato integral sem edição, identificação de quem manifestou (ou anônima), contato, vínculo, classificação sugerida pela Ana à parte, marcos de tempo e desfecho. Substitui o "índice, não dossiê" do ADR 0031, que deixou de valer. Nasce **em classificação**: nenhum processo automático despacha, só quem tem o [Perfil da Ouvidoria] valida e aciona a área. Denúncia e relato de conduta nascem com **sigilo reforçado**: nem aparecem no índice de quem está fora da Ouvidoria. Quem diz que o caso é denúncia é o [Tipo da manifestação], nunca o texto digitado.
_Evitar_: "protocolo" como sinônimo (o Protocolo é o número, a Manifestação é o caso); mudar estado por fora da máquina de estados.

**Tipo da manifestação**:
O que a [Manifestação] é, em lista fechada: `denuncia`, `reclamacao`, `sugestao`, `elogio`, `relato_de_conduta` (ADR 0037). É ele, e só ele, que decide o **sigilo reforçado**: `denuncia` e `relato_de_conduta` são sigilosos por natureza, nos três canais, sem ato humano. A regra automática é **piso, nunca teto**: o ouvidor eleva o sigilo de um caso que a lista não previu, e não retira o de um tipo sigiloso por natureza. Tipo vazio significa **não classificado**, e o caso não classificado é sigiloso (fail-closed): é assim que entram o [Canal aberto] e o canal da Ana, e a saída é a classificação. Ao lado dele vive a **categoria**, rótulo humano em texto livre ("demora no atendimento", "conduta da equipe noturna"), que descreve o caso e não decide nada.
_Evitar_: ler a categoria para decidir sigilo (era a regra antiga, e "Assédio moral" não casava com termo nenhum); deixar a Ana mandar o tipo (ela registra, não classifica); tratar tipo vazio como caso comum.

**Classificação**:
O ato do [Perfil da Ouvidoria] que grava o [Tipo da manifestação], o rótulo e o sigilo do caso, e é a **única porta do sigilo**: sobe e desce no mesmo lugar, com movimento na trilha e registro no log de acesso. Acontece em duas telas com a mesma regra: dentro da [Validação e acionamento], para o caso que vai ser despachado, e no Dossiê, para o que já foi ou nunca vai ser. Sem pedido explícito, o sigilo de hoje é mantido: descer é ato consciente, não efeito colateral de reclassificar. A reabertura por reincidência só **eleva**, porque reabrir não é classificar.
_Evitar_: abaixar sigilo sem ato explícito; porta de sigilo separada da classificação; mudar sigilo sem deixar rastro com autor.

**Anexo (da Manifestação)**:
A evidência que fica junto do caso: imagem, PDF, áudio ou documento, até 20 MB por arquivo. Só os metadados ficam no banco; o binário vive em bucket **privado** e se lê por URL assinada com expiração, emitida pelo backend depois de conferir o [Perfil da Ouvidoria]. Estar logado no app não abre anexo de ouvidoria.
_Evitar_: guardar binário no banco; bucket público ou link permanente; servir anexo por caminho que não confira a manifestação de origem.

**Canal de origem**:
Por onde a [Manifestação] chegou ao hospital. Hoje: `ana` (atendimento da Ana) e os três do registro manual do ouvidor, `telefone`, `presencial` e `email`. Não confundir com o **T0**, a data e hora reais do contato: o ouvidor pode digitar hoje um telefonema de ontem, e é o T0 que vale para abertura, protocolo e prazo, nunca o momento do clique.
_Evitar_: usar a hora da digitação como marco do caso; tratar canal como setor.

**Protocolo de ouvidoria**:
O número que identifica a [Manifestação] e é informado a quem manifestou, formato `ANO-NNNN` (ex.: 2026-0007), gerado por sequence do Postgres, nunca pela aplicação nem por IA; NNNN contínuo, não reinicia por ano. Números já comunicados a pacientes seguem valendo: a fundação da numeração não é tocada por migration nova.
_Evitar_: compor ou estimar número fora da sequence; reiniciar a numeração; prefixo `OUV-` como dado (pode ser exibição).

**Canal aberto**:
A entrada da [Manifestação] sem login: o **formulário público** (`/manifestacao`) e o **QR setorial**. O manifestante escreve o relato, se identifica ou não, e recebe o [Protocolo de ouvidoria] na tela; o caso entra em classificação, **sem área definida**, porque quem classifica é o ouvidor. A URL impressa no cartaz é `https://<app>/ouvidoria/qr?setor=X&ponto=Y` (rewrite do Next para a rota do backend), e é o **servidor** que decide o destino (hoje o formulário; amanhã a conversa da Ana no WhatsApp oficial), para o cartaz nunca precisar ser reimpresso. O setor do cartaz é **origem, não área responsável**: fica em `canal_setor`, junto do `canal_ponto`, e só vale se existir na taxonomia de Setores; a área continua sendo decisão do ouvidor. Canal sem credencial tem rate limit por manifestante (primeiro salto do `X-Forwarded-For`, porque o Next proxia a chamada), honeypot e nenhum campo que decida classificação, estado ou sigilo.
_Evitar_: deixar o manifestante escolher área, tipo, gravidade ou sigilo; gravar o setor do cartaz na coluna `setor` (faz o caso parecer já classificado); imprimir no cartaz a URL final em vez da `/ouvidoria/qr`; pendurar a página pública sob `/ouvidoria` (aquele espaço é da área logada do ouvidor).

**Movimento**:
O registro do que aconteceu com uma [Manifestação]: estado anterior, estado novo, quem fez e quando. A trilha é **imutável** e append-only, gravada na mesma transação da mudança de estado (RPC `ouvidoria_transicionar`): nem a aplicação, nem a API, nem o Super admin editam ou apagam, e o banco recusa por trigger.
_Evitar_: mudar `status` direto por UPDATE; corrigir a trilha (o erro se conserta com movimento novo).

**Calendário útil**:
O relógio em que os prazos da Ouvidoria correm: segunda a sexta, das 08h às 17h, no fuso `America/Sao_Paulo`, sem os feriados nacionais, estaduais do RJ e municipais do Rio (tabela administrável, RN-22). Manifestação que entra fora do expediente tem a entrada registrada na hora real, mas a contagem só abre na próxima abertura. **Dia útil não conta o dia do fato**: o prazo de 2 dias úteis de um caso validado sexta às 16h50 abre segunda às 08h e vence terça às 17h. **Hora útil** anda dentro do expediente e para às 17h.
_Evitar_: contar em dias corridos; contar madrugada e fim de semana; embutir feriado no código.

**Motor de prazos**:
A função pura que, dada a gravidade, a [Tabela de prazos] e os feriados, devolve o vencimento (em UTC) e o rótulo em linguagem natural ("vence em 2 dias úteis", "vencido há 3 horas úteis"). Não lê banco nem consulta o relógio: quem carrega os parâmetros é a rota, quem grava o vencimento é quem valida a [Manifestação]. O vencimento fica **congelado** no caso desde o acionamento: mudar a tabela de prazos depois não recalcula caso já despachado. O painel e o email do setor mostram o mesmo rótulo porque saem do mesmo motor.
_Evitar_: recalcular prazo de caso já despachado; calcular calendário útil no navegador; prazo em dias corridos.

**Tabela de prazos**:
Os prazos por gravidade (crítico, alto, médio, baixo) e por marco (triagem, resposta da área, resposta conclusiva), em banco e editáveis em tela **só pela `diretoria_executiva`**, com histórico append-only de quem mudou o quê (RN-21). Valor em branco significa sem prazo para aquela combinação (crítico não tem conclusiva fixa; baixo não passa pela área); zero significa imediato. Nasce com os valores da especificação da Diretoria como seed, porque a tabela ainda muda com as coordenações.
_Evitar_: prazo hardcoded; deixar o ouvidor editar (ele usa o prazo, quem o define é a Diretoria).

**Validação e acionamento**:
O ato único em que o ouvidor confere o tipo, a área e a gravidade da [Manifestação] e a área é acionada no mesmo passo: o caso vai de "em classificação" para "aguardando área", grava o marco **T1** (quando validou e quem validou), o [Motor de prazos] calcula o vencimento e o [Responsável do setor] recebe o email de acionamento. É a única porta do despacho: nenhum processo automático acorda um setor, e quem não tem o [Perfil da Ouvidoria] não passa nem pela API. A sugestão da Ana não vem junto: ela fica em `classificacao_ia` e nunca vira a classificação validada. É aqui também que o [Tipo da manifestação] é **decidido**, então a [Classificação] acontece dentro deste passo, com a mesma regra da outra porta: o sigilo sobe quando o tipo pede, e desce quando o ouvidor pede e o tipo permite.
_Evitar_: acionar setor sem validação; recalcular o vencimento de caso já acionado; deixar a IA preencher a gravidade; usar a reclassificação para tirar o sigilo de um caso.

**Extrato para o setor**:
O texto que o [Responsável do setor] lê no email de acionamento, escrito pelo ouvidor na [Validação e acionamento], com as palavras dele. **Obrigatório em todo acionamento, sem exceção**: a validação é recusada sem ele. Não é o relato de quem manifestou nem o resumo do caso, e nenhum dos dois serve de padrão, porque os dois carregam a palavra de quem manifestou (no canal aberto, os primeiros caracteres do que o cidadão digitou, com nome e leito; no canal da Ana, texto gerado a partir da conversa com ele) e o responsável do setor é pessoa de fora da Ouvidoria, sem login no app. Uma regra só, sem caso especial para alguém lembrar: todo email que sai da Ouvidoria leva texto escrito pela Ouvidoria. Fica gravado no caso, para o reenvio mandar a mesma coisa e para provar o que a área recebeu.
_Evitar_: mandar o relato ou o resumo por email ao setor; prometer no email uma proteção que o texto enviado não tem.

**Responsável do setor**:
Quem responde por um setor na Ouvidoria, com papel (`titular`, `substituto`, `gestor`) e **vigência** (o fim é inclusivo: quem sai no dia 31 ainda responde no dia 31). Fica sobre a taxonomia de Setores da casa, sem cadastro paralelo, e quem o mantém é a `diretoria_executiva`, como na [Tabela de prazos]. O titular vigente é quem recebe o acionamento; **setor sem titular vigente não é acionável** e a demanda sobe ao gestor da área, com alerta à Diretoria. Sem titular e sem gestor, a validação é recusada em vez de mandar a demanda para o vazio.
_Evitar_: apagar o responsável para tirá-lo do papel (o caminho é encerrar a vigência); cadastrar setor que não existe na taxonomia.

**Notificação da Ouvidoria**:
Todo email que a Ouvidoria dispara nasce antes como registro no caso (data, destinatário, gatilho), e é isso que prova a cobrança e alimenta o botão de reenvio. Gatilhos desta leva: `nova_demanda` (acionamento do setor) e `alerta_sem_titular` (aviso à Diretoria). Duas regras de tempo: **janela comercial** (notificação não crítica gerada fora do expediente espera a próxima abertura; caso crítico sai na hora) e **retentativa com backoff** (falha do provedor devolve a notificação à fila com espera crescente; na terceira falha o registro vira `falha` e o admin técnico é avisado). Quem tira da fila é um job periódico idempotente: antes de chamar o provedor, a notificação é reivindicada (estado `enviando`), para o job não pegar uma linha em voo e mandar a mesma cobrança duas vezes. O reenvio manual nasce como registro próprio, sem reescrever o envio original.
_Evitar_: mandar email sem registrar; reescrever o registro do primeiro envio; disparar cobrança automática de madrugada; devolver à fila uma notificação que já saiu.

**Perfil da Ouvidoria**:
O eixo de permissão próprio do contexto Ouvidoria, ortogonal ao perfil de acesso das Reuniões e ao perfil de POPs: `ouvidor` e `diretoria_executiva`. Só esses dois abrem a [Manifestação] completa, inclusive a sigilosa; o **Super admin fica de fora** (RN-40), porque administrar o sistema não é ler o relato de quem manifestou. Demais papéis de Reuniões veem só o índice. O Super admin concede o perfil pela tela de Usuários, e a concessão fica no audit log. Todo acesso à Manifestação gera registro de log.
_Evitar_: tratar Super admin como quem vê tudo; usar o perfil de Reuniões para decidir acesso ao dossiê.

**API da Ana**:
Os endpoints de serviço `/api/ana/*`: leitura das tabelas do Dados do Atendimento, registro e consulta de protocolo de ouvidoria. Autenticação por **API key de serviço** dedicada (header), fora do fluxo JWT do Supabase Auth; a chave vive no vault da plataforma da Ana e o escopo é restrito a esses endpoints. Nos endpoints de escrita, campo crítico é NOT NULL e validado (o cliente tem falha silenciosa conhecida que enviaria vazio com HTTP 200; o banco recusa). O registro de protocolo aceita, opcionalmente, os campos do Dossiê da [Manifestação] (relato integral, nome, contato, vínculo e a gravidade sugerida com grau de confiança, guardada à parte em `classificacao_ia`); o POST sem eles continua valendo. A Ana registra manifestação, não classifica caso: status, desfecho, [Tipo da manifestação] e sigilo são decisão do ouvidor e o endpoint recusa quem tentar mandá-los. Por isso o caso dela entra **sem tipo**, logo sigiloso, até o ouvidor classificar. A consulta de protocolo devolve o índice do caso comum e, do sigiloso, só o andamento: protocolo, estado e data.
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
