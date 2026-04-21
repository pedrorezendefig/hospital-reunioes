SELECT 
    p.id, p.nome_completo, p.role, p.email, p.ativo, p.auth_user_id AS "ID no Banco", a.id AS "ID do seu Token"
FROM participantes p
LEFT JOIN auth.users a ON p.auth_user_id = a.id
-- Adapte para o nome ou email que você está logado:
WHERE p.email ILIKE '%ricardo%' OR p.email ILIKE '%pmrdef%';
