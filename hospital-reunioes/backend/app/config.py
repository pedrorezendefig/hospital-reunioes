from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Aponta para hospital-reunioes/.env independente de onde o processo é iniciado
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


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
    environment: str = "development"

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
