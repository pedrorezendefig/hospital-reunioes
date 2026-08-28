-- =====================================================
-- Migration 085: Ponto de escuta, o cadastro dos cartazes de QR (issue #378, ADR 0036)
-- =====================================================
-- O canal `qr` existe desde a 063 e nunca foi usado: o app sabia RECEBER a
-- manifestacao vinda de um cartaz, mas nao sabia GERAR o cartaz. Nasce aqui a
-- entidade que faltava. Cada linha e um cartaz impresso, e o que vai no papel e
-- o `codigo`, nao o nome do setor por extenso (ADR 0036, decisao 2).
--
-- A tabela fica SOBRE a taxonomia de Setores da casa, sem FK: `setor` guarda o
-- nome canonico ja resolvido, mesmo padrao de `ouvidoria_setor_responsaveis`
-- (migration 068). Renomear um setor na taxonomia nao reescreve cartaz que ja
-- esta na parede, e e isso que se quer.
-- =====================================================

CREATE TABLE IF NOT EXISTS ouvidoria_pontos (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- O que vai impresso. Seis caracteres de um alfabeto sem os pares ambiguos
  -- (sem 0/O e sem 1/I): o codigo e lido em voz alta e digitado a mao quando a
  -- camera nao coopera (ADR 0036, decisao 3).
  codigo      TEXT NOT NULL,
  setor       TEXT NOT NULL,
  ponto       TEXT NOT NULL,
  ativo       BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
  criado_por  VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,

  -- O alfabeto vive no CHECK, e nao so no Python: contornar a API nao pode
  -- gravar um codigo que a camera confunde.
  CONSTRAINT ck_ouvidoria_pontos_codigo
    CHECK (codigo ~ '^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{6}$'),
  -- Mesmo teto do `canal_ponto` que o cartaz alimenta (80 caracteres), e o
  -- anti-vazio da casa: rotulo em branco nao ajuda ninguem a achar o cartaz.
  CONSTRAINT ck_ouvidoria_pontos_ponto
    CHECK (length(btrim(ponto)) BETWEEN 1 AND 80),
  CONSTRAINT ck_ouvidoria_pontos_setor
    CHECK (length(btrim(setor)) >= 1)
);

-- E o indice unico que faz a retentativa da geracao funcionar: o Python sorteia
-- e o banco decide quem ficou com o codigo.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_pontos_codigo
  ON ouvidoria_pontos(codigo);

-- A leitura da tela e por setor, e a resolucao do QR e por codigo (ja coberta
-- pelo indice unico acima).
CREATE INDEX IF NOT EXISTS idx_ouvidoria_pontos_setor
  ON ouvidoria_pontos(setor, ponto);

COMMENT ON TABLE ouvidoria_pontos IS
  'Ponto de escuta: um cartaz de QR code da Ouvidoria (ADR 0036). Desativa, nunca apaga: o historico de casos aponta para ele pelo canal_setor/canal_ponto congelados no momento da manifestacao.';
COMMENT ON COLUMN ouvidoria_pontos.codigo IS
  'O que vai impresso no cartaz, em https://<app>/ouvidoria/qr?p=<codigo>. Gerado pelo sistema e IMUTAVEL: mudar o codigo invalidaria o cartaz que ja esta na parede.';
COMMENT ON COLUMN ouvidoria_pontos.setor IS
  'Nome canonico do setor, resolvido contra a taxonomia (tabela setores) no cadastro e congelado aqui. Sem FK, mesmo padrao de ouvidoria_setor_responsaveis: renomear o setor nao reescreve cartaz impresso.';
COMMENT ON COLUMN ouvidoria_pontos.ponto IS
  'Onde o cartaz esta colado ("Poltrona 12"). Vira canal_ponto da manifestacao que nascer deste QR, exceto em caso anonimo (issue #375, decisao 5).';
COMMENT ON COLUMN ouvidoria_pontos.ativo IS
  'FALSE e o cartaz aposentado. O QR dele continua abrindo o formulario publico, mas SEM origem e nunca numa pagina de erro: ninguem parado na frente de um cartaz pode ficar sem canal por causa de faxina no cadastro (ADR 0036, decisao 6).';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/068/069/073/080).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_pontos ENABLE ROW LEVEL SECURITY;
