-- =====================================================
-- Migration 143: o agente de triagem da Ouvidoria
-- (issue #1624, PRD #1527, ADR 0087)
-- =====================================================
-- Logo depois da chegada de cada caso e de cada avaliacao com comentario, o
-- texto pseudonimizado vai ao modelo uma vez, e o agente sugere o assunto, o
-- envio ao Nucleo e a marca Para revisar. Duas mudancas:
--
--   1. O caso ganha `assunto`: uma linha, escrita pelo agente, sem nome de
--      pessoa. A fila mostra o assunto no lugar do comeco do relato. Nulo
--      quando o agente falhou, quando o teto do dia acabou e em todo caso
--      anterior a esta migration. As colunas do apontamento ao Nucleo ja
--      existem (migration 139), e as da marca Para revisar tambem (140).
--
--   2. A cota diaria do agente: no maximo 300 chamadas por dia no app
--      inteiro (ADR 0087, decisao 5). A contagem mora no banco para valer
--      entre processos e reinicios. `ouvidoria_agente_reservar_chamada` soma
--      uma chamada ao dia corrente (fuso do hospital) so se ainda houver
--      cota, num unico comando: duas chegadas ao mesmo tempo nunca passam
--      as duas pela ultima vaga. Devolve uma linha com `reservada`.
--
-- RETENCAO: o assunto sai com o relato (`CAMPOS_DO_DOSSIE` em
-- app/services/ouvidoria_retencao.py). A cota so guarda dia e numero.
--
-- RLS ligado e nenhuma policy na tabela nova; a funcao so pode ser chamada
-- pela service role, que e quem o backend usa.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

-- 1. O assunto do caso.
ALTER TABLE ouvidoria_protocolos ADD COLUMN IF NOT EXISTS assunto TEXT;

COMMENT ON COLUMN ouvidoria_protocolos.assunto IS
  'Assunto de uma linha escrito pelo agente de triagem na chegada (ADR 0087), sem nome de pessoa. Nulo quando o agente nao gerou. Sai com o relato na Retencao.';

-- 2. A cota diaria do agente.
CREATE TABLE IF NOT EXISTS ouvidoria_agente_cota (
  dia       DATE PRIMARY KEY,
  chamadas  INTEGER NOT NULL DEFAULT 0 CHECK (chamadas >= 0)
);

ALTER TABLE ouvidoria_agente_cota ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE ouvidoria_agente_cota IS
  'Quantas chamadas o agente de triagem da Ouvidoria fez em cada dia (ADR 0087, decisao 5). So o backend le e escreve.';

CREATE OR REPLACE FUNCTION ouvidoria_agente_reservar_chamada(p_teto INTEGER)
RETURNS TABLE (reservada BOOLEAN)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  v_dia DATE := (now() AT TIME ZONE 'America/Sao_Paulo')::date;
BEGIN
  INSERT INTO ouvidoria_agente_cota AS cota (dia, chamadas)
  VALUES (v_dia, 1)
  ON CONFLICT (dia) DO UPDATE
    SET chamadas = cota.chamadas + 1
    WHERE cota.chamadas < p_teto;
  -- Uma linha de uma coluna, e nao escalar: e o formato que o postgrest-py
  -- aceita sem tropeco (ver a migration 101). FOUND e falso quando o WHERE do
  -- ON CONFLICT barrou a soma, que e o teto atingido.
  reservada := FOUND AND p_teto > 0;
  RETURN NEXT;
END;
$$;

REVOKE EXECUTE ON FUNCTION ouvidoria_agente_reservar_chamada(INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION ouvidoria_agente_reservar_chamada(INTEGER) TO service_role;

COMMENT ON FUNCTION ouvidoria_agente_reservar_chamada(INTEGER) IS
  'Reserva uma chamada do agente de triagem no dia corrente, se a cota do dia ainda tem vaga. Devolve reservada = false no teto.';


-- recibo: a subida espera este numero no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (143) ON CONFLICT (numero) DO NOTHING;
