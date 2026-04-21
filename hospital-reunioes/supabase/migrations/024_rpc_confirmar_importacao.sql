-- =====================================================
-- Migration 024: RPC atômica para /importacao/confirmar
--
-- Atomiza em UMA transação PL/pgSQL:
--   1. INSERT reunioes        (status_ata='MIGRADA')
--   2. INSERT pendencias      (batch)
--   3. INSERT reuniao_participantes (batch, tolera duplicatas)
--   4. UPDATE reunioes.total_acoes
--
-- Entradas chegam já validadas pelo backend. Dependências externas
-- (upload Storage, provision_with_compensation) rodam ANTES da chamada
-- RPC — falhas nelas NÃO precisam de rollback DB.
--
-- Se QUALQUER passo falhar dentro da função, Postgres desfaz tudo
-- automaticamente (função roda como bloco atômico). Isso elimina o
-- risco anterior de reunião órfã + hash bloqueando re-import.
-- =====================================================

CREATE OR REPLACE FUNCTION confirmar_importacao_atomico(
  p_reuniao JSONB,
  p_pendencias JSONB,
  p_externos_links JSONB
) RETURNS TABLE(reuniao_id TEXT, pendencias_count INT) AS $$
DECLARE
  v_reuniao_id TEXT := p_reuniao->>'id_reuniao';
  v_count INT := 0;
BEGIN
  -- 1. Inserir reunião MIGRADA
  --    jsonb_populate_record mapeia por NOME de coluna; campos extras
  --    no JSON são IGNORADOS apenas se a coluna existir. Se o backend
  --    enviar um campo que não é coluna, a função falha.
  INSERT INTO reunioes
  SELECT * FROM jsonb_populate_record(NULL::reunioes, p_reuniao);

  -- 2. Inserir pendências em lote (pode estar vazio)
  IF jsonb_array_length(COALESCE(p_pendencias, '[]'::jsonb)) > 0 THEN
    INSERT INTO pendencias
    SELECT * FROM jsonb_populate_recordset(NULL::pendencias, p_pendencias);
    GET DIAGNOSTICS v_count = ROW_COUNT;
  END IF;

  -- 3. Vincular participantes (matched + externos). Tolera duplicatas via
  --    UNIQUE(id_reuniao, participante_id) em reuniao_participantes.
  --    OBS: jsonb_populate_recordset NÃO aciona DEFAULT das colunas ausentes
  --    no JSON; por isso geramos `id` e `sequence_assinatura` explicitamente
  --    caso o payload não os envie (evita 23502 em produção).
  IF jsonb_array_length(COALESCE(p_externos_links, '[]'::jsonb)) > 0 THEN
    INSERT INTO reuniao_participantes (id, id_reuniao, participante_id, sequence_assinatura)
    SELECT
      COALESCE(r.id, gen_random_uuid()),
      r.id_reuniao,
      r.participante_id,
      COALESCE(r.sequence_assinatura, 2)
    FROM jsonb_populate_recordset(NULL::reuniao_participantes, p_externos_links) r
    ON CONFLICT (id_reuniao, participante_id) DO NOTHING;
  END IF;

  -- 4. Atualizar contador cacheado (consistência com pendencias reais inseridas)
  UPDATE reunioes
  SET total_acoes = v_count
  WHERE id_reuniao = v_reuniao_id;

  RETURN QUERY SELECT v_reuniao_id, v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION confirmar_importacao_atomico IS
  'Atomiza confirmação de importação de ATA: reunião + pendências + vínculo participantes + total_acoes em uma única transação. Inputs JSONB mapeados por nome de coluna via jsonb_populate_record(set).';
