/**
 * LIMPEZA TOTAL DE DADOS (Zera o banco para novos testes)
 * Execute isso no SQL Editor do Supabase.
 */

TRUNCATE TABLE 
    agendamentos_email,
    pendencias,
    reuniao_participantes,
    tokens_validacao,
    signup_requests,
    reunioes,
    participantes
RESTART IDENTITY CASCADE;
