'use strict';

/* Curadoria funcional das tabelas do banco — alimenta o popover do Mapa da app.
   Uma linha por tabela dizendo O QUE ela guarda em linguagem de negócio, mais
   notas opcionais por coluna importante. Tabela nova sem verbete aparece no
   popover só com os dados técnicos (o painel avisa discreto que falta verbete).
   Fonte do vocabulário: CONTEXT.md + docs/spec/snapshots/ENTIDADES.md. */

export const TABELAS = {
  participantes: {
    resumo: 'O cadastro central de pessoas: quem entra em reunião, assina ata, recebe pendência ou administra o sistema.',
    colunas: {
      role: 'papel na plataforma de Reuniões (coordenador, presidente…)',
      access_profile: 'perfil de acesso (super_admin, secretaria…)',
      perfil_pop: 'papel no contexto POPs (concedido na tela de Usuários)',
      auth_user_id: 'liga a pessoa ao login do Supabase (vazio = sem login)',
      is_externo: 'convidado de fora do hospital (só recebe emails)',
    },
  },
  cargos: { resumo: 'Lista canônica de cargos do organograma, usada nos formulários.' },
  user_preferences: { resumo: 'O que cada pessoa quer receber: quais notificações in-app e quais emails.' },

  reunioes: {
    resumo: 'Cada reunião agendada ou realizada, com a ata inteira, o estado do ciclo de vida e os PDFs gerados.',
    colunas: {
      status_ata: 'onde a reunião está no ciclo (PROGRAMADA → … → ASSINADA)',
      json_ata: 'a ata estruturada que a IA gerou (resumo, tópicos, ações)',
      envelope_key_clicksign: 'liga a ata ao envelope de assinatura na ClickSign',
      falha_envio_assinatura: 'registro visível quando o envio pra assinatura falhou',
      fonte: 'de onde veio a transcrição (upload, Fireflies, mock)',
    },
  },
  reuniao_participantes: {
    resumo: 'Quem participou de cada reunião e em que ordem assina a ata.',
    colunas: { sequence_assinatura: 'ordem de assinatura no envelope (facilitador primeiro)' },
  },
  tipos_reuniao: { resumo: 'Tipos de reunião cadastráveis (RAP, alinhamento…), usados no agendamento.' },
  pendencias: {
    resumo: 'As ações que saíram das atas: o que ficou combinado, com responsável, prazo e status de cobrança.',
    colunas: {
      status: 'PENDENTE, EM_PROGRESSO, ATRASADO, CONCLUIDO…',
      co_responsavel_id: 'segunda pessoa cobrada junto (pode ser externo)',
    },
  },
  agendamentos_email: { resumo: 'A fila de emails de cobrança programados para cada pendência (lembrete, atraso).' },
  tokens_validacao: { resumo: 'Links seguros de uso único enviados por email (validar ata, corrigir).' },
  comentarios_pendencias: {
    resumo: 'A conversa dentro de cada pendência, com menções que geram notificação.',
    colunas: { mencoes: 'IDs das pessoas citadas com @ (recebem notificação)' },
  },

  notificacoes: { resumo: 'O sininho do app: avisos in-app por pessoa (menção, prazo, atribuição).' },
  audit_log: { resumo: 'Trilha de auditoria: quem fez o quê nas ações administrativas e destrutivas, com motivo.' },
  bulk_jobs: { resumo: 'Ações administrativas em massa rodando em background, com progresso e falhas por item.' },

  pops_setores: { resumo: 'Os Setores do contexto POPs; a sigla vira a base do Código de cada POP.' },
  pops_setores_participantes: { resumo: 'Vínculo pessoa ↔ Setor no contexto POPs: define o escopo do que cada um vê.' },
  pops: {
    resumo: 'Cada Procedimento Operacional Padrão: código travado, criticidade e os três papéis do fluxo (Elaborador, Revisor, Validador).',
    colunas: {
      criticidade: 'define a periodicidade de revisão do POP',
      codigo: 'identificador travado (SIGLA-NNN), gerado na criação',
    },
  },
  pops_versoes: {
    resumo: 'Cada versão de um POP, com o estado do fluxo de aprovação (A_ELABORAR → … → PUBLICADO).',
    colunas: {
      estado: 'etapa do fluxo (EM_ELABORACAO, EM_REVISAO, EM_ASSINATURA…)',
      rascunho: 'as 11 seções do documento em edição',
    },
  },
  pops_devolucoes: { resumo: 'Histórico das devoluções: quando Revisor ou Validador mandam a versão de volta, com comentários.' },
  pops_materiais_referencia: { resumo: 'Arquivos de apoio anexados na elaboração (PDF, DOCX…), com o texto extraído pro agente.' },
};
