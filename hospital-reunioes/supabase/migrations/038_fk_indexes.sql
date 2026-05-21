-- =====================================================
-- Migration 038: Indexes em foreign keys legadas
-- =====================================================
-- Postgres não cria index automático em FK. Audit comparando REFERENCES vs
-- CREATE INDEX nas migrations 001-037 revelou 5 FKs sem index explícito:
--
--   reunioes.facilitador_id       -> participantes(id)
--   agendamentos_email.id_acao    -> pendencias(id_acao) ON DELETE CASCADE
--   participantes.setor_id        -> setores(id)         ON DELETE SET NULL
--   participantes.cargo_id        -> cargos(id)          ON DELETE SET NULL
--   reunioes.tipo_id              -> tipos_reuniao(id)   ON DELETE SET NULL
--
-- Sem index, queries que filtram/joinam por essas colunas viram sequential scan
-- e, em cascading deletes, o Postgres varre a tabela filha inteira a cada
-- delete na tabela pai.
--
-- Nota sobre CONCURRENTLY: o runner de migrations do Supabase aplica tudo em
-- transação e CREATE INDEX CONCURRENTLY exige rodar fora dela. Como a base
-- ainda é pequena (poucas centenas de linhas), o lock de poucos ms de um
-- CREATE INDEX comum é aceitável. Em escala maior, refazer manualmente via
-- psql usando CONCURRENTLY e dropar/recriar.
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_reunioes_facilitador
  ON reunioes(facilitador_id);

CREATE INDEX IF NOT EXISTS idx_agendamentos_email_id_acao
  ON agendamentos_email(id_acao);

CREATE INDEX IF NOT EXISTS idx_participantes_setor_id
  ON participantes(setor_id);

CREATE INDEX IF NOT EXISTS idx_participantes_cargo_id
  ON participantes(cargo_id);

CREATE INDEX IF NOT EXISTS idx_reunioes_tipo_id
  ON reunioes(tipo_id);
