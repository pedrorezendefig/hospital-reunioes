import base64
import logging
import mimetypes
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

import httpx
import resend
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
# autoescape: variáveis renderizadas nos emails são texto puro vindo de input
# de usuário (ex.: nome do POP) — mesmo padrão do reuniao_email_service.
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# Quanto tempo o app espera o provedor de email, em segundos (issue #642).
#
# Sem teto, um provedor lento pendura a chamada para SEMPRE. Isso não é
# hipótese: o `smtplib.SMTP(host, port)` sem `timeout` herda o default global do
# socket, que é "espere indefinidamente", e o uvicorn deste app sobe com um
# worker só (`Dockerfile`). Uma chamada pendurada que não vá para thread trava o
# processo inteiro, e com ele a Ouvidoria, as Atas, as Reuniões e o portal
# público.
#
# 20 segundos é folgado para um POST de email e curto o bastante para não virar
# indisponibilidade: quem estourar isso já não ia entregar a tempo de nada.
TIMEOUT_DO_TRANSPORTE = 20


def _com_timeout_no_resend() -> None:
    """Põe o teto de tempo no cliente HTTP do SDK do Resend.

    O `resend` monta a requisição num cliente próprio (`resend.default_http_client`),
    e é ELE quem tem o `timeout`. As versões novas já trazem 30 segundos por
    padrão; as antigas, não. Como o `pyproject.toml` pede `resend>=2.0.0`, o que
    o CI instala não é o que a `uv.lock` fixa (foi o que mordeu nas issues #542 e
    #546), então o teto é escrito aqui e não deixado por conta da versão.

    Falhar aqui não pode derrubar a subida do app: SDK sem esta peça continua
    mandando email, só que sem o nosso teto, e o log diz isso.
    """
    try:
        from resend.http_client_requests import RequestsClient

        resend.default_http_client = RequestsClient(timeout=TIMEOUT_DO_TRANSPORTE)
    except Exception:  # noqa: BLE001 (timeout é guarda-corpo, não requisito de boot)
        logger.warning(
            "SDK do Resend sem cliente HTTP configurável: o envio fica sem o teto de %ss desta aplicação.",
            TIMEOUT_DO_TRANSPORTE,
        )


_com_timeout_no_resend()


def _resend_configurado() -> bool:
    return bool(settings.resend_api_key)


def _smtp_configurado() -> bool:
    return bool(settings.smtp_user) and "your-email" not in settings.smtp_user


def transporte_configurado() -> bool:
    """Existe transporte REAL de email nesta máquina (Resend ou SMTP)?

    `False` é o modo mock do desenvolvimento, e o detalhe que importa é o
    retorno de `_enviar_email` nele: `True`, sem nada ter saído. Quem lê esse
    `True` como entrega e PERSISTE estado a partir dele carimba "entregue" em
    cima de um email que ninguém recebeu.

    Em produção isso não é hipótese de laboratório: basta a chave do Resend ser
    rotacionada para vazio e todo envio do app vira sucesso silencioso (issue
    #435). O relatório da Ouvidoria pergunta aqui antes de carimbar; quem só
    loga o resultado não precisa.

    O processador externo em si (Resend, fora do Brasil) está registrado no
    ADR 0039."""
    return _resend_configurado() or _smtp_configurado()


# Anexo: (nome do arquivo, bytes). O tipo sai do nome, como no resto do mundo
# do email. Chega até aqui porque o relatório da Ouvidoria viaja em PDF
# (issue #345); antes dela, nenhum email do app levava arquivo.
Anexo = tuple[str, bytes]


def _tipo_do_anexo(nome: str) -> tuple[str, str]:
    tipo, _ = mimetypes.guess_type(nome)
    principal, _, secundario = (tipo or "application/octet-stream").partition("/")
    return principal, secundario or "octet-stream"


# O que entra no lugar do endereço de gente de fora, no log e no corpo do alerta
# ao admin técnico (issue #572). Uma constante só: os dois lugares dizem que
# omitiram, e dizem do mesmo jeito.
ENDERECO_OMITIDO = "(endereco omitido)"


