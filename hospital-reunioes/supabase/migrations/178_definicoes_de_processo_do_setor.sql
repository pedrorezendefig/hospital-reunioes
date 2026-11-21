-- =====================================================
-- Migration 178: Definicoes de processo do setor (ADR 0098, decisao 9; issue #1875)
-- =====================================================
-- A linha do tipo Processo do quadro da Ata entra, no envio, na lista do setor
-- da Reuniao, com o trecho da Ata copiado (`trecho`, e o "para que" em
-- `objetivo`). O setor vem da Reuniao (`reunioes.setor_id`), lido na hora: a
-- Reuniao antiga acertada depois pelo Super admin leva os itens junto.
--
-- `definicoes_processo`: um item por linha de Processo (chave id_reuniao +
-- quadro_pos, para o nascimento ser idempotente no Reenviar e na
-- reconciliacao). Tirar da lista nao apaga: o item vira RETIRADA, com o dia,
-- quem tirou e a anotacao, que o banco exige.
--
-- RLS default-deny: so o backend, com a service_role, le e grava. Nenhuma
-- policy de proposito. Rodar duas vezes e inofensivo. Aplicar a mao no Studio.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS definicoes_processo (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_reuniao         VARCHAR(20) NOT NULL REFERENCES reunioes(id_reuniao) ON DELETE RESTRICT,
  quadro_pos         INTEGER NOT NULL,
  trecho             TEXT NOT NULL CHECK (length(btrim(trecho)) > 0),
  objetivo           TEXT,
  status             TEXT NOT NULL DEFAULT 'ATIVA' CHECK (status IN ('ATIVA', 'RETIRADA')),
  retirada_em        TIMESTAMPTZ,
  -- Sem FK: o registro nao pode depender de um cadastro que muda.
  retirada_por_id    VARCHAR(10),
  retirada_por_nome  TEXT,
  anotacao_retirada  TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (id_reuniao, quadro_pos),
  -- Tirar da lista pede anotacao e o dia (pergunta 3 da #1859).
  CHECK (
    status = 'ATIVA'
    OR (retirada_em IS NOT NULL AND length(btrim(coalesce(anotacao_retirada, ''))) > 0)
  )
);

COMMENT ON TABLE definicoes_processo IS
  'Definicoes de processo do setor (ADR 0098, decisao 9): as linhas do tipo Processo das Atas, com o trecho copiado. Issue #1875.';

ALTER TABLE definicoes_processo ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON definicoes_processo FROM anon, authenticated;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (178) ON CONFLICT (numero) DO NOTHING;
