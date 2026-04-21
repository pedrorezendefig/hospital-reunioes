"""
Constantes de marca usadas em todos os templates de email.

O logo é embutido como data URI base64 no HTML do email para funcionar
sem depender de URL pública. Suportado por Gmail (web/mobile), Apple Mail,
Outlook 2019+ e outros clientes modernos.
"""
import base64
from functools import lru_cache
from pathlib import Path

_LOGO_PATH = Path(__file__).resolve().parents[1] / "static" / "images" / "logo_hospital_email.png"


@lru_cache(maxsize=1)
def get_logo_data_uri() -> str:
    """Lê o PNG do logo e retorna como data URI base64. Resultado cacheado."""
    encoded = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


BRAND_PRIMARY = "#2B2E7E"
BRAND_SECONDARY = "#2558A0"
BRAND_NAME = "Hospital São Matheus"
BRAND_TAGLINE = "Gestão de Atas e Decisões com IA"