def _alvo_no_log(destinatario: str, endereco_fora_do_log: bool) -> str:
    """Como o destinatário aparece no log da aplicação.

    Endereço de gente de fora do hospital não entra (issue #493). O log corre
    em INFO em produção, e ali o endereço sai lado a lado com o assunto, que
    carrega o protocolo: quem tem acesso ao log do Coolify e nenhum perfil no
    módulo passaria a saber QUEM abriu cada caso da Ouvidoria, inclusive os que
    nascem com sigilo reforçado. O residual que a issue #450 aceitou valia para
    destinatário INTERNO (ADR 0039, decisão 5); o ADR 0042 abriu a porta para o
    manifestante, e para ele o residual não vale.

    O rastro de "o email deste caso saiu?" continua existindo em dois lugares
    melhores: o assunto, que fica, e a linha em `ouvidoria_notificacoes`, que
    guarda o destinatário atrás do gate de acesso do Dossiê."""
    return ENDERECO_OMITIDO if endereco_fora_do_log else destinatario


def _assunto_no_log(assunto: str, assunto_para_o_log: str | None) -> str:
    """Como o assunto aparece no log da aplicação.

    Irmão do `_alvo_no_log`, e pelo mesmo motivo (issue #642): o log corre em
    INFO em produção, e o assunto sai lado a lado com o destinatário. Quando o
    assunto carrega texto que uma PESSOA digitou num campo livre, quem tem
    acesso ao log do Coolify e nenhum perfil no módulo passa a ler esse texto.

    Quem chama decide: sem `assunto_para_o_log`, vale o assunto de verdade, que
    é o que sempre valeu (os construtores da Ouvidoria montam o assunto em
    código, e o residual deles está na decisão 7 do ADR 0039). Com ele, o log
    fica com a versão neutra e quem recebe continua vendo o assunto útil.

    Truncar não serviria: o começo de "Prontuário da paciente Maria não abre" já
    é o que não pode ficar escrito. O que resolve é o assunto do log não conter
    campo livre nenhum."""
    return assunto_para_o_log or assunto


def _falha_no_log(erro: Exception, endereco_fora_do_log: bool) -> str:
    """Como a falha de envio aparece no log.

    O caminho de ERRO é o que mais vaza, e é o mais fácil de esquecer: a
    exceção formatada do provedor CARREGA o endereço que a mensagem tentou
    alcançar. `SMTPRecipientsRefused.__str__` é literalmente o dicionário dos
    destinatários recusados, e o erro do Resend ecoa o `to` do payload. Pior
    que o log de sucesso em três pontos: sai em ERROR, então sobrevive a
    qualquer subida de nível; dispara com contato digitado errado, que é rotina
    no formulário público, e não só em ataque; e não tem nada a ver com o
    conteúdo do email, então quem blindou o sucesso acha que terminou.

    Fora do caminho do manifestante nada muda: a mensagem do provedor é o que
    diz por que o email do setor não saiu, e o app inteiro depende dela."""
    return type(erro).__name__ if endereco_fora_do_log else str(erro)


