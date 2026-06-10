import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request

from app.config import settings
from app.dependencies import require_role
from app.limiter import limiter
from app.models.schemas import (
    EmailStatusResponse,
    IntegracaoStatus,
    TestResult,
)
from app.services.email_service import _enviar_email

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GET /admin/email/status
# ---------------------------------------------------------------------------


@router.get("/email/status", response_model=EmailStatusResponse)
async def get_email_status(
    current_user: dict = Depends(require_role("diretor")),
):
    resend_ok = bool(settings.resend_api_key)
    smtp_ok = bool(settings.smtp_user) and "your-email" not in settings.smtp_user

    if resend_ok:
        provedor = "resend"
        email_envio = settings.resend_from_email
    elif smtp_ok:
        provedor = "smtp"
        email_envio = settings.smtp_from_email or settings.smtp_user
    else:
        provedor = "mock"
        email_envio = "mock@localhost"

    return EmailStatusResponse(
        provedor_primario=provedor,
        email_envio=email_envio,
        resend_configurado=resend_ok,
        smtp_configurado=smtp_ok,
    )


# ---------------------------------------------------------------------------
# POST /admin/email/test
# ---------------------------------------------------------------------------


@router.post("/email/test", response_model=TestResult)
@limiter.limit("3/minute")
async def send_test_email(
    request: Request,
    current_user: dict = Depends(require_role("diretor")),
):
    destinatario = current_user.get("email")
    if not destinatario:
        raise HTTPException(status_code=400, detail="Email do usuário não encontrado")

    html = (
        "<h2>Email de Teste</h2>"
        "<p>Este é um email de teste enviado pelo painel administrativo "
        "do Hospital Reuniões.</p>"
        "<p>Se você recebeu este email, o serviço está funcionando corretamente.</p>"
    )
    texto = "Email de teste — Hospital Reuniões. Serviço de email funcionando."

    ok = _enviar_email(destinatario, "[Teste] Hospital Reuniões", html, texto)
    if ok:
        return TestResult(sucesso=True, mensagem=f"Email de teste enviado para {destinatario}")
    return TestResult(sucesso=False, mensagem="Falha ao enviar email de teste")


# ---------------------------------------------------------------------------
# GET /admin/integracoes
# ---------------------------------------------------------------------------


@router.get("/integracoes", response_model=list[IntegracaoStatus])
async def get_integracoes(
    current_user: dict = Depends(require_role("diretor")),
):
    return [
        IntegracaoStatus(
            nome="ClickSign",
            conectado=bool(settings.clicksign_api_key),
            ambiente="sandbox" if "sandbox" in settings.clicksign_base_url else "producao",
            descricao="Assinatura eletrônica",
        ),
        IntegracaoStatus(
            nome="OpenRouter",
            conectado=bool(settings.openrouter_api_key),
            ambiente=None,
            descricao="LLM de atas, correções, extração e transcrição",
        ),
        IntegracaoStatus(
            nome="Fireflies",
            conectado=bool(settings.fireflies_api_key),
            ambiente=None,
            descricao="Transcrição de reuniões",
        ),
    ]


# ---------------------------------------------------------------------------
# POST /admin/integracoes/{nome}/test
# ---------------------------------------------------------------------------


@router.post("/integracoes/{nome}/test", response_model=TestResult)
@limiter.limit("3/minute")
async def test_integracao(
    nome: str,
    request: Request,
    current_user: dict = Depends(require_role("diretor")),
):
    nome_lower = nome.lower()
    if nome_lower not in ("clicksign", "openrouter", "fireflies"):
        raise HTTPException(status_code=400, detail="Integração inválida. Use: clicksign, openrouter, fireflies")

    try:
        if nome_lower == "clicksign":
            return await _test_clicksign()
        elif nome_lower == "openrouter":
            return await _test_openrouter()
        else:
            return await _test_fireflies()
    except Exception as e:
        logger.error(f"Erro ao testar integração {nome}: {e}")
        return TestResult(sucesso=False, mensagem=str(e))


async def _test_clicksign() -> TestResult:
    if not settings.clicksign_api_key:
        return TestResult(sucesso=False, mensagem="API key não configurada")

    # Usa Authorization header (mesmo padrão do clicksign_service real) — evita
    # vazar API key em URL query param para logs HTTP/proxies.
    url = f"{settings.clicksign_base_url}/api/v1/documents?page=1&per_page=1"
    headers = {"Authorization": settings.clicksign_api_key}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code in (200, 201):
        return TestResult(sucesso=True, mensagem="ClickSign conectado com sucesso")
    return TestResult(sucesso=False, mensagem=f"ClickSign retornou status {resp.status_code}")


async def _test_openrouter() -> TestResult:
    if not settings.openrouter_api_key:
        return TestResult(sucesso=False, mensagem="API key não configurada")

    # GET /key é o endpoint autenticado leve do OpenRouter (devolve limites/uso
    # da chave) — valida a credencial sem gastar tokens de inferência.
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.openrouter_base_url}/key",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        )
    if resp.status_code == 200:
        return TestResult(sucesso=True, mensagem="OpenRouter conectado com sucesso")
    return TestResult(sucesso=False, mensagem=f"OpenRouter retornou status {resp.status_code}")


async def _test_fireflies() -> TestResult:
    if not settings.fireflies_api_key:
        return TestResult(sucesso=False, mensagem="API key não configurada")

    query = '{"query": "{ user { name email } }"}'
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.fireflies.ai/graphql",
            headers={
                "Authorization": f"Bearer {settings.fireflies_api_key}",
                "Content-Type": "application/json",
            },
            content=query,
        )
    if resp.status_code == 200:
        data = resp.json()
        if data.get("errors"):
            return TestResult(sucesso=False, mensagem=f"Fireflies erro: {data['errors'][0].get('message', '')}")
        return TestResult(sucesso=True, mensagem="Fireflies conectado com sucesso")
    return TestResult(sucesso=False, mensagem=f"Fireflies retornou status {resp.status_code}")
