-- =====================================================
-- Migration 065: Registro manual do ouvidor, com anexos (issue #321, ADR 0034)
-- =====================================================
-- Segunda fatia do PRD #317. A 064 fez a Manifestacao nascer com Dossie,
-- estados e trilha; aqui ela passa a nascer TAMBEM pela mao do ouvidor, com o
-- que chega por telefone, balcao e email.
--
-- Duas coisas entram: a origem do caso (canal e T0 real do contato) e o Anexo
-- (metadados aqui, binario no storage, leitura por URL assinada).
-- =====================================================

-- 1. De onde veio o caso (ADR 0034, decisao 9). 'ana' e o default porque toda
--    linha que existe hoje nasceu no atendimento da Ana ou no import do
--    NocoDB, que era o registro dela. O formulario publico e o QR entram na
--    fatia seguinte e acrescentam o valor deles ao CHECK.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS canal TEXT NOT NULL DEFAULT 'ana';

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_canal_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_canal_check
  CHECK (canal IN ('ana', 'telefone', 'presencial', 'email'));

COMMENT ON COLUMN ouvidoria_protocolos.canal IS
  'Por onde a manifestacao chegou ao hospital. Registro manual do ouvidor cobre telefone, presencial e email.';

-- 2. T0: a data e hora REAIS do contato (PRD #317, marco T0). Retroativa por
--    natureza, porque o ouvidor digita depois do telefonema. Nao confundir com
--    created_at de linha: aqui interessa quando chegou ao hospital, nao quando
--    foi digitado.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS contato_em TIMESTAMPTZ;

-- Retroativo tambem para o que ja existe: o unico marco confiavel dos casos
-- antigos e a data de abertura.
UPDATE ouvidoria_protocolos SET contato_em = data_abertura::timestamptz WHERE contato_em IS NULL;

ALTER TABLE ouvidoria_protocolos ALTER COLUMN contato_em SET DEFAULT now();
ALTER TABLE ouvidoria_protocolos ALTER COLUMN contato_em SET NOT NULL;

COMMENT ON COLUMN ouvidoria_protocolos.contato_em IS
  'T0: quando a manifestacao chegou ao hospital, nao quando foi digitada. O registro manual informa a hora real do contato.';

-- 3. Quem digitou. NULL para o que entra pela Ana (nao ha pessoa do hospital
--    no ato) e para linha cujo autor saiu do quadro depois.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS registrado_por VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL;

COMMENT ON COLUMN ouvidoria_protocolos.registrado_por IS
  'Quem da ouvidoria digitou o registro manual. NULL quando a manifestacao entrou por canal automatico.';

-- 4. Anexo: a evidencia junto do caso (ADR 0034, decisao 1). So metadados
--    aqui; o binario vive no bucket privado e e lido por URL assinada.
CREATE TABLE IF NOT EXISTS ouvidoria_anexos (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id  UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  filename         TEXT NOT NULL CHECK (btrim(filename) <> ''),
  content_type     TEXT NOT NULL CHECK (btrim(content_type) <> ''),
  -- 20 MB por arquivo, o mesmo limite que a API recusa (issue #321): contornar
  -- a API nao contorna o limite.
  tamanho_bytes    BIGINT NOT NULL CHECK (tamanho_bytes > 0 AND tamanho_bytes <= 20971520),
  storage_path     TEXT NOT NULL CHECK (btrim(storage_path) <> ''),
  enviado_por      VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  enviado_por_nome TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_anexos_manifestacao
  ON ouvidoria_anexos(manifestacao_id, created_at);

COMMENT ON TABLE ouvidoria_anexos IS
  'Anexos da manifestacao (ADR 0034): foto, PDF, audio ou documento. Metadados aqui, binario no bucket privado anexos-ouvidoria.';
COMMENT ON COLUMN ouvidoria_anexos.storage_path IS
  'Caminho no bucket privado. Nome sorteado: o filename original pode conter o nome de quem manifestou e nao entra em caminho.';
COMMENT ON COLUMN ouvidoria_anexos.enviado_por_nome IS
  'Nome no momento do envio: a trilha nao muda se a pessoa for renomeada ou removida depois.';

-- 5. RLS default-deny (padrao da casa: 009/041/051/063/064). Backend usa
--    service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_anexos ENABLE ROW LEVEL SECURITY;

-- 6. Bucket privado do anexo. Diferente do materiais-pops, aqui NAO existe
--    policy de leitura para 'authenticated': evidencia de ouvidoria (por vezes
--    de denuncia sigilosa) nao pode ser lida por qualquer usuario logado do
--    app. O unico caminho e a URL assinada que o backend emite, depois de
--    conferir o perfil da Ouvidoria.
INSERT INTO storage.buckets (id, name, public)
VALUES ('anexos-ouvidoria', 'anexos-ouvidoria', false)
ON CONFLICT (id) DO NOTHING;

-- Idempotente: CREATE POLICY nao tem IF NOT EXISTS no Postgres. O DROP existe
-- para o caso de uma policy ter sido criada a mao no Studio.
DROP POLICY IF EXISTS "Authenticated Access anexos-ouvidoria" ON storage.objects;
