-- 111_tecnologia_produto_central_de_comando.sql
--
-- O Produto "Central de Comando" na aba Tecnologia (issue #827, PRD #809,
-- ADR 0058 e ADR 0056). A Central foi ligada em producao nesta fatia, e os
-- pedidos sobre ela passam a ter lugar proprio: Produto proprio, com o texto
-- dele no Kit de conhecimento do Assistente de Tecnologia.
--
-- Idempotente, no molde do seed da migration 102: `ON CONFLICT DO NOTHING`
-- cai no indice unico de nome sem distinguir maiusculas, entao rodar de novo
-- nao duplica, e nao mexe em quem ja criou o Produto pela tela. A ordem e a
-- proxima livre, como o cadastro da tela faz, para o Produto entrar no fim da
-- lista mesmo que outros tenham nascido depois do seed.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL.

INSERT INTO tecnologia_produtos (nome, ordem) VALUES
  ('Central de Comando', (SELECT COALESCE(MAX(ordem), 0) + 1 FROM tecnologia_produtos))
ON CONFLICT DO NOTHING;
