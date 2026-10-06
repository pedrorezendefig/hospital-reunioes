# Índice dos ADRs por tema

Só `status: accepted` vale como decisão; `superseded` é histórico (CLAUDE.md). Supersessão e emenda são bidirecionais e o CI `lint-adr` trava. Os números que faltam (0009, 0010, 0019) foram removidos com o contexto que os motivou: histórico é o git (ADR 0044).

## Ouvidoria

| ADR | Status | Título |
|---|---|---|
| [0031](0031-dados-do-atendimento-ana-migram-para-o-app.md) | accepted | Dados do atendimento da Ana migram para o app: módulo admin, painel de ouvidoria e API de serviço |
| [0032](0032-resposta-da-api-da-ana-cabe-no-teto-do-cliente.md) | accepted | A resposta da API da Ana é dimensionada pelo teto de leitura do cliente |
| [0034](0034-ouvidoria-vira-tramitacao-dossie-despacho-cobranca.md) | accepted | Ouvidoria vira tramitação: dossiê no app, despacho por link tokenizado e cobrança com escalonamento |
| [0036](0036-qr-da-ouvidoria-vira-ponto-de-escuta-cadastrado.md) | accepted | O QR da Ouvidoria vira Ponto de escuta cadastrado, com código curto no cartaz |
| [0037](0037-tipo-da-manifestacao-e-lista-fechada-e-decide-o-sigilo.md) | accepted | O tipo da manifestação é lista fechada, e é ele que decide o sigilo |
| [0038](0038-convenios-sai-cobertura-vem-da-agenda-e-espelho-gh.md) | accepted | Convênios por especialidade sai do app: cobertura vem da agenda online e o Espelho da Global Health entra no lugar |
| [0039](0039-email-da-ouvidoria-sai-por-processador-externo.md) | accepted | O email da Ouvidoria sai por processador externo (Resend, fora do Brasil) |
| [0040](0040-informacao-entra-na-lista-de-tipos.md) | accepted | `informacao` entra na lista de tipos; os nomes atuais ficam |
| [0041](0041-acionamento-leva-resumo-relato-integral-e-nota.md) | accepted | O acionamento leva resumo, relato integral e nota da ouvidoria |
| [0042](0042-retornos-ao-manifestante-acuse-e-encerramento.md) | accepted | Retornos ao manifestante: acuse em horas corridas e aviso de encerramento |
| [0047](0047-apagar-manifestacao-e-retencao-antecipada-nao-delete.md) | accepted | Apagar manifestação é retenção antecipada, não DELETE |
| [0048](0048-devolucao-a-ouvidoria-volta-a-classificacao-e-t1-novo.md) | accepted | Devolução à Ouvidoria volta o caso à classificação, e o reacionamento carimba T1 novo |
| [0051](0051-email-recebido-passa-por-triagem-antes-de-virar-manifestacao.md) | accepted | E-mail recebido em ouvidoria@ passa por triagem antes de virar manifestação |
| [0052](0052-paciente-do-caso-viaja-para-a-area-no-caso-anonimo.md) | accepted | O Paciente do caso viaja para a área, inclusive no caso anônimo |
| [0055](0055-redirecionamento-pelo-ouvidor-e-cadastro-de-responsaveis-pelo-ouvidor.md) | accepted | O ouvidor redireciona o caso para outra área num ato só, e passa a manter o cadastro de responsáveis |

## Tecnologia (Demandas Vitta x Hospital)

| ADR | Status | Título |
|---|---|---|
| [0050](0050-demandas-de-tecnologia-moram-no-app-apartadas-das-pendencias.md) | accepted | Demandas de tecnologia moram no app do hospital, só para Super admin, apartadas das Pendências |
| [0054](0054-demanda-vinculada-a-issue-etapa-derivada-e-revisor-no-app.md) | accepted | Demanda vinculada a issue do GitHub: Etapa derivada, comentário do diretor espelhado e a bola volta a quem pediu (emenda 0020) |
| [0056](0056-assistente-de-tecnologia-rascunho-confirmado-kit-proprio.md) | accepted | Assistente de Tecnologia: rascunho confirmado por gente, kit próprio embarcado, responde do kit ou registra |
| [0060](0060-texto-que-sai-para-a-issue-publica-passa-pela-peneira-de-dado-pessoal.md) | accepted | Texto que sai para a issue pública passa pela peneira de dado pessoal (emenda 0054) |

## Central de Comando (números do ecossistema digital)

