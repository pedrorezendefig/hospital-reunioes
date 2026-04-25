-- Drop signup_requests table — auto-cadastro publico via codigo passe foi removido.
-- Contas agora sao criadas exclusivamente pelo super admin via /admin/usuarios +
-- /admin/usuarios/{id}/reset-password (provisiona auth.users e dispara email de
-- definicao de senha). Migrations 005 (create) e os routers signup.py e
-- admin/signup_requests.py foram removidos do backend, e o frontend nao tem mais
-- /signup nem /admin/solicitacoes.

DROP TABLE IF EXISTS signup_requests;
