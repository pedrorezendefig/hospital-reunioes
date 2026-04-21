-- 023_enable_rls_audit_bulk.sql
-- Habilita RLS em tabelas auditáveis. Backend usa service_role (bypassa RLS),
-- então escritas continuam funcionando. Default-deny para anon/authenticated.

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE bulk_jobs ENABLE ROW LEVEL SECURITY;

-- Policy explícita: super-admin pode SELECT direto (futuro acesso sem service_role)
CREATE POLICY audit_log_super_admin_read ON audit_log
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM participantes p
      WHERE p.auth_user_id = auth.uid()
        AND p.is_super_admin = true
    )
  );

CREATE POLICY bulk_jobs_super_admin_read ON bulk_jobs
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM participantes p
      WHERE p.auth_user_id = auth.uid()
        AND p.is_super_admin = true
    )
  );
