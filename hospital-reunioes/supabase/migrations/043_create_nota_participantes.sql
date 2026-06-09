-- =====================================================
-- Migration 043: Roster da Nota (issue #34, ADR 0004)
--
-- A Nota ganha "quem participou": cada Participante é um Colaborador do
-- cadastro (participante_id) OU um nome avulso (externo não cadastrado,
-- ex.: "fulano aliado") — exatamente um (CHECK). Espelha
-- reuniao_participantes, com a coluna extra de nome avulso. O roster afia o
-- casamento do responsável na extração de Pendências por IA.
--
-- ON DELETE CASCADE só dispara em hard-delete da Nota (o app usa soft-delete
-- via deleted_at — o roster acompanha a Nota arquivada).
--
-- Reversível via: DROP TABLE nota_participantes.
-- =====================================================

CREATE TABLE IF NOT EXISTS nota_participantes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_nota UUID NOT NULL REFERENCES notas(id) ON DELETE CASCADE,
  participante_id VARCHAR(10) REFERENCES participantes(id),
  nome_avulso VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT chk_nota_part_origem_unica
    CHECK ((participante_id IS NOT NULL) <> (nome_avulso IS NOT NULL)),
  UNIQUE (id_nota, participante_id)
);

-- Avulso não duplica dentro da mesma Nota (case-insensitive); o UNIQUE acima
-- já cobre o Colaborador do cadastro.
CREATE UNIQUE INDEX IF NOT EXISTS uq_nota_part_avulso
  ON nota_participantes (id_nota, lower(nome_avulso)) WHERE nome_avulso IS NOT NULL;

-- Lookup dominante: carregar o roster de uma Nota (painel e extração por IA).
CREATE INDEX IF NOT EXISTS idx_nota_part_nota ON nota_participantes(id_nota);

-- RLS default-deny: backend usa service_role (bypassa RLS). Sem policy, o
-- acesso via anon_key fica bloqueado por padrão (mesmo modelo da migration 009).
ALTER TABLE nota_participantes ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE nota_participantes IS
  'Roster da Nota (ADR 0004): Colaborador do cadastro OU nome avulso (externo), exatamente um por linha (CHECK chk_nota_part_origem_unica). Usado pela extração de Pendências por IA para casar o responsável.';
COMMENT ON COLUMN nota_participantes.nome_avulso IS
  'Externo não cadastrado: fica só como nome — sem id, sem cobrança. Exclusivo com participante_id.';
