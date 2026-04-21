-- =====================================================
-- Migration 010: RPCs atômicas para acoes_concluidas
-- Substitui o padrão read-then-write em pendencias.py
-- evitando race condition em atualizações concorrentes
-- =====================================================

CREATE OR REPLACE FUNCTION incrementar_acoes_concluidas(p_id_reuniao TEXT)
RETURNS void AS $$
  UPDATE reunioes
  SET acoes_concluidas = COALESCE(acoes_concluidas, 0) + 1
  WHERE id_reuniao = p_id_reuniao;
$$ LANGUAGE sql;

CREATE OR REPLACE FUNCTION decrementar_acoes_concluidas(p_id_reuniao TEXT)
RETURNS void AS $$
  UPDATE reunioes
  SET acoes_concluidas = GREATEST(COALESCE(acoes_concluidas, 0) - 1, 0)
  WHERE id_reuniao = p_id_reuniao;
$$ LANGUAGE sql;
