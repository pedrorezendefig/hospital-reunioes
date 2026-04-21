-- 1. Remover vínculos da reunião de teste
DELETE FROM reuniao_participantes WHERE id_reuniao = 'RD_20260324_214554';

-- 2. Remover o participante criado com email incorreto
DELETE FROM participantes WHERE id = 'P001';
