# ROTAS.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-09-02T11:01-0300 -->

Endpoints HTTP expostos pelo backend FastAPI do Hospital Reuniões.

## aceite (`app/routers/aceite.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/aceite/meu-link` | Link de aceite do próprio signatário, para o sino do Facilitador. | ✅ |
| GET | `/aceite/{token}` | Dados da página pública: a ata completa + quem está aceitando. | ❌ |
| POST | `/aceite/{token}/aceitar` | Botão "Li e aceito": registra o aceite (origem `aceite_interno`), cria | ❌ |

## ana (`app/routers/ana.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/ana/cirurgias-estimativas` | Estimativas de cirurgias ativas, com valores e caveat obrigatório. | ✅ |
| GET | `/ana/consultas-particulares` | Consultas particulares ativas, com preços e diferenciais. | ✅ |
| GET | `/ana/exames` | Exames ativos, com valores, preparo e local de realização. | ✅ |
| POST | `/ana/ouvidoria/protocolos` | Registra a manifestação e devolve o protocolo ANO-NNNN gerado pelo banco | ✅ |
| GET | `/ana/ouvidoria/protocolos/{protocolo}` | Consulta o índice da manifestação pelo número de protocolo (ANO-NNNN). | ✅ |

## pops (`app/routers/pops/assinatura.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/pops/{pop_id}/assinatura/reenviar` | Re-tenta o envio ao ClickSign de uma Versão EM_ASSINATURA. Exclusivo | ✅ |

## auth (`app/routers/auth.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/auth/invite/{participante_id}` | Envia e-mail de redefinição de senha para um participante. | ✅ |
| GET | `/auth/me` | Retorna dados do usuário autenticado via JWT. | ✅ |

## pops (`app/routers/pops/biblioteca.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pops/biblioteca` | Os POPs Publicados do escopo do perfil, com metadados completos. | ✅ |

## comentarios (`app/routers/comentarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pendencias/{id_acao}/comentarios` | Lista comentários de uma pendência, ordenados do mais antigo ao mais recente. | ✅ |
| POST | `/pendencias/{id_acao}/comentarios` | Cria um comentário na pendência e gera notificações de menção. | ✅ |
| DELETE | `/pendencias/{id_acao}/comentarios/{comentario_id}` | Exclui um comentário. Apenas o autor pode excluir. | ✅ |
| GET | `/pendencias/{id_acao}/mencionaveis` | Lista participantes mencionáveis no chat da Pendência (quem enxerga a Pendência). | ✅ |

## configuracoes (`app/routers/configuracoes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/configuracoes` | Get configuracoes | ✅ |
| PATCH | `/configuracoes` | Update configuracoes | ✅ |

## admin (`app/routers/admin/dados_atendimento.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/dados-atendimento/cirurgias-estimativas` | Lista todas as linhas (ativas e desativadas) e a data da última | ✅ |
| POST | `/admin/dados-atendimento/cirurgias-estimativas` | Create cirurgias estimativas | ✅ |
| PATCH | `/admin/dados-atendimento/cirurgias-estimativas/{item_id}` | Update cirurgias estimativas | ✅ |
| GET | `/admin/dados-atendimento/consultas-particulares` | Lista todas as linhas (ativas e desativadas) e a data da última | ✅ |
| POST | `/admin/dados-atendimento/consultas-particulares` | Create consultas particulares | ✅ |
| PATCH | `/admin/dados-atendimento/consultas-particulares/{item_id}` | Update consultas particulares | ✅ |
| GET | `/admin/dados-atendimento/exames` | Lista todas as linhas (ativas e desativadas) e a data da última | ✅ |
| POST | `/admin/dados-atendimento/exames` | Create exames | ✅ |
| PATCH | `/admin/dados-atendimento/exames/{item_id}` | Update exames | ✅ |

## pops (`app/routers/pops/documento.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pops/{pop_id}/documento` | PDF institucional das seções dinâmicas, com o nome travado do DRF §3.3. | ✅ |

