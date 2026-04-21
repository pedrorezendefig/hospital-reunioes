-- Migration 015: remove infraestrutura dos triggers de email 4-8
-- (validacao_ata, participantes_nao_reconhecidos, lembretes D+1/D-7/D-3).
--
-- Os seguintes triggers permanecem intactos:
--   1. Confirmacao de cadastro (backend customizado)
--   2. Convite/recuperacao admin (Supabase Auth)
--   3. Reset de senha self-service (Supabase Auth)
--   9. Convite de assinatura ClickSign (enviado pela ClickSign)
--
-- Esta migration e IDEMPOTENTE — pode rodar multiplas vezes com seguranca.

-- 1. Dropar tabela de agendamentos de email (alimentava cron disparar_lembretes)
DROP TABLE IF EXISTS public.agendamentos_email CASCADE;

-- 2. Dropar tabela de tokens de validacao (alimentava links por email)
DROP TABLE IF EXISTS public.tokens_validacao CASCADE;

-- 3. Limpar preferencias de email ociosas (coluna permanece para reuso futuro)
UPDATE public.user_preferences SET emails = '{}'::jsonb WHERE emails IS NOT NULL;
