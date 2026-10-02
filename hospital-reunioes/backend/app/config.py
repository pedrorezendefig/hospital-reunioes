from pathlib import Path

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Aponta para hospital-reunioes/.env independente de onde o processo é iniciado
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Os ambientes que o app conhece. `ci` é o do workflow do GitHub Actions; os
# outros três são o que o contrato de deploy usa (docs/spec/deploy/project.json).
#
# A lista existe para o ambiente DESCONHECIDO ser recusado no boot. Sem ela, um
# `ENVIRONMENT=prodution` digitado errado no Coolify desliga em silêncio as duas
# validações abaixo (as duas só apertam quando o valor é exatamente
# "production"), e o app sobe com ClickSign sandbox e DEBUG ligado sem um único
# aviso (issue #450).
AMBIENTES_CONHECIDOS = frozenset({"development", "ci", "staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Hospital Reuniões API"
    # Em produção, sobrescrita por APP_VERSION (injetado pelo /deploy a partir de frontend/package.json).
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api"

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_storage_bucket_audios: str = "audios"
    supabase_storage_bucket_transcricoes: str = "transcricoes"
    supabase_storage_bucket_pdfs: str = "pdfs"
    supabase_storage_bucket_pdfs_assinados: str = "pdfs-assinados"
    supabase_storage_bucket_materiais_pops: str = "materiais-pops"
    supabase_storage_bucket_anexos_ouvidoria: str = "anexos-ouvidoria"

    # LLM (OpenRouter — provedor único; sem chave configurada, cai no mock)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-5.4-mini"
    # Transcrição de voz (issue #35): endpoint /audio/transcriptions do
    # OpenRouter, mesma chave/billing do Pipeline. Prefixo `openai/` segue a
    # convenção de `llm_model` (OpenRouter roteia o modelo por provedor).
    transcricao_model: str = "openai/gpt-4o-mini-transcribe"

    # Fireflies
    fireflies_api_key: str = ""
    fireflies_webhook_secret: str = ""

    # ClickSign
    clicksign_api_key: str = ""
    clicksign_base_url: str = "https://sandbox.clicksign.com"
    clicksign_webhook_secret: str = ""

    # API da Ana (ADR 0031): API key de serviço, única porta máquina-a-máquina.
    # Vazia = API da Ana desabilitada (toda requisição é recusada).
    ana_api_key: str = ""

    # Espelho da Global Health (ADR 0038): token da agenda online de
    # HOMOLOGAÇÃO, header `Token`. Vazio = Espelho desabilitado (a rota
    # responde erro de configuração, nunca lista vazia). A base fica fixa no
    # service, não em env var: apontar para outro ambiente exige commit.
    gh_token_homolog: str = ""

    # Integração com o GitHub (ADR 0054, decisão 8): token pessoal
    # fine-grained, só neste repositório, só Issues: write. Nunca `GITHUB_TOKEN`,
    # que é reservado das Actions.
    #
    # Vazio = integração desligada: a API responde 503 com frase de gente e a
    # tela desenha os controles do Vínculo desabilitados, em vez de deixar
    # alguém digitar um número de issue que ninguém vai ler.
    github_integracao_token: str = ""
    github_integracao_repo: str = ""

    # O segredo do webhook do GitHub (issue #678). Ele é o ÚNICO jeito de a rota
    # `/webhooks/github` saber que a entrega veio mesmo do GitHub: a porta é
    # pública e não tem login nenhum na frente.
    #
    # Vazio = webhook indisponível: a rota responde 503 e registra a causa no
    # log. Nunca um default, que seria um segredo público, e nunca "sem segredo
    # aceita tudo", que é a porta aberta com aparência de guarda.
    github_webhook_secret: str = ""

    # Central de Comando (ADR 0058): os números do Site e do Instagram, só para
    # Super admin. Todas as variáveis da Central moram aqui desde a primeira
    # fatia do PRD #809, para as fatias paralelas não disputarem este arquivo.
    #
    # A Central nasceu dormente, com tudo vazio, e está ligada em produção desde
    # a issue #827 (ADR 0058, decisão 8): as credenciais já estão no Coolify.
    # Vazio continua querendo dizer funcionalidade desligada com erro honesto
    # de configuração (503), nunca número zero nem lista vazia.
    #
    # Google Analytics 4: o número da propriedade e o JSON inteiro da chave da
    # service account (papel Leitor na propriedade). A base da API fica fixa no
    # provedor (`services/central_de_comando/provedor_google.py`), não aqui.
    ga4_property_id: str = ""
    google_application_credentials_json: str = ""
    # Os eventos que o Site dispara no clique para falar com o hospital
    # (Contatos gerados). Os padrões são os que o Site publica hoje.
    ga4_evento_whatsapp: str = "wa_click"
    ga4_evento_fale_conosco: str = "generate_lead"
    # Instagram: o token de longa duração e o id da conta profissional. O token
    # expira e é renovado à mão, como na Central antiga.
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    # Conector MCP (ADR 0058, decisões 3 e 4): o emissor do WorkOS AuthKit, o
    # JWKS dele (vazio = `<emissor>/oauth2/jwks`) e o endereço do recurso, que é
    # a audiência do token. Quem conecta é quem é Super admin: a lista de
    # e-mails em variável do app antigo não existe aqui.
    mcp_auth_issuer: str = ""
    mcp_auth_jwks_uri: str = ""
    mcp_resource_url: str = ""
    # Aquecimento do cache no boot (issue #867, ADR 0059): logo depois de subir,
    # o backend lê uma vez, numa thread, o período padrão de cada tela, para a
    # primeira abertura depois do deploy não esperar a fonte. Ausente = true.
    # Defina 'false' e reinicie para desligar sem deploy de código. A suíte de
    # testes roda com ele desligado (`tests/conftest.py`).
    central_aquecer_no_boot: bool = True

    # Email (Resend)
    resend_api_key: str = ""
    resend_from_email: str = "noreply@hospitalsaomatheus.cloud"

    # Email (SMTP legacy — mantido para fallback local)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # Ouvidoria: freio da retenção (issue #343). O job de anonimização apaga
    # dado em definitivo, sozinho, de madrugada. Com OUVIDORIA_RETENCAO_ATIVA=false
    # no ambiente, ele passa e não toca em nada: dá para parar o triturador com
    # uma variável e um restart, sem esperar deploy de código.
    ouvidoria_retencao_ativa: bool = True

    # Geral
    diretor_email: str = ""
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    default_user_password: str = ""
    # O default é o ambiente MAIS restrito de propósito. A variável sumir do
    # ambiente do container (remoção, renome, processo que não herda env) não
    # pode abrir defesa nenhuma, e o gatilho é o mesmo: o modo mock do email só
    # acontece quando alguém mexeu nas env vars do Coolify, e a mão que apaga
    # RESEND_API_KEY pode apagar esta (issue #450). Quem roda local declara
    # ENVIRONMENT=development no .env, como os dois .env.example mostram.
    environment: str = "production"

    @field_validator("ga4_evento_whatsapp", "ga4_evento_fale_conosco", mode="before")
    @classmethod
    def evento_de_contato_vazio_vale_o_padrao(cls, valor: object, info: ValidationInfo) -> object:
        """A linha vazia do `.env.example`, copiada para o `.env`, vale o padrão.

        Um nome de evento vazio não é "sem evento": é um filtro que não casa com
        nada, e o canal apareceria sem clique nenhum, em silêncio.
        """
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return cls.model_fields[info.field_name].default
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.environment not in AMBIENTES_CONHECIDOS:
            raise ValueError(
                f"ENVIRONMENT={self.environment!r} não é um ambiente conhecido. "
                f"Use um de: {', '.join(sorted(AMBIENTES_CONHECIDOS))}."
            )
        return self

    @model_validator(mode="after")
    def validate_clicksign_prod(self) -> "Settings":
        if self.environment == "production" and "sandbox" in self.clicksign_base_url:
            raise ValueError(
                "clicksign_base_url não pode apontar para sandbox em produção. "
                "Configure CLICKSIGN_BASE_URL=https://app.clicksign.com no ambiente de produção."
            )
        return self

    @model_validator(mode="after")
    def validate_debug_prod(self) -> "Settings":
        if self.environment == "production" and self.debug:
            raise ValueError("DEBUG=true em producao expoe CORS e /docs. Defina DEBUG=false no ambiente de producao.")
        return self


settings = Settings()
