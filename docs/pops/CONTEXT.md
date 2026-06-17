# Gestão de POPs — HSM

Gerencia o ciclo de vida dos **POPs** (Procedimentos Operacionais Padrão) do Hospital São Matheus: elaboração assistida por IA → revisão → validação → assinatura digital → publicação na Biblioteca → treinamentos da equipe. Segundo contexto do repositório (ver [CONTEXT-MAP.md](../../CONTEXT-MAP.md)); convive com o contexto Reuniões no mesmo app, com glossário e permissões próprios. Nasceu do grilling do DRF da Diretoria (maio/2026); curado por humano daqui em diante.

## Pessoas e papéis de acesso

**Superadmin (POPs)**:
Perfil de acesso da Diretoria Executiva. Vê todos os POPs de todos os Setores, acessa o Dashboard completo e é o único que cria, edita e revoga usuários. Papel funcional do dia a dia — **não** confundir com o Super admin das Reuniões (bypass de debug).
_Evitar_: super admin (sem qualificar o contexto), administrador, diretoria (como nome de papel técnico).

**Gestor de Qualidade**:
Coordenador de Qualidade / Assessor de Acreditação. Lê todos os POPs de todos os Setores, cria e edita POPs em qualquer Setor, acessa o Dashboard completo. Não gerencia usuários.
_Evitar_: qualidade (como papel), auditor.

**Gerente**:
Perfil com acesso aos POPs dos **Setores sob sua gestão** (um ou mais). Cria POPs nesses Setores e recebe os alertas de prazo da sua área. Não acessa o Dashboard da Diretoria.

**Coordenador**:
Perfil com acesso aos POPs do **seu Setor** (normalmente um). Cria POPs e gere os eventos de Treinamento do Setor. Não acessa o Dashboard da Diretoria.

**Colaborador operacional**:
Técnicos, enfermeiros, médicos assistentes, ASG etc. **Não loga** na aplicação (mesmo sentido de "Colaborador" no contexto Reuniões) — é treinado nos POPs e aparece nas Listas de Presença. Rastreamento individual por colaborador é Fase 2.
_Evitar_: usuário, funcionário (no sentido de quem acessa o sistema).

> Os perfis de acesso do POPs vivem num eixo próprio (`perfil_pop`) na mesma entidade pessoa (`participantes`) usada pelas Reuniões — ortogonal ao `access_profile`. Ganhar perfil POP implica ganhar login. Ver [ADR 0007](../adr/0007-pops-segundo-contexto-mesmo-app.md).

## Papéis no fluxo de uma Versão

São designações **por POP** (escolhidas na criação, entre usuários cadastrados) — não perfis de acesso:

**Elaborador**:
Responsável por redigir o POP, interagindo com o agente de IA no ambiente de elaboração.

**Revisor**:
Responsável pela Revisão (etapa) — análise técnica que aprova ou devolve com comentários.

**Validador**:
Responsável pela Validação — aprovação final antes da assinatura digital. No DRF aparece como "Validador/Aprovador"; o termo canônico aqui é **Validador**.
_Evitar_: aprovador (reservar "aprovar" para o ato).

## Estrutura

**POP**:
Procedimento Operacional Padrão — a entidade permanente que padroniza um procedimento de um Setor. Carrega Código travado, criticidade (CRÍTICA/ALTA/MÉDIA), base normativa, Periodicidade de revisão e os responsáveis designados. O conteúdo em si vive nas suas **Versões**.
_Evitar_: procedimento (cru), protocolo, documento.

**Versão**:
Uma edição do conteúdo de um POP que percorre o fluxo (`A Elaborar → Em Elaboração → Em Revisão → Em Validação → Em Assinatura → Publicado`; Devoluções retornam a Em Elaboração). A **versão vigente** é a última Publicada; uma nova Versão pode estar em fluxo enquanto a vigente segue válida na Biblioteca. Numeração: 1.0 inicial; ajuste menor incrementa minor (1.1), revisão estrutural incrementa major (2.0) — quem inicia a revisão escolhe, com sugestão da IA.
_Evitar_: confundir com o POP (a entidade-mãe).

**Setor**:
Unidade do organograma do HSM (CTI, Centro Cirúrgico, Farmácia, Faturamento…). Entidade própria com nome e **sigla** (base do Código). Usuários se vinculam a Setores (Gerente: vários; Coordenador: normalmente um). Não confundir com o campo livre `setor` do cadastro de participantes das Reuniões.
_Evitar_: área, departamento, unidade.

**Código**:
Identificador travado do POP, `HSM_[SIGLA]-[NNN]`, com sequência por Setor (ex.: `HSM_CTI-001`). Gerado na criação e imutável — nenhum usuário o edita.

**Material de referência**:
Arquivos que o Elaborador sobe na Elaboração (POPs antigos, RDCs, resoluções, artigos). O agente os lê e usa **ativamente** — pode reescrever e reestruturar sem preservar o original. Conduta oposta à do **Documento de apoio** da Ata Guiada (contexto Reuniões), que é consultado só sob demanda. Quando um Material traz um **modelo de POP**, o agente **espelha a estrutura dele**: a estrutura do POP é dinâmica (lista de seções), não um template fixo (ver [ADR 0016](../adr/0016-estrutura-dinamica-pop-guiada-material.md)).
_Evitar_: documento de apoio (termo do outro contexto), anexo.

