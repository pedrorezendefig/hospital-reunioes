-- =====================================================
-- Migration 142: o teste do convite ao Google no QR
-- (issue #1625, PRD #1527, ADR 0089 decisoes 5, 6 e 7)
-- =====================================================
-- Quem da nota 4 ou 5 no cartaz pode ser convidado a avaliar o hospital no
-- Google, num teste que a diretoria executiva liga e desliga. O convite so
-- aparece com DUAS chaves ligadas, e as duas nascem desligadas:
--
--   1. A chave geral, na configuracao da Ouvidoria (`google_teste_global`),
--      com a data em que foi ligada (`google_teste_ligado_em`). A data conta
--      os 60 dias do teste: passado o prazo, a Central avisa para reavaliar,
--      e o convite continua aparecendo ate alguem desligar (decisao 7).
--
--   2. A chave do ponto, no cartaz (`google_teste_ativo`).
--
--   3. A auditoria das duas chaves: quem mudou, quando, o valor anterior e o
--      novo (decisao 6). Append-only como o historico de prazos (migration
--      065): UPDATE e DELETE recusados por trigger. `alterado_por` sem FK pelo
--      mesmo motivo de la (a acao da FK ao apagar a pessoa seria um UPDATE que
--      a trigger recusa), e no tipo da chave de participantes, VARCHAR(10).
--      O nome no momento do ato e o dado duravel.
--
-- Os convites exibidos e os cliques ja tem coluna na avaliacao desde a
-- migration 140 (`convite_google_exibido`, `convite_google_clicado`).
--
-- RLS ligado e nenhuma policy na tabela nova: so o backend le e escreve, pela
-- service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE ouvidoria_config ADD COLUMN IF NOT EXISTS google_teste_global BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ouvidoria_config ADD COLUMN IF NOT EXISTS google_teste_ligado_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_config.google_teste_global IS
  'Chave geral do teste do convite ao Google no QR (ADR 0089). Nasce desligada; so a diretoria executiva muda, com auditoria.';
COMMENT ON COLUMN ouvidoria_config.google_teste_ligado_em IS
  'Quando a chave geral foi ligada pela ultima vez. Conta os 60 dias do aviso de reavaliar na Central.';

ALTER TABLE ouvidoria_pontos ADD COLUMN IF NOT EXISTS google_teste_ativo BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN ouvidoria_pontos.google_teste_ativo IS
  'Chave do ponto no teste do convite ao Google (ADR 0089). O convite so aparece com esta e a chave geral ligadas.';

CREATE TABLE IF NOT EXISTS ouvidoria_convite_google_auditoria (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chave              TEXT NOT NULL CHECK (chave IN ('global', 'ponto')),
  -- Sem FK: o ponto nunca se apaga (ADR 0036, decisao 6), e a trigger abaixo
  -- recusaria a acao da FK de qualquer jeito.
  ponto_id           UUID,
  valor_anterior     BOOLEAN NOT NULL,
  valor_novo         BOOLEAN NOT NULL,
  alterado_por       VARCHAR(10),
  alterado_por_nome  TEXT NOT NULL,
  alterado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_ouvidoria_convite_google_auditoria_ponto
    CHECK ((chave = 'ponto') = (ponto_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_convite_google_auditoria_em
  ON ouvidoria_convite_google_auditoria(alterado_em DESC);

COMMENT ON TABLE ouvidoria_convite_google_auditoria IS
  'Quem ligou ou desligou as chaves do convite ao Google, quando, de que para que (ADR 0089, decisao 6). Append-only: UPDATE e DELETE bloqueados por trigger.';

-- Reaproveita a funcao de bloqueio da migration 064 (mesma regra das outras
-- trilhas append-only).
DROP TRIGGER IF EXISTS trg_ouvidoria_convite_google_auditoria_sem_update ON ouvidoria_convite_google_auditoria;
CREATE TRIGGER trg_ouvidoria_convite_google_auditoria_sem_update
  BEFORE UPDATE ON ouvidoria_convite_google_auditoria
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

DROP TRIGGER IF EXISTS trg_ouvidoria_convite_google_auditoria_sem_delete ON ouvidoria_convite_google_auditoria;
CREATE TRIGGER trg_ouvidoria_convite_google_auditoria_sem_delete
  BEFORE DELETE ON ouvidoria_convite_google_auditoria
  FOR EACH ROW EXECUTE FUNCTION ouvidoria_movimento_imutavel();

ALTER TABLE ouvidoria_convite_google_auditoria ENABLE ROW LEVEL SECURITY;

-- A Central conta convites e cliques por cartaz e periodo: so as notas que
-- mostraram o convite.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_avaliacoes_convite_google
  ON ouvidoria_avaliacoes(criada_em, ponto_id)
  WHERE convite_google_exibido;


-- recibo: a subida espera este numero no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (142) ON CONFLICT (numero) DO NOTHING;