| ADR | Status | Título |
|---|---|---|
| [0058](0058-central-de-comando-migra-para-dentro-do-app.md) | accepted | Central de Comando migra para dentro do app do hospital, só para Super admin, com o servidor portado para o FastAPI (emenda 0057) |
| [0059](0059-central-de-comando-aquece-o-cache-no-boot.md) | accepted | Central de Comando aquece o cache uma vez no boot, só no período padrão (emenda 0058) |

## Reuniões e Atas

| ADR | Status | Título |
|---|---|---|
| [0003](0003-estado-terminal-aprovada-sem-assinatura.md) | accepted | Estado terminal APROVADA: aprovação sem assinatura digital |
| [0004](0004-nota-registro-dinamico-paralelo-reuniao.md) | superseded | Nota: registro dinâmico paralelo à Reunião |
| [0005](0005-ata-guiada-segundo-modo-de-geracao.md) | accepted | Ata Guiada: segundo modo de gerar a Ata, sem Transcrição |
| [0006](0006-ata-guiada-tela-dedicada-documento-apoio.md) | accepted | Ata Guiada em tela dedicada: ata viva, correção pelo próprio chat e documento de apoio |
| [0008](0008-resolucao-de-responsavel-ao-vivo-na-ata-guiada.md) | accepted | Resolução de responsável ao vivo na Ata Guiada: LLM conversa, backend vincula |
| [0011](0011-descontinuar-notas-e-importacao-de-atas.md) | accepted | Descontinuar Notas e Importação de ATAs |
| [0023](0023-governanca-lista-participantes-ata.md) | accepted | Governança da lista de participantes da Ata |
| [0030](0030-pendencia-nasce-por-assinatura-gatilho-incremental.md) | accepted | Pendência nasce por assinatura: gatilho incremental e Aceite interno |

## POPs

| ADR | Status | Título |
|---|---|---|
| [0007](0007-pops-segundo-contexto-mesmo-app.md) | accepted | POPs: segundo contexto de domínio no mesmo app, com eixo de permissão próprio |
| [0014](0014-autoridade-concessao-perfil-pop-unificada.md) | accepted | Autoridade de concessão do perfil POP unificada no Super Admin de Reuniões |
| [0015](0015-papeis-fluxo-pop-editaveis-ate-assinatura.md) | accepted | Papéis do fluxo de POP editáveis até a assinatura |
| [0016](0016-estrutura-dinamica-pop-guiada-material.md) | accepted | Estrutura dinâmica do POP guiada pelo material de referência |
| [0017](0017-fluxograma-pop-mermaid-svg-no-pdf.md) | accepted | Fluxograma de POP em Mermaid: interativo na tela, SVG no PDF |
| [0018](0018-elaboracao-pop-especializada-por-natureza.md) | superseded | Elaboração de POP especializada por Natureza, com seleção automática |
| [0021](0021-rollback-natureza-elaboracao-ancorada-no-material.md) | accepted | Rollback da Natureza: Elaboração única ancorada no Material anexado |
| [0024](0024-fluxograma-pop-renderer-proprio-json.md) | accepted | Fluxograma de POP: o agente emite estrutura JSON e o app desenha o SVG |

## Workflow de agentes e ondas

