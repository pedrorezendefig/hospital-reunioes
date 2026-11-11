-- =====================================================
-- Migration 130: as colunas da ADR 0084 (issue #1549, PRD #1548)
-- =====================================================
-- A unica migration do PRD #1548. Todas as colunas que as fatias do PRD usam
-- entram aqui, para nenhuma delas pedir outra parada no Studio. Nenhuma tabela
-- nova: as duas ja existem com RLS ligado e sem policy (102 e 123), e o
-- backend escreve com a service_role.
--
-- Em `tecnologia_demandas`:
--
--   1. `origem`: quem abriu o card. `diretor` (o chat da aba, padrao: toda
--      Demanda que ja existe nasceu assim) ou `vitta` (a issue-raiz do app
--      aberta pelo terminal, ADR 0084, decisao 4);
--   2. `apagada_em` e `apagada_por`: a lapide do Apagar (decisao 2). A linha
--      fica, para o webhook reconhecer a issue fechada e nao recriar a
--      Demanda; a conversa, o planejamento e a Conversa da Demanda saem, e os
--      anexos saem do bucket. Toda leitura filtra `apagada_em IS NULL`;
--   3. `em_producao_em`: a data em que o card entrou Em producao, ao lado da
--      versao que ja existe (decisao 8);
--   4. `demonstracao_url` e `demonstracao_em`: o link do video da Vercel, lido
--      do marcador da issue-raiz, e quando ele chegou (decisao 9). So https.
--
-- Em `tecnologia_planejamentos`:
--
--   5. `documento`: o rascunho estruturado do documento do card, montado a
--      cada turno ao lado do chat (decisao 7);
--   6. `revisao_iniciada_em`, `revisao_por` e `revisao_versao_base`: a marca
--      da Revisao com o codigo de hoje (decisao 3);
--   7. quem respondeu cada turno: os turnos moram no JSONB `mensagens`, e o
--      campo `respondido_por` entra em cada fala. JSONB nao pede coluna: o que
--      muda e o comentario da coluna, que passa a dizer o contrato.
--
-- Sem indice novo: a tabela tem dezenas de linhas e o filtro da lapide le o
-- que a lista ja le. As FKs de quem apagou e de quem revisou seguem o molde de
-- `concluida_por` (102): ON DELETE SET NULL, sem indice.
--
-- Tudo com IF NOT EXISTS / DROP IF EXISTS / ON CONFLICT: rodar duas vezes e
-- inofensivo. Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. A Demanda ----------
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'diretor';
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS apagada_em TIMESTAMPTZ;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS apagada_por VARCHAR(10)
  REFERENCES participantes(id) ON DELETE SET NULL;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS em_producao_em TIMESTAMPTZ;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS demonstracao_url TEXT;
ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS demonstracao_em TIMESTAMPTZ;

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_origem_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_origem_check
  CHECK (origem IN ('diretor', 'vitta'));

ALTER TABLE tecnologia_demandas DROP CONSTRAINT IF EXISTS tecnologia_demandas_demonstracao_url_check;
ALTER TABLE tecnologia_demandas
  ADD CONSTRAINT tecnologia_demandas_demonstracao_url_check
  CHECK (demonstracao_url IS NULL OR demonstracao_url LIKE 'https://%');

COMMENT ON COLUMN tecnologia_demandas.origem IS
  'Quem abriu o card (ADR 0084, decisao 4): diretor (o chat da aba) ou vitta (a issue-raiz do app aberta pelo terminal, sem conversa com o agente).';
COMMENT ON COLUMN tecnologia_demandas.apagada_em IS
  'A lapide do Apagar (ADR 0084, decisao 2): a Demanda saiu do app. A linha fica para o webhook reconhecer a issue; toda leitura filtra apagada_em IS NULL. A issue no GitHub fecha como nao planejada e nunca e apagada.';
COMMENT ON COLUMN tecnologia_demandas.apagada_por IS
  'Quem apagou: o autor, na conversa Registrada, ou o Desenvolvedor, no card Em analise ou Planejada.';
COMMENT ON COLUMN tecnologia_demandas.em_producao_em IS
  'A data em que o card entrou Em producao, ao lado de versao_em_producao (ADR 0084, decisao 8).';
COMMENT ON COLUMN tecnologia_demandas.demonstracao_url IS
  'O link do video de demonstracao, lido do marcador <!-- demonstracao: <url> --> da issue-raiz (ADR 0084, decisao 9). So https.';
COMMENT ON COLUMN tecnologia_demandas.demonstracao_em IS
  'Quando o link da demonstracao chegou ou mudou.';

-- ---------- 2. O planejamento ----------
ALTER TABLE tecnologia_planejamentos ADD COLUMN IF NOT EXISTS documento JSONB;
ALTER TABLE tecnologia_planejamentos ADD COLUMN IF NOT EXISTS revisao_iniciada_em TIMESTAMPTZ;
ALTER TABLE tecnologia_planejamentos ADD COLUMN IF NOT EXISTS revisao_por VARCHAR(10)
  REFERENCES participantes(id) ON DELETE SET NULL;
ALTER TABLE tecnologia_planejamentos ADD COLUMN IF NOT EXISTS revisao_versao_base TEXT;

ALTER TABLE tecnologia_planejamentos DROP CONSTRAINT IF EXISTS tecnologia_planejamentos_documento_check;
ALTER TABLE tecnologia_planejamentos
  ADD CONSTRAINT tecnologia_planejamentos_documento_check
  CHECK (documento IS NULL OR jsonb_typeof(documento) = 'object');

COMMENT ON COLUMN tecnologia_planejamentos.documento IS
  'O rascunho do documento do card (ADR 0084, decisao 7): a frase e os topicos que o agente devolve a cada turno, mostrados ao lado do chat. Nulo = ainda sem rascunho.';
COMMENT ON COLUMN tecnologia_planejamentos.revisao_iniciada_em IS
  'Quando a Revisao com o codigo de hoje comecou (ADR 0084, decisao 3). Nulo = o planejamento nunca foi revisado.';
COMMENT ON COLUMN tecnologia_planejamentos.revisao_por IS
  'Quem clicou em Revisar: o autor ou o Desenvolvedor.';
COMMENT ON COLUMN tecnologia_planejamentos.revisao_versao_base IS
  'A versao do app sobre a qual a revisao leu o que ja existe (ex.: v0.244.0).';

-- ---------- 3. Quem respondeu cada turno ----------
COMMENT ON COLUMN tecnologia_planejamentos.mensagens IS
  'A conversa, na ordem. No chat da aba: as falas da IA e do diretor; a fala do diretor que trouxe documento leva o campo documentos, uma lista de {nome, tamanho_bytes, texto}, com o texto extraido inteiro (ate 100 mil caracteres), fora do teto de 5.000 da mensagem e fora da tela. O texto fica depois que o binario sai do bucket. No planejamento: perguntas da IA (contexto, opcoes A e B, recomendada), respostas do diretor (opcao, texto livre ou documentos) e o encerrou. Desde a ADR 0084 (decisao 3) cada resposta de gente leva o campo respondido_por, o id em participantes de quem respondeu o turno (o autor ou o Desenvolvedor); fala sem o campo e de antes da revisao e foi do autor.';

INSERT INTO migracoes_aplicadas (numero) VALUES (130) ON CONFLICT (numero) DO NOTHING;
