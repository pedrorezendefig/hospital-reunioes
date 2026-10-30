-- =====================================================
-- Migration 120: Storage, leitura so pelos fluxos do backend
-- (issue #1285, PRD #1282)
-- =====================================================
-- O backend le e grava todos os buckets com a service_role e entrega arquivo
-- ao navegador por URL assinada, depois de conferir o acesso. Nenhuma policy de
-- `storage.objects` precisa liberar SELECT para `authenticated`; as 066, 115 e
-- 116 ja nasceram sem ela. Saem as duas que sobraram:
--   - "Authenticated Access" (006): audios, transcricoes, pdfs, pdfs-assinados
--   - "Authenticated Access materiais-pops" (049)
-- A "Service Role Management" (006) fica. Nada e criado no lugar.
--
-- Idempotente: DROP POLICY IF EXISTS roda de novo sem erro.

DROP POLICY IF EXISTS "Authenticated Access" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated Access materiais-pops" ON storage.objects;

INSERT INTO migracoes_aplicadas (numero) VALUES (120) ON CONFLICT (numero) DO NOTHING;
