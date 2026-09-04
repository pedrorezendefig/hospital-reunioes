-- Super admin layer: a coluna, o indice parcial e o cargo do responsavel tecnico.
--
-- O SEED NOMINAL SAIU DAQUI. A versao original desta migration listava os seis
-- super admins por e-mail e nome em comentario. Isso e dado pessoal e, num
-- repositorio publico, e tambem um mapa de alvos: diz exatamente em qual conta
-- vale a pena tentar entrar. O conteudo real vive em
-- `local/017_super_admin_seed_real.sql` (pasta `local/`, ADR 0044).
--
-- Em producao esta migration JA FOI APLICADA com o seed nominal, entao as seis
-- flags continuam la. Nada muda no banco por causa desta reescrita.
--
-- Em ambiente novo (local ou homologacao), ninguem nasce super admin. Promova
-- pela tela de admin, ou rode o snippet de `local/`.

ALTER TABLE participantes ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX idx_participantes_super_admin ON participantes(is_super_admin) WHERE is_super_admin = true;
