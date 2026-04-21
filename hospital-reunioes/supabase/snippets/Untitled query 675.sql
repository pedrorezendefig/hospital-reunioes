SELECT 
    role, count(*) AS total_pessoas, array_agg(nome_completo) as nomes
FROM participantes
GROUP BY role
ORDER BY role;