| ADR | Status | Título |
|---|---|---|
| [0020](0020-ciclo-de-vida-da-issue-status-fiel-e-loop-do-diretor.md) | accepted | Ciclo de vida da issue: status fiel, critérios auto-verificados e loop do diretor |
| [0022](0022-onda-execucao-autonoma-da-fila.md) | superseded | Onda: execução autônoma da fila em ondas com checkpoint por lote e deploy único |
| [0027](0027-wayfinder-on-ramp-situacional.md) | accepted | Wayfinder: on-ramp situacional para planejamento multi-sessão, sob demanda |
| [0028](0028-bloqueio-por-dependencia-nativa.md) | accepted | Bloqueio entre issues por dependência nativa do GitHub |
| [0029](0029-onda-goal-prd-fonte-verdade-github.md) | superseded | Onda escopada em PRD: goal de conclusão, fonte de verdade no GitHub e orquestrador magro |
| [0035](0035-gates-de-review-da-onda-pertencem-ao-orquestrador.md) | superseded | Gates de review da onda pertencem ao orquestrador |
| [0061](0061-um-pipeline-dono-por-prd-e-main-protegida.md) | superseded | Um pipeline só, dono por PRD e `main` protegida: a esteira para três sócios em paralelo (emenda 0022, 0035) |
| [0062](0062-hospital-os-le-o-github-e-o-rabo-grava-so-a-verdade-do-deploy.md) | superseded | Hospital OS lê o GitHub ao vivo; o rabo grava só a verdade do deploy (emenda 0022, 0057, 0061) |
| [0063](0063-fluxo-automatico-ate-producao-so-a-migration-para.md) | superseded | Fluxo automático até produção: só a migration para no humano (emenda 0061) |
| [0064](0064-revisao-so-must-fix-e-merge-pr-a-pr-sem-em-dia-com-a-base.md) | superseded | Revisão só de must-fix em uma rodada, segurança por PRD; merge PR a PR sem "em dia com a base" (emenda 0061, 0062, 0063; emendada pela 0066 e 0067) |
| [0065](0065-bypass-da-main-e-uma-deploy-key-no-job-que-nao-instala-nada.md) | superseded | O bypass da `main` é uma deploy key, usada só no job da Action que não instala nada (emenda 0062) |
| [0066](0066-ondas-por-dependencia-nao-por-arquivo.md) | superseded | Ondas se separam por dependência, não por arquivo (emenda 0063, 0064) |
| [0067](0067-ferramenta-sem-revisor-e-revisao-unica-no-app.md) | superseded | PR de ferramenta sem revisor, revisão única no app, agente nunca para para perguntar (emenda 0064) |
| [0068](0068-o-fluxo-em-uma-pagina.md) | accepted | O fluxo em uma página: de issue a produção, como roda hoje (substitui 0022, 0029, 0035, 0061 a 0067) |
| [0043](0043-skills-locais-sao-o-kit-do-workflow.md) | accepted | Skills locais são o kit completo do workflow, duplicata com as globais é intencional |
| [0049](0049-wayfinder-instalada-e-lock-com-ref.md) | accepted | A wayfinder entra instalada no clone, e o `skills-lock.json` fixa o commit de origem |
| [0053](0053-fluxo-exportavel-por-roteiro-versionado.md) | accepted | O fluxo de trabalho é exportável por um roteiro versionado no repositório, não por prompt solto |

## UI e design system

| ADR | Status | Título |
|---|---|---|
| [0012](0012-ds-select-proprio-sem-select-nativo.md) | accepted | DS Select próprio para seleção única, sem `<select>` nativo |
| [0013](0013-saida-ia-sem-travessao-sanitizador.md) | accepted | Saída da IA sem travessão: sanitizador determinístico + convenção nos prompts |
| [0025](0025-dashboard-diagramas-renderer-proprio.md) | accepted | Dashboard desenha os diagramas com renderer próprio; mermaid.js sai do painel |
| [0033](0033-role-etiqueta-interna-invisivel-ao-usuario.md) | accepted | Role é etiqueta interna: o próprio usuário nunca vê o seu role |

## Comunicação e layout do repo

| ADR | Status | Título |
|---|---|---|
| [0026](0026-percepcao-de-valor-em-video-hyperframes.md) | accepted | Percepção de Valor passa a ser vídeo renderizado (HyperFrames); o HTML interativo com stepper é aposentado |
| [0044](0044-layout-do-repositorio.md) | accepted | Layout do repositório: o que fica no git, onde fica, e o que vive fora |
| [0045](0045-video-e-pagina-de-divulgacao-sao-uma-entrega-so.md) | accepted | Vídeo de percepção e página de divulgação são uma entrega só, numa pasta só por PRD |
| [0057](0057-manual-do-usuario-site-unico-por-modulo-e-fatia-de-manual-por-prd.md) | accepted | Manual do usuário: um site por módulo, vídeo por tarefa, fatia de manual por PRD (emenda 0044 e 0056) |
| [0046](0046-readme-e-o-mapa-do-repositorio.md) | accepted | O `README.md` da raiz é o mapa do repositório |
| [0047](0047-apagar-manifestacao-e-retencao-antecipada-nao-delete.md) | accepted | Apagar manifestação é retenção antecipada, não DELETE |

## Infra e deploy

| ADR | Status | Título |
|---|---|---|
| [0001](0001-supabase-self-hosted-coolify.md) | accepted | Supabase self-hosted no Coolify (não managed) |
| [0002](0002-controle-acesso-aplicacao-service-role.md) | accepted | Controle de acesso na aplicação (SERVICE_ROLE_KEY), não RLS |

Novo ADR: acrescente a linha no tema certo neste índice, no mesmo commit.
