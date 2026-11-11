-- =====================================================
-- Migration 129: a Conversa da Demanda (issue #1537, PRD #1529, ADR 0083,
-- decisao 8)
-- =====================================================
-- A troca de mensagens entre o diretor e os Desenvolvedores dentro de uma
-- Demanda volta, so no app. Duas coisas entram:
--
--   1. `tecnologia_conversa_da_demanda`: as mensagens de gente, numa tabela
--      propria, separada da conversa com o agente (que mora no JSONB
--      `mensagens` de `tecnologia_planejamentos`). Nao reaproveita
--      `tecnologia_conversas` (102): aquela e a Conversa espelhada na issue,
--      aposentada pela ADR 0077, com linhas automaticas e o id do comentario
--      no GitHub; misturar as duas traria historico de outro contrato para a
--      tela;
--   2. o tipo TECNOLOGIA no CHECK de `notificacoes`: o aviso do sino, com a
--      Demanda como referencia (o clique abre a Demanda na aba). O CHECK e
--      refeito inteiro, com os sete tipos que ja existem (116).
--
-- RLS default-deny (padrao da casa): quem le e escreve e o backend com a
-- service_role. Nenhuma policy de proposito.
--
-- Tudo com IF NOT EXISTS / DROP IF EXISTS / ON CONFLICT: rodar duas vezes tem
-- que ser inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. A Conversa da Demanda ----------
-- `mencoes` guarda os ids de quem foi mencionado ("@Nome Completo", no formato
-- dos comentarios de Pendencia), resolvidos pelo backend entre quem ve a
-- Demanda. Mesmo tipo de `participantes.id`.
--
-- ON DELETE CASCADE: a mensagem nao tem sentido sem a Demanda (que, na
-- pratica, nao se apaga). ON DELETE SET NULL no autor: a mensagem fica se a
-- pessoa sai do cadastro.
CREATE TABLE IF NOT EXISTS tecnologia_conversa_da_demanda (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  demanda_id  UUID NOT NULL REFERENCES tecnologia_demandas(id) ON DELETE CASCADE,
  autor_id    VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  texto       TEXT NOT NULL CHECK (btrim(texto) <> '' AND char_length(texto) <= 5000),
  mencoes     VARCHAR(10)[] NOT NULL DEFAULT '{}',
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tecnologia_conversa_da_demanda_demanda
  ON tecnologia_conversa_da_demanda (demanda_id, criado_em);

COMMENT ON TABLE tecnologia_conversa_da_demanda IS
  'Conversa da Demanda (ADR 0083, decisao 8): mensagens entre o diretor e os Desenvolvedores dentro de uma Demanda, separadas da conversa com o agente. Vive so no app e nunca vai para o GitHub.';
COMMENT ON COLUMN tecnologia_conversa_da_demanda.mencoes IS
  'Ids de quem foi mencionado com @Nome Completo, entre quem ve a Demanda (o autor e os Desenvolvedores). Vazio = sem mencao: a mensagem do autor avisa o Responsavel e a do Desenvolvedor avisa o autor.';

ALTER TABLE tecnologia_conversa_da_demanda ENABLE ROW LEVEL SECURITY;

-- ---------- 2. O aviso do sino ----------
ALTER TABLE notificacoes DROP CONSTRAINT IF EXISTS notificacoes_tipo_check;
ALTER TABLE notificacoes ADD CONSTRAINT notificacoes_tipo_check
  CHECK (tipo IN (
    'MENCAO',
    'STATUS_ALTERADO',
    'COMENTARIO',
    'PRAZO_PROXIMO',
    'RESPONSAVEL_ATRIBUIDO',
    'ACEITE_INTERNO',
    'CONTAS_MEDICAS',
    'TECNOLOGIA'
  ));

INSERT INTO migracoes_aplicadas (numero) VALUES (129) ON CONFLICT (numero) DO NOTHING;