## pops (`app/routers/pops/elaboracao.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pops/{pop_id}/elaboracao` | Estado completo da tela de elaboração — reabrir recupera o rascunho | ✅ |
| POST | `/pops/{pop_id}/elaboracao/aprovar` | "Aprovar versão final": EM_ELABORACAO → EM_REVISAO (auditado) + email | ✅ |
| POST | `/pops/{pop_id}/elaboracao/chat` | Chat do agente de elaboração — stateless, síncrono, sem pipeline. | ✅ |
| POST | `/pops/{pop_id}/elaboracao/fluxograma-svg` | Persiste na Versão o SVG do fluxograma renderizado no cliente (ADR 0017). | ✅ |
| POST | `/pops/{pop_id}/elaboracao/materiais` | Upload múltiplo de Materiais de referência (.pdf/.docx/.txt/.md) — o | ✅ |
| DELETE | `/pops/{pop_id}/elaboracao/materiais/{material_id}` | Remove um Material de referência — sai do contexto das interações | ✅ |
| PATCH | `/pops/{pop_id}/elaboracao/periodicidade` | Escolha final do Elaborador para a Periodicidade de revisão — o agente | ✅ |

## admin (`app/routers/admin/espelho_global_health.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/espelho-global-health/especialidades` | Elo 1: especialidades publicadas na agenda, ao vivo. | ✅ |
| GET | `/admin/espelho-global-health/especialidades/{especialidade_id}/convenios` | Elo 2a: convênios aceitos na especialidade escolhida. | ✅ |
| GET | `/admin/espelho-global-health/especialidades/{especialidade_id}/convenios/{convenio_id}/planos` | Elo 3: planos do convênio, dentro da especialidade escolhida. | ✅ |
| GET | `/admin/espelho-global-health/especialidades/{especialidade_id}/convenios/{convenio_id}/planos/{plano_id}/horarios` | Elo 4: os horários livres da combinação escolhida na tela. | ✅ |
| GET | `/admin/espelho-global-health/especialidades/{especialidade_id}/profissionais` | Elo 2b: profissionais disponíveis na especialidade escolhida. | ✅ |

## health (`app/routers/health.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/health` | Health check | ❌ |

## admin (`app/routers/admin/legacy.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/email/status` | Get email status | ✅ |
| POST | `/admin/email/test` | Send test email | ✅ |
| GET | `/admin/integracoes` | Get integracoes | ✅ |
| POST | `/admin/integracoes/{nome}/test` | Test integracao | ✅ |

## notificacoes (`app/routers/notificacoes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/notificacoes` | Lista notificações do usuário autenticado. | ✅ |
| GET | `/notificacoes/count` | Retorna a contagem de notificações não lidas. | ✅ |
| PATCH | `/notificacoes/ler-todas` | Marca todas as notificações do usuário como lidas. | ✅ |
| PATCH | `/notificacoes/{notificacao_id}/lida` | Marca uma notificação como lida. | ✅ |

