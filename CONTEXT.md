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

## Dados do Atendimento (Ana)

Área nascida no ADR 0031 (14/ago/2026): o app vira a casa dos dados que alimentam a **Ana**, e ganha a primeira API de serviço para outro sistema.

**Ana**:
A agente de IA de atendimento e agendamento de pacientes via WhatsApp do mesmo hospital: produto irmão, com repo e roadmap próprios (`~/PedroDev/Ana`). Consome dados deste app pela [API da Ana]; não loga, não tem conta, não é usuária.
_Evitar_: tratar a Ana como feature deste app (é cliente de serviço).

**Dados do Atendimento**:
O módulo da área admin com as tabelas que alimentam a Ana: consultas particulares (preços e diferenciais), exames e estimativas de cirurgias. Super admins e secretárias editam; facilitadores leem. Edição vale imediatamente para a Ana (leitura direta, sem cache). Substitui a planilha do NocoDB (aposentado pelo ADR 0031). A tabela de convênios por especialidade saiu no ADR 0038: cobertura de convênio é a agenda online da Global Health quem responde, e no lugar dela vive o [Espelho da Global Health]. A regra que organiza o módulo: a Global Health é dona da agenda (o que existe, quem atende, quem é aceito, quando); as tabelas daqui são donas do que ela não tem (preço particular, preparo, estimativa).
_Evitar_: "tabelas do NocoDB" (a casa agora é aqui); cache entre a edição e a API.

**Manifestação**:
O caso de ouvidoria completo, que vive neste app desde o ADR 0034: relato integral sem edição, identificação de quem manifestou (ou anônima), contato, vínculo, classificação sugerida pela Ana à parte, marcos de tempo e desfecho. Substitui o "índice, não dossiê" do ADR 0031, que deixou de valer. Nasce **em classificação**: nenhum processo automático despacha, só quem tem o [Perfil da Ouvidoria] valida e aciona a área. Denúncia e relato de conduta nascem com **sigilo reforçado**: nem aparecem no índice de quem está fora da Ouvidoria. Quem diz que o caso é denúncia é o [Tipo da manifestação], nunca o texto digitado.
_Evitar_: "protocolo" como sinônimo (o Protocolo é o número, a Manifestação é o caso); mudar estado por fora da máquina de estados.

**Paciente do caso**:
A pessoa atendida de quem a [Manifestação] fala, quando não é quem manifestou (decisão de 09/09/2026, a partir do áudio da Diretoria: o acompanhante reclama pelo QR e a área não acha o atendimento). São dois dados do caso, ambos opcionais: o **nome do paciente** e a **referência do atendimento** (texto curto: data, setor ou leito). Nascem no [Canal aberto] e no registro manual do ouvidor; a Ana fica para leva própria. Não são editáveis depois do nascimento, como o resto da identificação. **Viajam para a área** no caso comum e no caso anônimo, porque o anonimato protege quem falou e o paciente é outra pessoa; não viajam no sigilo reforçado, onde o extrato do ouvidor decide o que sai. Relato em nome de outra pessoa sem nome do paciente acende um aviso no Dossiê antes do acionamento, sem travar nada.
_Evitar_: tornar o nome obrigatório (canal aberto nunca barra); esconder o campo quando o manifestante marca "anônimo"; colar o nome dentro do relato (o relato é integral, sem edição); esconder o paciente da área no caso anônimo (é o que faz a área devolver por "não achei"); confundir com "quem manifestou".

**Tipo da manifestação**:
O que a [Manifestação] é, em lista fechada: `denuncia`, `reclamacao`, `sugestao`, `elogio`, `relato_de_conduta`, `informacao` (ADR 0037; `informacao` entrou pelo ADR 0040, a partir do diagnóstico da Diretoria de 31/08/2026, RN-57, sem sigilo por natureza e sem renomear `relato_de_conduta`). É ele, e só ele, que decide o **sigilo reforçado**: `denuncia` e `relato_de_conduta` são sigilosos por natureza, nos três canais, sem ato humano. A regra automática é **piso, nunca teto**: o ouvidor eleva o sigilo de um caso que a lista não previu, e não retira o de um tipo sigiloso por natureza. Tipo vazio significa **não classificado**, e o caso não classificado é sigiloso (fail-closed): é assim que entram o [Canal aberto] e o canal da Ana, e a saída é a classificação. Ao lado dele vive a **categoria**, rótulo humano em texto livre ("demora no atendimento", "conduta da equipe noturna"), que descreve o caso e não decide nada.
_Evitar_: ler a categoria para decidir sigilo (era a regra antiga, e "Assédio moral" não casava com termo nenhum); deixar a Ana mandar o tipo (ela registra, não classifica); tratar tipo vazio como caso comum.

**Classificação**:
O ato do [Perfil da Ouvidoria] que grava o [Tipo da manifestação], o rótulo e o sigilo do caso, e é a **única porta do sigilo**: sobe e desce no mesmo lugar, com movimento na trilha e registro no log de acesso. Acontece em duas telas com a mesma regra: dentro da [Validação e acionamento], para o caso que vai ser despachado, e no Dossiê, para o que já foi ou nunca vai ser. Sem pedido explícito, o sigilo de hoje é mantido: descer é ato consciente, não efeito colateral de reclassificar. A reabertura por reincidência só **eleva**, porque reabrir não é classificar.
_Evitar_: abaixar sigilo sem ato explícito; porta de sigilo separada da classificação; mudar sigilo sem deixar rastro com autor.

**Anexo (da Manifestação)**:
A evidência que fica junto do caso: imagem, PDF, áudio ou documento, até 20 MB por arquivo. Só os metadados ficam no banco; o binário vive em bucket **privado** e se lê por URL assinada com expiração, emitida pelo backend depois de conferir o [Perfil da Ouvidoria]. Estar logado no app não abre anexo de ouvidoria.
_Evitar_: guardar binário no banco; bucket público ou link permanente; servir anexo por caminho que não confira a manifestação de origem.