def _enviar_via_resend(
    destinatario: str,
    assunto: str,
    html_content: str,
    texto_fallback: str,
    anexos: list[Anexo] | None = None,
    endereco_fora_do_log: bool = False,
    assunto_no_log: str | None = None,
) -> bool:
    resend.api_key = settings.resend_api_key
    payload = {
        "from": settings.resend_from_email,
        "to": [destinatario],
        "subject": assunto,
        "html": html_content,
        "text": texto_fallback,
    }
    if anexos:
        # `content` em base64: é a forma que a API documenta, e cabe na
        # requisição sem virar uma lista de milhares de inteiros.
        payload["attachments"] = [
            {
                "filename": nome,
                "content": base64.b64encode(conteudo).decode("ascii"),
                "content_type": "/".join(_tipo_do_anexo(nome)),
            }
            for nome, conteudo in anexos
        ]
    try:
        resend.Emails.send(payload)
        logger.info(
            f"Email enviado via Resend para {_alvo_no_log(destinatario, endereco_fora_do_log)} "
            f"| Assunto: {_assunto_no_log(assunto, assunto_no_log)}"
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email via Resend: {_falha_no_log(e, endereco_fora_do_log)}")
        return False


# ─── Leitura do e-mail RECEBIDO (Triagem de e-mail, ADR 0051) ────────────────
#
# O webhook do Resend traz só os metadados do e-mail que chegou em ouvidoria@.
# Corpo, cabeçalhos e anexos são buscados pela API, NO ATO: o Resend guarda o
# e-mail por 30 dias e depois apaga (ADR 0051, decisão 6).
#
# A leitura mora aqui, ao lado do envio, e atrás de UMA função só
# (`ler_email_recebido`): é ela que os testes dublam, e é por ela que qualquer
# troca de provedor passaria. Ela fala direto com a API pelo httpx, e não pelo
# SDK: o `pyproject.toml` pede `resend>=2.0.0`, e as versões antigas do SDK não
# conhecem a API de recebimento.

# Os cabeçalhos que ajudam a ler o e-mail na triagem: quem responde a quem, se
# é resposta automática, se é lista de distribuição. O resto (a cadeia de
# `Received`, DKIM, ARC) é ruído de transporte e não é guardado.
CABECALHOS_RELEVANTES = (
    "message-id",
    "in-reply-to",
    "references",
    "reply-to",
    "cc",
    "date",
    "auto-submitted",
    "precedence",
    "list-id",
    "list-unsubscribe",
    "x-autoreply",
    "x-auto-response-suppress",
)


class LeituraDoResendError(Exception):
    """O e-mail recebido não pôde ser lido na API do Resend.

    A mensagem é o tipo da falha, nunca o corpo da resposta: o que o Resend
    devolve pode carregar remetente e assunto, e isto vai para o log."""


class AnexoAcimaDoTetoError(Exception):
    """O binário do anexo passou do teto de quem baixa. O download para no
    pedaço que passou: o resto nem chega à memória."""


@dataclass(frozen=True)
class AnexoDoResend:
    """Um anexo do e-mail recebido, só os metadados, sem o binário.

    O binário não vem junto de propósito (revisão de segurança do PR #899): o
    remetente é anônimo, e baixar tudo de uma vez seguraria na memória do
    worker o que quer que ele tenha mandado. Quem guarda baixa um por vez, com
    teto, por `baixar_anexo_recebido`. `tamanho` é o que o Resend declara (None
    quando não declara) e `download_url` é o link assinado (None quando a lista
    de anexos não veio)."""

    id: str
    filename: str
    content_type: str
    tamanho: int | None = None
    download_url: str | None = None


@dataclass(frozen=True)
class EmailDoResend:
    """O que a API devolve do e-mail recebido: corpo em texto e em HTML, os
    cabeçalhos relevantes e os metadados dos anexos (sem binário)."""

    texto: str | None
    html: str | None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    anexos: tuple[AnexoDoResend, ...] = ()


def _cabecalhos_relevantes(dados: dict) -> dict[str, str]:
    brutos = dados.get("headers") or {}
    cabecalhos = {}
    if isinstance(brutos, dict):
        for nome, valor in brutos.items():
            chave = str(nome).strip().lower()
            if chave in CABECALHOS_RELEVANTES and valor is not None:
                cabecalhos[chave] = ", ".join(map(str, valor)) if isinstance(valor, list) else str(valor)
    # Os campos que a API já entrega separados valem mais que o cabeçalho cru.
    if dados.get("message_id"):
        cabecalhos["message-id"] = str(dados["message_id"])
    for campo, chave in (("reply_to", "reply-to"), ("cc", "cc")):
        valor = dados.get(campo)
        if valor:
            cabecalhos[chave] = ", ".join(map(str, valor)) if isinstance(valor, list) else str(valor)
    return cabecalhos


def _tamanho_declarado(*fontes: dict | None) -> int | None:
    for fonte in fontes:
        valor = (fonte or {}).get("size")
        if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0:
            return valor
        if isinstance(valor, str) and valor.isdigit():
            return int(valor)
    return None


def _anexo_do_resend(meta: dict, detalhe: dict | None) -> AnexoDoResend:
    url = (detalhe or {}).get("download_url")
    return AnexoDoResend(
        id=str(meta.get("id") or ""),
        filename=str(meta.get("filename") or ""),
        content_type=str(meta.get("content_type") or "application/octet-stream"),
        tamanho=_tamanho_declarado(detalhe, meta),
        download_url=url if isinstance(url, str) else None,
    )


def baixar_anexo_recebido(anexo: AnexoDoResend, *, limite_bytes: int, cliente: httpx.Client | None = None) -> bytes:
    """Baixa o binário de UM anexo pelo link assinado, em pedaços, e para no
    pedaço que passa de `limite_bytes` (`AnexoAcimaDoTetoError`). O teto vale
    sobre o que chega de fato, e não sobre o que o servidor declara: um
    `Content-Length` mentiroso ou uma compressão que infla não furam o teto.

    Levanta `LeituraDoResendError` quando o binário não vem (sem link, rede,
    status de erro), com o tipo da falha como mensagem."""
    url = anexo.download_url
    # O link vem da API autenticada do Resend. Mesmo assim, só https: um link
    # de outro esquema não é o que a API documenta, e não há por que segui-lo.
    if not isinstance(url, str) or not url.startswith("https://"):
        raise LeituraDoResendError("sem link de download")
    proprio = cliente is None
    http = cliente or httpx.Client(timeout=TIMEOUT_DO_TRANSPORTE)
    try:
        # Sem a chave no cabeçalho: o link já é assinado, e a chave do Resend
        # não tem nada que ir para o host que serve o binário.
        with http.stream("GET", url) as resposta:
            resposta.raise_for_status()
            declarado = resposta.headers.get("content-length", "")
            if declarado.isdigit() and int(declarado) > limite_bytes:
                raise AnexoAcimaDoTetoError("Content-Length acima do teto")
            recebido = bytearray()
            for pedaco in resposta.iter_bytes():
                recebido += pedaco
                if len(recebido) > limite_bytes:
                    raise AnexoAcimaDoTetoError("binário acima do teto")
        return bytes(recebido)
    except httpx.HTTPError as exc:
        raise LeituraDoResendError(type(exc).__name__) from exc
    finally:
        if proprio:
            http.close()


def ler_email_recebido(email_id: str, *, cliente: httpx.Client | None = None) -> EmailDoResend:
    """Busca na API do Resend o corpo, os cabeçalhos e os metadados dos anexos
    do e-mail recebido (tamanho declarado e link assinado de cada um). O
    binário NÃO é baixado aqui: é `baixar_anexo_recebido`, um por vez, com teto.

    Levanta `LeituraDoResendError` quando o e-mail em si não vem (sem chave,
    API fora, e-mail inexistente). A falta da lista de anexos não levanta: os
    anexos voltam sem link, e quem chama grava o item como incompleto em vez
    de perder o que veio (issue #648)."""
    chave = settings.resend_inbound_api_key or settings.resend_api_key
    if not chave:
        raise LeituraDoResendError("chave do Resend para leitura não configurada")
    base = settings.resend_inbound_base_url.rstrip("/")
    caminho = f"{base}/emails/receiving/{quote(email_id, safe='')}"
    autenticacao = {"Authorization": f"Bearer {chave}"}

    proprio = cliente is None
    http = cliente or httpx.Client(timeout=TIMEOUT_DO_TRANSPORTE)
    try:
        try:
            resposta = http.get(caminho, headers=autenticacao)
            resposta.raise_for_status()
            dados = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LeituraDoResendError(type(exc).__name__) from exc
        if not isinstance(dados, dict):
            raise LeituraDoResendError("resposta fora do formato")

        metas = [m for m in (dados.get("attachments") or []) if isinstance(m, dict)]
        detalhes: dict[str, dict] = {}
        if metas:
            try:
                lista = http.get(f"{caminho}/attachments", headers=autenticacao)
                lista.raise_for_status()
                for detalhe in lista.json().get("data") or []:
                    if isinstance(detalhe, dict) and detalhe.get("id"):
                        detalhes[str(detalhe["id"])] = detalhe
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                logger.warning("Resend: lista de anexos do e-mail %s não veio (%s)", email_id, type(exc).__name__)

        return EmailDoResend(
            texto=dados.get("text"),
            html=dados.get("html"),
            cabecalhos=_cabecalhos_relevantes(dados),
            anexos=tuple(_anexo_do_resend(meta, detalhes.get(str(meta.get("id")))) for meta in metas),
        )
    finally:
        if proprio:
            http.close()


def _enviar_via_smtp(
    destinatario: str,
    assunto: str,
    html_content: str,
    texto_fallback: str,
    anexos: list[Anexo] | None = None,
    endereco_fora_do_log: bool = False,
    assunto_no_log: str | None = None,
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = destinatario
    msg.set_content(texto_fallback)
    msg.add_alternative(html_content, subtype="html")
    for nome, conteudo in anexos or []:
        principal, secundario = _tipo_do_anexo(nome)
        msg.add_attachment(conteudo, maintype=principal, subtype=secundario, filename=nome)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_DO_TRANSPORTE) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(
            f"Email enviado via SMTP para {_alvo_no_log(destinatario, endereco_fora_do_log)} "
            f"| Assunto: {_assunto_no_log(assunto, assunto_no_log)}"
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar email via SMTP: {_falha_no_log(e, endereco_fora_do_log)}")
        return False


def _enviar_email(
    destinatario: str,
    assunto: str,
    html_content: str,
    texto_fallback: str,
    anexos: list[Anexo] | None = None,
    endereco_fora_do_log: bool = False,
    assunto_no_log: str | None = None,
) -> bool:
    """
    Tenta enviar email via Resend (primário). Se não configurado, tenta SMTP.
    Se nenhum configurado, loga em modo mock.

    O corpo da mensagem só entra no log quando `ENVIRONMENT=development`. Fora
    dele, o log fica com destinatário, assunto e anexos, e diz que omitiu o
    corpo: o modo mock também acontece em produção (chave rotacionada para
    vazio), e ali o corpo é conteúdo de caso da Ouvidoria (issue #450, ADR 0039
    decisão 7).

    `endereco_fora_do_log` tira o endereço de TODOS os caminhos de log daqui, e
    quem o liga é quem escreve para fora do hospital (issue #493). Ver
    `_alvo_no_log`.
    """
    if _resend_configurado():
        return _enviar_via_resend(
            destinatario, assunto, html_content, texto_fallback, anexos, endereco_fora_do_log, assunto_no_log
        )

    if _smtp_configurado():
        return _enviar_via_smtp(
            destinatario, assunto, html_content, texto_fallback, anexos, endereco_fora_do_log, assunto_no_log
        )

    anexados = ", ".join(f"{nome} ({len(conteudo)} bytes)" for nome, conteudo in anexos or []) or "nenhum"
    cabecalho = (
        f"[MOCK EMAIL] Para: {_alvo_no_log(destinatario, endereco_fora_do_log)} "
        f"| Assunto: {_assunto_no_log(assunto, assunto_no_log)} | Anexos: {anexados}"
    )
    if settings.environment == "development":
        logger.warning(
            f"\n\n{cabecalho}\n{texto_fallback}\n--- Configure RESEND_API_KEY no .env para enviar emails reais ---\n"
        )
    else:
        # O modo mock NÃO é exclusividade do desenvolvimento (ADR 0039, decisão
        # 7): basta a chave do Resend ser rotacionada para vazio e produção
        # inteira cai aqui. Imprimir o corpo então põe o `extrato_para_o_setor`
        # das notificações da Ouvidoria no log do container, legível para quem
        # tem acesso ao Coolify e não tem perfil nenhum no módulo: o gate do
        # Dossiê deixaria de valer para aquele trecho (issue #450).
        #
        # O cabeçalho fica, porque é o que responde "o email deste caso saiu?"
        # quando alguém liga dizendo que não recebeu. Ele NÃO é dado neutro: os
        # assuntos dos construtores da Ouvidoria levam protocolo, setor e estado
        # do caso ("Ouvidoria 2026-0042: caso CRITICO validado no setor
        # Recepcao"), então quem lê o log ainda monta um índice de casos com
        # cronologia. O que sai daqui é o RELATO, que é o conteúdo; manter
        # destinatário e assunto foi decidido na issue #450, e o residual deles
        # é pendência humana na decisão 7 do ADR 0039 (truncar o protocolo no
        # assunto do log, ou aceitar).
        #
        # E o log DIZ que omitiu, senão quem lê conclui que o corpo veio vazio
        # do construtor.
        logger.warning(
            f"\n\n{cabecalho} | Corpo omitido: o modo mock só imprime a mensagem "
            f"quando ENVIRONMENT=development.\n"
            f"--- Configure RESEND_API_KEY no ambiente para enviar emails reais ---\n"
        )
    return True


def enviar_com_anexo(
    destinatario: str, assunto: str, html_content: str, texto_fallback: str, anexos: list[Anexo]
) -> bool:
    """A porta pública do envio com arquivo junto. Mesmo caminho de sempre
    (Resend primeiro, SMTP como reserva), só que carregando o anexo."""
    return _enviar_email(destinatario, assunto, html_content, texto_fallback, anexos)


def send_meeting_scheduled_notification(
    supabase,
    id_reuniao: str,
    facilitador_id: str,
    criador_id: str,
) -> bool:
    """Notifica o facilitador quando outra pessoa (ex: secretária) agendou uma reunião pra ele.

    Busca os dados da reunião, do facilitador (destinatário) e do criador,
    renderiza o template `email_reuniao_agendada.html` e dispara via _enviar_email.
    Idempotente do ponto de vista do banco (não persiste nada além do log).
    """
    from app.services.email_constants import get_logo_data_uri

    try:
        r = (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, data, hora_inicio, hora_fim, objetivo")
            .eq("id_reuniao", id_reuniao)
            .limit(1)
            .execute()
        )
        if not r.data:
            logger.warning(f"[meeting_scheduled] reunião {id_reuniao} não encontrada, abortando email")
            return False
        reuniao = r.data[0]

        fac = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("id", facilitador_id)
            .limit(1)
            .execute()
        )
        if not fac.data:
            logger.warning(f"[meeting_scheduled] facilitador {facilitador_id} não encontrado")
            return False
        facilitador = fac.data[0]
        if not facilitador.get("email"):
            logger.warning(f"[meeting_scheduled] facilitador {facilitador_id} sem email, pulando notificação")
            return False

        cr = supabase.table("participantes").select("id, nome_completo").eq("id", criador_id).limit(1).execute()
        criador_nome = cr.data[0].get("nome_completo") if cr.data else "Equipe da secretaria"

        template = jinja_env.get_template("email_reuniao_agendada.html")
        html = template.render(
            facilitador_nome=facilitador.get("nome_completo") or "Facilitador",
            criador_nome=criador_nome,
            id_reuniao=reuniao.get("id_reuniao"),
            titulo=reuniao.get("titulo") or "Sem título",
            data=reuniao.get("data") or "A definir",
            hora_inicio=reuniao.get("hora_inicio"),
            hora_fim=reuniao.get("hora_fim"),
            objetivo=reuniao.get("objetivo"),
            frontend_url=settings.frontend_url,
            logo_base64=get_logo_data_uri(),
        )
        texto_fallback = (
            f"Olá {facilitador.get('nome_completo')},\n\n"
            f"{criador_nome} agendou uma nova reunião pra você:\n"
            f"- Título: {reuniao.get('titulo')}\n"
            f"- Data: {reuniao.get('data')}\n"
            f"- Horário: {reuniao.get('hora_inicio') or 'A definir'}\n"
            f"Acesse o sistema em {settings.frontend_url}/reunioes\n"
        )

        return _enviar_email(
            destinatario=facilitador["email"],
            assunto=f"Nova reunião agendada: {reuniao.get('titulo') or id_reuniao}",
            html_content=html,
            texto_fallback=texto_fallback,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[meeting_scheduled] Falha ao enviar email pra facilitador {facilitador_id}: {e}")
        return False
