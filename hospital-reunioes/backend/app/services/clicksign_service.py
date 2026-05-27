"""
ClickSign API v3 Service
Integração para envio de documentos e coleta de assinaturas digitais.
Documentação: https://developers.clicksign.com/
Auth: header Authorization: <access_token>
Formato: JSON:API (Content-type: application/vnd.api+json)
"""

import base64
import hashlib
import hmac
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_PATH = "/api/v3"


def _url(path: str) -> str:
    """Monta a URL v3."""
    base = settings.clicksign_base_url.rstrip("/")
    full_url = f"{base}{BASE_PATH}{path}"
    logger.debug(f"[ClickSign] URL gerada: {full_url}")
    return full_url


def _headers() -> dict:
    """Headers padrão para API v3: Authorization via header, não query param."""
    return {
        "Authorization": settings.clicksign_api_key,
        "Content-type": "application/vnd.api+json",
        "Accept": "application/json",
    }


def envelope_name(id_reuniao: str) -> str:
    """Nome deterministico do Envelope no ClickSign.

    Usado ao criar o Envelope (start_signature_flow) e ao recupera-lo no
    self-heal (find_envelope_id). Manter os dois pontos identicos e o que
    permite reencontrar o Envelope de Atas pre-039 pela busca por nome.
    """
    return f"Ata de Reunião - {id_reuniao}"


