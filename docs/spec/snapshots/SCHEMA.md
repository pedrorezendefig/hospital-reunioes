# SCHEMA.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-10-13T17:14+0000 -->

Diagrama relacional do Hospital Reuniões. Renderiza nativo no GitHub.

## Diagrama ER (Mermaid)

```mermaid
erDiagram
    cm_arquivo ||--o{ cm_conta : "arquivo_id"
    cm_atendimento ||--o{ cm_arquivo : "atendimento_id"
    cm_atendimento ||--o{ cm_chamada_ia : "atendimento_id"
    cm_atendimento ||--o{ cm_cirurgia : "atendimento_id"
    cm_atendimento ||--o{ cm_conta : "atendimento_id"
    cm_atendimento ||--o{ cm_eventos : "atendimento_id"
    cm_atendimento ||--o{ cm_glicemia_dia : "atendimento_id"
    cm_atendimento ||--o{ cm_prescricao : "atendimento_id"
    cm_cenario ||--o{ cm_cenario_item : "cenario_id"
    cm_cenario ||--o{ cm_lembrete : "cenario_id"
    cm_conta ||--o{ cm_chamada_ia : "conta_id"
    cm_conta ||--o{ cm_conta_item : "conta_id"
    cm_conta ||--o{ cm_guia_linha : "conta_id"
    cm_conta ||--o{ cm_lembrete : "conta_id"
    cm_conta ||--o{ cm_observacao : "conta_id"
    cm_contrato ||--o{ cm_aviso : "contrato_id"
    cm_envio ||--o{ cm_arquivo : "envio_id"
    cm_guia_linha ||--o{ cm_validacao_tema_linha : "guia_linha_id"
    cm_item_dicionario ||--o{ cm_validacao_tema : "item_dicionario_id"
    cm_lembrete ||--o{ cm_lembrete_item : "lembrete_id"
    cm_memoria_versao ||--o{ cm_conta : "memoria_versao_id"
    cm_memoria_versao ||--o{ cm_regra : "memoria_versao_id"
    cm_memoria_versao ||--o{ cm_regra_historico : "memoria_versao_id"
    cm_observacao ||--o{ cm_validacao_tema_linha : "observacao_id"
    cm_operadora ||--o{ cm_atendimento : "operadora_id"
    cm_operadora ||--o{ cm_cenario : "operadora_id"
    cm_operadora ||--o{ cm_contrato : "operadora_id"
    cm_operadora ||--o{ cm_memoria_versao : "operadora_id"
    cm_operadora ||--o{ cm_operadora_plano : "operadora_id"
    cm_operadora ||--o{ cm_operadora_tabela : "operadora_id"
    cm_operadora ||--o{ cm_regra : "operadora_id"
    cm_operadora ||--o{ cm_validacao_tema : "operadora_id"
    cm_prescricao ||--o{ cm_prescricao_item : "prescricao_id"
    cm_regra ||--o{ cm_regra_historico : "regra_id"
    cm_tabela_preco ||--o{ cm_guia_linha : "tabela_id"
    cm_tabela_preco ||--o{ cm_operadora_tabela : "tabela_id"
    cm_tabela_preco ||--o{ cm_tabela_preco_item : "tabela_id"
    cm_validacao_tema ||--o{ cm_validacao_tema_linha : "tema_id"
    participantes ||--o{ audit_log : "actor_id"
    participantes ||--o{ bulk_jobs : "actor_id"
    participantes ||--o{ cm_cenario : "autor_id"
    participantes ||--o{ cm_conta : "faturista_id"
    participantes ||--o{ cm_contrato : "confirmado_por"
    participantes ||--o{ cm_envio : "usuario_id"
    participantes ||--o{ cm_guia_linha : "marcado_por"
    participantes ||--o{ cm_item_dicionario : "autor_id"
    participantes ||--o{ cm_lembrete : "marcado_por"
    participantes ||--o{ cm_memoria_versao : "autor_id"
    participantes ||--o{ cm_observacao : "autor_id"
    participantes ||--o{ cm_registro : "autor_id"
    participantes ||--o{ cm_regra : "validado_por"
    participantes ||--o{ cm_regra_historico : "autor_id"
    participantes ||--o{ cm_tabela_preco : "autor_id"
    participantes ||--o{ cm_validacao_tema : "decidido_por"
    participantes ||--o{ comentarios_pendencias : "autor_id"
    participantes ||--o{ notificacoes : "destinatario_id"
    participantes ||--o{ ouvidoria_acessos : "ator_id"
    participantes ||--o{ ouvidoria_anexos : "enviado_por"
    participantes ||--o{ ouvidoria_movimentos : "autor_id"
    participantes ||--o{ ouvidoria_nota_externa : "e"
    participantes ||--o{ ouvidoria_pontos : "criado_por"
    participantes ||--o{ ouvidoria_prorrogacoes : "decidida_por"
    participantes ||--o{ ouvidoria_tentativas_contato : "autor_id"
    participantes ||--o{ pendencias : "co_responsavel_id"
    participantes ||--o{ pendencias : "responsavel_id"
    participantes ||--o{ pops : "criado_por"
    participantes ||--o{ pops : "elaborador_id"
    participantes ||--o{ pops : "revisor_id"
    participantes ||--o{ pops : "validador_id"
    participantes ||--o{ pops_devolucoes : "autor_id"
    participantes ||--o{ pops_materiais_referencia : "criado_por"
    participantes ||--o{ pops_setores_participantes : "participante_id"
    participantes ||--o{ reuniao_aceite_tokens : "participante_id"
    participantes ||--o{ reuniao_aceites : "participante_id"
    participantes ||--o{ reuniao_participantes : "participante_id"
    participantes ||--o{ reunioes : "criada_por"
    participantes ||--o{ reunioes : "facilitador_id"
    participantes ||--o{ reunioes : "nome_arquivo_original"
    participantes ||--o{ tecnologia_anexos : "anexado_por"
    participantes ||--o{ tecnologia_conversas : "autor_id"
    participantes ||--o{ tecnologia_demandas : "autor_id"
    participantes ||--o{ tecnologia_demandas : "cancelada_por"
    participantes ||--o{ tecnologia_demandas : "concluida_por"
    participantes ||--o{ tecnologia_demandas : "responsavel_id"
    participantes ||--o{ tecnologia_demandas : "vinculado_por"
    participantes ||--o{ tecnologia_produtos : "dono_id"
    participantes ||--o{ user_preferences : "participante_id"
    pendencias ||--o{ agendamentos_email : "id_acao"
    pendencias ||--o{ comentarios_pendencias : "id_acao"
    pops ||--o{ pops_versoes : "pop_id"
    pops_setores ||--o{ pops : "setor_id"
    pops_setores ||--o{ pops_setores_participantes : "setor_id"
    pops_versoes ||--o{ pops_devolucoes : "versao_id"
    pops_versoes ||--o{ pops_materiais_referencia : "versao_id"
    reunioes ||--o{ pendencias : "id_reuniao"
    reunioes ||--o{ reuniao_participantes : "id_reuniao"
    reunioes ||--o{ tokens_validacao : "id_reuniao"
    tecnologia_conversas ||--o{ tecnologia_anexos : "conversa_id"
    tecnologia_demandas ||--o{ tecnologia_anexos : "demanda_id"
    tecnologia_demandas ||--o{ tecnologia_conversas : "demanda_id"
    tecnologia_produtos ||--o{ tecnologia_demandas : "produto_id"
    tipos_reuniao ||--o{ reunioes : "tipo_id"

    participantes {
        VARCHAR id PK
        TEXT nome_completo
        TEXT cargo
        TEXT email
        TEXT area
        TEXT setor
        user_role role
        BOOLEAN ativo
        _ mais_colunas "+11"
    }
    reunioes {
        VARCHAR id_reuniao PK
        DATE data
        TIME hora_inicio
        TIME hora_fim
        TEXT titulo
        TEXT tipo
        VARCHAR facilitador_id FK
        TEXT setor
        _ mais_colunas "+29"
    }
    reuniao_participantes {
        UUID id PK
        VARCHAR id_reuniao FK
        VARCHAR participante_id FK
        INTEGER sequence_assinatura
    }
    pendencias {
        VARCHAR id_acao PK
        VARCHAR id_reuniao FK
        TEXT descricao_acao
        VARCHAR responsavel_id FK
        TEXT responsavel_nome
        TEXT cargo
        DATE prazo
        TEXT meta_entregavel
        _ mais_colunas "+7"
    }
    agendamentos_email {
        UUID id PK
        VARCHAR id_acao FK
        TEXT tipo
        DATE data_disparo
        BOOLEAN enviado
        TIMESTAMPTZ enviado_em
        TIMESTAMPTZ created_at
    }
    tokens_validacao {
        UUID token PK
        VARCHAR id_reuniao FK
        TEXT tipo
        BOOLEAN usado
        INTEGER ciclo_correcao
        TIMESTAMPTZ expires_at
        TIMESTAMPTZ created_at
    }
    comentarios_pendencias {
        UUID id PK
        VARCHAR id_acao FK
        VARCHAR autor_id FK
        TEXT autor_nome
        TEXT conteudo
        VARCHAR mencoes
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    notificacoes {
        UUID id PK
        VARCHAR destinatario_id FK
        TEXT tipo
        TEXT titulo
        TEXT mensagem
        VARCHAR referencia_id
        BOOLEAN lida
        TIMESTAMPTZ created_at
    }
    user_preferences {
        VARCHAR participante_id PK
        JSONB notificacoes
        JSONB emails
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    audit_log {
        UUID id PK
        TIMESTAMPTZ timestamp
        VARCHAR actor_id FK
        TEXT actor_email
        TEXT action
        TEXT target_type
        TEXT target_id
        JSONB metadata
        _ mais_colunas "+2"
    }
    bulk_jobs {
        UUID id PK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        VARCHAR actor_id FK
        TEXT actor_email
        TEXT job_type
        status reenviar_email
        target_ids failed
        _ mais_colunas "+4"
    }
    cargos {
        UUID id PK
        TEXT nome
        BOOLEAN ativo
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    tipos_reuniao {
        UUID id PK
        TEXT nome
        BOOLEAN ativo
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    pops_setores {
        UUID id PK
        TEXT nome
        TEXT sigla
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    pops_setores_participantes {
        UUID setor_id FK
        VARCHAR participante_id FK
        TIMESTAMPTZ created_at
    }
    pops {
        UUID id PK
        UUID setor_id FK
        INT numero
        TEXT codigo
        TEXT nome
        TEXT criticidade
        TEXT base_normativa
        TEXT periodicidade_revisao
        _ mais_colunas "+8"
    }
    pops_versoes {
        UUID id PK
        UUID pop_id FK
        TEXT numero_versao
        TEXT estado
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        JSONB rascunho
        TEXT envelope_id_clicksign
    }
    pops_devolucoes {
        UUID id PK
        UUID versao_id FK
        VARCHAR autor_id FK
        TEXT etapa_retorno
        TEXT comentarios
        TIMESTAMPTZ created_at
    }
    pops_materiais_referencia {
        UUID id PK
        UUID versao_id FK
        TEXT filename
        TEXT extensao
        INTEGER tamanho_bytes
        TEXT storage_path
        TEXT texto
        VARCHAR criado_por FK
        _ mais_colunas "+1"
    }
    reuniao_aceites {
        UUID id PK
        VARCHAR participante_id FK
        TEXT signer_key
        TEXT email
        TEXT origem
        TIMESTAMPTZ aceito_em
        TIMESTAMPTZ created_at
    }
    reuniao_aceite_tokens {
        UUID id PK
        VARCHAR participante_id FK
        TEXT token_hash
        TIMESTAMPTZ criado_em
        TIMESTAMPTZ usado_em
    }
    consultas_particulares {
        UUID id PK
        TEXT especialidade
        NUMERIC valor_rs
        TEXT descricao_servico
        TEXT diferencial_1
        TEXT diferencial_2
        TEXT diferencial_3
        BOOLEAN alta_demanda
        _ mais_colunas "+3"
    }
    exames {
        UUID id PK
        TEXT nome_exame
        TEXT tipo_exame
        BOOLEAN convenio_aceito
        NUMERIC valor_particular_rs
        BOOLEAN requer_pedido_medico
        BOOLEAN preparo_necessario
        TEXT instrucoes_preparo_completas
        _ mais_colunas "+7"
    }
    cirurgias_estimativas {
        UUID id PK
        TEXT procedimento
        TEXT descricao_procedimento
        NUMERIC honorarios_equipe_rs
        NUMERIC valor_internacao_rs
        NUMERIC estimativa_total_rs
        TEXT o_que_inclui_honorarios
        TEXT o_que_inclui_internacao
        _ mais_colunas "+6"
    }
    ouvidoria_movimentos {
        UUID id PK
        UUID manifestacao_id FK
        TIMESTAMPTZ ocorrido_em
        TEXT estado_anterior
        TEXT estado_novo
        VARCHAR autor_id FK
        TEXT autor_nome
        TEXT observacao
    }
    ouvidoria_acessos {
        UUID id PK
        UUID manifestacao_id FK
        TIMESTAMPTZ ocorrido_em
        VARCHAR ator_id FK
        TEXT ator_nome
        TEXT acao
        UUID email_recebido_id FK
    }
    ouvidoria_prazos {
        TEXT gravidade
        TEXT marco
        INTEGER valor
        TEXT unidade
        TIMESTAMPTZ atualizado_em
    }
    ouvidoria_prazos_historico {
        UUID id PK
        TEXT gravidade
        TEXT marco
        INTEGER valor_anterior
        TEXT unidade_anterior
        INTEGER valor_novo
        TEXT unidade_nova
        acao qualquer
        _ mais_colunas "+4"
    }
    ouvidoria_feriados {
        DATE data PK
        TEXT nome
        TEXT abrangencia
    }
    ouvidoria_anexos {
        UUID id PK
        UUID manifestacao_id FK
        TEXT filename
        TEXT content_type
        mesmo o
        TEXT storage_path
        VARCHAR enviado_por FK
        TEXT enviado_por_nome
        _ mais_colunas "+1"
    }
    ouvidoria_setor_responsaveis {
        UUID id PK
        TEXT setor
        TEXT papel
        TEXT nome
        TEXT email
        data com
        titular o
        DATE vigencia_fim
        _ mais_colunas "+2"
    }
    ouvidoria_notificacoes {
        UUID id PK
        UUID manifestacao_id FK
        TEXT gatilho
        TEXT destinatario_nome
        TEXT destinatario_email
        TEXT papel_destinatario
        o para
        INTEGER tentativas
        _ mais_colunas "+5"
    }
    ouvidoria_setor_tokens {
        UUID id PK
        UUID manifestacao_id FK
        TEXT destinatario_nome
        TEXT destinatario_email
        TEXT token_hash
        TIMESTAMPTZ criado_em
        TIMESTAMPTZ expira_em
        TIMESTAMPTZ usado_em
        _ mais_colunas "+1"
    }
    ouvidoria_prorrogacoes {
        UUID id PK
        UUID manifestacao_id FK
        TEXT justificativa
        INTEGER dias_uteis_pedidos
        sem e
        TIMESTAMPTZ prazo_novo
        TEXT status
        TIMESTAMPTZ solicitada_em
        _ mais_colunas "+6"
    }
    ouvidoria_tentativas_contato {
        UUID id PK
        UUID manifestacao_id FK
        TIMESTAMPTZ tentada_em
        TEXT canal
        TEXT observacao
        VARCHAR autor_id FK
        TEXT autor_nome
    }
    ouvidoria_relatorios {
        UUID id PK
        o e
        DATE periodo_inicio
        DATE periodo_fim
        relogio no
        TIMESTAMPTZ gerado_em
        nunca sem
        recebeu quem
        _ mais_colunas "+13"
    }
    ouvidoria_nota_externa {
        UUID id PK
        TEXT fonte
        NUMERIC nota
        banco no
        script um
        relogio no
        e e
        o e FK
        _ mais_colunas "+2"
    }
    ouvidoria_pontos {
        UUID id PK
        TEXT setor
        TEXT ponto
        BOOLEAN ativo
        TIMESTAMPTZ criado_em
        VARCHAR criado_por FK
        nao e
        o e
    }
    tecnologia_produtos {
        UUID id PK
        TEXT nome
        BOOLEAN ativo
        VARCHAR dono_id FK
        INTEGER ordem
        TIMESTAMPTZ criado_em
        TIMESTAMPTZ atualizado_em
    }
    tecnologia_demandas {
        UUID id PK
        TEXT titulo
        TEXT descricao
        TEXT tipo
        UUID produto_id FK
        TEXT estado
        VARCHAR responsavel_id FK
        VARCHAR autor_id FK
        _ mais_colunas "+19"
    }
    tecnologia_conversas {
        UUID id PK
        UUID demanda_id FK
        VARCHAR autor_id FK
        TEXT linha
        TEXT texto
        VARCHAR mencoes
        TEXT movimento_campo
        TEXT movimento_de
        _ mais_colunas "+5"
    }
    ouvidoria_emails_recebidos_anexos {
        UUID id PK
        UUID email_recebido_id FK
        TEXT resend_anexo_id
        TEXT filename
        TEXT content_type
        BIGINT tamanho_bytes
        TEXT storage_path
        TIMESTAMPTZ created_at
        _ mais_colunas "+1"
    }
    migracoes_aplicadas {
        INTEGER numero PK
        TIMESTAMPTZ aplicada_em
    }
    tecnologia_anexos {
        UUID id PK
        UUID demanda_id FK
        INTEGER ordem
        TEXT storage_path
        TEXT nome_original
        TEXT content_type
        BIGINT tamanho_bytes
        VARCHAR anexado_por FK
        _ mais_colunas "+3"
    }
    cm_perfil_permissao {
        TEXT perfil
        TEXT permissao
        BOOLEAN ligada
    }
    cm_operadora {
        UUID id PK
        TEXT sigla
        TEXT nome
        TEXT situacao
        TIMESTAMPTZ criado_em
    }
    cm_operadora_plano {
        UUID id PK
        UUID operadora_id FK
        TEXT nome_mv
        TEXT coluna_preco
        TIMESTAMPTZ criado_em
    }
    cm_memoria_versao {
        UUID id PK
        UUID operadora_id FK
        TEXT versao
        JSONB parametros_json
        TEXT texto_md
        BOOLEAN vigente
        VARCHAR autor_id FK
        TIMESTAMPTZ criado_em
        _ mais_colunas "+1"
    }
    cm_regra {
        UUID id PK
        UUID operadora_id FK
        UUID memoria_versao_id FK
        TEXT codigo
        TEXT secao
        TEXT texto
        TEXT tipo
        TEXT origem
        _ mais_colunas "+7"
    }
    cm_tabela_preco {
        UUID id PK
        TEXT nome
        TEXT tipo
        TEXT versao
        DATE vigencia_inicio
        DATE vigencia_fim
        TEXT situacao
        TEXT arquivo_nome
        _ mais_colunas "+4"
    }
    cm_tabela_preco_item {
        UUID id PK
        UUID tabela_id FK
        TEXT codigo
        TEXT codigo_alternativo
        TEXT descricao
        TEXT grupo
        TEXT unidade
        JSONB precos_json
        _ mais_colunas "+1"
    }
    cm_operadora_tabela {
        UUID id PK
        UUID operadora_id FK
        TEXT categoria
        UUID tabela_id FK
        JSONB regra_uso_json
        TIMESTAMPTZ criado_em
    }
    cm_setor {
        UUID id PK
        TEXT nome_mv
        TEXT acomodacao
        TEXT grupo_gases
        TIMESTAMPTZ criado_em
    }
    cm_item_dicionario {
        UUID id PK
        TEXT termo
        TEXT codigo_conta
        TEXT descricao_conta
        TEXT unidade_cobranca
        TEXT conteudo_por_unidade
        TEXT origem
        TEXT situacao
        _ mais_colunas "+2"
    }
    cm_envio {
        UUID id PK
        VARCHAR usuario_id FK
        TIMESTAMPTZ criado_em
    }
    cm_atendimento {
        UUID id PK
        TEXT numero_atendimento
        TEXT paciente_rotulo
        INTEGER idade_anos
        UUID operadora_id FK
        TEXT plano
        TEXT coluna_preco
        TEXT acomodacao_contratada
        _ mais_colunas "+1"
    }
    cm_arquivo {
        UUID id PK
        UUID envio_id FK
        TEXT tipo
        UUID atendimento_id FK
        TEXT numero_atendimento
        INTEGER paginas
        TEXT chave_bucket
        TEXT hash
        _ mais_colunas "+3"
    }
    cm_eventos {
        UUID id PK
        UUID atendimento_id FK
        JSONB eventos_json
        DATE prontuario_ate
        TIMESTAMPTZ criado_em
    }
    cm_prescricao {
        UUID id PK
        UUID atendimento_id FK
        DATE data
        TIME hora
        TEXT subtipo
        INTEGER pagina
    }
    cm_prescricao_item {
        UUID id PK
        UUID prescricao_id FK
        TEXT secao
        INTEGER n
        TEXT nome
        TEXT generico
        JSONB colunas
        NUMERIC doses_por_dia
        _ mais_colunas "+5"
    }
    cm_cirurgia {
        UUID id PK
        UUID atendimento_id FK
        JSONB procedimentos_json
        TIMESTAMPTZ inicio
        TIMESTAMPTZ fim
        TIMESTAMPTZ anestesia_inicio
        TIMESTAMPTZ anestesia_fim
        TEXT tecnica
        _ mais_colunas "+2"
    }
    cm_glicemia_dia {
        UUID id PK
        UUID atendimento_id FK
        DATE data
        INTEGER quantidade
    }
    cm_conta {
        UUID id PK
        UUID atendimento_id FK
        UUID arquivo_id FK
        TEXT numero_conta
        INTEGER parcial_ordem
        DATE periodo_inicio
        DATE periodo_fim
        NUMERIC total_lancado
        _ mais_colunas "+25"
    }
    cm_conta_item {
        UUID id PK
        UUID conta_id FK
        INTEGER ordem
        DATE data
        TEXT grupo_conta
        TEXT setor
        TEXT grupo_procedimento
        TEXT codigo
        _ mais_colunas "+8"
    }
    cm_guia_linha {
        UUID id PK
        UUID conta_id FK
        INTEGER ordem
        TEXT acao
        DATE data
        DATE data_fim
        TEXT setor
        TEXT codigo
        _ mais_colunas "+21"
    }
    cm_observacao {
        UUID id PK
        UUID conta_id FK
        VARCHAR autor_id FK
        TEXT texto
        TIMESTAMPTZ criado_em
    }
    cm_chamada_ia {
        UUID id PK
        UUID conta_id FK
        UUID atendimento_id FK
        TEXT passo
        TEXT modelo
        INTEGER tokens_entrada
        INTEGER tokens_saida
        INTEGER tokens_cache
        _ mais_colunas "+5"
    }
    cm_linha_formulario {
        UUID id PK
        TEXT familia
        TEXT linha
        INTEGER contagem
        TIMESTAMPTZ criado_em
        TIMESTAMPTZ atualizado_em
    }
    cm_registro {
        UUID id PK
        VARCHAR autor_id FK
        TIMESTAMPTZ data
        TEXT entidade
        TEXT entidade_id
        JSONB antes_json
        JSONB depois_json
    }
    cm_regra_historico {
        UUID id PK
        UUID regra_id FK
        UUID memoria_versao_id FK
        TEXT texto_anterior
        TEXT texto_novo
        VARCHAR autor_id FK
        TIMESTAMPTZ criado_em
    }
    cm_validacao_tema {
        UUID id PK
        UUID operadora_id FK
        TEXT tipo
        TEXT regra_codigo
        TEXT codigo_item
        UUID item_dicionario_id FK
        TEXT titulo
        TEXT estado
        _ mais_colunas "+6"
    }
    cm_validacao_tema_linha {
        UUID id PK
        UUID tema_id FK
        UUID guia_linha_id FK
        UUID observacao_id FK
        TIMESTAMPTZ criado_em
    }
    cm_cenario {
        UUID id PK
        TEXT codigo
        TEXT nome
        UUID operadora_id FK
        TEXT gatilho_texto
        TEXT orientacao
        BOOLEAN ativo
        VARCHAR autor_id FK
        _ mais_colunas "+1"
    }
    cm_cenario_item {
        UUID id PK
        UUID cenario_id FK
        TEXT codigo
        TEXT descricao
        NUMERIC quantidade
    }
    cm_lembrete {
        UUID id PK
        UUID conta_id FK
        UUID cenario_id FK
        DATE data
        TEXT setor
        INTEGER evidencia_pagina
        TEXT evidencia_trecho
        TEXT estado
        _ mais_colunas "+4"
    }
    cm_lembrete_item {
        UUID id PK
        UUID lembrete_id FK
        TEXT codigo
        TEXT descricao
        NUMERIC quantidade
        NUMERIC preco_tabela
        NUMERIC valor
    }
    cm_contrato {
        UUID id PK
        UUID operadora_id FK
        DATE data_assinatura
        TEXT aditivo_numero
        DATE aditivo_data
        DATE vigencia_inicio
        DATE vencimento
        BOOLEAN vencimento_calculado
        _ mais_colunas "+6"
    }
    cm_aviso {
        UUID id PK
        UUID contrato_id FK
        DATE data_prevista
        TIMESTAMPTZ enviado_em
        TIMESTAMPTZ criado_em
    }
```

