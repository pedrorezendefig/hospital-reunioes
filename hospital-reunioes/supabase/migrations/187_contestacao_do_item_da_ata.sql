-- =====================================================
-- Migration 187: Contestacao do item da Ata (PRD #1757; issue #1870)
-- =====================================================
-- O responsavel contesta o item dele enquanto a Ata esta em assinatura, e o
-- Facilitador (ou o Super admin) ajusta ou recusa, sempre com anotacao. Os
-- tres gravam evento no Historico pela mesma funcao das outras acoes
-- (`registrar_acao_da_pendencia`, migration 169). A regra (quem pode, quando)
-- fica no Python (`app/services/pendencia_ciclo.py`).
--
-- 1. O CHECK de `pendencia_historico.comando` ganha 'contestar', 'ajustar' e
--    'recusar', sem tirar nenhum dos de antes (171).
-- 2. Indice parcial para achar a Contestacao aberta (o ultimo evento da
--    Contestacao de cada Pendencia), lido toda vez que o Inicio abre.
-- 3. O ajuste corrige tambem o responsavel errado: `registrar_acao_da_pendencia`
--    ganha tres parametros opcionais (id, nome e cargo do responsavel novo) e o
--    Historico guarda o nome de quem era e de quem passou a ser. Sem eles, a
--    funcao faz o mesmo de antes, entao o codigo de antes segue funcionando.
--
-- Depende da 169 e da 171. Sem tabela nova: o RLS default-deny da 169
-- continua valendo, sem policy. Rodar duas vezes e inofensivo. Aplicar a mao
-- no Studio.
-- =====================================================

BEGIN;

-- 1. Os comandos da Contestacao ---------------------------------------------------

ALTER TABLE pendencia_historico DROP CONSTRAINT IF EXISTS pendencia_historico_comando_check;
ALTER TABLE pendencia_historico ADD CONSTRAINT pendencia_historico_comando_check
  CHECK (comando IN (
    'nascimento', 'iniciar', 'anotar', 'concluir', 'repactuar', 'cancelar', 'reabrir', 'migracao',
    'contestar', 'ajustar', 'recusar'
  ));

-- 2. A Contestacao aberta ---------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_pendencia_historico_contestacao
  ON pendencia_historico (id_acao, criado_em)
  WHERE comando IN ('contestar', 'ajustar', 'recusar');

-- 3. O ajuste troca o responsavel ---------------------------------------------------

ALTER TABLE pendencia_historico ADD COLUMN IF NOT EXISTS responsavel_antes TEXT;
ALTER TABLE pendencia_historico ADD COLUMN IF NOT EXISTS responsavel_depois TEXT;

-- A assinatura de 10 parametros sai: com a nova ao lado, a chamada de 10
-- argumentos ficaria ambigua.
DROP FUNCTION IF EXISTS registrar_acao_da_pendencia(VARCHAR, TEXT, TEXT, VARCHAR, TEXT, TEXT, TEXT, DATE, BOOLEAN, BOOLEAN);

CREATE OR REPLACE FUNCTION registrar_acao_da_pendencia(
  p_id_acao           VARCHAR,
  p_comando           TEXT,
  p_anotacao          TEXT,
  p_autor_id          VARCHAR,
  p_autor_nome        TEXT,
  p_status_esperado   TEXT,
  p_status_novo       TEXT,
  p_prazo_novo        DATE,
  p_concluida         BOOLEAN,
  p_conta_atraso      BOOLEAN,
  p_responsavel_id    VARCHAR DEFAULT NULL,
  p_responsavel_nome  TEXT DEFAULT NULL,
  p_cargo             TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
  v_atual   pendencias%ROWTYPE;
  v_evento  BIGINT;
BEGIN
  SELECT * INTO v_atual
    FROM pendencias
   WHERE id_acao = p_id_acao AND deleted_at IS NULL
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Pendencia % nao encontrada.', p_id_acao USING ERRCODE = 'PT404';
  END IF;
  IF v_atual.status IS DISTINCT FROM p_status_esperado THEN
    RAISE EXCEPTION 'A pendencia mudou enquanto a acao era feita. Recarregue e tente de novo.'
      USING ERRCODE = 'PT409';
  END IF;

  UPDATE pendencias
     SET status = p_status_novo,
         prazo = COALESCE(p_prazo_novo, prazo),
         concluida_em = CASE
           WHEN p_concluida IS TRUE THEN now()
           WHEN p_concluida IS FALSE THEN NULL
           ELSE concluida_em
         END,
         responsavel_id = COALESCE(p_responsavel_id, responsavel_id),
         responsavel_nome = CASE WHEN p_responsavel_id IS NULL THEN responsavel_nome ELSE p_responsavel_nome END,
         cargo = CASE WHEN p_responsavel_id IS NULL THEN cargo ELSE p_cargo END
   WHERE id_acao = p_id_acao;

  INSERT INTO pendencia_historico (
    id_acao, comando, anotacao, autor_id, autor_nome,
    status_antes, status_depois, prazo_antes, prazo_depois, conta_atraso,
    responsavel_antes, responsavel_depois
  ) VALUES (
    p_id_acao, p_comando, p_anotacao, p_autor_id, p_autor_nome,
    v_atual.status, p_status_novo, v_atual.prazo, COALESCE(p_prazo_novo, v_atual.prazo),
    COALESCE(p_conta_atraso, false),
    CASE WHEN p_responsavel_id IS NULL THEN NULL ELSE v_atual.responsavel_nome END,
    CASE WHEN p_responsavel_id IS NULL THEN NULL ELSE p_responsavel_nome END
  )
  RETURNING id INTO v_evento;

  IF v_atual.id_reuniao IS NOT NULL THEN
    IF p_status_novo = 'CONCLUIDO' AND v_atual.status <> 'CONCLUIDO' THEN
      UPDATE reunioes SET acoes_concluidas = COALESCE(acoes_concluidas, 0) + 1
       WHERE id_reuniao = v_atual.id_reuniao;
    ELSIF v_atual.status = 'CONCLUIDO' AND p_status_novo <> 'CONCLUIDO' THEN
      UPDATE reunioes SET acoes_concluidas = GREATEST(COALESCE(acoes_concluidas, 0) - 1, 0)
       WHERE id_reuniao = v_atual.id_reuniao;
    END IF;
  END IF;

  RETURN v_evento;
END;
$$;

REVOKE EXECUTE ON FUNCTION registrar_acao_da_pendencia(VARCHAR, TEXT, TEXT, VARCHAR, TEXT, TEXT, TEXT, DATE, BOOLEAN, BOOLEAN, VARCHAR, TEXT, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION registrar_acao_da_pendencia(VARCHAR, TEXT, TEXT, VARCHAR, TEXT, TEXT, TEXT, DATE, BOOLEAN, BOOLEAN, VARCHAR, TEXT, TEXT)
  TO service_role;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (187) ON CONFLICT (numero) DO NOTHING;
