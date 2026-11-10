-- =====================================================
-- Migration 127: o documento no chat da Tecnologia
-- (issue #1520, PRD #1519, ADR 0069, emenda de 09/11/2026)
-- =====================================================
-- O Anexo da Demanda deixa de ser so print: o diretor anexa tambem documento
-- (.md, .txt, .pdf, .docx) pelo mesmo botao do chat, e o original vira Anexo
-- quando a fala entra na conversa. Nenhuma tabela nova. Tres coisas mudam:
--
--   1. o CHECK de `content_type` de `tecnologia_anexos` aceita os tipos de
--      documento. Ja entram tambem os da planilha (.csv e .xlsx), que a fatia
--      seguinte (#1521) passa a aceitar no codigo: assim ela nao pede outra
--      parada no Studio. Ate la, quem decide o que entra e a tabela do codigo
--      (`assistente_tecnologia.TIPOS_DE_ANEXO`);
--   2. o CHECK de `tamanho_bytes` vai a 15 MB, o teto do .pdf e do .docx no
--      extrator. A imagem continua em 3,75 MB, decidido no codigo;
--   3. o campo do texto extraido. A fala do chat mora no JSONB `mensagens` de
--      `tecnologia_planejamentos` (ADR 0077, decisao 2), e o texto do
--      documento entra nela em campo proprio, `documentos`, fora do teto de
--      5.000 caracteres da mensagem. JSONB nao pede coluna: o que muda aqui e
--      o comentario da coluna, que passa a dizer o contrato.
--
-- Os dois CHECKs foram criados na migration 115 junto da coluna, sem nome, e o
-- Postgres os batizou `tecnologia_anexos_<coluna>_check`. Aqui eles saem pelo
-- nome e voltam com o mesmo nome: rodar duas vezes e inofensivo. As linhas que
-- ja existem (so imagens, ate 5 MB) passam pelos CHECKs novos.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL.
-- =====================================================

-- ---------- 1. Os tipos do Anexo ----------
ALTER TABLE tecnologia_anexos DROP CONSTRAINT IF EXISTS tecnologia_anexos_content_type_check;
ALTER TABLE tecnologia_anexos
  ADD CONSTRAINT tecnologia_anexos_content_type_check
  CHECK (content_type IN (
    'image/png',
    'image/jpeg',
    'image/webp',
    'text/markdown',
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ));

-- ---------- 2. O teto do tamanho ----------
ALTER TABLE tecnologia_anexos DROP CONSTRAINT IF EXISTS tecnologia_anexos_tamanho_bytes_check;
ALTER TABLE tecnologia_anexos
  ADD CONSTRAINT tecnologia_anexos_tamanho_bytes_check
  CHECK (tamanho_bytes > 0 AND tamanho_bytes <= 15728640);

COMMENT ON TABLE tecnologia_anexos IS
  'Anexo da Demanda (ADR 0069, emenda de 09/11/2026): print de tela ou documento guardado junto da Demanda, ate dez somando os dois. Metadados aqui, binario no bucket privado anexos-tecnologia. Nunca vai para o GitHub.';

-- ---------- 3. O texto extraido, na fala ----------
COMMENT ON COLUMN tecnologia_planejamentos.mensagens IS
  'A conversa, na ordem. No chat da aba: as falas da IA e do diretor; a fala do diretor que trouxe documento leva o campo documentos, uma lista de {nome, tamanho_bytes, texto}, com o texto extraido inteiro (ate 100 mil caracteres), fora do teto de 5.000 da mensagem e fora da tela. O texto fica depois que o binario sai do bucket. No planejamento: perguntas da IA (contexto, opcoes A e B, recomendada), respostas do diretor (opcao, texto livre ou documentos) e o encerrou.';

INSERT INTO migracoes_aplicadas (numero) VALUES (127) ON CONFLICT (numero) DO NOTHING;
