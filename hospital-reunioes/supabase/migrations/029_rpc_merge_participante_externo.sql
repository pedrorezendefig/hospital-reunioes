-- =====================================================
-- Migration 029: RPC merge_participante_externo
--
-- Objetivo (Fase 2 do super-admin CRUD): permitir que o super-admin
-- mescle um participante externo (criado pelo resolver de STT quando um
-- nome nao bate com nenhum interno conhecido) com um participante
-- interno ja existente, transferindo TODAS as FKs e deletando o externo
-- em uma transacao atomica.
--
-- Cenario tipico: resolver criou "Joao Silva" externo (is_externo=true)
-- porque nao achou "João Silva" (P042) por variação ortográfica. O
-- super-admin aciona Resolver -> Mesclar -> seleciona P042. Esta RPC
-- substitui `externo_id` por `interno_id` em todas as tabelas que
-- referenciam participantes(id), atualiza os caches *_nome, trata o
-- array de mencoes[] em comentarios_pendencias, respeita UNIQUE em
-- reuniao_participantes e finaliza com DELETE do externo.
--
-- Tabelas afetadas:
-- - reuniao_participantes.participante_id (com UNIQUE(id_reuniao, pid))
-- - reunioes.facilitador_id
-- - reunioes.importado_por_id
-- - pendencias.responsavel_id + responsavel_nome (cache)
-- - pendencias.co_responsavel_id + co_responsavel_nome (cache)
-- - comentarios_pendencias.autor_id + autor_nome (cache)
-- - comentarios_pendencias.mencoes[] (array VARCHAR(10))
-- - notificacoes.destinatario_id
-- - audit_log.actor_id e bulk_jobs.actor_id sao IGNORADOS: externo nao
--   tem auth, entao nunca e actor. Se (bug passado) tiver, ON DELETE
--   SET NULL se encarrega.
-- - user_preferences.participante_id tem ON DELETE CASCADE: sera limpo
--   junto com o DELETE do externo.
--
-- Auditoria: grava uma linha em audit_log com action='merge_participante',
-- target_type='participante', target_id=externo_id e metadata contendo
-- interno_id, motivo e contadores por tabela afetada.
--
-- Segurança/validação:
-- - externo_id deve existir e ter is_externo=true.
-- - interno_id deve existir e ter is_externo=false.
-- - externo_id != interno_id.
-- - actor_id, se fornecido, e usado em audit_log.actor_id + actor_email.
--
-- Retorno: tabela de uma linha com os contadores (para feedback UX).
--
-- Reversivel? NAO — a operacao e destrutiva. O audit_log preserva o
-- historico (os IDs e contadores), mas nao restaura as FKs se um merge
-- errado for executado. Por isso a UI exige motivo obrigatorio.
-- =====================================================

