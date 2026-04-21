-- 025_expand_id_reuniao.sql
-- O gerador `_generate_reuniao_id` para ATAs migradas produz 21 chars
-- ("MIG_YYYYMMDD_HHMMSSXX") — excedia VARCHAR(20) original, quebrando
-- /reunioes/importacao/confirmar em runtime (SQLSTATE 22001).
-- Aumenta colunas em todas as tabelas que referenciam id_reuniao.

ALTER TABLE reunioes ALTER COLUMN id_reuniao TYPE VARCHAR(30);
ALTER TABLE reuniao_participantes ALTER COLUMN id_reuniao TYPE VARCHAR(30);
ALTER TABLE pendencias ALTER COLUMN id_reuniao TYPE VARCHAR(30);

COMMENT ON COLUMN reunioes.id_reuniao IS
  'ID da reunião. Prefixos: (sem prefixo) = reunião normal; MIG_ = ATA importada legada.';
