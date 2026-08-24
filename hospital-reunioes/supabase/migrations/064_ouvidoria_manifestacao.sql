-- =====================================================
-- Migration 064: Manifestacao nasce (issue #320, ADR 0034)
-- =====================================================
-- O ADR 0034 emenda a decisao 3 do ADR 0031 ("indice, nao dossie"): a
-- manifestacao completa passa a viver neste app. A fundacao da 063 e
-- preservada inteira - sequence, numero e a coluna gerada ANO-NNNN nao sao
-- tocadas, porque numeros ja foram comunicados a pacientes.
--
-- Esta migration cuida da maquina de estados do PRD. O estado
-- 'aguardando_manifestante' e do PRD de governanca de prazo (#318) e nao entra
-- aqui.
-- =====================================================

-- 1. Maquina de estados do PRD substitui aberto/respondido/encerrado.
--    Ordem obrigatoria: os dados migram ANTES do CHECK novo, senao o ALTER
--    falha ao validar as linhas existentes.
ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_status_check;

UPDATE ouvidoria_protocolos SET status = 'em_classificacao' WHERE status = 'aberto';

ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_status_check
  CHECK (status IN ('novo', 'em_classificacao', 'aguardando_area', 'respondido', 'encerrado'));

-- 2. Toda manifestacao nasce aguardando classificacao (ADR 0034, decisao 3):
--    nenhum processo automatico despacha. O POST da Ana nao manda status.
ALTER TABLE ouvidoria_protocolos ALTER COLUMN status SET DEFAULT 'em_classificacao';

COMMENT ON COLUMN ouvidoria_protocolos.status IS
  'Estado na maquina do PRD (ADR 0034). Nasce em em_classificacao; so ouvidor ou diretoria_executiva valida e aciona a area.';

-- 3. O Dossie (ADR 0034, decisao 1). Todas as colunas sao opcionais: o POST
--    atual da Ana nao as manda e o caso entra com dados_incompletos, para o
--    ouvidor completar na validacao.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS relato_integral      TEXT,
  ADD COLUMN IF NOT EXISTS manifestante_nome    TEXT,
  ADD COLUMN IF NOT EXISTS manifestante_contato TEXT,
  ADD COLUMN IF NOT EXISTS manifestante_vinculo TEXT,
  ADD COLUMN IF NOT EXISTS anonimo              BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS sigilo_reforcado     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS dados_incompletos    BOOLEAN NOT NULL DEFAULT true,
  -- Classificacao sugerida pela Ana, a parte: nunca sobrescreve a validada
  -- pelo ouvidor (ADR 0034, decisao 10).
  ADD COLUMN IF NOT EXISTS classificacao_ia     JSONB,
  ADD COLUMN IF NOT EXISTS desfecho             TEXT,
  ADD COLUMN IF NOT EXISTS desfecho_descricao   TEXT;

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_vinculo_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_vinculo_check
  CHECK (manifestante_vinculo IS NULL
         OR manifestante_vinculo IN ('paciente', 'acompanhante', 'colaborador', 'terceiro', 'outro'));

COMMENT ON TABLE ouvidoria_protocolos IS
  'Manifestacao de ouvidoria com o Dossie completo (ADR 0034, emenda a decisao 3 do ADR 0031). Dado pessoal e por vezes sensivel: acesso minimo por perfil, trilha imutavel e log de acesso.';
COMMENT ON COLUMN ouvidoria_protocolos.sigilo_reforcado IS
  'Denuncia e relato de conduta nascem sigilosos: so ouvidor e diretoria_executiva leem, e o super admin tecnico fica de fora (RN-40).';
COMMENT ON COLUMN ouvidoria_protocolos.classificacao_ia IS
  'Classificacao sugerida pela Ana, persistida a parte. Nunca sobrescreve a validada pelo ouvidor.';

-- 4. Perfis do contexto Ouvidoria (ADR 0034, decisao 8), eixo proprio e
--    ortogonal ao access_profile (Reunioes) e ao perfil_pop, no padrao da
--    migration 045. NULL = sem papel na Ouvidoria.
ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS perfil_ouvidoria TEXT;

ALTER TABLE participantes DROP CONSTRAINT IF EXISTS participantes_perfil_ouvidoria_check;
ALTER TABLE participantes
  ADD CONSTRAINT participantes_perfil_ouvidoria_check
  CHECK (perfil_ouvidoria IS NULL OR perfil_ouvidoria IN ('ouvidor', 'diretoria_executiva'));

CREATE INDEX IF NOT EXISTS idx_participantes_perfil_ouvidoria
  ON participantes(perfil_ouvidoria) WHERE perfil_ouvidoria IS NOT NULL;

-- 5. Trilha imutavel de movimentos (ADR 0034, consequencia LGPD). Nasce
--    append-only: nem a aplicacao nem o super admin editam ou apagam.
CREATE TABLE IF NOT EXISTS ouvidoria_movimentos (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id   UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  ocorrido_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  estado_anterior   TEXT,
  estado_novo       TEXT NOT NULL,
  autor_id          VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  autor_nome        TEXT NOT NULL,
  observacao        TEXT
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_movimentos_manifestacao
  ON ouvidoria_movimentos(manifestacao_id, ocorrido_em);

COMMENT ON TABLE ouvidoria_movimentos IS
  'Trilha imutavel do que aconteceu com a manifestacao (ADR 0034). Append-only: UPDATE e DELETE sao bloqueados por trigger, inclusive para o super admin.';
COMMENT ON COLUMN ouvidoria_movimentos.autor_nome IS
  'Nome no momento do ato: a trilha nao muda se a pessoa for renomeada ou removida depois.';

-- ON DELETE RESTRICT acima ja impede apagar a manifestacao com movimento;
-- a trigger abaixo fecha o resto do caminho.
CREATE OR REPLACE FUNCTION ouvidoria_movimento_imutavel() RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'Movimento de ouvidoria e imutavel: % nao e permitido', TG_OP
    USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ouvidoria_movimentos_sem_update ON ouvidoria_movimentos;
CREATE TRIGGER trg_ouvidoria_movimentos_sem_update
  BEFORE UPDATE ON ouvidoria_movimentos
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

DROP TRIGGER IF EXISTS trg_ouvidoria_movimentos_sem_delete ON ouvidoria_movimentos;
CREATE TRIGGER trg_ouvidoria_movimentos_sem_delete
  BEFORE DELETE ON ouvidoria_movimentos
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

-- 6. Log de acesso ao Dossie (ADR 0034, consequencia LGPD): quem abriu o que,
--    e quando. Tambem append-only.
CREATE TABLE IF NOT EXISTS ouvidoria_acessos (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  ocorrido_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  ator_id         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ator_nome       TEXT NOT NULL,
  acao            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_acessos_manifestacao
  ON ouvidoria_acessos(manifestacao_id, ocorrido_em DESC);

COMMENT ON TABLE ouvidoria_acessos IS
  'Log de acesso a manifestacao (ADR 0034): dado pessoal e por vezes sensivel, todo acesso deixa registro.';

DROP TRIGGER IF EXISTS trg_ouvidoria_acessos_sem_update ON ouvidoria_acessos;
CREATE TRIGGER trg_ouvidoria_acessos_sem_update
  BEFORE UPDATE ON ouvidoria_acessos
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

DROP TRIGGER IF EXISTS trg_ouvidoria_acessos_sem_delete ON ouvidoria_acessos;
CREATE TRIGGER trg_ouvidoria_acessos_sem_delete
  BEFORE DELETE ON ouvidoria_acessos
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

-- 7. RLS default-deny nas tabelas novas (padrao da casa: 009/041/051/063).
--    Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_movimentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE ouvidoria_acessos ENABLE ROW LEVEL SECURITY;

-- 8. Porta de entrada unica da maquina de estados. Status e movimento na MESMA
--    transacao: a funcao roda como bloco atomico, entao ou os dois entram ou
--    nenhum entra. A regra do grafo vive aqui tambem (nao so no backend), para
--    que contornar a API nao contorne a maquina de estados.
CREATE OR REPLACE FUNCTION ouvidoria_transicionar(
  p_manifestacao_id   UUID,
  p_estado_novo       TEXT,
  p_autor_id          VARCHAR(10),
  p_autor_nome        TEXT,
  p_observacao        TEXT DEFAULT NULL,
  p_desfecho          TEXT DEFAULT NULL,
  p_desfecho_descricao TEXT DEFAULT NULL
) RETURNS ouvidoria_protocolos AS $$
DECLARE
  v_atual   TEXT;
  v_destino ouvidoria_protocolos;
BEGIN
  -- FOR UPDATE: duas transicoes simultaneas na mesma manifestacao serializam,
  -- em vez de as duas lerem o mesmo estado atual e ambas passarem na regra.
  SELECT status INTO v_atual FROM ouvidoria_protocolos WHERE id = p_manifestacao_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Manifestacao nao encontrada' USING ERRCODE = 'no_data_found';
  END IF;

  IF NOT (
       (v_atual = 'novo'             AND p_estado_novo = 'em_classificacao')
    OR (v_atual = 'em_classificacao' AND p_estado_novo IN ('aguardando_area', 'encerrado'))
    OR (v_atual = 'aguardando_area'  AND p_estado_novo IN ('respondido', 'encerrado'))
    OR (v_atual = 'respondido'       AND p_estado_novo = 'encerrado')
  ) THEN
    RAISE EXCEPTION 'Transicao invalida: % para %', v_atual, p_estado_novo USING ERRCODE = 'check_violation';
  END IF;

  IF p_estado_novo = 'encerrado' AND (
       p_desfecho IS NULL
    OR p_desfecho NOT IN ('procedente', 'improcedente', 'parcialmente_procedente', 'sem_condicoes_de_apuracao')
    OR btrim(COALESCE(p_desfecho_descricao, '')) = ''
  ) THEN
    RAISE EXCEPTION 'Encerrar exige desfecho e descricao' USING ERRCODE = 'check_violation';
  END IF;

  UPDATE ouvidoria_protocolos
     SET status             = p_estado_novo,
         desfecho           = COALESCE(p_desfecho, desfecho),
         desfecho_descricao = COALESCE(p_desfecho_descricao, desfecho_descricao)
   WHERE id = p_manifestacao_id
  RETURNING * INTO v_destino;

  INSERT INTO ouvidoria_movimentos (manifestacao_id, estado_anterior, estado_novo, autor_id, autor_nome, observacao)
  VALUES (p_manifestacao_id, v_atual, p_estado_novo, p_autor_id, p_autor_nome, p_observacao);

  RETURN v_destino;
END;
$$ LANGUAGE plpgsql;
