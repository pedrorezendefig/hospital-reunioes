from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Aponta para hospital-reunioes/.env independente de onde o processo é iniciado
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Hospital Reuniões API"
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

    # LLM (OpenRouter primário, OpenAI direto como fallback)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-5.4-mini"
    openai_api_key: str = ""
    llm_fallback_model: str = "gpt-4o-mini"

    # Fireflies
    fireflies_api_key: str = ""
    fireflies_webhook_secret: str = ""

    # ClickSign
    clicksign_api_key: str = ""
    clicksign_base_url: str = "https://sandbox.clicksign.com"
    clicksign_webhook_secret: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    resend_from_email: str = "noreply@hospitalsaomatheus.com.br"

    # Email (SMTP legacy — mantido para fallback local)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # Geral
    diretor_email: str = ""
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    default_user_password: str = ""
    enable_bypass_endpoints: bool = False
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
    def validate_bypass_prod(self) -> "Settings":
        if self.environment == "production" and self.enable_bypass_endpoints:
            raise ValueError("ENABLE_BYPASS_ENDPOINTS nao pode ser true em producao")
        return self

    @model_validator(mode="after")
    def validate_debug_prod(self) -> "Settings":
        if self.environment == "production" and self.debug:
            import warnings

            warnings.warn("DEBUG=true em producao — CORS e API docs estao expostos", stacklevel=2)
        return self


settings = Settings()
