-- =====================================================
-- Migration 068: responsaveis do setor, marco T1 e fila de notificacoes
-- (issue #325, PRD #317, ADR 0034 decisoes 5 e 7)
-- =====================================================
-- A 064 fez a Manifestacao nascer, a 065 deu o motor de prazos e a 066 o
-- registro manual. Aqui entra o que falta para a area ser acionada de verdade:
-- quem responde por cada setor, quando o ouvidor validou, e o registro de toda
-- notificacao enviada.
--
-- O calculo do vencimento continua fora do banco (app/services/ouvidoria_prazos.py):
-- esta migration so guarda o resultado, como a 065 estabeleceu.
-- =====================================================

-- 1. Titular, substituto e gestor de cada setor (ADR 0034, decisao 5).
--    O setor vem por NOME, a mesma chave que `ouvidoria_protocolos.setor` usa:
--    a validacao casa os dois com igualdade simples, e a tela oferece so os
--    nomes da taxonomia `setores` (migration 027). Nao ha cadastro paralelo de
--    setor aqui; ha o cadastro de PESSOAS que respondem por ele.
CREATE TABLE IF NOT EXISTS ouvidoria_setor_responsaveis (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  setor           TEXT NOT NULL CHECK (btrim(setor) <> ''),
  papel           TEXT NOT NULL CHECK (papel IN ('titular', 'substituto', 'gestor')),
  nome            TEXT NOT NULL CHECK (btrim(nome) <> ''),
  email           TEXT NOT NULL CHECK (btrim(email) <> ''),
  -- Vigencia (RN da spec): quem entra e quem sai do papel, com data. Fim NULL
  -- e o caso comum, o titular de hoje. O fim e inclusivo: quem sai no dia 31
  -- ainda responde no dia 31.
  vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
  vigencia_fim    DATE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ouvidoria_setor_responsaveis_vigencia_check
    CHECK (vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);

CREATE INDEX IF NOT EXISTS idx_ouvidoria_setor_responsaveis_setor
  ON ouvidoria_setor_responsaveis(setor, papel);

COMMENT ON TABLE ouvidoria_setor_responsaveis IS
  'Quem responde por cada setor na Ouvidoria (ADR 0034, decisao 5). Setor sem titular vigente nao e acionavel: a demanda sobe ao gestor da area com alerta a Diretoria.';
COMMENT ON COLUMN ouvidoria_setor_responsaveis.setor IS
  'Nome do setor, a mesma chave de ouvidoria_protocolos.setor. A tela so oferece nomes da taxonomia `setores`.';
COMMENT ON COLUMN ouvidoria_setor_responsaveis.vigencia_fim IS
  'Ultimo dia em que a pessoa responde pelo setor, inclusive. NULL significa vigencia aberta.';

DROP TRIGGER IF EXISTS trigger_ouvidoria_setor_responsaveis_updated_at ON ouvidoria_setor_responsaveis;
CREATE TRIGGER trigger_ouvidoria_setor_responsaveis_updated_at
  BEFORE UPDATE ON ouvidoria_setor_responsaveis
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- 2. T1: quando o ouvidor validou e quem validou. A spec mede triagem
--    (T0 ate T1) e resposta da area (T1 ate T2) separadamente, entao o marco
--    precisa de coluna propria: derivar de `ouvidoria_movimentos` daria a hora,
--    mas nao sobreviveria a uma reabertura no PRD de governanca.
--    Junto vem o extrato que o setor recebeu. O `resumo` guarda a palavra crua
--    de quem manifestou (no canal aberto sao os primeiros caracteres do que o
--    cidadao digitou) e nao pode sair da Ouvidoria por email: quem escreve o
--    que o setor le e o ouvidor, na validacao, e o texto fica gravado para o
--    reenvio mandar a mesma coisa e para provar o que a area recebeu.
ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS validada_em          TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS validada_por         VARCHAR(10) REFERENCES participantes(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS extrato_para_o_setor TEXT;

COMMENT ON COLUMN ouvidoria_protocolos.validada_em IS
  'T1: quando o ouvidor validou tipo, area e gravidade e acionou o setor.';
COMMENT ON COLUMN ouvidoria_protocolos.validada_por IS
  'Quem validou. NULL enquanto o caso nao passou pela validacao, ou se a pessoa saiu do quadro depois.';
COMMENT ON COLUMN ouvidoria_protocolos.extrato_para_o_setor IS
  'O texto que foi por email ao responsavel do setor, escrito pelo ouvidor na validacao. Em caso sigiloso ou anonimo e obrigatorio; nos demais cai no resumo. O email NUNCA le o resumo direto.';

-- 3. Fila de notificacoes (ADR 0034, decisao 7). Toda notificacao nasce aqui
--    ANTES de virar email: e o que prova a cobranca, e o que o ouvidor reenvia
--    e e o que sobra quando o Resend cai.
--
--    O catalogo de gatilhos desta fatia tem dois valores. O escalonamento
--    completo (vespera, prazo rompido, gestor, diretoria) e do PRD de
--    governanca de prazo (#318) e acrescenta os proprios valores ao CHECK.
CREATE TABLE IF NOT EXISTS ouvidoria_notificacoes (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  manifestacao_id    UUID NOT NULL REFERENCES ouvidoria_protocolos(id) ON DELETE RESTRICT,
  gatilho            TEXT NOT NULL CHECK (gatilho IN ('nova_demanda', 'alerta_sem_titular')),
  destinatario_nome  TEXT NOT NULL,
  destinatario_email TEXT NOT NULL CHECK (btrim(destinatario_email) <> ''),
  papel_destinatario TEXT,
  -- `enviando` e a linha em voo: o app reivindica a notificacao antes de
  -- chamar o provedor, para o job periodico nao pegar a mesma cobranca e
  -- mandar o email duas vezes.
  status             TEXT NOT NULL DEFAULT 'agendada'
                     CHECK (status IN ('agendada', 'enviando', 'enviada', 'falha')),
  tentativas         INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
  -- Janela comercial e backoff moram nesta coluna: notificacao nao critica
  -- gerada de madrugada nasce apontando para a proxima abertura, e falha de
  -- envio empurra a data para a proxima tentativa.
  enviar_a_partir_de TIMESTAMPTZ NOT NULL DEFAULT now(),
  enviada_em         TIMESTAMPTZ,
  ultimo_erro        TEXT,
  detalhe            TEXT,
  criada_em          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Quem aplicou a versao anterior desta migration ficou com o CHECK sem
-- `enviando`, e CHECK nao tem IF NOT EXISTS: derruba e recria.
ALTER TABLE ouvidoria_notificacoes
  DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_status_check;
ALTER TABLE ouvidoria_notificacoes
  ADD CONSTRAINT ouvidoria_notificacoes_status_check
  CHECK (status IN ('agendada', 'enviando', 'enviada', 'falha'));

-- O job periodico le exatamente por aqui: agendadas cuja hora ja chegou.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_notificacoes_fila
  ON ouvidoria_notificacoes(enviar_a_partir_de) WHERE status = 'agendada';
CREATE INDEX IF NOT EXISTS idx_ouvidoria_notificacoes_manifestacao
  ON ouvidoria_notificacoes(manifestacao_id, criada_em DESC);

COMMENT ON TABLE ouvidoria_notificacoes IS
  'Registro de toda notificacao da Ouvidoria (ADR 0034, decisao 7): data, destinatario e gatilho. Reenviavel manualmente pelo ouvidor.';
COMMENT ON COLUMN ouvidoria_notificacoes.enviar_a_partir_de IS
  'A partir de quando pode sair. Janela comercial (nao critico espera a abertura) e backoff de retentativa vivem aqui.';
COMMENT ON COLUMN ouvidoria_notificacoes.detalhe IS
  'Contexto curto que o email precisa e que nao esta na manifestacao (ex.: o nome do gestor a quem a demanda subiu).';

-- 4. RLS default-deny nas tabelas novas (padrao da casa: 009/041/051/063/064/065/066).
--    Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_setor_responsaveis ENABLE ROW LEVEL SECURITY;
ALTER TABLE ouvidoria_notificacoes ENABLE ROW LEVEL SECURITY;
