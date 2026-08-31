-- =====================================================
-- Migration 088: quem recebeu EM QUAL entrega do relatorio (issue #435)
-- =====================================================
-- `destinatarios` (migration 080) e a evidencia acumulada: quem ja recebeu
-- esta edicao alguma vez, sem nunca encolher. Ela responde bem a pergunta do
-- arquivo ("este email chegou a sair para alguem?") e nao responde nenhuma
-- pergunta de um documento REEMITIDO, porque uma lista plana nao guarda quando
-- nem em qual entrega cada endereco entrou.
--
-- O relatorio da Ouvidoria e exatamente esse tipo de documento: ele sai por
-- email, pode ser reenviado pelo ouvidor quantas vezes for preciso, e a
-- Diretoria que o recebe hoje pode nao ser a de tres meses atras. Depois de um
-- reenvio, "helena@ e rita@" nao diz se as duas receberam a primeira entrega
-- ou se rita@ so entrou no reenvio.
--
-- As duas colunas convivem porque respondem coisas diferentes, e nenhuma
-- deriva da outra sem perda: `destinatarios` e o conjunto, `entregas` e a
-- historia.
-- =====================================================

-- Uma linha por entrega que ACONTECEU, na ordem em que aconteceram:
--   {"em": "<timestamptz ISO>", "tipo": "primeira" | "reenvio",
--    "destinatarios": ["a@hsm.br", ...]}
--
-- `destinatarios` de cada elemento e quem recebeu NAQUELA entrega, e nao o
-- acumulado: numa entrega parcial (o provedor aceita um endereco e recusa
-- outro) entra so quem o provedor aceitou.
--
-- A tentativa que FALHOU nao vira elemento aqui, pelo mesmo motivo que ela nao
-- carimba `enviado_em`: afirmaria recebimento onde nao houve. O motivo da
-- falha continua em `ultimo_erro`, e a contagem em `tentativas`.
--
-- JSONB, e nao tabela filha: o conteudo e um apendice do registro, sempre lido
-- junto dele, nunca consultado por endereco e nunca editado depois de
-- escrito. Uma tabela filha custaria join na listagem e uma politica de RLS a
-- mais para responder o que o registro ja responde sozinho.
--
-- DEFAULT '[]': as edicoes geradas antes desta migration ficam com lista
-- vazia, o que e verdade sobre o que se sabe delas. `destinatarios` continua
-- guardando quem recebeu naquelas, sem a quebra por entrega.
ALTER TABLE ouvidoria_relatorios
  ADD COLUMN IF NOT EXISTS entregas JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN ouvidoria_relatorios.entregas IS
  'Historico por entrega: uma linha {em, tipo, destinatarios} por entrega que aconteceu, na ordem. Complementa destinatarios, que e o conjunto acumulado e nao diz em qual entrega cada endereco entrou.';

-- Sem ENABLE ROW LEVEL SECURITY aqui: nao ha CREATE TABLE nesta migration, e
-- `ouvidoria_relatorios` ja e default-deny desde a 080.