## ouvidoria (`app/routers/ouvidoria.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/ouvidoria/feriados` | Os dias que saem do calendário útil (RN-22). | ✅ |
| POST | `/ouvidoria/feriados` | Cadastra um feriado. A partir daqui o motor deixa de contar esse dia. | ✅ |
| DELETE | `/ouvidoria/feriados/{data}` | Remove um feriado: o dia volta a contar no calendário útil. | ✅ |
| POST | `/ouvidoria/manifestacoes` | Registra a manifestação que chegou por telefone, balcão ou email. | ✅ |
| GET | `/ouvidoria/manifestacoes/por-protocolo/{protocolo}` | Abre o Dossiê pelo protocolo, que é o endereço público do caso (RN-53). | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}` | Abre o Dossiê completo de uma manifestação. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/anexos` | Anexos do caso, sem o caminho no storage: o acesso ao binário é sempre | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/anexos` | Guarda a evidência junto do caso: foto, PDF, áudio ou documento. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/anexos/{anexo_id}/url` | URL assinada, com expiração, para abrir o anexo. | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/classificacao` | Classifica a manifestação e, no mesmo ato, resolve o sigilo dela. | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/devolucoes` | Devolve ao setor a resposta que não resolve, com meio prazo novo. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/movimentos` | A linha do tempo do caso: a trilha imutável lida, enfim (issue #485). | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/notificacoes` | Toda notificação que o caso já gerou, da mais recente para a mais antiga. | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/notificacoes/{notificacao_id}/reenviar` | Manda a mesma notificação de novo, quando o setor diz que não recebeu. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/prorrogacoes` | O pedido de prorrogação do caso, quando existe. É uma lista de zero ou | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/prorrogacoes/{prorrogacao_id}/decidir` | O ouvidor aprova ou nega o pedido da área (PRD #318, história 3). | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/reaberturas` | Devolve à área um caso encerrado que o manifestante voltou a cobrar. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/respostas` | O histórico de respostas do caso, um ciclo por resposta da área. | ✅ |
| GET | `/ouvidoria/manifestacoes/{manifestacao_id}/tentativas-contato` | O que já se tentou NESTE ciclo do caso, em ordem cronológica. | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/tentativas-contato` | Grava que a Ouvidoria tentou falar com o manifestante. | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/transicoes` | Porta de entrada única da máquina de estados: valida a regra e grava o | ✅ |
| POST | `/ouvidoria/manifestacoes/{manifestacao_id}/validar` | Valida a manifestação e aciona a área na mesma ação. | ✅ |
| GET | `/ouvidoria/metricas` | Os números da Ouvidoria no período (PRD #319, fatia I1). | ✅ |
| GET | `/ouvidoria/nota-externa` | A última nota de cada fonte, com a escala junto do número. | ✅ |
| POST | `/ouvidoria/nota-externa` | Registra a nota atual do Google ou do Reclame Aqui (PRD #319, história 10). | ✅ |
| GET | `/ouvidoria/pontos` | Os cartazes, com o QR já embutido. | ✅ |
| POST | `/ouvidoria/pontos` | Cria o cartaz e devolve o código sorteado. | ✅ |
| PATCH | `/ouvidoria/pontos/{ponto_id}` | Renomeia o cartaz, aposenta ou traz de volta. | ✅ |
| GET | `/ouvidoria/pontos/{ponto_id}/cartaz.pdf` | O cartaz A5 pronto para a gráfica. | ✅ |
| GET | `/ouvidoria/pontos/{ponto_id}/qr.png` | O PNG do QR, para quem quer montar o próprio material. | ✅ |
| GET | `/ouvidoria/prazos` | A tabela de prazos por gravidade que alimenta o motor. Leitura para | ✅ |
| GET | `/ouvidoria/prazos/historico` | Quem mudou qual prazo, quando, de quanto para quanto. | ✅ |
| PUT | `/ouvidoria/prazos/{gravidade}/{marco}` | Edita um prazo (RN-21). A mudança vale para validação nova: nenhum caso | ✅ |
| GET | `/ouvidoria/protocolos` | Todos os protocolos, mais recentes primeiro, com prazo e status. | ✅ |
| GET | `/ouvidoria/relatorios` | Os relatórios já gerados (PRD #319, fatia I3). | ✅ |
| POST | `/ouvidoria/relatorios/{relatorio_id}/reenvio` | Manda de novo um relatório já gerado, para recuperar email perdido. | ✅ |
| GET | `/ouvidoria/responsaveis` | Quem responde por cada setor. O ouvidor precisa enxergar o cadastro para | ✅ |
| POST | `/ouvidoria/responsaveis` | Cadastra titular, substituto ou gestor de um setor. | ✅ |
| DELETE | `/ouvidoria/responsaveis/{responsavel_id}` | Tira a pessoa do cadastro. Para guardar a história de quem respondeu | ✅ |
| PUT | `/ouvidoria/responsaveis/{responsavel_id}` | Edita o cadastro. Encerrar a vigência aqui é o que faz a próxima demanda | ✅ |

## ouvidoria-publica (`app/routers/ouvidoria_publica.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/ouvidoria/publico/manifestacoes` | Registra a manifestação do canal aberto e devolve o protocolo ANO-NNNN. | ❌ |
| GET | `/ouvidoria/publico/pontos/{codigo}` | De qual cartaz veio quem está com o formulário aberto. | ❌ |
| GET | `/ouvidoria/qr` | Destino do QR do cartaz: manda ao formulário, com o código do Ponto de | ❌ |

## ouvidoria-setor (`app/routers/ouvidoria_setor.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/ouvidoria-setor/{token}` | O que o titular vê ao abrir o link do email: extrato, prazo e se o caso | ❌ |
| POST | `/ouvidoria-setor/{token}/prorrogacao` | O pedido de mais prazo, feito pelo próprio link do email (issue #333). | ❌ |
| POST | `/ouvidoria-setor/{token}/responder` | A resposta da área: o que foi FEITO para corrigir. Grava o marco T2, | ❌ |

## participantes (`app/routers/participantes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/participantes` | List participantes | ✅ |
| POST | `/participantes` | Cadastra a pessoa e provisiona a conta de login dela. | ✅ |
| GET | `/participantes/cargos` | Retorna a lista canônica de cargos do organograma hospitalar. | ✅ |
| GET | `/participantes/facilitadores` | Lista participantes que já foram facilitadores de alguma reunião viva. | ✅ |
| GET | `/participantes/me` | Retorna o participante do usuario autenticado. | ✅ |
| GET | `/participantes/setores` | Retorna a lista canonica de setores ativos. | ✅ |
| DELETE | `/participantes/{participante_id}` | Desliga a pessoa do hospital: soft delete na tabela e conta de login | ✅ |
| GET | `/participantes/{participante_id}` | Cadastro de um participante. Gate de contexto Reuniões (issue #440): | ✅ |
| PATCH | `/participantes/{participante_id}` | Edita o cadastro. Só o dono da linha ou o Super Admin chegam aqui | ✅ |

## pendencias (`app/routers/pendencias.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pendencias` | Lista pendências com visibilidade binária: super users veem tudo, demais veem por reunião. | ✅ |
| GET | `/pendencias/minhas` | Lista apenas as pendências atreladas diretamente ao usuário autenticado. | ✅ |
| GET | `/pendencias/stats` | Retorna contadores de pendências agrupados por status para o dashboard. | ✅ |
| GET | `/pendencias/{id_acao}` | Retorna uma pendência específica. | ✅ |
| PATCH | `/pendencias/{id_acao}` | Atualiza campos de uma pendência. Quando concluída, incrementa acoes_concluidas na reunião. | ✅ |
| DELETE | `/pendencias/{id_acao}/force` | Super admin only: deleta uma pendencia em qualquer status. Motivo obrigatorio. | ✅ |
| PATCH | `/pendencias/{id_acao}/force` | Super admin only: edita qualquer campo da pendencia em qualquer status. | ✅ |

## perfil (`app/routers/perfil.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/perfil/stats` | Get stats | ✅ |

## pops (`app/routers/pops/pops.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pops` | Lista os POPs do escopo do perfil, com a versão corrente de cada um. | ✅ |
| POST | `/pops` | Cria um POP no Setor informado: gera o Código travado e a Versão 1.0. | ✅ |
| GET | `/pops/designaveis` | Usuários elegíveis a Elaborador/Revisor/Validador no formulário de criação. | ✅ |
| DELETE | `/pops/{pop_id}` | Exclui um POP que ainda não chegou à assinatura (issue #185): limpeza | ✅ |
| PATCH | `/pops/{pop_id}` | Edita os papéis do fluxo (Elaborador, Revisor, Validador) de um POP, | ✅ |

## reunioes (`app/routers/reunioes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/reunioes` | List reunioes | ✅ |
| POST | `/reunioes/agendar` | Cria uma reunião programada no calendário (sem transcrição). | ✅ |
| GET | `/reunioes/calendario` | Lista reuniões para exibição no calendário, com participantes vinculados. | ✅ |
| DELETE | `/reunioes/grupo/{id_grupo_recorrencia}` | Deleta permanentemente todas as reuniões PROGRAMADAS ou em ERRO de um mesmo grupo de recorrência. | ✅ |
| POST | `/reunioes/upload-transcricao` | Upload transcricao | ✅ |
| DELETE | `/reunioes/{id_reuniao}` | Deleta permanentemente uma reunião PROGRAMADA ou em ERRO. | ✅ |
| GET | `/reunioes/{id_reuniao}` | Get reuniao | ✅ |
| PATCH | `/reunioes/{id_reuniao}` | Edita campos de uma reunião PROGRAMADA. | ✅ |
| POST | `/reunioes/{id_reuniao}/anexar-transcricao` | Anexa uma transcrição a uma reunião PROGRAMADA existente e dispara o pipeline de IA. | ✅ |
| POST | `/reunioes/{id_reuniao}/aprovar` | Aprovar reuniao | ✅ |
| POST | `/reunioes/{id_reuniao}/aprovar-sem-assinatura` | Finaliza a Ata sem assinatura digital: cria as Pendências na hora e leva a | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-guiada/chat` | Chat da Ata Guiada — stateless, síncrono, sem pipeline. Recebe o rascunho | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-guiada/concluir` | Persiste a Ata Guiada: grava o `json_ata` enxuto (resumo + quadro), marca | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-guiada/extrair-documento` | Extrai o texto de um Documento de apoio (ADR 0006) para a Ata Guiada, | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-participantes` | Adiciona um participante do cadastro à lista da Ata na validação (ADR 0023). | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-participantes/excluir` | Exclui um participante da lista da Ata na validação (ADR 0023). | ✅ |
| POST | `/reunioes/{id_reuniao}/chat-correcao` | Chat conversacional para correção de ATA. Leve, síncrono, sem pipeline. | ✅ |
| POST | `/reunioes/{id_reuniao}/corrigir` | Corrigir reuniao | ✅ |
| DELETE | `/reunioes/{id_reuniao}/force` | Super admin only: deleta uma reuniao em QUALQUER status. Motivo obrigatorio. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/force` | Super admin only: edita qualquer campo de uma reuniao em qualquer status. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/force-status` | Super admin only: forca qualquer transicao de status (mesmo invalidas). Motivo obrigatorio. | ✅ |
| POST | `/reunioes/{id_reuniao}/participantes` | Adiciona participantes a uma reunião PROGRAMADA. | ✅ |
| DELETE | `/reunioes/{id_reuniao}/participantes/{participante_id}` | Remove um participante de uma reunião PROGRAMADA. | ✅ |
| POST | `/reunioes/{id_reuniao}/pular-resolucao` | Ignora participantes não reconhecidos e retoma o pipeline sem cadastrá-los. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/quadro-atribuicoes/{index}` | Edita um item do `json_ata.quadro_atribuicoes` antes da liberação de pendências. | ✅ |
| POST | `/reunioes/{id_reuniao}/reprocessar` | Reprocessar reuniao | ✅ |
| POST | `/reunioes/{id_reuniao}/resolver-participantes` | Resolve participantes não reconhecidos pela IA e retoma o pipeline. | ✅ |
| POST | `/reunioes/{id_reuniao}/signatarios/sincronizar` | Botão "Sincronizar" do card de Signatários (issue #279, ADR 0030). | ✅ |
| GET | `/reunioes/{id_reuniao}/signatarios/status` | Retorna lista live de signatarios do ClickSign pra essa reuniao. | ✅ |
| POST | `/reunioes/{id_reuniao}/signatarios/{participante_id}/aceite-manual` | Botão "Registrar aceite manualmente" do card de Signatários (issue #278). | ✅ |
| POST | `/reunioes/{id_reuniao}/signatarios/{signer_id}/lembrar` | Reenvia o email de assinatura para um signatário pendente. | ✅ |
| POST | `/reunioes/{id_reuniao}/transferir-facilitador` | Super admin troca o facilitador de uma reuniao por outro super admin. | ✅ |

## pops (`app/routers/pops/revisao.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/pops/{pop_id}/revisao/aprovar` | Aprovação do Revisor: EM_REVISAO → EM_VALIDACAO (auditado) + email ao | ✅ |
| POST | `/pops/{pop_id}/revisao/devolver` | Devolução do Revisor: EM_REVISAO → EM_ELABORACAO, comentários | ✅ |
| POST | `/pops/{pop_id}/validacao/aprovar` | Aprovação final do Validador: EM_VALIDACAO → EM_ASSINATURA (auditado) | ✅ |
| POST | `/pops/{pop_id}/validacao/devolver` | Devolução do Validador: EM_VALIDACAO → EM_ELABORACAO com etapa de | ✅ |
| GET | `/pops/{pop_id}/versao` | A Versão completa para leitura formal — mesma renderização das 11 | ✅ |

## pops (`app/routers/pops/setores.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pops/setores` | Lista os Setores. Leitura aberta a todos os perfis do contexto POPs. | ✅ |
| POST | `/pops/setores` | Cria um Setor. Sigla é normalizada para maiúsculas (base do Código). | ✅ |
| GET | `/pops/setores/meus` | Setores do escopo do usuário — popula o select do formulário de criação. | ✅ |
| PATCH | `/pops/setores/{setor_id}` | Edita nome e/ou sigla de um Setor, mantendo a unicidade dos dois. | ✅ |

## admin (`app/routers/admin/super_admins.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/super-admins` | Lista todos os participantes com access_profile super_admin (fonte da verdade). | ✅ |
| POST | `/admin/super-admins/{participante_id}/demote` | Rebaixa um participante de super admin. Motivo obrigatorio. Loga em audit_log. | ✅ |
| POST | `/admin/super-admins/{participante_id}/promote` | Promove um participante a super admin. Motivo obrigatorio. Loga em audit_log. | ✅ |

## admin (`app/routers/admin/taxonomia.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/cargos` | List cargos | ✅ |
| POST | `/admin/cargos` | Create cargos | ✅ |
| DELETE | `/admin/cargos/{item_id}` | Archive cargos | ✅ |
| PATCH | `/admin/cargos/{item_id}` | Update cargos | ✅ |
| GET | `/admin/setores` | List setores | ✅ |
| POST | `/admin/setores` | Create setores | ✅ |
| DELETE | `/admin/setores/{item_id}` | Archive setores | ✅ |
| PATCH | `/admin/setores/{item_id}` | Update setores | ✅ |
| GET | `/admin/tipos-reuniao` | List tipos reuniao | ✅ |
| POST | `/admin/tipos-reuniao` | Create tipos reuniao | ✅ |
| DELETE | `/admin/tipos-reuniao/{item_id}` | Archive tipos reuniao | ✅ |
| PATCH | `/admin/tipos-reuniao/{item_id}` | Update tipos reuniao | ✅ |

## transcricao (`app/routers/transcricao.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/transcricao/voz` | Comando por voz (issue #35): recebe o áudio ditado e devolve o texto | ✅ |

## admin (`app/routers/admin/usuarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/usuarios` | Lista participantes (incluindo inativos) com filtros e paginacao. | ✅ |
| POST | `/admin/usuarios` | Cria um novo participante. Loga CREATE_USUARIO em audit_log. | ✅ |
| POST | `/admin/usuarios/{externo_id}/merge` | Mescla participante externo com interno existente via RPC atomica. | ✅ |
| PATCH | `/admin/usuarios/{externo_id}/promote` | Promove participante externo a interno. | ✅ |
| DELETE | `/admin/usuarios/{participante_id}` | Hard delete. Motivo obrigatorio. Bloqueia auto-delete. | ✅ |
| GET | `/admin/usuarios/{participante_id}` | Detalhe + ultimos 20 audit logs em que o participante e actor ou target. | ✅ |
| PATCH | `/admin/usuarios/{participante_id}` | Atualizacao parcial. Loga EDIT_USUARIO com antes/depois por campo. | ✅ |
| POST | `/admin/usuarios/{participante_id}/grant-super-admin` | Concede flag is_super_admin=true. Motivo obrigatorio. | ✅ |
| PATCH | `/admin/usuarios/{participante_id}/perfil-ouvidoria` | Concede, troca ou revoga (null) o perfil da Ouvidoria de uma pessoa. | ✅ |
| POST | `/admin/usuarios/{participante_id}/reset-password` | Reseta senha no Supabase Auth. Motivo obrigatorio. | ✅ |
| POST | `/admin/usuarios/{participante_id}/revoke-super-admin` | Revoga flag is_super_admin=false. Motivo obrigatorio. | ✅ |
| GET | `/pops/admin/usuarios` | Lista pessoas para o admin POPs (conceder/revogar perfil, vínculos). | ✅ |
| PATCH | `/pops/admin/usuarios/{participante_id}/perfil-pop` | Concede, troca ou revoga (null) o perfil POP de uma pessoa. | ✅ |
| GET | `/pops/admin/usuarios/{participante_id}/setores` | Lista os Setores vinculados à pessoa. | ✅ |
| PUT | `/pops/admin/usuarios/{participante_id}/setores` | Substitui os vínculos pessoa↔Setor pelo conjunto informado. | ✅ |

## admin (`app/routers/admin/utilitarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/admin/utilitarios/converter-markdown` | Converte um PDF ou DOCX em Markdown localmente, sem consumo de IA. | ✅ |

## webhooks (`app/routers/webhooks.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/webhooks/clicksign` | Recebe notificações da ClickSign sobre assinaturas e fechamento de documentos. | ❌ |

---

**Totais:** 191 endpoints em 30 routers · 94% exigem auth.