# ---------------------------------------------------------------------------
# 1. Criar Envelope
# ---------------------------------------------------------------------------
def create_envelope(name: str) -> str | None:
    """
    Passo 2 do fluxo: Cria um envelope no ClickSign.
    Retorna o envelope_id ou None em caso de falha.
    """
    payload = {
        "data": {
            "type": "envelopes",
            "attributes": {
                "name": name,
            },
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(_url("/envelopes"), json=payload, headers=_headers())
            logger.debug(f"[ClickSign v3] create_envelope status={resp.status_code} body={resp.text[:300]}")
            resp.raise_for_status()
            envelope_id = resp.json()["data"]["id"]
            logger.info(f"[ClickSign] Envelope criado: id={envelope_id}")
            return envelope_id
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao criar envelope: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao criar envelope: {e}")
        return None


# ---------------------------------------------------------------------------
# 2. Adicionar Documento ao Envelope
# ---------------------------------------------------------------------------
def add_document(envelope_id: str, pdf_bytes: bytes, filename: str) -> str | None:
    """
    Passo 3 do fluxo: Adiciona o PDF ao envelope.
    Retorna o document_id ou None em caso de falha.
    """
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    payload = {
        "data": {
            "type": "documents",
            "attributes": {
                "filename": filename,
                "content_base64": f"data:application/pdf;base64,{pdf_b64}",
            },
        }
    }
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/documents"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] add_document status={resp.status_code} body={resp.text[:200]}")
            resp.raise_for_status()
            document_id = resp.json()["data"]["id"]
            logger.info(f"[ClickSign] Documento adicionado: id={document_id} ao envelope {envelope_id}")
            return document_id
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao adicionar documento: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao adicionar documento: {e}")
        return None


# ---------------------------------------------------------------------------
# 3. Adicionar Signatário ao Envelope
# ---------------------------------------------------------------------------
def add_signer(envelope_id: str, nome: str, email: str) -> str | None:
    """
    Passo 4 do fluxo: Adiciona um signatário ao envelope.
    Retorna o signer_id ou None em caso de falha.
    """
    payload = {
        "data": {
            "type": "signers",
            "attributes": {
                "name": nome,
                "email": email,
            },
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/signers"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] add_signer {email} status={resp.status_code} body={resp.text[:300]}")
            resp.raise_for_status()
            signer_id = resp.json()["data"]["id"]
            logger.info(f"[ClickSign] Signatario adicionado: {email} -> id={signer_id}")
            return signer_id
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao adicionar signatário {email}: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao adicionar signatário {email}: {e}")
        return None


# ---------------------------------------------------------------------------
# 4. Criar Requisito de Qualificação (agree / sign)
# ---------------------------------------------------------------------------
def create_qualification_requirement(envelope_id: str, document_id: str, signer_id: str) -> str | None:
    """
    Passo 5 do fluxo: Requisito que define o PAPEL do signatário (assinar).
    Retorna o requirement_id ou None em caso de falha.
    """
    payload = {
        "data": {
            "type": "requirements",
            "attributes": {
                "action": "agree",
                "role": "sign",
            },
            "relationships": {
                "document": {"data": {"type": "documents", "id": document_id}},
                "signer": {"data": {"type": "signers", "id": signer_id}},
            },
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/requirements"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] create_qualification_requirement status={resp.status_code}")
            resp.raise_for_status()
            req_id = resp.json()["data"]["id"]
            logger.info(f"[ClickSign] Requisito de qualificacao criado: id={req_id}")
            return req_id
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao criar requisito de qualificação: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao criar requisito de qualificação: {e}")
        return None


# ---------------------------------------------------------------------------
# 5. Criar Requisito de Autenticação (provide_evidence / email)
# ---------------------------------------------------------------------------
def create_auth_requirement(envelope_id: str, document_id: str, signer_id: str) -> str | None:
    """
    Passo 6 do fluxo: Requisito que define o MÉTODO de autenticação (e-mail).
    Retorna o requirement_id ou None em caso de falha.
    """
    payload = {
        "data": {
            "type": "requirements",
            "attributes": {
                "action": "provide_evidence",
                "auth": "email",
            },
            "relationships": {
                "document": {"data": {"type": "documents", "id": document_id}},
                "signer": {"data": {"type": "signers", "id": signer_id}},
            },
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/requirements"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] create_auth_requirement status={resp.status_code}")
            resp.raise_for_status()
            req_id = resp.json()["data"]["id"]
            logger.info(f"[ClickSign] Requisito de autenticacao criado: id={req_id}")
            return req_id
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao criar requisito de autenticação: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao criar requisito de autenticação: {e}")
        return None


# ---------------------------------------------------------------------------
# 6. Ativar o Envelope (status → running)
# ---------------------------------------------------------------------------
def activate_envelope(envelope_id: str) -> bool:
    """
    Passo 7 do fluxo: Ativa o envelope para aceitar assinaturas.
    Altera o status para "running".
    """
    payload = {
        "data": {
            "id": envelope_id,
            "type": "envelopes",
            "attributes": {
                "status": "running",
            },
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.patch(
                _url(f"/envelopes/{envelope_id}"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] activate_envelope status={resp.status_code}")
            resp.raise_for_status()
            logger.info(f"[ClickSign] Envelope {envelope_id} ativado (status=running)")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao ativar envelope: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao ativar envelope: {e}")
        return False


# ---------------------------------------------------------------------------
# 7. Notificar todos os Signatários
# ---------------------------------------------------------------------------
def notify_signers(envelope_id: str) -> bool:
    """
    Passo 8 do fluxo: Dispara e-mails para TODOS os signatários do envelope
    de uma só vez (diferente da v1 que enviava um por um).
    """
    payload = {
        "data": {
            "type": "notifications",
            "attributes": {},
        }
    }
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/notifications"),
                json=payload,
                headers=_headers(),
            )
            logger.debug(f"[ClickSign v3] notify_signers status={resp.status_code}")
            resp.raise_for_status()
            logger.info(f"[ClickSign] Emails disparados para todos signatarios do envelope {envelope_id}")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao notificar signatários: {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao notificar signatários: {e}")
        return False


# ---------------------------------------------------------------------------
# 8. Baixar PDF assinado
# ---------------------------------------------------------------------------
def get_signed_document(envelope_id: str) -> bytes | None:
    """
    Baixa o PDF assinado do ClickSign consultando os documentos do envelope.
    Retorna os bytes do PDF ou None em caso de falha.
    """
    try:
        with httpx.Client(timeout=60) as client:
            # Busca os documentos do envelope para obter a URL de download
            resp = client.get(
                _url(f"/envelopes/{envelope_id}/documents"),
                headers=_headers(),
            )
            resp.raise_for_status()
            documents = resp.json().get("data", [])
            if not documents:
                logger.warning(f"[ClickSign v3] Nenhum documento encontrado no envelope {envelope_id}")
                return None

            # Pega o primeiro documento (nosso PDF da ata)
            doc = documents[0]
            download_url = doc.get("attributes", {}).get("download_url")
            if not download_url:
                logger.warning(f"[ClickSign v3] URL de download não disponível para envelope {envelope_id}")
                return None

            dl_resp = client.get(download_url, timeout=60)
            dl_resp.raise_for_status()
            logger.info(f"[ClickSign v3] PDF assinado baixado ({len(dl_resp.content)} bytes)")
            return dl_resp.content
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] Erro ao baixar PDF assinado: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] Erro inesperado ao baixar PDF: {e}")
        return None


# ---------------------------------------------------------------------------
# 8.5 Listar signatarios de um envelope (status + signed_at)
# ---------------------------------------------------------------------------
def list_envelope_events(envelope_id: str) -> list[dict] | None:
    """
    GET /api/v3/envelopes/{envelope_id}/events  (segue paginacao via links.next)

    Retorna a lista crua de eventos (data[] do JSON:API), ou None em erro
    irrecuperavel. Lista vazia [] = sucesso sem eventos.

    Na API v3 a assinatura CONCLUIDA aparece aqui como evento `name == "sign"`
    — o objeto signer (GET /signers) NAO carrega status de assinatura. Por isso
    os eventos sao a fonte da verdade de quem ja assinou (e quando, em `created`).
    """
    try:
        with httpx.Client(timeout=30) as client:
            events: list[dict] = []
            url: str | None = _url(f"/envelopes/{envelope_id}/events")
            pages = 0
            while url and pages < 50:  # guarda contra paginacao infinita
                resp = client.get(url, headers=_headers())
                if resp.status_code == 404:
                    logger.warning(f"[ClickSign v3] envelope {envelope_id} sem eventos (404)")
                    return None
                resp.raise_for_status()
                body = resp.json() or {}
                events.extend(body.get("data", []) or [])
                url = (body.get("links") or {}).get("next")
                pages += 1
            return events
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] list_envelope_events HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except httpx.TimeoutException:
        logger.error(f"[ClickSign v3] list_envelope_events timeout env={envelope_id}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] list_envelope_events excecao: {e}")
        return None


def _build_signed_map(events: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """A partir dos eventos do Envelope, mapeia quem ASSINOU.

    Retorna (por_signer_key, por_email_normalizado) -> signed_at (ISO de `created`).
    So conta o evento `sign` (assinatura concluida); ignora `signature_started`
    (apenas abriu o documento), `add_signer`, `upload` etc.
    """
    by_key: dict[str, str] = {}
    by_email: dict[str, str] = {}
    for ev in events:
        attrs = ev.get("attributes", {}) or {}
        if attrs.get("name") != "sign":
            continue
        signer = ((attrs.get("data") or {}).get("signer")) or {}
        signed_at = attrs.get("created")
        key = signer.get("key")
        email = (signer.get("email") or "").strip().lower()
        if key:
            by_key[key] = signed_at
        if email:
            by_email[email] = signed_at
    return by_key, by_email


def list_signers(envelope_id: str) -> list[dict] | None:
    """
    Lista os signatarios de um Envelope com o status REAL de assinatura.

    Combina duas fontes da API v3 (a v3 NAO expoe status no objeto signer):
      - GET /envelopes/{id}/signers -> identidade (id, nome, email), paginado.
      - GET /envelopes/{id}/events  -> evento `sign` marca quem concluiu a
        assinatura (e quando, em `created`).

    Correlaciona por signer.key (== id do signer) com fallback por email
    normalizado. Retorna [{signer_id, nome, email, status, signed_at}, ...].

    Retorna None em erro irrecuperavel (caller devolve 503) — inclusive se os
    eventos nao puderem ser lidos: sem eles nao da pra saber quem assinou, e
    afirmar "0 assinaram" silenciosamente seria pior que pedir nova tentativa.
    """
    try:
        with httpx.Client(timeout=30) as client:
            signers_raw: list[dict] = []
            url: str | None = _url(f"/envelopes/{envelope_id}/signers")
            pages = 0
            while url and pages < 50:  # guarda contra paginacao infinita
                resp = client.get(url, headers=_headers())
                if resp.status_code == 404:
                    logger.warning(f"[ClickSign v3] envelope {envelope_id} nao encontrado em list_signers")
                    return None
                resp.raise_for_status()
                body = resp.json() or {}
                signers_raw.extend(body.get("data", []) or [])
                url = (body.get("links") or {}).get("next")
                pages += 1
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] list_signers HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except httpx.TimeoutException:
        logger.error(f"[ClickSign v3] list_signers timeout env={envelope_id}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] list_signers excecao: {e}")
        return None

    # Fonte da verdade do status: eventos `sign` do Envelope (a v3 nao traz
    # signed_at no signer). Sem os eventos, nao da pra afirmar quem assinou.
    events = list_envelope_events(envelope_id)
    if events is None:
        logger.error(f"[ClickSign v3] list_signers: eventos indisponiveis env={envelope_id}")
        return None
    signed_by_key, signed_by_email = _build_signed_map(events)

    normalized: list[dict] = []
    for item in signers_raw:
        attrs = item.get("attributes", {}) or {}
        sid = item.get("id")
        email = attrs.get("email") or ""
        signed_at = signed_by_key.get(sid) or signed_by_email.get(email.strip().lower())
        normalized.append(
            {
                "signer_id": sid,
                "nome": attrs.get("name") or "",
                "email": email,
                "status": "signed" if signed_at else "pending",
                "signed_at": signed_at,
            }
        )
    assinaram = sum(1 for s in normalized if s["status"] == "signed")
    logger.info(f"[ClickSign v3] list_signers env={envelope_id} -> {len(normalized)} signers, {assinaram} assinaram")
    return normalized


# ---------------------------------------------------------------------------
# 8.6 Reenviar email de lembrete para um signatario individual
# ---------------------------------------------------------------------------
def remind_signer(envelope_id: str, signer_id: str, message: str | None = None) -> bool:
    """
    POST /api/v3/envelopes/{envelope_id}/signers/{signer_id}/notifications

    Reenvia o email de assinatura para o signer especifico. Aceita uma
    mensagem custom (PT-BR), que o ClickSign anexa ao corpo padrao do email
    (que ja inclui o link clicavel de assinatura).

    Retorna True em sucesso, False em qualquer erro (caller traduz pra HTTP).
    """
    payload: dict = {"data": {"type": "notifications", "attributes": {}}}
    if message:
        payload["data"]["attributes"]["message"] = message
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                _url(f"/envelopes/{envelope_id}/signers/{signer_id}/notifications"),
                json=payload,
                headers=_headers(),
            )
            if resp.status_code in (200, 201, 202, 204):
                logger.info(f"[ClickSign v3] lembrete enviado env={envelope_id} signer={signer_id}")
                return True
            logger.warning(
                f"[ClickSign v3] lembrete falhou env={envelope_id} signer={signer_id} "
                f"status={resp.status_code} body={resp.text[:200]}"
            )
            return False
    except httpx.TimeoutException:
        logger.error(f"[ClickSign v3] remind_signer timeout env={envelope_id} signer={signer_id}")
        return False
    except Exception as e:
        logger.error(f"[ClickSign v3] remind_signer excecao: {e}")
        return False


# ---------------------------------------------------------------------------
# 8.7 Localizar envelope_id na conta (self-heal de Atas pre-039)
# ---------------------------------------------------------------------------
def find_envelope_id(name: str, document_id: str) -> str | None:
    """Localiza o envelope_id na conta ClickSign pelo nome deterministico do
    Envelope, desambiguando pelo document_id (unico) — assim reenvios com o
    mesmo nome nao confundem. Esconde paginacao e o formato JSON:API.

    Retorna o envelope_id ou None se nao encontrar / em erro.
    """
    try:
        with httpx.Client(timeout=30) as client:
            url: str | None = _url("/envelopes")
            params: dict | None = {"filter[name]": name}
            pages = 0
            while url and pages < 50:  # guarda contra paginacao infinita
                resp = client.get(url, headers=_headers(), params=params)
                resp.raise_for_status()
                body = resp.json() or {}
                for env in body.get("data", []) or []:
                    if (env.get("attributes") or {}).get("name") != name:
                        continue  # filter[name] pode ser parcial; exigimos match exato
                    env_id = env.get("id")
                    if env_id and _envelope_contains_document(client, env_id, document_id):
                        logger.info(f"[ClickSign v3] find_envelope_id: env={env_id} casa doc={document_id}")
                        return env_id
                url = (body.get("links") or {}).get("next")
                params = None  # links.next ja embute a query string
                pages += 1
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[ClickSign v3] find_envelope_id HTTP {e.response.status_code}: {e.response.text[:200]}")
        return None
    except httpx.TimeoutException:
        logger.error(f"[ClickSign v3] find_envelope_id timeout name={name!r}")
        return None
    except Exception as e:
        logger.error(f"[ClickSign v3] find_envelope_id excecao: {e}")
        return None


def _envelope_contains_document(client: httpx.Client, envelope_id: str, document_id: str) -> bool:
    """True se o Envelope contem o documento com o id dado (GET .../documents).

    Em erro ao consultar os documentos deste candidato (ex: Envelope arquivado →
    404, ou timeout), devolve False para a busca seguir avaliando os demais
    candidatos do reenvio, em vez de abortar a recuperacao inteira.
    """
    try:
        resp = client.get(_url(f"/envelopes/{envelope_id}/documents"), headers=_headers())
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
        logger.warning(f"[ClickSign v3] candidato {envelope_id} inacessivel ({e}); ignorando")
        return False
    for doc in (resp.json() or {}).get("data", []) or []:
        if doc.get("id") == document_id:
            return True
    return False


# ---------------------------------------------------------------------------
# 9. Validação HMAC do webhook
# ---------------------------------------------------------------------------
def verify_webhook_hmac(payload_body: bytes, received_signature: str, secret: str) -> bool:
    """
    Valida a assinatura HMAC-SHA256 do webhook ClickSign.
    CRÍTICO: Deve ser chamado antes de processar qualquer callback.
    Em ambiente de desenvolvimento, se secret não estiver configurado,
    retorna True (permissivo).
    """
    if not secret:
        logger.error("[ClickSign] CLICKSIGN_WEBHOOK_SECRET não configurado — rejeitando webhook.")
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, received_signature)


# ---------------------------------------------------------------------------
# 10. Orquestrador: fluxo completo de assinatura (8 passos)
# ---------------------------------------------------------------------------
def start_signature_flow(supabase, id_reuniao: str, reuniao: dict) -> None:
    """
    Orquestra o fluxo completo de assinatura via ClickSign API v3:
      1. Baixa o PDF do Storage
      2. Cria o Envelope
      3. Adiciona o Documento ao Envelope
      4. Para cada participante:
         4a. Adiciona o Signatário
         4b. Cria Requisito de Qualificação (assinar)
         4c. Cria Requisito de Autenticação (e-mail)
      5. Ativa o Envelope (status → running)
      6. Notifica todos os Signatários (1 chamada)
      7. Salva o envelope_id no banco e atualiza status
    """
    from app.services import storage

    logger.info(f"[ClickSign] Iniciando fluxo de assinatura para reuniao {id_reuniao}")

    try:
        # 1. Baixar PDF do Storage
        pdf_bytes = storage.download_file(
            supabase,
            settings.supabase_storage_bucket_pdfs,
            f"{id_reuniao}/ata_preliminar.pdf",
        )
        if not pdf_bytes:
            logger.error(f"[ClickSign v3] PDF não encontrado no Storage para {id_reuniao}")
            return

        # 2. Criar Envelope
        env_name = envelope_name(id_reuniao)
        envelope_id = create_envelope(env_name)
        if not envelope_id:
            logger.error(f"[ClickSign v3] Falha ao criar envelope para {id_reuniao}")
            return

        # 3. Adicionar Documento ao Envelope
        filename = f"ata_{id_reuniao}.pdf"
        document_id = add_document(envelope_id, pdf_bytes, filename)
        if not document_id:
            logger.error(f"[ClickSign v3] Falha ao adicionar documento ao envelope {envelope_id}")
            return

        # 4. Buscar participantes e adicionar como signatários
        participantes_result = (
            supabase.table("reuniao_participantes")
            .select("participante_id, sequence_assinatura")
            .eq("id_reuniao", id_reuniao)
            .order("sequence_assinatura")
            .execute()
        )

        signatarios_adicionados = 0
        for rp in participantes_result.data or []:
            p_result = (
                supabase.table("participantes").select("nome_completo, email").eq("id", rp["participante_id"]).execute()
            )

            if not p_result.data:
                continue

            p = p_result.data[0]

            # 4a. Adicionar Signatário
            signer_id = add_signer(envelope_id, nome=p["nome_completo"], email=p["email"])
            if not signer_id:
                logger.warning(f"[ClickSign v3] Pulando signatário {p['email']} (falha na criação)")
                continue

            # 4b. Requisito de Qualificação (papel: assinar)
            qual_id = create_qualification_requirement(envelope_id, document_id, signer_id)
            if not qual_id:
                logger.warning(f"[ClickSign v3] Falha no requisito de qualificação para {p['email']}")
                continue

            # 4c. Requisito de Autenticação (método: e-mail)
            auth_id = create_auth_requirement(envelope_id, document_id, signer_id)
            if not auth_id:
                logger.warning(f"[ClickSign v3] Falha no requisito de autenticação para {p['email']}")
                continue

            signatarios_adicionados += 1

        if signatarios_adicionados == 0:
            logger.error(f"[ClickSign v3] Nenhum signatário adicionado ao envelope {envelope_id}. Abortando.")
            return

        logger.info(f"[ClickSign] {signatarios_adicionados} signatarios adicionados ao envelope {envelope_id}")

        # 5. Ativar o Envelope
        if not activate_envelope(envelope_id):
            logger.error(f"[ClickSign v3] Falha ao ativar envelope {envelope_id}")
            return

        # 6. Notificar todos os Signatários de uma vez
        notify_signers(envelope_id)

        # 7. Salvar os IDs no banco e atualizar status
        # envelope_key_clicksign = document_id (o que o webhook envia em document.key)
        # envelope_id_clicksign  = envelope_id (usado pelos endpoints /signatarios/status e /lembrar)
        supabase.table("reunioes").update(
            {
                "envelope_key_clicksign": document_id,  # webhook usa document.key
                "envelope_id_clicksign": envelope_id,  # endpoints v3 usam envelope_id
                "status_ata": "AGUARDANDO_ASSINATURA",
            }
        ).eq("id_reuniao", id_reuniao).execute()

        logger.info(
            f"[ClickSign] Fluxo concluido: envelope_id={envelope_id}, document_id={document_id}, "
            f"reuniao {id_reuniao} -> AGUARDANDO_ASSINATURA"
        )

    except Exception as e:
        logger.error(f"[ClickSign v3] Erro crítico no fluxo de assinatura para {id_reuniao}: {e}", exc_info=True)
