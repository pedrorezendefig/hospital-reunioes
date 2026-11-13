-- =====================================================
-- Migration 141: o Codigo de acompanhamento do anonimo
-- (issue #1623, PRD #1527, ADR 0086 decisao 7)
-- =====================================================
-- Quem se manifesta de forma anonima recebe, junto com o protocolo, um codigo
-- mostrado uma vez so, para acompanhar o caso na pagina publica /acompanhar.
-- O banco guarda so o hash, com sal e derivacao lenta (pbkdf2_sha256), no
-- formato `pbkdf2_sha256$<iteracoes>$<sal>$<hash>`. O codigo em claro nao
-- existe em lugar nenhum depois da resposta do envio.
--
-- Nulavel: o caso identificado entra pelo contato e nao tem codigo, e o
-- anonimo de antes desta migration nao ganha codigo retroativo (nao ha como
-- mostra-lo a quem manifestou).
--
-- RETENCAO: o hash sai com o Dossie, pelo cron dos cinco anos e pela porta
-- antecipada da diretoria executiva (`CAMPOS_DO_DOSSIE` em
-- app/services/ouvidoria_retencao.py), como o contato do identificado.
--
-- Sem tabela nova e sem policy: a linha do caso segue com a RLS que nega por
-- padrao, e o backend le e escreve com a service role.
--
-- Aplicar a mao no Studio: o deploy nao aplica SQL. Rodar duas vezes e
-- inofensivo.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS codigo_acompanhamento_hash TEXT;

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ck_ouvidoria_protocolos_codigo_acompanhamento_hash;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ck_ouvidoria_protocolos_codigo_acompanhamento_hash
  CHECK (codigo_acompanhamento_hash IS NULL OR codigo_acompanhamento_hash LIKE 'pbkdf2_sha256$%');

COMMENT ON COLUMN ouvidoria_protocolos.codigo_acompanhamento_hash IS
  'Hash (pbkdf2_sha256 com sal) do Codigo de acompanhamento do caso anonimo (ADR 0086, decisao 7). O codigo e mostrado uma vez, na confirmacao do envio, e nunca e guardado em claro. Nulo no caso identificado, que entra na pagina de acompanhamento pelo contato.';


-- recibo: a subida espera este número no /api/health (issue #969)
INSERT INTO migracoes_aplicadas (numero) VALUES (141) ON CONFLICT (numero) DO NOTHING;