## Ciclo de vida

**Elaboração**:
Etapa em que o Elaborador produz o conteúdo da Versão com o agente de IA, a partir dos Materiais de referência. Termina quando ele aprova a versão final e o fluxo segue ao Revisor.

**Revisão (etapa)**:
Análise técnica do Revisor dentro do fluxo de uma Versão. Aprova ou lança Devolução. **Não confundir** com Revisão periódica — o DRF usa "revisão" para os dois sentidos; aqui sempre qualificamos.

**Revisão periódica**:
O ciclo programado de re-elaboração de um POP Publicado, ditado pela Periodicidade de revisão (contada da data de assinatura). Reinicia o fluxo completo — mesmo sem mudança de conteúdo exige nova passagem por Elaboração → Revisão → Validação → assinatura. Gera nova Versão; a anterior vira Versão Descontinuada.
_Evitar_: revisão (sem qualificar), renovação.

**Validação**:
Aprovação final pelo Validador antes da assinatura digital.

**Devolução**:
Ato de Revisor ou Validador retornarem a Versão ao Elaborador com comentários (registrados com nome e timestamp). Após a resposta (prazo: 5 dias úteis), o fluxo volta **direto a quem devolveu** — uma Devolução do Validador não repassa pelo Revisor. Sem limite de ciclos.
_Evitar_: rejeição, reprovação.

**Publicado**:
Estado terminal de uma Versão: assinada por Elaborador, Revisor e Validador no ClickSign (mesma mecânica de Envelope do contexto Reuniões) e disponível na Biblioteca como versão vigente.
_Evitar_: aprovado (é a etapa anterior), assinado (é o meio, não o estado).

**Periodicidade de revisão**:
Intervalo entre Revisões periódicas: 3 meses, 6 meses, 1 ano ou 2 anos. Sugerida pela IA na Elaboração, escolhida pelo Elaborador. Conta a partir da assinatura.

**Versão Descontinuada**:
Versão anterior substituída por uma mais recente. Permanece para sempre com PDF assinado, datas, signatários e motivo da descontinuação.
_Evitar_: versão antiga, arquivada, deletada.

## Biblioteca

**Biblioteca**:
O repositório oficial e único dos POPs com Versão Publicada, organizado por Setor, com Semáforo de validade e download do PDF. POPs vencidos **nunca** saem da Biblioteca.
_Evitar_: repositório, acervo, drive.

**Semáforo de validade**:
Condição de validade da versão vigente — ortogonal ao fluxo: 🟢 **Válido** (dentro do prazo), 🟡 **Atenção** (entre D-90 e D-30 do vencimento), 🔴 **Revisão Pendente** (prazo de Revisão periódica vencido; o POP permanece acessível com o apontamento).
_Evitar_: status (cru), farol.

## Treinamento e avaliação

**Treinamento**:
Evento (presencial ou videoconferência) que capacita Colaboradores operacionais em um ou mais POPs Publicados. Tem Ministrante, data prevista definida pelo gestor, pauta e Evidências obrigatórias para fechar o registro. Novo ciclo é disparado por Revisão periódica vencida ou nova Versão com alterações significativas.
_Evitar_: capacitação, curso, reunião (termo do outro contexto).

**Ministrante**:
Quem conduz o Treinamento — qualquer usuário cadastrado, não necessariamente o Elaborador do POP.
_Evitar_: instrutor, professor.

**Lista de Presença**:
PDF gerado pelo sistema ao criar o Treinamento (logotipo, POPs com código e versão, tabela de participantes com coluna de Nota). É impressa, assinada fisicamente, preenchida com as notas pelo Ministrante, digitalizada e devolvida por upload — tornando-se a evidência-fonte da Avaliação.

**Evidência**:
O que fecha o registro de um Treinamento: Lista de Presença assinada com notas (PDF/JPG/PNG) + ao menos 1 foto do evento.

**Avaliação**:
Nota 0–10 por participante, atribuída pelo Ministrante na Lista de Presença física. O sistema lê o scan e **pré-preenche** os dados, que um humano confirma antes de valerem — só então alimentam os indicadores (média da turma, % abaixo da nota mínima 7,0, configurável). Na Fase 1 os indicadores são agregados por turma; nota individual rastreada por colaborador é Fase 2.
_Evitar_: prova, teste (o teste em si é externo, via NotebookLM).

## Dashboard

**Alerta de risco**:
Aviso no Dashboard da Diretoria sobre POP crítico não publicado ou com Revisão periódica vencida, classificado como **Risco Regulatório** (exposição ANVISA/ONA/JCI) ou **Risco Assistencial** (segurança do paciente), com recomendação objetiva de ação. O gatilho é regra determinística (criticidade × prazo × estado); a IA apenas redige a recomendação.
_Evitar_: notificação (reservado aos emails), warning.
