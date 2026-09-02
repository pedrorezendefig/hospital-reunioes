-- =====================================================
-- Migration 092: o visto GLOBAL da Ouvidoria no caso
-- (issue #484, PRD #470, diagnostico D-09 e RN-66)
-- =====================================================
-- O ouvidor abre a fila e nao consegue distinguir o caso que a area acabou de
-- responder do caso parado ha dias: ele abre um por um para descobrir o que
-- mudou. O que falta e a marca de "ja vi este caso".
--
-- A marca e UMA por caso, e nao uma por pessoa (decisao de grilling do PRD
-- #470). O ponto na linha significa "a Ouvidoria ainda nao viu", e nao "eu
-- ainda nao vi": a Ouvidoria do hospital trabalha como um posto, o caso e da
-- casa, e um carimbo por usuario faria o mesmo caso aparecer novo para o
-- colega que ja tinha sido informado pelo primeiro.
--
-- NULL e o normal, e e o valor com que TODO caso ja existente entra aqui: sem
-- backfill de proposito. Ninguem pode afirmar que a Ouvidoria leu os casos
-- abertos antes desta coluna existir, e carimbar uma data agora apagaria o
-- ponto de casos que talvez nunca tenham sido lidos. Caso existente nasce
-- "com novidade", que e o lado seguro do erro.
--
-- Nenhuma coluna de "ultima movimentacao" nasce aqui. A trilha
-- (`ouvidoria_movimentos`, migration 064) ja e a fonte, e duplicar o instante
-- dela numa coluna do protocolo criaria dois lugares para a mesma verdade,
-- que e exatamente o tipo de par que sai de sincronia quando alguem grava um
-- movimento por um caminho novo. A funcao abaixo agrega a trilha na hora da
-- leitura, apoiada no indice (manifestacao_id, ocorrido_em) que a 064 ja criou.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos seguem valendo para a linha inteira, coluna nova
-- inclusa.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS vista_pela_ouvidoria_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.vista_pela_ouvidoria_em IS
  'Quando a Ouvidoria abriu o Dossie deste caso pela ultima vez (issue #484, RN-66). Carimbo GLOBAL: um por caso, nao um por usuario. NULL = ninguem da Ouvidoria abriu ainda, e o caso conta como novidade na fila. Sem backfill: caso aberto antes desta coluna nasce NULL de proposito.';

-- A ultima movimentacao de cada caso, agregada na leitura. E o outro lado da
-- comparacao que acende o ponto: novidade e `ultimo_movimento_em >
-- vista_pela_ouvidoria_em`, ou visto nulo.
--
-- Vive aqui, e nao numa leitura da trilha inteira pela API, porque a fila do
-- ouvidor e a tela mais aberta do modulo: trazer todos os movimentos de todos
-- os casos a cada carga cresce com o historico do hospital, enquanto o
-- agregado cresce com o numero de casos.
--
-- SECURITY INVOKER (o padrao): quem chama e o backend com a service_role, e a
-- funcao nao pode virar um atalho que enxerga a trilha por cima do RLS
-- default-deny da migration 064. O EXECUTE e revogado de PUBLIC pelo mesmo
-- motivo: sem isso a anon_key do bundle do frontend poderia chamar a funcao e
-- contar quantas manifestacoes o hospital recebeu.
CREATE OR REPLACE FUNCTION ouvidoria_ultimo_movimento()
RETURNS TABLE (manifestacao_id UUID, ultimo_movimento_em TIMESTAMPTZ)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
  SELECT m.manifestacao_id, MAX(m.ocorrido_em)
    FROM ouvidoria_movimentos m
   GROUP BY m.manifestacao_id;
$$;

COMMENT ON FUNCTION ouvidoria_ultimo_movimento() IS
  'Instante da ultima movimentacao de cada caso, derivado da trilha ouvidoria_movimentos (issue #484). Sem coluna redundante no protocolo: a trilha continua sendo a unica fonte.';

REVOKE ALL ON FUNCTION ouvidoria_ultimo_movimento() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ouvidoria_ultimo_movimento() TO service_role;
