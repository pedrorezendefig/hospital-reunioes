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

-- O dono: o mesmo do Site. A migration 102 nao carimba dono porque nao sabe
-- quem e; aqui ha uma escolha humana para copiar. A Central sao os numeros do
-- Site e do Instagram, e quem responde pelo Site do lado da Vitta responde por
-- eles. Sem dono a API recusa Demanda no Produto, e o pedido sobre a Central
-- nao teria para onde ir.
--
-- Idempotente e conservador: so preenche a Central SEM dono, entao rodar de
-- novo nao troca o dono escolhido depois pela tela. Site sem dono deixa a
-- Central sem dono tambem, e a tela cobra um, como cobra dos sete do seed.
UPDATE tecnologia_produtos AS central
   SET dono_id = site.dono_id
  FROM tecnologia_produtos AS site
 WHERE lower(central.nome) = 'central de comando'
   AND central.dono_id IS NULL
   AND lower(site.nome) = 'site'
   AND site.dono_id IS NOT NULL;
