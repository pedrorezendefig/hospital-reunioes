-- Super admin layer: flag + seed 6 pessoas + cargo Pedro = Engenheiro de IA

ALTER TABLE participantes ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX idx_participantes_super_admin ON participantes(is_super_admin) WHERE is_super_admin = true;

UPDATE participantes SET is_super_admin = true
WHERE LOWER(email) IN (
  'pmrdef@gmail.com',                              -- Pedro Rezende (Engenheiro de IA)
  'felipemalafaia@yahoo.com.br',                   -- Felipe Malafaia (Diretor Executivo)
  'josiane@hospitalsaomatheus.com.br',             -- Josiane Alves
  'carolizidorio@hospitalsaomatheus.com.br',       -- Caroline Izidorio Drumond (Carol)
  'engenheira.carolinelima@gmail.com',             -- Caroline Lima
  'diretoriamedica@hospitalsaomatheus.com.br'      -- Jorge Porto Marassi
);

UPDATE participantes SET cargo = 'Engenheiro de IA' WHERE LOWER(email) = 'pmrdef@gmail.com';