**Canal de origem**:
Por onde a [Manifestação] chegou ao hospital. Hoje: `ana` (atendimento da Ana), os dois do [Canal aberto], `site` e `qr`, e os sete do registro manual do ouvidor: `whatsapp`, `telefone`, `presencial`, `email`, `instagram`, `reclame_aqui` e `google` (decisão de 15/09/2026, a partir do relato de que o ouvidor carimbava como telefone o que chegava pelo WhatsApp do Kommo). Os quatro últimos nasceram **antes** de qualquer integração: o ouvidor lê a conversa, a avaliação ou o comentário na plataforma e digita o caso à mão, como faz com o telefonema. `ana` e `whatsapp` são canais distintos e a diferença é **quem atendeu**, não o aplicativo: `ana` é a agente de IA pela [API da Ana]; `whatsapp` é humano no WhatsApp do hospital (hoje no Kommo). O link da avaliação pública ou o @ do perfil vão no contato do manifestante ou como anexo; campo estruturado para isso fica para quando a resposta pública virar ação. O canal é fixo depois do nascimento, como o resto da identificação: caso carimbado errado ganha um [Movimento] com a nota, não uma edição. Não confundir com o **T0**, a data e hora reais do contato: o ouvidor pode digitar hoje um telefonema de ontem, e é o T0 que vale para abertura, protocolo e prazo, nunca o momento do clique.
_Evitar_: usar a hora da digitação como marco do caso; tratar canal como setor; ler `whatsapp` como caso da Ana; corrigir canal antigo em massa (o WhatsApp começa do zero no relatório do mês da virada, e isso é verdade).

**Protocolo de ouvidoria**:
O número que identifica a [Manifestação] e é informado a quem manifestou, formato `ANO-NNNN` (ex.: 2026-0007), gerado por sequence do Postgres, nunca pela aplicação nem por IA; NNNN contínuo, não reinicia por ano. Números já comunicados a pacientes seguem valendo: a fundação da numeração não é tocada por migration nova.
_Evitar_: compor ou estimar número fora da sequence; reiniciar a numeração; prefixo `OUV-` como dado (pode ser exibição).

**Canal aberto**:
A entrada da [Manifestação] sem login: o **formulário público** (`/manifestacao`) e o **QR setorial**. O manifestante escreve o relato, se identifica ou não, e recebe o [Protocolo de ouvidoria] na tela; o caso entra em classificação, **sem área definida**, porque quem classifica é o ouvidor. A URL impressa no cartaz é `https://<app>/ouvidoria/qr?p=<codigo>` (rewrite do Next para a rota do backend), onde o código resolve um [Ponto de escuta] cadastrado; o formato antigo `?setor=X&ponto=Y` foi aposentado pelo ADR 0036. É o **servidor** que decide o destino (hoje o formulário; amanhã a conversa da Ana no WhatsApp oficial), para o cartaz nunca precisar ser reimpresso. O setor do cartaz é **origem, não área responsável**: fica em `canal_setor`, junto do `canal_ponto`, e os dois só são gravados quando o código resolve um Ponto de escuta ativo; a área continua sendo decisão do ouvidor. Canal sem credencial tem rate limit por manifestante (primeiro salto do `X-Forwarded-For`, porque o Next proxia a chamada), honeypot e nenhum campo que decida classificação, estado ou sigilo. O seletor das quatro naturezas do formulário (elogio primeiro, opcional, RN-88/ADR 0040) é **sugestão** gravada à parte em `natureza_informada`: não classifica, não decide nada. O ouvidor a lê no Dossiê, num bloco que nomeia a origem ("O manifestante informou: Elogio") e diz que a classificação segue sendo dele; caso sem escolha não desenha bloco nenhum. Desde 09/09/2026 o formulário pergunta, logo depois do relato e com resposta obrigatória de um toque, **"Este relato é sobre quem?"**: "Sobre mim" grava o vínculo `paciente`, "Sobre outra pessoa" grava `acompanhante` e abre os dois campos do [Paciente do caso]; esses campos continuam visíveis com "anônimo" marcado. Colaborador e terceiro ficam para os canais em que alguém conversa com a pessoa.
_Evitar_: deixar o manifestante escolher área, tipo, gravidade ou sigilo; gravar o setor do cartaz na coluna `setor` (faz o caso parecer já classificado); imprimir no cartaz a URL final em vez da `/ouvidoria/qr`; imprimir setor e ponto por extenso na URL; pendurar a página pública sob `/ouvidoria` (aquele espaço é da área logada do ouvidor).

**Ponto de escuta**:
Cada lugar do hospital que tem um cartaz de QR da Ouvidoria: setor, rótulo do ponto ("Poltrona 12", "Corredor do 3o andar"), código curto de 6 caracteres e ativo. É o cadastro por trás do [Canal aberto]: o código impresso no cartaz resolve aqui, e é daqui que saem o PNG do QR e o cartaz A5 em PDF que a tela `/ouvidoria/pontos` entrega prontos. Quem cadastra e imprime é o [Perfil da Ouvidoria], porque cartaz é operação do canal e não governança. Ponto **desativa, nunca apaga** (o histórico de casos aponta para ele), e o QR de ponto inativo abre o formulário público normal, sem origem: quem está parado na frente de um cartaz nunca fica sem canal.
_Evitar_: apagar ponto; devolver erro ao QR de ponto inativo; ler `canal = 'qr'` como prova de presença física (o código está impresso na parede, à vista de quem passa); cadastro de pontos paralelo à taxonomia de Setores.

**Triagem de e-mail**:
O filtro por onde passa todo e-mail que chega em `ouvidoria@` antes de virar caso (ADR 0051). Cada **e-mail recebido** (remetente, assunto, data, corpo e anexos) entra numa lista que só o [Perfil da Ouvidoria] vê, e acende o mesmo ponto de novidade da fila. O ouvidor tem três ações: **virar manifestação** (abre o registro manual pré-preenchido, com canal `email`, T0 igual à data do e-mail e o corpo como relato; o ouvidor escolhe o tipo, e o acuse de recebimento do ADR 0042 sai daí), **juntar a um caso existente** (o texto e os anexos entram como [Movimento] do caso, sem mudar estado nem prazo; se o assunto traz o [Protocolo de ouvidoria], o app sugere o caso) e **descartar** (fica só o cabeçalho, com quem descartou e quando; corpo e anexos são apagados). Não é [Canal aberto]: e-mail traz spam, newsletter e resposta interna, e manifestação não se apaga (ADR 0047), então o filtro vem antes do caso. Ninguém recebe resposta automática na chegada.
_Evitar_: transformar e-mail em caso sem ato do ouvidor; responder automaticamente ao e-mail recebido (responde a robô e abre loop); guardar corpo de e-mail descartado; chamar a tela de "caixa de entrada" (promete responder por ali, e o app não responde e-mail).

**Movimento**:
O registro do que aconteceu com uma [Manifestação]: estado anterior, estado novo, quem fez e quando. A trilha é **imutável** e append-only, gravada na mesma transação da mudança de estado (RPC `ouvidoria_transicionar`): nem a aplicação, nem a API, nem o Super admin editam ou apagam, e o banco recusa por trigger. O **fato** é imutável para sempre; o **conteúdo** da `observacao` tem uma única saída, a [Retenção], porque a resposta da área viaja inteira para dentro dele. Apagar linha continua proibido sem exceção.
_Evitar_: mudar `status` direto por UPDATE; corrigir a trilha (o erro se conserta com movimento novo); tratar a saída da retenção como permissão geral de editar observação.

