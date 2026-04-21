SELECT 
    id_acao, id_reuniao, status, responsavel_nome, responsavel_id, prazo 
FROM pendencias
ORDER BY created_at DESC;
