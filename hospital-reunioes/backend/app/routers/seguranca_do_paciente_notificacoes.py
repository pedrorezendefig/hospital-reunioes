"""Notificar um incidente (issue #1987, PRD #1979, ADR 0107).

Três portas para o mesmo formulário, e a origem vem da porta:

- `POST /nsp/publico/notificacoes`, sem login, para o QR (`/notificar/qr`) e o
  endereço (`/notificar`). Só aceita essas duas origens;
- `POST /nsp/notificacoes`, com login, para o botão "Notificar incidente" do
  módulo, que todo usuário logado vê. A identificação vem da sessão.

As rotas de envio e a de acompanhamento usam o limite sem IP (ADR 0107,
decisão 6): a conta é pelo endereço, com chave embaralhada, e a linha do log
sai sem endereço. Nada aqui lê IP ou identificador do aparelho para gravar.
O botão do módulo conta também por pessoa (`LIMITE_POR_PESSOA`).

Com arquivo (issue #1988), o envio vem em multipart: o relato em `dados`, como
JSON, e até três arquivos em `anexos`. Sem arquivo, o JSON de sempre continua
valendo. O arquivo só sai por `GET /nsp/notificacoes/{id}/anexos/{anexo}`, para
quem tem o recurso de casos.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from starlette.datastructures import UploadFile
from supabase import Client

from app.dependencies import (
    barrar_desligado,
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    require_recurso_nsp,
)
from app.limiter import limiter
from app.services import limite_sem_ip, ouvidoria_nucleo
from app.services.ouvidoria_anexos import AnexoGrandeDemaisError, AnexoRecusadoError, TipoNaoPermitidoError
from app.services.seguranca_do_paciente import agente_de_triagem, anexos, caso_grave, esclarecimentos, notificacoes
from app.services.seguranca_do_paciente.permissao import hoje_em_sao_paulo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nsp", tags=["seguranca-do-paciente"])

# A conta do limite sem IP é por endereço, e o endereço é o da rede: os
# computadores e o Wi-Fi do hospital saem por um só, como os celulares de uma
# mesma operadora. O teto da rede precisa caber no hospital inteiro, senão
# quem esgota a conta fecha o canal para todos. Cada rota tem a sua conta:
# esgotar as portas sem login não fecha o botão do módulo.
LIMITE_DA_REDE = "30/minute;300/hour"
# O botão do módulo sabe quem está logado e conta por pessoa.
LIMITE_POR_PESSOA = "5/minute;20/hour"

SETOR_INVALIDO = "Escolha o setor na lista."
FALHA_AO_REGISTRAR = "Não foi possível registrar a notificação agora. Tente de novo em instantes."
FALHA_DOS_ANEXOS = "Não foi possível guardar os arquivos agora. Tente de novo em instantes."


class RelatoDoIncidente(BaseModel):
    """As quatro telas do formulário, menos a origem, que vem da porta."""

    relato: str = Field(..., min_length=1, max_length=10000)
    leito_ou_atendimento: str | None = Field(default=None, max_length=60)
    setor_id: UUID
    data_ocorrencia: date
    turno: Literal["manha", "tarde", "noite"]
    hora_aproximada: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    chegou_ao_paciente: Literal["nao", "sem_dano", "com_dano", "nao_sei"]
    grave_ou_morte: bool | None = None
    percebido_ou_reclamacao: Literal["sim", "nao", "nao_sei"] | None = None
    anonimo: bool

    @field_validator("relato", "leito_ou_atendimento")
    @classmethod
    def _sem_espaco_sobrando(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None

    @field_validator("data_ocorrencia")
    @classmethod
    def _nao_e_futura(cls, valor: date) -> date:
        if valor > hoje_em_sao_paulo():
            raise ValueError("A data do incidente não pode ser depois de hoje.")
        return valor

    @model_validator(mode="after")
    def _gravidade_quando_houve_dano_ou_nao_sei(self):
        if not self.relato:
            raise ValueError("Conte o que aconteceu.")
        if self.chegou_ao_paciente in ("com_dano", "nao_sei"):
            if self.grave_ou_morte is None:
                raise ValueError("Diga se foi grave ou se houve morte.")
        else:
            self.grave_ou_morte = None
        return self


class EnvioPublico(RelatoDoIncidente):
    origem: Literal["qr", "endereco"]
    nome: str | None = Field(default=None, max_length=200)
    contato: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _identificado_deixa_nome_e_contato(self):
        self.nome = (self.nome or "").strip() or None
        self.contato = (self.contato or "").strip() or None
        if self.anonimo:
            self.nome = self.contato = None
        elif not self.nome or not self.contato:
            raise ValueError("Para notificar com o seu nome, deixe o nome e um e-mail ou telefone.")
        return self


def _ler_o_envio(modelo: type[RelatoDoIncidente]):
    """O relato e os arquivos do envio. Multipart quando há arquivo: o relato
    vem em `dados`, como JSON, e os arquivos em `anexos`; sem arquivo, o corpo
    é o JSON de sempre. A recusa do relato é a mesma 422 nas duas formas."""

    async def ler(request: Request) -> tuple[RelatoDoIncidente, list[anexos.ArquivoRecebido]]:
        arquivos: list[anexos.ArquivoRecebido] = []
        try:
            if request.headers.get("content-type", "").startswith("multipart/form-data"):
                # Folga acima do máximo: o quarto arquivo é recusado aqui, com
                # a mensagem da regra, e não pelo teto do parser.
                formulario = await request.form(max_files=anexos.MAXIMO_DE_ARQUIVOS * 3, max_fields=5)
                dados = formulario.get("dados")
                if not isinstance(dados, str):
                    raise RequestValidationError(
                        [{"type": "missing", "loc": ("body", "dados"), "msg": "Field required", "input": None}]
                    )
                envio = modelo.model_validate_json(dados)
                for parte in formulario.getlist("anexos"):
                    if isinstance(parte, UploadFile):
                        arquivos.append(anexos.ArquivoRecebido(parte.filename or "", await parte.read()))
            else:
                envio = modelo.model_validate(await request.json())
        except ValidationError as erro:
            raise RequestValidationError(erro.errors(include_url=False)) from erro
        except json.JSONDecodeError as erro:
            raise RequestValidationError(
                [{"type": "json_invalid", "loc": ("body",), "msg": "JSON decode error", "input": None}]
            ) from erro
        return envio, arquivos

    return ler


def _recusa_do_arquivo(erro: AnexoRecusadoError) -> HTTPException:
    if isinstance(erro, TipoNaoPermitidoError):
        codigo = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(erro, AnexoGrandeDemaisError):
        codigo = status.HTTP_413_CONTENT_TOO_LARGE
    else:
        codigo = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=codigo, detail=str(erro))


def _setor_ativo(supabase, setor_id: str) -> bool:
    linhas = supabase.table("setores").select("id").eq("id", setor_id).eq("ativo", True).limit(1).execute().data
    return bool(linhas)


def _avisar_a_chegada(supabase, tarefas: BackgroundTasks, notificacao_id: str) -> None:
    """O alerta de caso grave e a confirmação de recebimento (issue #1989):
    registrados aqui, no envio, antes de qualquer triagem; entregues logo
    depois da resposta. A notificação já está gravada: falha aqui não a
    desfaz, e o caso grave segue destacado no início do módulo."""
    try:
        registros, agora = caso_grave.avisar_a_chegada(supabase, notificacao_id)
    except Exception as erro:  # noqa: BLE001 (o protocolo já saiu para quem notificou)
        logger.error("Falha ao registrar os avisos da chegada da notificação: %s", type(erro).__name__)
        return
    if registros:
        tarefas.add_task(caso_grave.entregar_os_avisos_da_chegada, supabase, registros, agora)


def _gravar_notificacao(
    supabase,
    tarefas: BackgroundTasks,
    envio: RelatoDoIncidente | RegistroRapido,
    arquivos: list[anexos.ArquivoRecebido],
    **identificacao,
) -> dict:
    """Confere os arquivos, sobe ao bucket, grava a notificação e liga os
    anexos a ela, e registra os avisos da chegada. Arquivo recusado não
    deixa rastro; falha depois da subida tira do bucket o que subiu."""
    try:
        aceitos = anexos.conferir_os_arquivos(arquivos)
    except AnexoRecusadoError as erro:
        raise _recusa_do_arquivo(erro) from erro
    try:
        if not _setor_ativo(supabase, str(envio.setor_id)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=SETOR_INVALIDO)
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao registrar a notificação de incidente: %s", type(erro).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_AO_REGISTRAR) from erro
    caminhos = anexos.subir_ao_bucket(supabase, aceitos)
    if caminhos is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_DOS_ANEXOS)
    try:
        relato = envio.model_dump(mode="json")
        recibo = notificacoes.registrar(supabase, relato, anonimo=envio.anonimo, **identificacao)
    except (APIError, httpx.HTTPError) as erro:
        # Detalhe do banco não vai para um canal aberto; quem notifica vê que
        # não deu e tenta de novo, com o relato ainda na tela.
        anexos.tirar_do_bucket(supabase, caminhos)
        logger.error("Falha ao registrar a notificação de incidente: %s", type(erro).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_AO_REGISTRAR) from erro
    notificacao_id = recibo.pop("id")
    _avisar_a_chegada(supabase, tarefas, notificacao_id)
    agente_de_triagem.agendar_triagem_do_nucleo(tarefas, supabase, notificacao_id)
    if caminhos:
        try:
            anexos.ligar_a_notificacao(supabase, notificacao_id, aceitos, caminhos)
        except (APIError, httpx.HTTPError) as erro:
            # A notificação já tem protocolo e não se desfaz: o relato vale
            # mais que o arquivo. A tela diz que os arquivos não ficaram.
            anexos.tirar_do_bucket(supabase, caminhos)
            logger.error("Falha ao ligar os anexos à notificação %s: %s", recibo["protocolo"], type(erro).__name__)
            recibo["anexos_guardados"] = False
            return recibo
        recibo["anexos_guardados"] = True
    return recibo


@router.post("/publico/notificacoes", status_code=status.HTTP_201_CREATED)
@limite_sem_ip.limitar(LIMITE_DA_REDE)
async def notificar_sem_login(
    request: Request,
    tarefas: BackgroundTasks,
    pedido: tuple[EnvioPublico, list[anexos.ArquivoRecebido]] = Depends(_ler_o_envio(EnvioPublico)),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """O formulário público, pelo QR ou pelo endereço."""
    envio, arquivos = pedido
    return _gravar_notificacao(
        supabase, tarefas, envio, arquivos, origem=envio.origem, nome=envio.nome, contato=envio.contato
    )


async def _quem_esta_logado(
    request: Request,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Todo usuário logado notifica pelo módulo, mesmo sem nenhum outro acesso
    ao Núcleo (Ajuste do plano #2045). Só o desligado fica de fora."""
    me = await get_participante_for_user(current_user, supabase)
    barrar_desligado(me)
    if not me:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cadastro não encontrado.")
    # O limitador roda depois das dependências e conta por esta pessoa.
    request.state.nsp_notificante_id = str(me["id"])
    return me


def _chave_da_pessoa(request: Request) -> str:
    """A conta do botão do módulo: quem está logado, e não a rede."""
    return "nsp-pessoa:" + request.state.nsp_notificante_id


@router.post("/notificacoes", status_code=status.HTTP_201_CREATED)
@limite_sem_ip.limitar(LIMITE_DA_REDE)
@limiter.limit(LIMITE_POR_PESSOA, key_func=_chave_da_pessoa)
async def notificar_pelo_modulo(
    request: Request,
    tarefas: BackgroundTasks,
    pedido: tuple[RelatoDoIncidente, list[anexos.ArquivoRecebido]] = Depends(_ler_o_envio(RelatoDoIncidente)),
    me: dict = Depends(_quem_esta_logado),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """O botão "Notificar incidente" do módulo: a identificação vem da sessão,
    e não do que a tela mandar."""
    envio, arquivos = pedido
    return _gravar_notificacao(
        supabase,
        tarefas,
        envio,
        arquivos,
        origem=notificacoes.ORIGEM_MODULO,
        nome=me.get("nome_completo"),
        contato=me.get("email"),
        notificante_id=me["id"],
    )


class RegistroRapido(BaseModel):
    """O registro rápido (issue #1998): o incidente que o próprio Núcleo achou,
    numa tela só. A origem é a de onde o Núcleo o achou, e não uma porta."""

    relato: str = Field(..., min_length=1, max_length=10000)
    setor_id: UUID
    data_ocorrencia: date
    origem: Literal["busca_ativa", "ronda", "reuniao_rapida", "auditoria", "outra"]
    # Quem registra é o autor: o registro rápido nunca é anônimo.
    anonimo: Literal[False] = False

    @field_validator("relato")
    @classmethod
    def _relato_com_texto(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("Conte o que aconteceu.")
        return valor.strip()

    @field_validator("data_ocorrencia")
    @classmethod
    def _data_ate_hoje(cls, valor: date) -> date:
        if valor > hoje_em_sao_paulo():
            raise ValueError("A data do incidente não pode ser depois de hoje.")
        return valor


_quem_abre_os_casos = require_recurso_nsp("casos")


async def _quem_registra(request: Request, me: dict = Depends(_quem_abre_os_casos)) -> dict:
    """A Presidência e o membro com Termo (o recurso de casos). O limitador
    conta por esta pessoa, como no botão do módulo."""
    request.state.nsp_notificante_id = str(me["id"])
    return me


@router.post("/notificacoes/registro-rapido", status_code=status.HTTP_201_CREATED)
@limite_sem_ip.limitar(LIMITE_DA_REDE)
@limiter.limit(LIMITE_POR_PESSOA, key_func=_chave_da_pessoa)
async def registro_rapido_do_nucleo(
    request: Request,
    envio: RegistroRapido,
    tarefas: BackgroundTasks,
    me: dict = Depends(_quem_registra),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Relato, setor, data e origem. Quem registrou é o autor, pela sessão, e
    a notificação segue a mesma gravação de todas as portas."""
    return _gravar_notificacao(
        supabase,
        tarefas,
        envio,
        [],
        origem=envio.origem,
        nome=me.get("nome_completo"),
        contato=me.get("email"),
        notificante_id=me["id"],
    )


@router.get("/publico/setores")
@limite_sem_ip.limitar("60/minute")
async def setores_do_formulario(request: Request, supabase: Client = Depends(get_supabase_client)) -> dict:
    """A lista de "Onde" do formulário: os setores ativos, pelo id."""
    linhas = supabase.table("setores").select("id, nome").eq("ativo", True).order("nome").execute().data or []
    return {"setores": [{"id": linha["id"], "nome": linha["nome"]} for linha in linhas]}


class ConsultaDeAcompanhamento(BaseModel):
    """O protocolo e uma das duas chaves: o código (anônima) ou o e-mail ou
    telefone (identificada). POST, para o código não ficar na URL."""

    protocolo: str = Field(..., min_length=1, max_length=20)
    codigo: str | None = Field(default=None, max_length=40)
    contato: str | None = Field(default=None, max_length=200)


NAO_ENCONTRADA = (
    "Não encontramos uma notificação com esses dados. Confira o protocolo e o código, "
    "ou o e-mail ou telefone que você deixou."
)


@router.post("/publico/acompanhamento")
@limite_sem_ip.limitar(LIMITE_DA_REDE)
async def acompanhar_notificacao(
    request: Request,
    consulta: ConsultaDeAcompanhamento,
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """A página de acompanhamento: só o estado, em palavras simples. O limite
    da rede segura quem tenta adivinhar o código (dez símbolos)."""
    try:
        situacao = notificacoes.consultar(supabase, consulta.protocolo, consulta.codigo, consulta.contato)
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao consultar o acompanhamento da notificação: %s", type(erro).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível consultar agora. Tente novamente em instantes.",
        ) from erro
    if situacao is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NAO_ENCONTRADA)
    return situacao


# A confirmação pergunta de novo enquanto o agente lê a notificação: a conta
# é própria, para não gastar a do acompanhamento.
LIMITE_DAS_PERGUNTAS = "60/minute;600/hour"
FALHA_DAS_PERGUNTAS = "Não foi possível falar com o hospital agora. Tente novamente em instantes."
PERGUNTA_SEM_VAGA = "Essa pergunta já foi respondida ou não está mais aberta. Consulte de novo."


def _caso_conferido(supabase, consulta: ConsultaDeAcompanhamento) -> dict:
    try:
        caso = notificacoes.conferir(supabase, consulta.protocolo, consulta.codigo, consulta.contato)
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao conferir a notificação para as perguntas: %s", type(erro).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_DAS_PERGUNTAS) from erro
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NAO_ENCONTRADA)
    return caso


@router.post("/publico/perguntas")
@limite_sem_ip.limitar(LIMITE_DAS_PERGUNTAS)
async def perguntas_de_esclarecimento(
    request: Request,
    consulta: ConsultaDeAcompanhamento,
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """As perguntas do agente que ainda esperam resposta (issue #1991), com a
    mesma chave do acompanhamento. `aguardando` diz que o agente ainda não
    leu a notificação: a confirmação pergunta de novo daqui a pouco."""
    caso = _caso_conferido(supabase, consulta)
    try:
        abertas, ultima = esclarecimentos.pendentes(supabase, caso["id"])
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao ler as perguntas de esclarecimento: %s", type(erro).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_DAS_PERGUNTAS) from erro
    aguardando = (
        ultima is None
        and not caso.get("classificar_manualmente")
        and not esclarecimentos.triagem_confirmada(caso)
        and agente_de_triagem.agente_ligado()
    )
    return {"perguntas": abertas, "aguardando": aguardando}


class RespostaDeEsclarecimento(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=1000)
    resposta: str = Field(..., max_length=500)

    @field_validator("resposta")
    @classmethod
    def _com_texto(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("Escreva a resposta.")
        return valor


class EnvioDeRespostas(ConsultaDeAcompanhamento):
    respostas: list[RespostaDeEsclarecimento] = Field(..., min_length=1, max_length=2)


@router.post("/publico/respostas")
@limite_sem_ip.limitar(LIMITE_DA_REDE)
async def responder_as_perguntas(
    request: Request,
    envio: EnvioDeRespostas,
    tarefas: BackgroundTasks,
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Quem notificou responde as perguntas, na confirmação ou no
    acompanhamento. O agente lê de novo depois da resposta, só enquanto a
    triagem não foi confirmada; depois, a resposta só fica gravada."""
    caso = _caso_conferido(supabase, envio)
    try:
        esclarecimentos.responder(supabase, caso, [(item.pergunta, item.resposta) for item in envio.respostas])
    except esclarecimentos.PerguntaSemVagaError as erro:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=PERGUNTA_SEM_VAGA) from erro
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao gravar a resposta de esclarecimento: %s", type(erro).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=FALHA_DAS_PERGUNTAS) from erro
    agente_de_triagem.agendar_triagem_com_esclarecimentos(tarefas, supabase, caso["id"])
    try:
        abertas, _ = esclarecimentos.pendentes(supabase, caso["id"])
    except (APIError, httpx.HTTPError) as erro:
        # A resposta já ficou: a tela consulta de novo.
        logger.error("Falha ao ler as perguntas depois da resposta: %s", type(erro).__name__)
        abertas = []
    return {"perguntas": abertas}


@router.get("/notificacoes")
@limite_sem_ip.limitar("60/minute")
async def lista_de_casos(
    request: Request,
    me: dict = Depends(require_recurso_nsp("casos")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Notificações: todos os casos, para quem tem o recurso de casos. Quem
    notificou só para a Presidência e o Acesso pleno."""
    com_identidade = "identidade_notificante" in me["recursos_nsp"]
    casos = notificacoes.listar(supabase, com_identidade=com_identidade)
    por_caso = anexos.anexos_dos_casos(supabase, [caso["id"] for caso in casos])
    for caso in casos:
        caso["anexos"] = por_caso.get(caso["id"], [])
    return {"notificacoes": casos}


@router.get("/notificacoes/{notificacao_id}/anexos/{anexo_id}")
@limite_sem_ip.limitar("60/minute")
async def abrir_anexo_do_caso(
    request: Request,
    notificacao_id: UUID,
    anexo_id: UUID,
    me: dict = Depends(require_recurso_nsp("casos")),
    supabase: Client = Depends(get_supabase_client),
) -> Response:
    """O arquivo do caso, entregue pelo backend: sem URL assinada, que valeria
    para quem recebesse o link. O nome original não volta."""
    try:
        achado = anexos.abrir_o_anexo(supabase, str(notificacao_id), str(anexo_id))
    except (APIError, httpx.HTTPError, anexos.AnexoIndisponivelError) as erro:
        logger.error("Falha ao abrir o anexo da notificação: %s", type(erro).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o arquivo agora. Tente de novo em instantes.",
        ) from erro
    if achado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado.")
    conteudo, content_type, extensao = achado
    return Response(
        content=conteudo,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="anexo{extensao}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


def agora_utc() -> datetime:
    return datetime.now(UTC)


@router.get("/notificacoes/{caso_id}")
@limite_sem_ip.limitar("60/minute")
async def caso_do_nucleo(
    request: Request,
    caso_id: UUID,
    me: dict = Depends(require_recurso_nsp("casos")),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Um caso do Núcleo. O caso que veio da Ouvidoria traz o que ela apurou
    e o estado da manifestação, e abri-lo é o Recebido do Núcleo na
    Ouvidoria (issue #1997, ADR 0107 decisão 7): o e-mail de ciência traz o
    endereço desta tela, que pede login."""
    com_identidade = "identidade_notificante" in me["recursos_nsp"]
    try:
        caso = notificacoes.abrir(supabase, str(caso_id), com_identidade=com_identidade)
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao abrir o caso do Núcleo: %s", type(erro).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o caso agora. Tente de novo em instantes.",
        ) from erro
    if caso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caso não encontrado.")
    if caso.get("origem") == notificacoes.ORIGEM_OUVIDORIA:
        _marcar_o_recebido_na_ouvidoria(supabase, str(caso_id), me)
    return caso


def _marcar_o_recebido_na_ouvidoria(supabase, caso_id: str, me: dict) -> None:
    """Melhor esforço: o Recebido que não gravou volta no próximo abrir, e a
    falha não tira o caso da tela de quem o abriu."""
    try:
        manifestacao_id = notificacoes.manifestacao_do_caso(supabase, caso_id)
        if manifestacao_id:
            ouvidoria_nucleo.receber_pelo_modulo(supabase, manifestacao_id, me, agora_utc())
    except (APIError, httpx.HTTPError) as erro:
        logger.error("Falha ao marcar o Recebido do Núcleo na Ouvidoria: %s", type(erro).__name__)
