-- =====================================================
-- Migration 140: a Avaliacao do QR da Ouvidoria
-- (issue #1622, PRD #1527, ADR 0086 decisoes 1, 2, 3 e 9)
-- =====================================================
-- O cartaz deixa de abrir direto o formulario: a pessoa da uma nota de 1 a 5,
-- marca os motivos se quiser e deixa um comentario opcional. A nota e dado de
-- gestao, nao caso: nao tem protocolo, prazo nem fila. Duas coisas:
--
--   1. Nasce `ouvidoria_avaliacoes`, com as colunas da secao 4.4 da
--      especificacao da Diretoria. A linha NAO guarda IP, aparelho nem
--      contato (decisao 2): o abuso e contido pelo limite de 3 notas a cada
--      10 minutos por endereco e cartaz, contado so na memoria do backend.
--      As colunas do convite ao Google (#1625) e da revisao (#1624 e #1626)
--      nascem aqui, desligadas, para as fatias seguintes nao mexerem na
--      tabela.
--
--   2. O caso ganha `avaliacao_id`: a nota de onde a pessoa seguiu para a
--      Manifestacao guiada (decisao 3). A ligacao mora SO no caso, e nao
--      tambem numa `manifestacao_id` da avaliacao como a especificacao
--      desenha: duas colunas para a mesma ligacao podem discordar, e uma so
--      basta para ir e voltar. O indice unico garante uma nota por caso. O
--      anonimo nao grava a ligacao.
--
-- RETENCAO (decisao 9): o comentario sai cinco anos depois de criado, pelo
-- cron da Retencao (`apagar_comentarios_de_avaliacao` em
-- app/services/ouvidoria_retencao.py); nota e motivos ficam. O `avaliacao_id`
-- do caso sai com o Dossie.
--
-- RLS ligado e nenhuma policy: so o backend le e escreve, pela service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

CREATE TABLE IF NOT EXISTS ouvidoria_avaliacoes (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ponto_id                 UUID REFERENCES ouvidoria_pontos(id) ON DELETE SET NULL,
  canal                    TEXT NOT NULL DEFAULT 'qr' CHECK (canal IN ('qr', 'whatsapp')),
  nota                     SMALLINT NOT NULL CHECK (nota BETWEEN 1 AND 5),
  motivos                  TEXT[] NOT NULL DEFAULT '{}',
  comentario               TEXT CHECK (comentario IS NULL OR char_length(comentario) BETWEEN 1 AND 500),
  criada_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
  convite_google_exibido   BOOLEAN NOT NULL DEFAULT FALSE,
  convite_google_clicado   BOOLEAN NOT NULL DEFAULT FALSE,
  pediu_retorno            BOOLEAN NOT NULL DEFAULT FALSE,
  revisar                  BOOLEAN NOT NULL DEFAULT FALSE,
  revisar_motivo           TEXT,
  revisao_desfecho         TEXT CHECK (revisao_desfecho IN ('convertida', 'arquivada')),
  revisada_por             VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  revisada_em              TIMESTAMPTZ,
  -- Os oito motivos da tela N2. A lista vive aqui e em
  -- app/services/ouvidoria_avaliacoes.py, e um teste confere que batem.
  CONSTRAINT ck_ouvidoria_avaliacoes_motivos
    CHECK (motivos <@ ARRAY['atencao_equipe', 'tempo_espera', 'informacao_recebida', 'limpeza', 'conforto', 'atendimento_medico', 'atendimento_enfermagem', 'recepcao']::TEXT[])
);

-- A aba Avaliacoes le por cartaz e periodo; a Retencao, por data.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_avaliacoes_ponto
  ON ouvidoria_avaliacoes(ponto_id, criada_em);
CREATE INDEX IF NOT EXISTS idx_ouvidoria_avaliacoes_comentario
  ON ouvidoria_avaliacoes(criada_em)
  WHERE comentario IS NOT NULL;

ALTER TABLE ouvidoria_avaliacoes ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE ouvidoria_avaliacoes IS
  'Avaliacao do QR (ADR 0086): nota de 1 a 5, motivos e comentario opcionais. Nao gera protocolo e nao guarda IP, aparelho nem contato. So o backend le.';
COMMENT ON COLUMN ouvidoria_avaliacoes.comentario IS
  'Texto livre de quem avaliou, ate 500 caracteres. Sai cinco anos depois de criado, pela Retencao; nota e motivos ficam.';
COMMENT ON COLUMN ouvidoria_avaliacoes.pediu_retorno IS
  'A nota de 1 a 3 que seguiu para a Manifestacao guiada com a pessoa identificada. O anonimo nao marca.';

ALTER TABLE ouvidoria_protocolos ADD COLUMN IF NOT EXISTS avaliacao_id UUID REFERENCES ouvidoria_avaliacoes(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_ouvidoria_protocolos_avaliacao
  ON ouvidoria_protocolos(avaliacao_id)
  WHERE avaliacao_id IS NOT NULL;

COMMENT ON COLUMN ouvidoria_protocolos.avaliacao_id IS
  'A nota do cartaz de onde a pessoa seguiu para a Manifestacao guiada (ADR 0086, decisao 3). Nulo no anonimo e em quem veio direto. Sai com o Dossie na Retencao.';


-- recibo: a subida espera este numero no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (140) ON CONFLICT (numero) DO NOTHING;
