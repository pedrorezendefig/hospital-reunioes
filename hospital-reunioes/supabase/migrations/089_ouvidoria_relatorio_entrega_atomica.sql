-- =====================================================
-- Migration 089: o append do historico de entregas acontece no BANCO (issue #450)
-- =====================================================
-- Tres colunas de `ouvidoria_relatorios` ACUMULAM: `entregas` (a historia por
-- entrega, migration 088), `destinatarios` (o conjunto de quem ja recebeu,
-- migration 080) e `reenvios` (o contador). Ate aqui, as tres acumulavam em
-- Python: o backend lia a linha, somava a entrega da vez e gravava o resultado
-- inteiro de volta.
--
-- Isso e read-modify-write, e ele perde escrita. Dois reenvios manuais
-- simultaneos (ou um reenvio concorrente com a rodada do job) leem a MESMA
-- linha e cada um grava "a base que eu li mais a minha entrega": a ultima
-- escrita apaga a entrega da outra. O que se perde e justamente a evidencia de
-- distribuicao de dado da Ouvidoria para fora do sistema, que e o motivo de
-- essas colunas existirem.
--
-- O caminho AUTOMATICO nao tem esse buraco: `_reivindicar` (o UPDATE
-- condicional em `enviado_em`) serializa uma rodada por edicao. O do botao do
-- ouvidor nao tem guarda nenhuma, e ele nao pode ter a mesma: quem aperta
-- aquele botao esta pedindo o segundo email de proposito.
--
-- Entao o append desce para o banco, onde as duas escritas se resolvem na
-- ordem em que o Postgres as recebe, sem nenhuma delas ler o estado da outra.
--
-- Nao ha CREATE TABLE aqui: `ouvidoria_relatorios` ja e default-deny desde a
-- 080, e nenhuma coluna nova nasce nesta migration.
-- =====================================================

-- SECURITY INVOKER (o default, como todas as funcoes desta casa): o backend
-- chama com a service_role, que ja passa por cima do RLS, e a funcao nao
-- precisa de privilegio que quem chama nao tenha. Tornar DEFINER aqui daria a
-- anon_key do bundle do frontend uma porta de escrita nesta tabela.
CREATE OR REPLACE FUNCTION ouvidoria_relatorio_registrar_entrega(
  p_id            UUID,
  p_entrega       JSONB,
  p_entregues     TEXT[],
  p_conta_reenvio BOOLEAN,
  p_campos        JSONB
) RETURNS SETOF ouvidoria_relatorios
LANGUAGE sql
AS $$
  UPDATE ouvidoria_relatorios AS r
     SET
         -- A entrega da vez no FIM da historia que a linha ja tem, e nao no fim
         -- da que este processo leu. E este `||` que faz as duas escritas
         -- concorrentes conviverem.
         entregas = r.entregas || jsonb_build_array(p_entrega),

         -- O conjunto acumulado, sem repetir e sem encolher: entra so quem
         -- ainda nao estava na linha GRAVADA.
         --
         -- O GROUP BY tambem deduplica p_entregues contra SI MESMO, e nao e
         -- zelo: duas pessoas da Diretoria com o mesmo email e cadastro que a
         -- aplicacao nao impede, e as duas entram em `entregues` na mesma
         -- entrega. Sem isto, o endereco entraria duas vezes numa coluna cujo
         -- contrato e ser conjunto.
         --
         -- WITH ORDINALITY + ORDER BY min(ordem) preserva a ordem de chegada:
         -- DISTINCT sozinho ordenaria pelo texto do email, e a lista deixaria de
         -- ler como a cronologia da distribuicao.
         destinatarios = r.destinatarios || ARRAY(
           SELECT t.novo
             FROM unnest(p_entregues) WITH ORDINALITY AS t(novo, ordem)
            WHERE NOT (t.novo = ANY (r.destinatarios))
            GROUP BY t.novo
            ORDER BY min(t.ordem)
         ),

         -- O contador soma sobre o valor da linha. Somar em Python faria dois
         -- reenvios simultaneos deixarem o contador em 1.
         reenvios = r.reenvios + CASE WHEN p_conta_reenvio THEN 1 ELSE 0 END,

         -- Os carimbos escalares continuam sobrescrita, que e o que eles sao:
         -- `p_campos` traz SO o que a tentativa decidiu mudar, e o que ela nao
         -- diz a linha mantem. O teste de presenca da chave (`?`) e o que
         -- separa "nao mexe" de "grava NULL": `{"ultimo_erro": null}` limpa a
         -- coluna, e a ausencia da chave a preserva.
         enviado_em   = CASE WHEN p_campos ? 'enviado_em'
                             THEN (p_campos->>'enviado_em')::timestamptz   ELSE r.enviado_em   END,
         reenviado_em = CASE WHEN p_campos ? 'reenviado_em'
                             THEN (p_campos->>'reenviado_em')::timestamptz ELSE r.reenviado_em END,
         desistido_em = CASE WHEN p_campos ? 'desistido_em'
                             THEN (p_campos->>'desistido_em')::timestamptz ELSE r.desistido_em END,
         tentativas   = CASE WHEN p_campos ? 'tentativas'
                             THEN (p_campos->>'tentativas')::integer       ELSE r.tentativas   END,
         ultimo_erro  = CASE WHEN p_campos ? 'ultimo_erro'
                             THEN  p_campos->>'ultimo_erro'                ELSE r.ultimo_erro  END
   WHERE r.id = p_id
  RETURNING r.*;
$$;

-- `CREATE FUNCTION` da EXECUTE a PUBLIC por default, e todo papel do Supabase
-- herda de PUBLIC. Sem este REVOKE, o PostgREST expoe
-- `POST /rest/v1/rpc/ouvidoria_relatorio_registrar_entrega` para a anon_key que
-- viaja no bundle do frontend, e esta funcao nao e so escrita: o
-- `RETURNS SETOF` devolve a linha inteira, `dados` (o objeto de metricas)
-- incluso. A RLS default-deny da 080 segura o SELECT direto na tabela, mas a
-- defesa moraria num arquivo que esta migration nao controla, e a casa tem o
-- historico exato desse padrao (issues #440 e #459).
--
-- PUBLIC e o grant que existe de fato; `anon` e `authenticated` entram por
-- nome para o REVOKE valer tambem se alguem tiver dado grant direto a eles.
REVOKE EXECUTE ON FUNCTION ouvidoria_relatorio_registrar_entrega(UUID, JSONB, TEXT[], BOOLEAN, JSONB)
  FROM PUBLIC, anon, authenticated;

COMMENT ON FUNCTION ouvidoria_relatorio_registrar_entrega(UUID, JSONB, TEXT[], BOOLEAN, JSONB) IS
  'Registra UMA entrega do relatorio somando entregas, destinatarios e reenvios no proprio banco, para dois reenvios concorrentes nao apagarem um ao outro (issue #450). Os carimbos escalares vem em p_campos e sao sobrescrita: chave ausente preserva a coluna.';
