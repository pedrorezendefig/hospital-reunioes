-- 1. Limpar todas as tabelas transacionais de negócio PRIMEIRO
TRUNCATE TABLE participantes CASCADE;
TRUNCATE TABLE reunioes CASCADE;
TRUNCATE TABLE pendencias CASCADE;
TRUNCATE TABLE reuniao_participantes CASCADE;
TRUNCATE TABLE tokens_validacao CASCADE;
TRUNCATE TABLE agendamentos_email CASCADE;

-- 2. Expulsar todos os usuários do Authentication DEPOIS
DELETE FROM auth.users;
