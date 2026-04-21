-- =====================================================
-- Migration 009: Habilitar RLS em todas as tabelas (default-deny)
-- Backend usa service_role (bypassa RLS automaticamente).
-- Sem policies = acesso via anon_key bloqueado por padrao.
-- =====================================================

ALTER TABLE participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reunioes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reuniao_participantes ENABLE ROW LEVEL SECURITY;
ALTER TABLE pendencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE tokens_validacao ENABLE ROW LEVEL SECURITY;
ALTER TABLE agendamentos_email ENABLE ROW LEVEL SECURITY;
ALTER TABLE signup_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE comentarios_pendencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE notificacoes ENABLE ROW LEVEL SECURITY;