**Retenção**:
A política de LGPD que apaga o Dossiê da [Manifestação] encerrada há mais de cinco anos e preserva o que os relatórios contam (tipo, área, gravidade, canal, datas, marcos e desfecho). Roda sozinha, de madrugada, e varre os cinco lugares onde o relato mora: a manifestação, os anexos (metadados e binário), a `observacao` dos [Movimento]s, o texto livre das tentativas de contato e das prorrogações, e o `detalhe` das notificações (por onde viajam o motivo da devolução e o da reabertura, escritos pelo ouvidor). O ato entra na trilha, e o carimbo `anonimizada_em` faz o job ser idempotente.
 Desde a decisão de 04/09/2026, a mesma política tem uma **porta antecipada**: a `diretoria_executiva` pode apagar o Dossiê de um caso encerrado antes dos cinco anos, um caso por vez, com motivo escrito obrigatório. É isso que "apagar uma manifestação" significa neste app: o relato, o nome, o contato, os anexos e o texto livre somem hoje; o protocolo, a trilha e os números ficam. O ato entra na trilha com autor e motivo, e é a única coisa que sobra para explicar o buraco. O Dossiê de caso apagado (pela porta antecipada ou pelos cinco anos) mostra o aviso no lugar do relato, e o caso **não reabre** por reincidência: quem volta abre caso novo. Caso apagado entra no [Arquivo] sozinho.
_Evitar_: contar os cinco anos de qualquer marco que não seja o encerramento (T3); anonimizar caso sem `encerrada_em` (o import histórico do NocoDB nasceu assim, `encerrado` sem marco); apagar linha de trilha, de tentativa ou de prorrogação (some a estatística; o que sai é o texto); apagar a linha da manifestação ou tirá-la dos números ("apagar totalmente" é a porta antecipada, nunca DELETE); apagar sem motivo; apagar pelo `ouvidor` ou pelo Super admin; reabrir caso apagado.

**Calendário útil**:
O relógio em que os prazos da Ouvidoria correm: segunda a sexta, das 08h às 17h, no fuso `America/Sao_Paulo`, sem os feriados nacionais, estaduais do RJ e municipais do Rio (tabela administrável, RN-22). Manifestação que entra fora do expediente tem a entrada registrada na hora real, mas a contagem só abre na próxima abertura. **Dia útil não conta o dia do fato**: o prazo de 2 dias úteis de um caso validado sexta às 16h50 abre segunda às 08h e vence terça às 17h. **Hora útil** anda dentro do expediente e para às 17h.
_Evitar_: contar em dias corridos; contar madrugada e fim de semana; embutir feriado no código.

**Motor de prazos**:
A função pura que, dada a gravidade, a [Tabela de prazos] e os feriados, devolve o vencimento (em UTC) e o rótulo em linguagem natural ("vence em 2 dias úteis", "vencido há 3 horas úteis"). Não lê banco nem consulta o relógio: quem carrega os parâmetros é a rota, quem grava o vencimento é quem valida a [Manifestação]. O vencimento fica **congelado** no caso desde o acionamento: mudar a tabela de prazos depois não recalcula caso já despachado. O painel e o email do setor mostram o mesmo rótulo porque saem do mesmo motor.
_Evitar_: recalcular prazo de caso já despachado; calcular calendário útil no navegador; prazo em dias corridos.

**Tabela de prazos**:
Os prazos por gravidade (crítico, alto, médio, baixo) e por marco (acusar recebimento, triagem, resposta da área, resposta conclusiva), em banco e editáveis em tela **só pela `diretoria_executiva`**, sendo o acusar recebimento o único marco em **horas corridas** (promessa ao paciente, ADR 0042; os demais correm no [Calendário útil]), com histórico append-only de quem mudou o quê (RN-21). Valor em branco significa sem prazo para aquela combinação (crítico não tem conclusiva fixa; baixo não passa pela área); zero significa imediato. Nasce com os valores da especificação da Diretoria como seed, porque a tabela ainda muda com as coordenações.
_Evitar_: prazo hardcoded; deixar o ouvidor editar (ele usa o prazo, quem o define é a Diretoria).

