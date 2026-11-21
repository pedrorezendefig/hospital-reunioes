-- =====================================================
-- Migration 196: Guarda do e-mail de segunda de Reunioes (PRD #1757; issue #1876)
-- =====================================================
-- Toda segunda, o job manda um e-mail por pessoa: ao Facilitador, o que foi
-- concluido, atualizado e repactuado na semana nas Reunioes dele e o que segue
-- atrasado; ao responsavel, as Pendencias dele em aberto. O job roda de hora em
-- hora das 8h as 12h, e esta tabela e a guarda: uma linha por pessoa e por
-- semana (a segunda-feira da semana, no fuso de Sao Paulo), gravada antes do
-- envio. A chave (participante_id, semana) garante um e-mail so por semana: o
-- job grava com `ON CONFLICT DO NOTHING` e so manda quando a linha nasceu.
-- Se o envio falha, o job apaga a linha e a hora seguinte tenta de novo.
--
-- So o backend (service_role) le e grava: RLS default-deny, sem policy.
-- Rodar duas vezes e inofensivo. Aplicar a mao no Studio.
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS email_de_segunda (
  participante_id  VARCHAR(10) NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
  semana           DATE        NOT NULL CHECK (EXTRACT(ISODOW FROM semana) = 1),
  enviado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (participante_id, semana)
);

-- O job procura quem ja recebeu na semana.
CREATE INDEX IF NOT EXISTS idx_email_de_segunda_semana ON email_de_segunda (semana);

ALTER TABLE email_de_segunda ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON email_de_segunda FROM anon, authenticated;

COMMIT;


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (196) ON CONFLICT (numero) DO NOTHING;