## Indexes principais

| Tabela | Index | Colunas | Origem |
|--------|-------|---------|--------|
| `participantes` | `idx_participantes_email` | `email` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_setor` | `setor` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_ativo` | `ativo` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_auth` | `auth_user_id` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_super_admin` | `is_super_admin` | `017_add_super_admin.sql` |
| `participantes` | `idx_participantes_access_profile` | `access_profile` | `036_add_access_profile.sql` |
| `participantes` | `idx_participantes_setor_id` | `setor_id` | `038_fk_indexes.sql` |
| `participantes` | `idx_participantes_cargo_id` | `cargo_id` | `038_fk_indexes.sql` |
| `participantes` | `idx_participantes_perfil_pop` | `perfil_pop` | `045_pops_fundacao_acesso.sql` |
| `participantes` | `idx_participantes_perfil_ouvidoria` | `perfil_ouvidoria` | `064_ouvidoria_manifestacao.sql` |
| `participantes` | `participantes_github_login_lower_idx` | `(lower(github_login` | `103_tecnologia_vinculo.sql` |
| `participantes` | `idx_participantes_perfil_contas_medicas` | `perfil_contas_medicas` | `116_contas_medicas_fundacao.sql` |
| `reunioes` | `idx_reunioes_status` | `status_ata` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_data` | `data DESC` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_setor` | `setor` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_fireflies` | `fireflies_meeting_id` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_programada` | `data, status_ata` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_documento_id_origem` | `documento_id_origem` | `016_importacao_ata_legada.sql` |
| `reunioes` | `idx_reunioes_arquivo_hash` | `arquivo_hash` | `016_importacao_ata_legada.sql` |
| `reunioes` | `idx_reunioes_importado_por` | `importado_por_id` | `020_historico_importacao.sql` |
| `reunioes` | `idx_reunioes_live` | `data DESC` | `030_add_soft_delete.sql` |
| `reunioes` | `idx_reunioes_lembrete_pendente` | `data, hora_inicio` | `035_add_lembrete_24h_reunioes.sql` |
| `reunioes` | `idx_reunioes_criada_por` | `criada_por` | `036_add_access_profile.sql` |
| `reunioes` | `idx_reunioes_facilitador` | `facilitador_id` | `038_fk_indexes.sql` |
| `reunioes` | `idx_reunioes_tipo_id` | `tipo_id` | `038_fk_indexes.sql` |
| `reuniao_participantes` | `idx_reuniao_part_reuniao` | `id_reuniao` | `002_create_reunioes.sql` |
| `reuniao_participantes` | `idx_reuniao_part_participante` | `participante_id` | `002_create_reunioes.sql` |
| `pendencias` | `idx_pendencias_reuniao` | `id_reuniao` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_responsavel` | `responsavel_id` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_status` | `status` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_prazo` | `prazo` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_co_responsavel` | `co_responsavel_id` | `014_add_externo_co_responsavel.sql` |
| `pendencias` | `idx_pendencias_live` | `prazo` | `030_add_soft_delete.sql` |
| `pendencias` | `idx_pendencias_nota` | `id_nota` | `042_add_id_nota_pendencias.sql` |
| `pendencias` | `ux_pendencias_reuniao_quadro_pos` | `id_reuniao, quadro_pos` | `057_registro_aceites_incremental.sql` |
| `agendamentos_email` | `idx_agendamentos_disparo` | `data_disparo, enviado` | `003_create_pendencias.sql` |
| `agendamentos_email` | `idx_agendamentos_email_id_acao` | `id_acao` | `038_fk_indexes.sql` |
| `tokens_validacao` | `idx_tokens_reuniao` | `id_reuniao` | `004_create_tokens_validacao.sql` |
| `tokens_validacao` | `idx_tokens_expires` | `expires_at` | `004_create_tokens_validacao.sql` |
| `comentarios_pendencias` | `idx_comentarios_id_acao` | `id_acao` | `007_create_comentarios_pendencias.sql` |
| `comentarios_pendencias` | `idx_comentarios_autor` | `autor_id` | `007_create_comentarios_pendencias.sql` |
| `comentarios_pendencias` | `idx_comentarios_created` | `created_at DESC` | `007_create_comentarios_pendencias.sql` |
| `notificacoes` | `idx_notificacoes_destinatario` | `destinatario_id, lida` | `008_create_notificacoes.sql` |
| `notificacoes` | `idx_notificacoes_created` | `created_at DESC` | `008_create_notificacoes.sql` |
| `notificacoes` | `idx_notificacoes_referencia` | `referencia_id` | `008_create_notificacoes.sql` |
| `audit_log` | `idx_audit_log_timestamp` | `timestamp DESC` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_actor` | `actor_id` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_target` | `target_type, target_id` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_action` | `action` | `018_create_audit_log.sql` |
| `bulk_jobs` | `idx_bulk_jobs_actor` | `actor_id` | `019_create_bulk_jobs.sql` |
| `bulk_jobs` | `idx_bulk_jobs_status` | `status` | `019_create_bulk_jobs.sql` |
| `bulk_jobs` | `idx_bulk_jobs_created_at` | `created_at DESC` | `019_create_bulk_jobs.sql` |
| `cargos` | `cargos_nome_lower_idx` | `(lower(nome` | `027_create_taxonomy_tables.sql` |
| `tipos_reuniao` | `tipos_reuniao_nome_lower_idx` | `(lower(nome` | `027_create_taxonomy_tables.sql` |
| `pops_setores` | `pops_setores_nome_lower_idx` | `(lower(nome` | `045_pops_fundacao_acesso.sql` |
| `pops_setores` | `pops_setores_sigla_lower_idx` | `(lower(sigla` | `045_pops_fundacao_acesso.sql` |
| `pops_setores_participantes` | `idx_pops_setores_participantes_participante` | `participante_id` | `045_pops_fundacao_acesso.sql` |
| `pops` | `idx_pops_setor` | `setor_id` | `046_pops_criar_pop.sql` |
| `pops` | `idx_pops_elaborador` | `elaborador_id` | `046_pops_criar_pop.sql` |
| `pops_versoes` | `idx_pops_versoes_pop` | `pop_id` | `046_pops_criar_pop.sql` |
| `pops_versoes` | `idx_pops_versoes_estado` | `estado` | `046_pops_criar_pop.sql` |
| `pops_versoes` | `idx_pops_versoes_envelope_key` | `envelope_key_clicksign` | `050_pops_clicksign_publicacao.sql` |
| `pops_devolucoes` | `idx_pops_devolucoes_versao` | `versao_id` | `048_pops_revisao_validacao.sql` |
| `pops_materiais_referencia` | `idx_pops_materiais_versao` | `versao_id` | `049_pops_materiais_referencia.sql` |
| `reuniao_aceites` | `ux_reuniao_aceites_signer_key` | `id_reuniao, signer_key` | `057_registro_aceites_incremental.sql` |
| `reuniao_aceites` | `ux_reuniao_aceites_email` | `id_reuniao, email` | `057_registro_aceites_incremental.sql` |
| `reuniao_aceites` | `ux_reuniao_aceites_participante` | `id_reuniao, participante_id` | `057_registro_aceites_incremental.sql` |
| `reuniao_aceites` | `idx_reuniao_aceites_reuniao` | `id_reuniao` | `057_registro_aceites_incremental.sql` |
| `reuniao_aceites` | `idx_reuniao_aceites_participante` | `participante_id` | `057_registro_aceites_incremental.sql` |
| `reuniao_aceite_tokens` | `ux_reuniao_aceite_tokens_hash` | `token_hash` | `060_aceite_interno_tokens.sql` |
| `reuniao_aceite_tokens` | `ux_reuniao_aceite_tokens_participante` | `id_reuniao, participante_id` | `060_aceite_interno_tokens.sql` |
| `reuniao_aceite_tokens` | `idx_reuniao_aceite_tokens_reuniao` | `id_reuniao` | `060_aceite_interno_tokens.sql` |
| `ouvidoria_movimentos` | `idx_ouvidoria_movimentos_manifestacao` | `manifestacao_id, ocorrido_em` | `064_ouvidoria_manifestacao.sql` |
| `ouvidoria_acessos` | `idx_ouvidoria_acessos_manifestacao` | `manifestacao_id, ocorrido_em DESC` | `064_ouvidoria_manifestacao.sql` |
| `ouvidoria_acessos` | `idx_ouvidoria_acessos_email_recebido` | `email_recebido_id, ocorrido_em DESC` | `112_ouvidoria_triagem_email.sql` |
| `ouvidoria_prazos_historico` | `idx_ouvidoria_prazos_historico_celula` | `gravidade, marco, ocorrido_em DESC` | `065_ouvidoria_prazos_calendario.sql` |
| `ouvidoria_anexos` | `idx_ouvidoria_anexos_manifestacao` | `manifestacao_id, created_at` | `066_ouvidoria_registro_manual_anexos.sql` |
| `ouvidoria_setor_responsaveis` | `idx_ouvidoria_setor_responsaveis_setor` | `setor, papel` | `068_ouvidoria_responsaveis_notificacoes.sql` |
| `ouvidoria_notificacoes` | `idx_ouvidoria_notificacoes_fila` | `enviar_a_partir_de` | `068_ouvidoria_responsaveis_notificacoes.sql` |
| `ouvidoria_notificacoes` | `idx_ouvidoria_notificacoes_manifestacao` | `manifestacao_id, criada_em DESC` | `068_ouvidoria_responsaveis_notificacoes.sql` |
| `ouvidoria_setor_tokens` | `idx_ouvidoria_setor_tokens_hash` | `token_hash` | `069_ouvidoria_portal_setor.sql` |
| `ouvidoria_setor_tokens` | `idx_ouvidoria_setor_tokens_vigente` | `manifestacao_id, destinatario_email` | `069_ouvidoria_portal_setor.sql` |
| `ouvidoria_setor_tokens` | `idx_ouvidoria_setor_tokens_destinatario` | `manifestacao_id, destinatario_email` | `070_ouvidoria_setor_tokens_multiplos.sql` |
| `ouvidoria_prorrogacoes` | `idx_ouvidoria_prorrogacoes_unica` | `manifestacao_id` | `073_ouvidoria_prorrogacao.sql` |
| `ouvidoria_tentativas_contato` | `idx_ouvidoria_tentativas_manifestacao` | `manifestacao_id, tentada_em` | `075_ouvidoria_aguardando_manifestante.sql` |
| `ouvidoria_relatorios` | `idx_ouvidoria_relatorios_competencia` | `competencia` | `080_ouvidoria_relatorios.sql` |
| `ouvidoria_relatorios` | `idx_ouvidoria_relatorios_nao_enviados` | `periodo_fim DESC` | `080_ouvidoria_relatorios.sql` |
| `ouvidoria_relatorios` | `idx_ouvidoria_relatorios_periodo` | `periodo_fim DESC` | `080_ouvidoria_relatorios.sql` |
| `ouvidoria_relatorios` | `idx_ouvidoria_relatorios_fila_recuperacao` | `tentativas ASC, periodo_fim ASC` | `087_ouvidoria_relatorio_fila_recuperacao.sql` |
| `ouvidoria_nota_externa` | `idx_ouvidoria_nota_externa_fonte` | `fonte, registrada_em DESC` | `082_ouvidoria_nota_externa.sql` |
| `ouvidoria_pontos` | `idx_ouvidoria_pontos_codigo` | `codigo` | `085_ouvidoria_pontos_de_escuta.sql` |
| `ouvidoria_pontos` | `idx_ouvidoria_pontos_setor` | `setor, ponto` | `085_ouvidoria_pontos_de_escuta.sql` |
| `tecnologia_produtos` | `tecnologia_produtos_nome_lower_idx` | `(lower(nome` | `102_tecnologia_fundacao.sql` |
| `tecnologia_demandas` | `idx_tecnologia_demandas_estado` | `estado` | `102_tecnologia_fundacao.sql` |
| `tecnologia_demandas` | `idx_tecnologia_demandas_responsavel` | `responsavel_id` | `102_tecnologia_fundacao.sql` |
| `tecnologia_demandas` | `idx_tecnologia_demandas_produto` | `produto_id` | `102_tecnologia_fundacao.sql` |
| `tecnologia_demandas` | `tecnologia_demandas_github_issue_numero_idx` | `github_issue_numero` | `103_tecnologia_vinculo.sql` |
| `tecnologia_conversas` | `idx_tecnologia_conversas_demanda` | `demanda_id, criado_em` | `102_tecnologia_fundacao.sql` |
| `tecnologia_anexos` | `idx_tecnologia_anexos_conversa` | `conversa_id` | `115_tecnologia_anexos_e_em_producao.sql` |
| `cm_operadora_plano` | `idx_cm_operadora_plano_nome_mv` | `(lower(nome_mv` | `116_contas_medicas_fundacao.sql` |
| `cm_memoria_versao` | `idx_cm_memoria_versao_vigente` | `operadora_id` | `116_contas_medicas_fundacao.sql` |
| `cm_regra` | `idx_cm_regra_operadora_codigo` | `operadora_id, codigo` | `116_contas_medicas_fundacao.sql` |
| `cm_regra` | `idx_cm_regra_modelo` | `modelo_id` | `118_contas_medicas_gestao.sql` |
| `cm_tabela_preco_item` | `idx_cm_tabela_preco_item_tabela_codigo` | `tabela_id, codigo` | `116_contas_medicas_fundacao.sql` |
| `cm_operadora_tabela` | `idx_cm_operadora_tabela_operadora` | `operadora_id, categoria` | `116_contas_medicas_fundacao.sql` |
| `cm_setor` | `idx_cm_setor_nome_mv` | `(lower(nome_mv` | `116_contas_medicas_fundacao.sql` |
| `cm_item_dicionario` | `idx_cm_item_dicionario_termo` | `(lower(termo` | `116_contas_medicas_fundacao.sql` |
| `cm_atendimento` | `idx_cm_atendimento_numero` | `numero_atendimento` | `116_contas_medicas_fundacao.sql` |
| `cm_arquivo` | `idx_cm_arquivo_apagar_em` | `apagar_em` | `116_contas_medicas_fundacao.sql` |
| `cm_eventos` | `idx_cm_eventos_atendimento` | `atendimento_id` | `116_contas_medicas_fundacao.sql` |
| `cm_prescricao` | `idx_cm_prescricao_atendimento` | `atendimento_id, data` | `116_contas_medicas_fundacao.sql` |
| `cm_prescricao_item` | `idx_cm_prescricao_item_prescricao` | `prescricao_id` | `116_contas_medicas_fundacao.sql` |
| `cm_cirurgia` | `idx_cm_cirurgia_atendimento` | `atendimento_id` | `116_contas_medicas_fundacao.sql` |
| `cm_conta` | `idx_cm_conta_faturista_situacao_ordem` | `faturista_id, situacao, ordem_fila` | `116_contas_medicas_fundacao.sql` |
| `cm_conta` | `idx_cm_conta_atendimento` | `atendimento_id` | `116_contas_medicas_fundacao.sql` |
| `cm_conta_item` | `idx_cm_conta_item_conta` | `conta_id` | `116_contas_medicas_fundacao.sql` |
| `cm_guia_linha` | `idx_cm_guia_linha_conta` | `conta_id` | `116_contas_medicas_fundacao.sql` |
| `cm_guia_linha` | `idx_cm_guia_linha_causa_raiz_data` | `causa_raiz, data` | `117_contas_medicas_ia.sql` |
| `cm_guia_linha` | `idx_cm_guia_linha_tabela` | `tabela_id` | `119_contas_medicas_versao_da_tabela.sql` |
| `cm_observacao` | `idx_cm_observacao_conta` | `conta_id` | `116_contas_medicas_fundacao.sql` |
| `cm_chamada_ia` | `idx_cm_chamada_ia_conta` | `conta_id` | `117_contas_medicas_ia.sql` |
| `cm_chamada_ia` | `idx_cm_chamada_ia_criado_em` | `criado_em` | `117_contas_medicas_ia.sql` |
| `cm_registro` | `idx_cm_registro_entidade` | `entidade, entidade_id, data DESC` | `118_contas_medicas_gestao.sql` |
| `cm_regra_historico` | `idx_cm_regra_historico_regra` | `regra_id, criado_em DESC` | `118_contas_medicas_gestao.sql` |
| `cm_validacao_tema` | `idx_cm_validacao_tema_estado` | `estado, tipo` | `118_contas_medicas_gestao.sql` |
| `cm_validacao_tema_linha` | `idx_cm_validacao_tema_linha_tema` | `tema_id` | `118_contas_medicas_gestao.sql` |
| `cm_validacao_tema_linha` | `idx_cm_validacao_tema_linha_guia` | `tema_id, guia_linha_id` | `118_contas_medicas_gestao.sql` |
| `cm_cenario_item` | `idx_cm_cenario_item_cenario` | `cenario_id` | `118_contas_medicas_gestao.sql` |
| `cm_lembrete` | `idx_cm_lembrete_conta` | `conta_id` | `118_contas_medicas_gestao.sql` |
| `cm_lembrete` | `idx_cm_lembrete_estado` | `estado, criado_em` | `118_contas_medicas_gestao.sql` |
| `cm_lembrete_item` | `idx_cm_lembrete_item_lembrete` | `lembrete_id` | `118_contas_medicas_gestao.sql` |

---
**Resumo:** 78 tabelas · 102 relacionamentos FK detectados.