**Semáforo de prazo**:
A cor que a linha da fila dá ao vencimento da [Manifestação], em quatro degraus (vencido, vence hoje, até um dia útil de folga, folga maior) mais o relógio parado de quem já saiu das mãos da Ouvidoria (RN-58). A régua de cor é **própria**, nos tokens da tela: vermelho (`text-red-600`) para vencido e vence hoje, âmbar (`text-amber-600`) para o degrau de alerta, neutro (`text-slate-500`) acima disso. Ela **não** é a paleta de gravidade, que vive na pílula da linha (vermelho, laranja, âmbar e cinza claros) e, no email estratificado do setor, nos hexes da spec da Diretoria (`#B3261E` crítico, `#C77700` alto, `#1F3864` médio, `#5F5E5A` baixo, RN-34). Três escalas convivem na mesma linha e cada uma tem seu lugar e sua paleta: estado só na faixa do bloco (RN-70), gravidade só na pílula, prazo só no vencimento. O motivo é a RN-71: pintar o prazo com os hexes da gravidade poria duas perguntas diferentes ("é grave?" e "está atrasado?") na mesma dupla de cores, e é justamente isso que a regra existe para impedir (decisão de 03/09/2026, que emendou a decisão 1 do PRD #471).
_Evitar_: usar os hexes da gravidade no semáforo de prazo; misturar cor de estado, de gravidade e de prazo no mesmo elemento; ler cor de prazo como cor de gravidade.

**Arquivo (da Manifestação)**:
O depósito dos casos **encerrados** que o ouvidor tirou da vista da lista. Arquivar não muda estado, não apaga nada e não entra na trilha: o caso guarda só quando e quem arquivou, e desarquivar limpa o carimbo. Só caso `encerrado` arquiva; caso em andamento tem prazo correndo e setor esperando, e esconder isso é esconder atraso. A recíproca vale no tempo, e não só no instante do clique: a reabertura por reincidência **tira o caso do arquivo**, porque o caso que volta a andar deixa de ser caso guardado, e um prazo novo correndo numa linha que ninguém vê é o mesmo atraso escondido pela porta de trás. Quem arquiva e desarquiva são os dois papéis do [Perfil da Ouvidoria], um caso por vez ou todos os encerrados de uma vez. **Ler** o arquivo é ato do mesmo perfil, e quem confere é o servidor: a vista dos arquivados não é um filtro de tela que se esconde de quem não deve ver, é a outra metade do ato de arquivar, e o índice geral da equipe de Reuniões continua aberto a quem sempre o leu. A lista nasce sem os arquivados e os mostra atrás de um filtro próprio; o caso arquivado continua abrindo pelo protocolo e continua contando nos relatórios e nas métricas, porque arquivar é organização da lista, não fato do caso. Caso apagado pela [Retenção] entra aqui sozinho.
_Evitar_: arquivar caso em andamento; deixar arquivado o caso que foi reaberto; tratar arquivo como estado da máquina; gravar movimento ao arquivar (acenderia o ponto de novidade num caso em que ninguém mexeu); tirar caso arquivado das métricas; guardar a vista dos arquivados só na tela; confundir arquivar (esconde, tem volta) com apagar (some o relato, não tem volta).

**Visto da Ouvidoria**:
O carimbo que apaga o ponto de novidade da linha e tira o caso do contador do menu (RN-66). É **global, um por caso** (`vista_pela_ouvidoria_em`), e não um por pessoa: o ponto diz "a Ouvidoria ainda não viu", não "eu ainda não vi". Novidade é derivada na leitura, nunca guardada: o caso tem novidade quando a última movimentação da trilha é mais recente que o carimbo, ou quando o carimbo é nulo (caso anterior à coluna nasce assim, de propósito). **Dois atos carimbam**, e só eles: a **leitura** (abrir o Dossiê, pelo id ou pelo protocolo) e a **ação do próprio ouvidor** sobre o caso, que são **encerrar** e **validar** (decisão de 03/09/2026, issue #521). A régua tem dois lugares porque o ouvidor encerra e valida pelo botão da própria lista, sem abrir o caso: sem o segundo carimbo, o movimento que a ação grava acendia o ponto e subia o contador logo depois de ele ter trabalhado ali. Quem carimba é o **servidor**, na mesma requisição da transição, e o instante é lido **depois** do movimento, senão o carimbo nasce mais velho que ele e o ponto não apaga.
_Evitar_: carimbar na tela; carimbar pausa, devolução, resposta da área ou reabertura (nenhuma é o ouvidor dizendo "vi e resolvi"); carimbar antes de a transição valer; um carimbo por usuário.

**Validação e acionamento**:
O ato único em que o ouvidor confere o tipo, a área e a gravidade da [Manifestação] e a área é acionada no mesmo passo: o caso vai de "em classificação" para "aguardando área", grava o marco **T1** (quando validou e quem validou), o [Motor de prazos] calcula o vencimento e o [Responsável do setor] recebe o email de acionamento. É a única porta do despacho: nenhum processo automático acorda um setor, e quem não tem o [Perfil da Ouvidoria] não passa nem pela API. A sugestão da Ana não vem junto: ela fica em `classificacao_ia` e nunca vira a classificação validada. É aqui também que o [Tipo da manifestação] é **decidido**, então a [Classificação] acontece dentro deste passo, com a mesma regra da outra porta: o sigilo sobe quando o tipo pede, e desce quando o ouvidor pede e o tipo permite. É também a porta do **reacionamento** depois de uma [Devolução à Ouvidoria] (decisão de 04/09/2026): o caso voltou a "em classificação", a tela vem pré-preenchida com o que o ouvidor já tinha decidido, ele troca a área e confirma; o T1 é carimbado de novo e o prazo da área nasce cheio. O [Redirecionamento] entra pela mesma porta, na mesma requisição em que tira o caso da área antiga.
_Evitar_: acionar setor sem validação; recalcular o vencimento de caso já acionado; deixar a IA preencher a gravidade; usar a reclassificação para tirar o sigilo de um caso.

**Extrato para o setor**:
O texto que o [Responsável do setor] lê no acionamento, escrito pelo ouvidor na [Validação e acionamento], com as palavras dele. **Obrigatório em todo acionamento, sem exceção**: a validação é recusada sem ele. Desde o diagnóstico da Diretoria de 31/08/2026 (RN-78), o email de acionamento e a tela do responsável carregam **três blocos separados**: resumo, relato integral e o extrato (a "nota da ouvidoria"), nesta ordem e visualmente distintos, para a área responder ao paciente e não à interpretação da Ouvidoria. Caso com sigilo reforçado é a exceção (RN-79): sem identificação do manifestante, e o extrato substitui o relato integral. Nessa exceção o **resumo também não viaja** (ele é a palavra crua de quem manifestou, capaz de carregar nome e leito), e o **caso anônimo recebe a mesma proteção**, pelo mesmo motivo de o anonimato se desfazer dentro do próprio texto: o acionamento protegido sai só com a nota da ouvidoria. A extensão ao caso anônimo foi **ratificada em 03/09/2026** (ADR 0041): ali o anonimato pesa mais que a RN-78, e é o extrato do ouvidor que sustenta o trabalho da área, o que faz da qualidade dele o gargalo desses casos. Pseudonimizar resumo e relato de caso anônimo continua possível, mas seria PRD próprio. Essa decisão revogou a proibição anterior de mandar o relato ou o resumo por email ao setor; o extrato continua obrigatório, agora como um dos três blocos. O extrato fica gravado no caso, para o reenvio mandar a mesma coisa e para provar o que a área recebeu.
_Evitar_: fundir os três blocos ou dar a eles a mesma formatação (RN-60); mandar relato ou identificação em caso sigiloso; prometer no email uma proteção que o texto enviado não tem.

**Responsável do setor**:
Quem responde por um setor na Ouvidoria, com papel (`titular`, `substituto`, `gestor`) e **vigência** (o fim é inclusivo: quem sai no dia 31 ainda responde no dia 31). Fica sobre a taxonomia de Setores da casa, sem cadastro paralelo. Quem o mantém é o [Perfil da Ouvidoria] inteiro, `ouvidor` e `diretoria_executiva` (decisão de 14/09/2026, ADR 0055; antes era só a Diretoria, como na [Tabela de prazos], que continua só dela): trocar quem responde é encerrar a vigência do titular e cadastrar o novo, e um Cobrar em seguida leva o caso ao vigente. Não existe destinatário por caso: a cadeia de cobrança e escalonamento inteira parte deste cadastro. O titular vigente é quem recebe o acionamento; **setor sem titular vigente não é acionável** e a demanda sobe ao gestor da área, com alerta à Diretoria. Sem titular e sem gestor, a validação é recusada em vez de mandar a demanda para o vazio.
_Evitar_: apagar o responsável para tirá-lo do papel (o caminho é encerrar a vigência); cadastrar setor que não existe na taxonomia; escolher a pessoa por caso ao acionar (o responsável é do setor).

**Tela do responsável**:
A página que o [Responsável do setor] abre pelo link do email de acionamento, sem senha, do celular, uma vez só. A RN-59 fixa a ordem de leitura, porque quem abre este link é o usuário menos treinado do módulo e a hierarquia da tela é o que substitui o treinamento: gravidade, prazo em contagem regressiva, a linha secundária (protocolo, setor e categoria), **quem manifestou**, os três blocos do [Extrato para o setor], o campo único O QUE FOI FEITO e os dois botões (RESPONDER e SOLICITAR PRORROGAÇÃO). São **dez elementos** desde 03/09/2026 (issue #511): "quem manifestou" já estava na tela desde o portal do setor, sem nome na regra, e o que não tem nome fica fora de qualquer teste de ordem. Ele é o mesmo dado que o email de acionamento carrega e sai pela mesma guarda do caso protegido: caso sigiloso e caso anônimo chegam com "Sem identificação", e a linha permanece, porque a ausência é informação (apagada, a área não distingue caso sem identificação de tela incompleta).
_Evitar_: enfiar elemento novo entre a gravidade e o prazo (no celular ele empurra o prazo para fora da primeira tela, que é o que a RN-59 existe para evitar; a única exceção, nomeada e fechada em 03/09/2026 na issue #559, é a **linha de identidade do hospital**, o logo mais "Demanda da Ouvidoria", que fica ali de propósito, porque a página é pública e abre a partir de um email, e sem ela quem recebe o link não sabe que a tela é do hospital; qualquer outro elemento continua proibido ali); montar quem manifestou por fora da guarda do caso protegido; deixar a tela reconstruir resumo ou relato que o servidor cortou.
 Desde a decisão de 04/09/2026, a tela tem um **décimo primeiro elemento**, o último de propósito: o link discreto da [Devolução à Ouvidoria] ("Este caso não é do meu setor?"), abaixo dos dois botões, porque responder continua sendo o ato principal e a devolução não pode competir com ele.

**Devolução à Ouvidoria**:
O ato do [Responsável do setor] que devolve ao ouvidor a [Manifestação] que não é da área dele, com motivo escrito **obrigatório** (decisão de 04/09/2026, a partir do pedido da Diretoria: a Recepção recebe um caso que é do médico e precisa devolver para o ouvidor encaminhar). Nasce na [Tela do responsável], pelo link discreto abaixo dos dois botões. A área **não escolhe destino**: ela diz por que o caso não é dela, e quem encaminha é o ouvidor, como em todo despacho. O caso volta a **em classificação**, o relógio da área para e a cobrança daquele setor cessa; a Ouvidoria é avisada e o ponto de novidade acende. O ouvidor reaciona pela mesma [Validação e acionamento], que vem **pré-preenchida** com tipo, gravidade e extrato do acionamento anterior: ele troca a área e confirma. O reacionamento grava **T1 novo** e a área certa recebe **prazo cheio**: o tempo perdido com a área errada entra no trecho da Triagem, na conta da Ouvidoria, que foi quem despachou. Não há limite de vezes: a cada volta há um humano decidindo, e a trilha guarda cada devolução com o motivo. O motivo é texto livre, sem piso e com o mesmo teto dos demais textos da área, e vive na `observacao` do [Movimento], por onde a [Retenção] o alcança. Devolver usa o link **uma vez só** e só vale enquanto o caso aguarda a área. Não confundir com a **Devolução por insuficiência**, que anda na direção contrária: o ouvidor devolve resposta fraca ao mesmo setor, com meio prazo. Nem com o [Redirecionamento], que é o mesmo erro de destino percebido pelo ouvidor, e não pela área.
_Evitar_: deixar a área escolher a área nova; chamar de "recusa" (a área não se nega a trabalhar, ela diz que o caso não é dela); estado novo na máquina para o caso devolvido; fazer a área certa herdar o prazo que sobrou da errada; botão do mesmo peso de RESPONDER; devolução no relatório antes de haver histórico para ler (fica para leva própria).

**Redirecionamento**:
O ato do ouvidor que tira a [Manifestação] de uma área e a aciona em outra, num clique só, sem esperar a [Devolução à Ouvidoria] (decisão de 14/09/2026, ADR 0055, a partir da pergunta da Diretoria: "o ouvidor consegue, de forma fácil, alterar a área responsável?"). Vale para caso em **aguardando área** ou **respondido** (a área errada que responde "isso é do Centro Médico" em vez de devolver); caso pausado é retomado antes. O botão "Redirecionar", no Dossiê e no menu da linha da fila, abre a [Validação e acionamento] pré-preenchida com tipo, gravidade e extrato, área em branco e **motivo obrigatório**. Numa requisição só, o servidor tira o caso da área antiga (consome o link, para o relógio, zera os carimbos de cobrança e escalonamento, grava o movimento "Redirecionado pelo ouvidor (de <setor>): motivo") e aciona a área nova pela porta de sempre: **T1 novo, prazo cheio**, e o tempo perdido na conta da Triagem da Ouvidoria, a mesma contabilidade da devolução. Se a área nova não tem titular nem gestor vigente, nada acontece e o caso fica onde estava. A área antiga recebe um **aviso curto** (gatilho `redirecionamento_area`): a demanda daquele protocolo foi encaminhada a outra área e não é preciso responder, sem motivo e sem dizer qual. A resposta da área errada, se houver, fica na trilha como está e não viaja para a área nova. Sem limite de vezes, sem linha no relatório nesta leva.
_Evitar_: fazer em dois atos (retirar e depois validar deixa o caso parado em classificação sem ninguém cobrando); a área nova herdar o prazo restante da errada; redirecionar caso pausado; contar redirecionamento como devolução no Dossiê (o prefixo da observação separa os dois); usar a transição genérica `aguardando_area -> em_classificacao` como redirecionamento (ela não consome o link nem para o relógio); mandar o motivo ou a área nova no aviso à área antiga.

**Notificação da Ouvidoria**:
Todo email que a Ouvidoria dispara nasce antes como registro no caso (data, destinatário, gatilho), e é isso que prova a cobrança e alimenta o botão de reenvio. Gatilhos desta leva: `nova_demanda` (acionamento do setor) e `alerta_sem_titular` (aviso à Diretoria); o catálogo cresceu depois para 12 gatilhos internos (prazos, escalonamentos, prorrogações, devolução e reabertura), e o ADR 0042 acrescentou os dois primeiros com o manifestante como destinatário: `acusar_recebimento` (automático na abertura, fora da janela comercial) e `encerramento_manifestante` (protocolo, desfecho em linguagem simples e canal para reabrir). Duas regras de tempo: **janela comercial** (notificação não crítica gerada fora do expediente espera a próxima abertura; caso crítico sai na hora) e **retentativa com backoff** (falha do provedor devolve a notificação à fila com espera crescente; na terceira falha o registro vira `falha` e o admin técnico é avisado). Quem tira da fila é um job periódico idempotente: antes de chamar o provedor, a notificação é reivindicada (estado `enviando`), para o job não pegar uma linha em voo e mandar a mesma cobrança duas vezes. O reenvio manual nasce como registro próprio, sem reescrever o envio original.
_Evitar_: mandar email sem registrar; reescrever o registro do primeiro envio; disparar cobrança automática de madrugada; devolver à fila uma notificação que já saiu.

**Nota externa**:
A nota que o hospital tem FORA dele: as estrelas do Google (escala de 0 a 5) e o índice do Reclame Aqui (escala de 0 a 10). Nenhuma das duas é medida pelo sistema. Quem as sabe é o [Perfil da Ouvidoria], que abre as duas páginas e digita o que leu; a integração automática é fase seguinte da spec. Cada registro é uma **linha nova**, nunca uma edição, e o que vale é a última de cada fonte: o diário é o que guarda a evolução e o que deixa o relatório de julho, reenviado em setembro, mostrar a nota de julho. O relatório congela a nota junto dos números e a imprime no bloco **Retrato externo**.
_Evitar_: mostrar a nota sem a escala ao lado (4,3 de 5 é 86% e 7,8 de 10 é 78%: lado a lado sem denominador, o leitor conclui o contrário); transformar ausência de registro em 0 (leria como a pior nota possível); sobrescrever a linha anterior; validar as duas fontes contra um teto único (aceitaria "Google 8").

**Perfil da Ouvidoria**:
O eixo de permissão próprio do contexto Ouvidoria, ortogonal ao perfil de acesso das Reuniões e ao perfil de POPs: `ouvidor` e `diretoria_executiva`. Só esses dois abrem a [Manifestação] completa, inclusive a sigilosa; o **Super admin fica de fora** (RN-40), porque administrar o sistema não é ler o relato de quem manifestou. Demais papéis de Reuniões veem só o índice. O Super admin concede o perfil pela tela de Usuários, e a concessão fica no audit log. Todo acesso à Manifestação gera registro de log.
_Evitar_: tratar Super admin como quem vê tudo; usar o perfil de Reuniões para decidir acesso ao dossiê.

**API da Ana**:
Os endpoints de serviço `/api/ana/*`: leitura das tabelas do Dados do Atendimento, registro e consulta de protocolo de ouvidoria. Autenticação por **API key de serviço** dedicada (header), fora do fluxo JWT do Supabase Auth; a chave vive no vault da plataforma da Ana e o escopo é restrito a esses endpoints. Nos endpoints de escrita, campo crítico é NOT NULL e validado (o cliente tem falha silenciosa conhecida que enviaria vazio com HTTP 200; o banco recusa). O registro de protocolo aceita, opcionalmente, os campos do Dossiê da [Manifestação] (relato integral, nome, contato, vínculo e a gravidade sugerida com grau de confiança, guardada à parte em `classificacao_ia`); o POST sem eles continua valendo. A Ana registra manifestação, não classifica caso: status, desfecho, [Tipo da manifestação] e sigilo são decisão do ouvidor e o endpoint recusa quem tentar mandá-los. Por isso o caso dela entra **sem tipo**, logo sigiloso, até o ouvidor classificar. A consulta de protocolo devolve o índice do caso comum e, do sigiloso, só o andamento: protocolo, estado e data.
_Evitar_: reusar a key para outros consumidores; endpoint anônimo; expor esses endpoints no fluxo JWT comum.

**Modo de resposta (API da Ana)**:
O degrau de detalhe que a [API da Ana] escolhe **pelo tamanho** da resposta, para caber no teto de leitura do cliente (a plataforma da Ana corta toda resposta de tool em 4.000 caracteres, sem aviso). São três, do mais rico ao mais magro: `completo` (todos os campos), `resumo` (a vitrine: nome e valor) e `indice` (só os nomes, cada item em texto e não em objeto, porque repetir o nome do campo em cada linha é o que faz o degrau mais magro estourar). O endpoint monta o `completo`; se passar de 3.500 caracteres, desce um degrau, e depois outro. Tirar campo é permitido, **tirar linha nunca**: cortar a lista é o defeito que a regra existe para matar (ADR 0032). O corpo sempre declara o `modo` e a `dica` do gesto seguinte. Cada GET de tabela aceita um filtro por termo (`?exame=`, `?especialidade=`, `?procedimento=`), com termo vazio valendo como sem filtro.

**Espelho da Global Health**:
A seção somente leitura da tela Dados do Atendimento que mostra ao vivo o que a agenda online da Global Health publica (ADR 0038). Quatro elos encadeados: especialidades publicadas, convênios aceitos e profissionais da especialidade, planos do convênio, horários livres. Botão "Atualizar" dispara a chamada; nada é gravado no banco (espelho, não cópia). O backend é o único que fala com a Global Health (o token nunca chega ao navegador), sempre a base de homologação, só leitura. Falha de rede aparece como falha, e bloco vazio diz por quê. Responde as quatro perguntas de quando a Ana não acha horário: especialidade não publicada, convênio fora da lista, médico desligado no Painel, ou agenda sem horário livre.
_Evitar_: chamar de integração de agendamento (não agenda nada), gravar o que a Global Health respondeu.
_Evitar_: paginação; cortar a lista para caber; supor que a mesma chamada devolve sempre a mesma forma.

## Tecnologia (Demandas entre o hospital e a Vitta)

**Demanda**:
Um pedido entre o hospital e a Vitta sobre as aplicações que a Vitta mantém para o hospital (Ana, Reuniões, Ouvidoria, POPs). Vai nos dois sentidos: o diretor pede à Vitta (ajuste, dúvida, consultoria) e a Vitta pede ao diretor (decisão, resposta, acesso). Vive na aba **Tecnologia** da área admin, que só o Super admin vê, e fica **totalmente apartada** das Pendências de Ata: Demanda é assunto de tecnologia entre fornecedor e cliente, Pendência é compromisso operacional do hospital. Nasceu em 08/09/2026 para tirar do WhatsApp a conversa entre o Pedro e o diretor, que se perdia.
_Evitar_: chamar de Pendência, tarefa ou ticket; misturar no painel de Pendências; "Demandas TI" (TI, no vocabulário do programa Ana, é o analista de TI do hospital, um terceiro).

**Tipo da Demanda**:
Lista fechada de sete, cada um com o seu símbolo desenhado: **Decisão** (a Vitta precisa que o hospital escolha), **Informação** (a Vitta precisa de um dado do hospital), **Terceiro** (depende de alguém de fora: Global Health, analista de TI, MV), **Ajuste** (o hospital quer mudar algo que existe), **Novo** (o hospital quer algo que não existe), **Defeito** (algo quebrado) e **Consultoria** (opinião ou estudo da Vitta, sem código).
_Evitar_: tipo fora da lista; usar o tipo para dizer de quem é a vez (isso é o estado e o responsável).

**Produto**:
Cada coisa que a Vitta mantém para o hospital, com um **dono** do lado da Vitta: Ana (WhatsApp), Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site, Infra. Lista editável pelo Super admin. Toda Demanda pertence a um Produto e nasce atribuída ao dono dele, que pode repassar.
_Evitar_: "aplicação" como eixo separado (é o mesmo eixo, agora com dono); Produto sem dono.

**Estado da Demanda**:
Cinco colunas de Kanban: **Nova**, **Em andamento**, **Aguardando**, **Concluída**, **Cancelada**. Quem move é quem atende ou quem pediu. Além do estado, a Demanda tem **Responsável** (uma pessoa), **Prioridade** (Baixa, Normal, Alta) e **Prazo** opcional, só quando existe de verdade; sem prazo o card não atrasa, só envelhece (idade em dias à vista, vermelha a partir de 14).
_Evitar_: estado por arrastar sem responsável; prazo inventado para preencher campo.

**Vínculo com o desenvolvimento**:
A ligação de uma Demanda com **uma** issue-raiz do GitHub (o PRD, ou uma issue simples de correção); as fatias são as sub-issues dessa raiz e nunca se vinculam uma a uma. Nasce por número (o PRD já existia) ou pelo botão **Levar para desenvolvimento**, que cria a issue com o texto do diretor. Só quem tem login no GitHub vê número, link e botão; o diretor vê a Etapa e O que muda. Nem toda Demanda tem Vínculo: Decisão, Informação, Terceiro e Consultoria quase nunca viram código.
_Evitar_: vincular fatia em vez do PRD; Demanda com mais de uma issue; mostrar número de issue ao diretor.

**Etapa**:
Onde a Demanda vinculada está na entrega, em palavras do diretor, sempre derivada do GitHub e nunca editada à mão: **Registrada** (sem Vínculo), **Em análise**, **Planejada**, **Em desenvolvimento**, **Entregue** e **Não será feita**. É um eixo à parte do Estado da Demanda: o Estado diz de quem é a vez na conversa, a Etapa diz o que o desenvolvimento já fez. Num PRD, vem com "X de Y partes entregues". Só uma Etapa mexe no Estado: **Entregue** devolve a Demanda a quem pediu (Aguardando, responsável o autor) para ele conferir e concluir.
_Evitar_: Etapa digitada; confundir Etapa com Estado; concluir a Demanda sozinho na entrega; Entregue como "deploy confirmado" (é o fechamento da issue).

**O que muda**:
O que a entrega acrescenta para quem pediu, em linguagem de leigo. O card da Demanda vinculada mostra o texto da entrega inteira e, embaixo, o de cada parte dela com a situação (Planejada, Em desenvolvimento, Entregue). Vem do bloco "Para o diretor" da issue e **nunca é digitado no app**: quem escreve é o planejamento da Vitta, e o app só lê (ADR 0054, decisão 7). Sem o bloco escrito, o card diz "Descrição em preparação". O botão **Copiar para IA** leva esse texto junto.
_Evitar_: reescrever o valor na descrição da Demanda (duplica e apodrece); mostrar o corpo técnico da issue no lugar do bloco; título de parte, número de issue, link ou label na tela de quem não trabalha no GitHub.

**Conversa da Demanda**:
O fio de respostas dentro do card, com @menção a quem tem acesso à aba. É onde a decisão evolui; o botão **Copiar para IA** copia a Demanda inteira (título, tipo, produto, descrição e a Conversa até ali) em texto simples, pronto para colar numa IA. E-mail sai em três gatilhos: atribuição (inclui a criação), @menção e resposta nova numa Demanda de que você é o responsável. Numa Demanda com [Vínculo com o desenvolvimento], toda resposta é espelhada como comentário na issue (ADR 0054, decisão 4): a de quem tem login no GitHub leva o marcador de automação, a de quem não tem leva o marcador do revisor e acende `revisor-comentou`; nome civil nenhum sai (só `@login` ou o rótulo "Pessoa do hospital", inclusive nas @menções do texto), e a caixa de resposta avisa que a resposta é pública; corrigir a resposta nos 10 minutos edita o comentário; linhas automáticas nunca são espelhadas e nenhum comentário do GitHub volta para o fio.
_Evitar_: e-mail por mudança de coluna; resumo diário; copiar sem a Conversa.

**Assistente de Tecnologia**:
O agente de IA que abre quando alguém da aba Tecnologia clica em "Nova Demanda" (decisão de 15/09/2026): numa tela dedicada, o diretor conversa por texto, voz, arquivo de texto, imagem ou áudio, e do outro lado o **Rascunho da Demanda** toma forma ao vivo, com os mesmos campos do formulário (título, tipo, produto, prioridade, descrição), todos editáveis à mão. O agente **nunca grava sozinho**: a Demanda só nasce no botão "Criar Demanda", pela mesma porta e com as mesmas regras de sempre (nasce Nova, com o dono do Produto), e o botão nunca é segurado por falta de informação. Ele conhece a casa pelo [Kit de conhecimento] e as Demandas abertas do Quadro: responde ali mesmo o que está escrito no kit, dizendo de onde tirou, e oferece registrar mesmo assim; o que não está no kit ele não responde, registra. Avisa quando já existe Demanda aberta sobre o mesmo assunto. Tudo que entra é **efêmero**: anexo, áudio e a própria conversa não persistem; o produto é a Demanda com a descrição no [Roteiro por Tipo]. Sem nome próprio: nome próprio compete com a Ana. O formulário antigo continua a um clique ("prefiro preencher à mão").
_Evitar_: nome de persona; agente que cria Demanda sem clique humano; guardar a conversa na Conversa da Demanda ou em tabela própria; segurar a criação até o roteiro estar completo; responder de cabeça o que não está no kit.

**Kit de conhecimento**:
O conjunto de textos que o [Assistente de Tecnologia] recebe inteiro a cada conversa: um arquivo por Produto (Ana, Integração Ana x MV, Reuniões, Ouvidoria, POPs, Site, Infra) mais um sobre a própria aba Tecnologia. Escrito para o leitor diretor, em linguagem de uso, sem número de issue, label, nome de tabela ou vocabulário interno do repositório. Vive no código do backend e viaja no deploy; é um documento **curado por gente**, com regra própria de sincronia: mudou o comportamento de um módulo, o arquivo dele muda no mesmo PR (o [Manual] segue outra regra: página própria na fatia de manual do mesmo PRD, ADR 0057). Não é o glossário nem o manual copiados: é uma terceira escrita, para outro leitor.
_Evitar_: mandar `CONTEXT.md` ou o manual em HTML ao modelo; busca vetorial; gerar o kit por script a partir do glossário; kit desatualizado (vira agente mentindo).

**Roteiro por Tipo**:
A forma da descrição que o [Assistente de Tecnologia] monta, em texto puro com rótulos fixos por [Tipo da Demanda]: Defeito (Onde, O que aconteceu, O que esperava, Quando, Como repetir), Novo e Ajuste (O que precisa, Por quê, Quem usa, Hoje é assim), Informação e Consultoria (Pergunta, Contexto, O que já sei), Terceiro (Quem de fora, O que falta dele). Só entra o que o diretor disse; rótulo sem resposta não aparece, e se ele criar antes de responder tudo, o rótulo sai como "não informado". Prioridade nasce Normal e só sobe se o diretor disser que é urgente; prazo só quando ele disser uma data de verdade. O roteiro é também a lista do que o agente ainda pergunta.
_Evitar_: markdown na descrição; inventar prioridade ou prazo; rótulo preenchido com suposição do modelo.

## Manual do usuário

**Manual**:
O site único de documentação da plataforma para quem usa o app no hospital (decisão de 15/09/2026, grilling; ADR 0057). Um endereço só, organizado **por módulo, na ordem do menu do app** (Primeiros passos, Reuniões e metas, Ouvidoria, POPs, Admin), e dentro de cada módulo uma [Visão geral do módulo], as [Páginas de tarefa], as páginas [Como funciona] e as [Novidades]. Publica **só o que está em produção**: o que ainda não subiu fica escrito, mas invisível, até o deploy. A aba Tecnologia fica fora (ferramenta da Diretoria com a Vitta). O app aponta para ele por um item **Ajuda** no menu, que abre a seção do módulo em que a pessoa está.
_Evitar_: um manual por módulo em endereços separados; manual por papel (o papel é selo, não estrutura); selo "em desenvolvimento" ou "planejado" para o usuário; capítulo técnico (endpoint, gatilho de e-mail, variável) dentro do manual.

**Página de tarefa**:
A unidade do [Manual]: uma ação que alguém faz no app, com o título no infinitivo ("Registrar uma manifestação", "Assinar a ata"). Molde fixo e curto: **quando usar** (uma frase), **quem faz** (selos), o [Vídeo de tarefa], **passo a passo** (até 6 passos, print só quando a tela muda) e **se der errado** (2 a 4 situações). Tratamento "você", passos no imperativo, e a palavra é sempre a que aparece na tela. Cabe numa tela de celular; passou disso, são duas tarefas. Publica sem vídeo, com aviso "vídeo em produção".
_Evitar_: "por que existe", histórico, conceito (isso é [Como funciona]); "o usuário deverá"; sinônimo inventado para o nome do botão.

**Selo**:
Marcação curta na [Página de tarefa] que diz quem faz (Ouvidoria, Gestor do setor, Facilitador, Secretária), **Só admin** para o que só o Super admin vê, e **Sem login** para as telas que a pessoa abre por link ou QR sem entrar no app (formulário público, portal do setor, aceite da Ata). Telas sem login moram dentro do módulo delas, com o selo, não numa seção à parte.

**Visão geral do módulo**:
A página de abertura de cada módulo do [Manual]: o que o módulo é em poucas linhas, as palavras que a pessoa vai ver o tempo todo, o caminho de ponta a ponta (o caminho de um caso, o caminho de uma Ata) e os vídeos de capítulo quando existem. É o único lugar do módulo onde conceito tem vez.

**Como funciona**:
Página de um tema do módulo que não é ação de ninguém, mas que a pessoa precisa entender para não estranhar o app ("Como o prazo é contado", "O que o sistema apaga sozinho"). Fica fora da lista de tarefas, no fim do módulo.

**Novidades**:
Página de cada módulo com **uma entrada por PRD entregue**, da mais nova para a mais antiga: título em linguagem de usuário, mês e ano do deploy, duas linhas do que mudou, o [Vídeo de percepção de valor] quando existe, e links para as [Páginas de tarefa] que nasceram ou mudaram.
_Evitar_: uma entrada por deploy ou por fix (isso é o changelog, que é doc de engenharia).

**Vídeo de tarefa**:
O vídeo de 30 a 60 s de uma [Página de tarefa]: um exemplo único com dados de exemplo, do primeiro clique ao resultado, mudo, com legendas curtas, gerado com a mesma receita do [Vídeo de percepção de valor] e aprovado por gente antes de publicar. Regerável quando a tela muda. Não é gravação de tela com voz.
_Evitar_: um vídeo por capítulo como unidade (obriga a assistir 90 s para achar 15); vídeo obrigatório para publicar a página.

**Vídeo de percepção de valor**:
O vídeo de uma entrega (PRD) feito para o diretor ver o sistema funcionando (ADR 0026, ADR 0045): a unidade é o que mudou, não a tarefa. No [Manual] ele entra em [Novidades], e serve de [Vídeo de tarefa] quando a entrega coincide com uma tarefa.

**Roteiro de prints**:
O script versionado, um por módulo, que abre o app local com dados de exemplo, navega e captura os prints que as páginas daquele módulo usam. Print do [Manual] é sempre tela real do app, nunca desenho; mudou a tela, roda o roteiro de novo.
_Evitar_: print tirado à mão sem roteiro; quadro extraído do vídeo no lugar do print.

**Fatia de manual**:
A issue que todo PRD com tela ganha no fim, bloqueada pelas fatias de código: escreve ou muda as [Páginas de tarefa], roda o [Roteiro de prints], produz os [Vídeos de tarefa] e a entrada de [Novidades]. Nasce invisível e aparece no deploy do PRD. É o par do vídeo de divulgação: uma entrega, uma fatia de manual.
_Evitar_: manual dentro do PR de código (a tela ainda não existe para o print); manual fora da fila de issues (some da cobrança).

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
