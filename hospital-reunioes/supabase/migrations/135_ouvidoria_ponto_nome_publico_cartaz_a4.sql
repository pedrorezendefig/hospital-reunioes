-- =====================================================
-- Migration 135: o Ponto de escuta ganha os campos do cartaz A4
-- (issue #1617, PRD #1527, ADR 0086 decisao 10)
-- =====================================================
-- O cartaz passa a A4, no modelo aprovado pela Diretoria, e o paciente deixa
-- de ver o nome interno do setor. Cinco colunas novas em `ouvidoria_pontos`:
--
--   1. `nome_publico`: o que o paciente ve ("Emergencia adulta"). Nulavel: sem
--      ele, vale o rotulo do ponto, nunca o nome do setor;
--   2. `descricao_local`: onde o cartaz esta, por extenso. Obrigatoria. As
--      linhas que ja existem recebem o rotulo do ponto, que e o "onde o cartaz
--      esta colado" de hoje, para o NOT NULL entrar sem apagar nada;
--   3. `titulo_cartaz`: um dos dois modelos do cartaz;
--   4. `codigo_controle`: o codigo da instalacao ("PSA-01"), impresso fora da
--      moldura. Nao e o `codigo` do QR, que continua o mesmo;
--   5. `ala_internacao`: o cartaz de ala de internacao manda falar com a
--      enfermagem do posto, e nao com a equipe do setor.
--
-- Sem indice e sem policy nova: a tabela ja esta com RLS que nega por padrao
-- (migration 085) e o backend escreve com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS nome_publico TEXT;
ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS descricao_local TEXT;
ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS titulo_cartaz TEXT NOT NULL DEFAULT 'atendimento_hoje';
ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS codigo_controle TEXT;
ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS ala_internacao BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE ouvidoria_pontos SET descricao_local = ponto WHERE descricao_local IS NULL;
ALTER TABLE ouvidoria_pontos ALTER COLUMN descricao_local SET NOT NULL;

-- O anti-vazio da casa nos tres textos: em branco nao ajuda ninguem a achar o
-- cartaz. Os tetos sao os da API.
ALTER TABLE ouvidoria_pontos DROP CONSTRAINT IF EXISTS ck_ouvidoria_pontos_descricao_local;
ALTER TABLE ouvidoria_pontos
  ADD CONSTRAINT ck_ouvidoria_pontos_descricao_local
  CHECK (length(btrim(descricao_local)) BETWEEN 1 AND 300);

ALTER TABLE ouvidoria_pontos DROP CONSTRAINT IF EXISTS ck_ouvidoria_pontos_nome_publico;
ALTER TABLE ouvidoria_pontos
  ADD CONSTRAINT ck_ouvidoria_pontos_nome_publico
  CHECK (nome_publico IS NULL OR length(btrim(nome_publico)) BETWEEN 1 AND 80);

ALTER TABLE ouvidoria_pontos DROP CONSTRAINT IF EXISTS ck_ouvidoria_pontos_codigo_controle;
ALTER TABLE ouvidoria_pontos
  ADD CONSTRAINT ck_ouvidoria_pontos_codigo_controle
  CHECK (codigo_controle IS NULL OR length(btrim(codigo_controle)) BETWEEN 1 AND 20);

-- Os dois modelos do cartaz. A lista vive aqui e no Python, e um teste confere
-- que as duas batem.
ALTER TABLE ouvidoria_pontos DROP CONSTRAINT IF EXISTS ck_ouvidoria_pontos_titulo_cartaz;
ALTER TABLE ouvidoria_pontos
  ADD CONSTRAINT ck_ouvidoria_pontos_titulo_cartaz
  CHECK (titulo_cartaz IN ('atendimento_hoje', 'um_minuto'));

COMMENT ON COLUMN ouvidoria_pontos.nome_publico IS
  'O nome do local que o paciente ve ("Emergencia adulta"). Nulo vale o rotulo do ponto; o nome interno do setor nunca chega ao paciente (ADR 0086, decisao 10).';
COMMENT ON COLUMN ouvidoria_pontos.descricao_local IS
  'Onde o cartaz esta, por extenso. Obrigatoria: e o que o painel mostra.';
COMMENT ON COLUMN ouvidoria_pontos.titulo_cartaz IS
  'Modelo do titulo do cartaz A4: atendimento_hoje ("Como foi seu atendimento hoje?") ou um_minuto ("Um minuto para nos contar").';
COMMENT ON COLUMN ouvidoria_pontos.codigo_controle IS
  'Codigo da instalacao ("PSA-01"), impresso fora da moldura do cartaz. Nao substitui o codigo do QR.';
COMMENT ON COLUMN ouvidoria_pontos.ala_internacao IS
  'TRUE no cartaz de ala de internacao: o aviso manda falar com a enfermagem do posto da ala.';
COMMENT ON COLUMN ouvidoria_pontos.codigo IS
  'O que vai impresso no cartaz, em https://<app>/a/<codigo> desde a ADR 0086 (a URL antiga /ouvidoria/qr?p=<codigo> redireciona). Gerado pelo sistema e IMUTAVEL: mudar o codigo invalidaria o cartaz que ja esta na parede.';

INSERT INTO migracoes_aplicadas (numero) VALUES (135) ON CONFLICT (numero) DO NOTHING;
