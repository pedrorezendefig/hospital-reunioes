# Lente de banco

Entra quando o PR tem migration. Olhe só as migrations do diff e o código que lê o que elas mudam. É must-fix:

- **Migration que perde dado:** `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE` ou `UPDATE` sem `WHERE`, troca de tipo que corta valor, `RENAME` de coluna que o código ainda lê pelo nome antigo.
- **Coluna obrigatória sem valor padrão:** `NOT NULL` novo em tabela que já tem linhas, sem `DEFAULT` nem preenchimento antes, falha ao aplicar.
- **Sem `IF NOT EXISTS` / `IF EXISTS`:** a migration não roda duas vezes sem erro.
- **Índice:** consulta nova filtrando ou ordenando por coluna sem índice; índice único sobre dado que já pode ter repetição.
- **Ordem das migrations:** número repetido ou menor que o último em `origin/main`; migration que usa objeto criado por outra que vem depois; migration já aplicada editada em vez de uma nova.
