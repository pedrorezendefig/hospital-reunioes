/**
 * LIMPEZA TOTAL DE DADOS (Zera o banco para novos testes)
 * Execute isso no SQL Editor do Supabase.
 */

TRUNCATE TABLE
    agendamentos_email,
    pendencias,
    reuniao_participantes,
    tokens_validacao,
    reunioes,
    participantes
RESTART IDENTITY CASCADE;
