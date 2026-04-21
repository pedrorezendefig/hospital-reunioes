-- Tabela de preferências do usuário (notificações e emails)
CREATE TABLE IF NOT EXISTS user_preferences (
    participante_id VARCHAR(10) PRIMARY KEY REFERENCES participantes(id) ON DELETE CASCADE,
    notificacoes JSONB NOT NULL DEFAULT '{
        "mencao": true,
        "prazo_proximo": true,
        "comentario": true,
        "responsavel_atribuido": true
    }'::jsonb,
    emails JSONB NOT NULL DEFAULT '{
        "validacao_ata": true,
        "lembrete_prazo": true,
        "resumo_semanal": false
    }'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Cada usuário lê/atualiza suas próprias preferências
CREATE POLICY "user_preferences_select_own" ON user_preferences
    FOR SELECT USING (
        participante_id IN (
            SELECT id FROM participantes WHERE auth_user_id = auth.uid()
        )
    );

CREATE POLICY "user_preferences_update_own" ON user_preferences
    FOR UPDATE USING (
        participante_id IN (
            SELECT id FROM participantes WHERE auth_user_id = auth.uid()
        )
    );

-- Diretor pode ler todas
CREATE POLICY "user_preferences_select_diretor" ON user_preferences
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM participantes
            WHERE auth_user_id = auth.uid() AND role = 'diretor'
        )
    );

-- Insert: service role ou o próprio usuário
CREATE POLICY "user_preferences_insert_own" ON user_preferences
    FOR INSERT WITH CHECK (
        participante_id IN (
            SELECT id FROM participantes WHERE auth_user_id = auth.uid()
        )
    );
