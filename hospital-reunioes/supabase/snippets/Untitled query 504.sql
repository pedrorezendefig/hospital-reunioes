-- Desabilita temporariamente as foreign keys para evitar erros de restrição
SET session_replication_role = 'replica';

-- Deleta os dados de todas as tabelas mencionadas
TRUNCATE TABLE 
    pendencias, 
    tokens_validacao, 
    reuniao_participantes, 
    participantes, 
    reunioes 
RESTART IDENTITY CASCADE;

-- Reabilita as restrições
SET session_replication_role = 'origin';