CREATE OR REPLACE FUNCTION merge_participante_externo(
  p_externo_id VARCHAR,
  p_interno_id VARCHAR,
  p_motivo     TEXT,
  p_actor_id   VARCHAR DEFAULT NULL,
  p_actor_email TEXT   DEFAULT NULL
)
RETURNS TABLE (
  reuniao_participantes_moved INT,
  reuniao_participantes_dropped INT,
  reunioes_facilitador INT,
  reunioes_importado_por INT,
  pendencias_responsavel INT,
  pendencias_co_responsavel INT,
  comentarios_autor INT,
  comentarios_mencoes INT,
  notificacoes INT
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_externo           RECORD;
  v_interno           RECORD;
  v_rp_moved          INT := 0;
  v_rp_dropped        INT := 0;
  v_fac               INT := 0;
  v_imp               INT := 0;
  v_resp              INT := 0;
  v_co                INT := 0;
  v_com_autor         INT := 0;
  v_com_menc          INT := 0;
  v_notif             INT := 0;
BEGIN
  -- ---------- Validações ----------
  IF p_externo_id IS NULL OR p_interno_id IS NULL THEN
    RAISE EXCEPTION 'externo_id e interno_id sao obrigatorios';
  END IF;
  IF p_externo_id = p_interno_id THEN
    RAISE EXCEPTION 'externo_id e interno_id nao podem ser iguais';
  END IF;
  IF p_motivo IS NULL OR length(trim(p_motivo)) = 0 THEN
    RAISE EXCEPTION 'motivo e obrigatorio';
  END IF;

  SELECT * INTO v_externo FROM participantes WHERE id = p_externo_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'externo nao encontrado: %', p_externo_id;
  END IF;
  IF NOT COALESCE(v_externo.is_externo, FALSE) THEN
    RAISE EXCEPTION 'participante % nao e externo', p_externo_id;
  END IF;

  SELECT * INTO v_interno FROM participantes WHERE id = p_interno_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'interno nao encontrado: %', p_interno_id;
  END IF;
  IF COALESCE(v_interno.is_externo, FALSE) THEN
    RAISE EXCEPTION 'participante % e externo — nao pode ser alvo de merge', p_interno_id;
  END IF;

  -- ---------- reuniao_participantes (respeitando UNIQUE) ----------
  -- Primeiro: onde o interno JÁ está na mesma reunião que o externo,
  -- apenas apaga o vinculo do externo (UPDATE violaria UNIQUE).
  WITH dup AS (
    SELECT rp_ext.id
    FROM reuniao_participantes rp_ext
    JOIN reuniao_participantes rp_int
      ON rp_int.id_reuniao = rp_ext.id_reuniao
     AND rp_int.participante_id = p_interno_id
    WHERE rp_ext.participante_id = p_externo_id
  )
  DELETE FROM reuniao_participantes rp
  USING dup
  WHERE rp.id = dup.id;
  GET DIAGNOSTICS v_rp_dropped = ROW_COUNT;

  -- Depois: o que sobrou, transfere para o interno.
  UPDATE reuniao_participantes
     SET participante_id = p_interno_id
   WHERE participante_id = p_externo_id;
  GET DIAGNOSTICS v_rp_moved = ROW_COUNT;

  -- ---------- reunioes.facilitador_id ----------
  UPDATE reunioes SET facilitador_id = p_interno_id
   WHERE facilitador_id = p_externo_id;
  GET DIAGNOSTICS v_fac = ROW_COUNT;

  -- ---------- reunioes.importado_por_id ----------
  UPDATE reunioes SET importado_por_id = p_interno_id
   WHERE importado_por_id = p_externo_id;
  GET DIAGNOSTICS v_imp = ROW_COUNT;

  -- ---------- pendencias: responsavel ----------
  UPDATE pendencias
     SET responsavel_id = p_interno_id,
         responsavel_nome = v_interno.nome_completo,
         cargo = COALESCE(v_interno.cargo, cargo)
   WHERE responsavel_id = p_externo_id;
  GET DIAGNOSTICS v_resp = ROW_COUNT;

  -- ---------- pendencias: co_responsavel ----------
  UPDATE pendencias
     SET co_responsavel_id = p_interno_id,
         co_responsavel_nome = v_interno.nome_completo
   WHERE co_responsavel_id = p_externo_id;
  GET DIAGNOSTICS v_co = ROW_COUNT;

  -- ---------- comentarios_pendencias: autor ----------
  UPDATE comentarios_pendencias
     SET autor_id = p_interno_id,
         autor_nome = v_interno.nome_completo
   WHERE autor_id = p_externo_id;
  GET DIAGNOSTICS v_com_autor = ROW_COUNT;

  -- ---------- comentarios_pendencias.mencoes[]: substitui e deduplica ----------
  UPDATE comentarios_pendencias
     SET mencoes = (
       SELECT ARRAY(
         SELECT DISTINCT unnest(
           array_replace(mencoes, p_externo_id, p_interno_id)
         )
       )
     )
   WHERE p_externo_id = ANY(mencoes);
  GET DIAGNOSTICS v_com_menc = ROW_COUNT;

  -- ---------- notificacoes ----------
  UPDATE notificacoes SET destinatario_id = p_interno_id
   WHERE destinatario_id = p_externo_id;
  GET DIAGNOSTICS v_notif = ROW_COUNT;

  -- ---------- Auditoria ----------
  INSERT INTO audit_log (
    actor_id, actor_email, action, target_type, target_id,
    metadata, reason
  ) VALUES (
    p_actor_id,
    COALESCE(p_actor_email, 'desconhecido'),
    'merge_participante',
    'participante',
    p_externo_id,
    jsonb_build_object(
      'interno_id', p_interno_id,
      'interno_nome', v_interno.nome_completo,
      'externo_nome', v_externo.nome_completo,
      'externo_email', v_externo.email,
      'contadores', jsonb_build_object(
        'reuniao_participantes_moved',   v_rp_moved,
        'reuniao_participantes_dropped', v_rp_dropped,
        'reunioes_facilitador',          v_fac,
        'reunioes_importado_por',        v_imp,
        'pendencias_responsavel',        v_resp,
        'pendencias_co_responsavel',     v_co,
        'comentarios_autor',             v_com_autor,
        'comentarios_mencoes',           v_com_menc,
        'notificacoes',                  v_notif
      )
    ),
    p_motivo
  );

  -- ---------- Delete final do externo ----------
  -- ON DELETE CASCADE cuida de user_preferences e notificacoes eventualmente
  -- remanescentes. Tabelas com ON DELETE SET NULL (audit_log.actor_id,
  -- bulk_jobs.actor_id) mantem o historico com actor_id=NULL.
  DELETE FROM participantes WHERE id = p_externo_id;

  RETURN QUERY SELECT
    v_rp_moved, v_rp_dropped, v_fac, v_imp,
    v_resp, v_co, v_com_autor, v_com_menc, v_notif;
END;
$$;

COMMENT ON FUNCTION merge_participante_externo IS
  'Mescla externo com interno: transfere todas as FKs, atualiza caches _nome, trata mencoes[], loga audit_log e deleta externo. Uso exclusivo por super-admin via endpoint /admin/usuarios/{externo_id}/merge.';
