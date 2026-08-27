"""Painel de ouvidoria (issue #292, ADR 0031 decisão 3): a equipe do hospital
enxerga os protocolos registrados pela Ana e marca cada um como respondido.

Fluxo JWT (usuário logado), fora da API de serviço da Ana. O painel lista o
índice para toda a equipe e abre o Dossiê só para a Ouvidoria (ADR 0034).

Desde a issue #321 a Manifestação também nasce aqui: o ouvidor registra o que
chegou por telefone, balcão ou email, com a data e hora reais do contato.
"""

import datetime as dt
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from supabase import Client

from app.config import settings
from app.dependencies import (
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    tem_acesso_reunioes,
)
from app.limiter import limiter
from app.routers.ana import _CAMPOS_PROTOCOLO_TUPLA
from app.services import (
    ouvidoria_escalonamento,
    ouvidoria_metricas,
    ouvidoria_notificacoes,
    ouvidoria_prorrogacao,
    ouvidoria_respostas,
    storage,
)
from app.services.ouvidoria_anexos import (
    AnexoGrandeDemaisError,
    AnexoRecusadoError,
    TipoNaoPermitidoError,
    validar_anexo,
)
from app.services.ouvidoria_estados import (
    DESFECHO_SEM_RETORNO,
    JANELA_REINCIDENCIA_DIAS,
    ORIGENS_DA_DEVOLUCAO,
    DadosInsuficientesError,
    TransicaoInvalidaError,
    dentro_da_janela_de_reincidencia,
    e_devolucao,
    e_pausa,
    e_retomada,
    entra_no_indicador_de_resolucao,
    validar_transicao,
)
from app.services.ouvidoria_prazos import (
    Prazo,
    calcular_vencimento,
    contato_suficiente_para_encerrar,
    cumprimento_da_area,
    esta_vencido,
    estouro_consumado,
    minutos_uteis_entre,
    minutos_uteis_pausados,
    rotular_vencimento,
    vencimento_apos_devolucao,
    vencimento_apos_retomada,
)
from app.services.ouvidoria_responsaveis import escolher_destinatario
from app.services.ouvidoria_taxonomia import (
    ROTULO_TIPO,
    SigiloTravadoError,
    TipoManifestacao,
    nasce_sigilosa,
    resolver_sigilo,
)
from app.utils.text_sanitizer import sanitizar_travessao

# O T0 é hora de relógio de parede do hospital: o ouvidor digita "14/08 16h50"
# pensando em Brasília, e a persistência é em UTC.
FUSO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# Folga para relógio de máquina adiantado, ao recusar contato "no futuro".
TOLERANCIA_RELOGIO = timedelta(minutes=5)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria"])


def agora_utc() -> dt.datetime:
    """O relógio do módulo, num ponto só. Prazo, janela comercial e marco T1
    precisam enxergar o MESMO instante dentro de uma validação: lidos em
    chamadas diferentes, o email poderia dizer um vencimento e o banco guardar
    outro."""
    return dt.datetime.now(dt.UTC)


async def require_acesso_painel(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do painel: quem tem papel no contexto Reuniões (facilitador,
    secretária, super admin) mais quem tem papel na Ouvidoria. O ouvidor pode
    não participar de Reuniões nenhuma e ainda assim é o dono desta tela.

    Devolve o participante: a listagem decide o que mostrar pelo perfil."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or not (tem_acesso_reunioes(me) or tem_perfil_ouvidoria(me)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à equipe de Reuniões",
        )
    return me


# Índice do painel: os campos da API da Ana mais o prazo do motor novo. Fica
# separado de _CAMPOS_PROTOCOLO_TUPLA de propósito: aquela tupla dimensiona a
# resposta da API da Ana, que tem teto de leitura no cliente (ADR 0032).
# `respondida_em` entra por causa do indicador de cumprimento, que compara o
# marco T2 com o vencimento VIGENTE (prorrogação aprovada já mexeu nele).
# `minutos_pausados` entra pelo relato separado da espera pelo manifestante: o
# desconto já está dentro do vencimento, e sem este número ao lado dele a
# Diretoria veria o prazo esticado sem enxergar a espera que o esticou
# (PRD #318, história 10).
# `desfecho` entra pelo indicador de resolução: é ele que separa resolvido,
# não resolvido e o caso neutro que ninguém apurou (issue #335).
# `tipo_manifestacao` entra porque a fila do ouvidor precisa enxergar o que
# falta classificar, e porque a tela de validação já abre com o tipo escolhido
# (issue #372). Não vaza nada: o caso sigiloso nem chega a esta listagem para
# quem está fora da Ouvidoria.
_CAMPOS_INDICE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + (
    "tipo_manifestacao",
    # `sigilo_reforcado` decide QUEM recebe a linha e agora também vai NELA: a
    # tela de validação abre a partir do índice e precisa mostrar a marca de
    # sigilo no estado real. Sem a coluna aqui, ela abria desligada num caso
    # protegido e a validação retirava o sigilo sem ninguém desmarcar nada.
    # Não vaza: a linha sigilosa não chega a quem está fora da Ouvidoria, então
    # para esse público o campo é sempre falso.
    "sigilo_reforcado",
    "gravidade",
    "prazo_area_em",
    "respondida_em",
    "minutos_pausados",
    "desfecho",
    # `pausada_em` entra porque a projeção do prazo congela nele: sem esta
    # coluna a listagem mediria o caso parado contra o relógio de parede.
    "pausada_em",
    # `area_estourou_em` entra porque o indicador de cumprimento lê o estouro
    # consumado antes de tudo: sem esta coluna o índice diria "em_prazo" para
    # um caso que a área já atrasou e teve devolvido (issue #374).
    "area_estourou_em",
)
_CAMPOS_INDICE = ", ".join(_CAMPOS_INDICE_TUPLA)


def carregar_feriados(supabase) -> frozenset[dt.date]:
    """Os feriados que o motor precisa (RN-22). Falha aqui não derruba o
    painel: sem a lista o motor conta feriado como dia útil, o que erra para
    menos (cobra antes), e é melhor que a tela não abrir."""
    try:
        result = supabase.table("ouvidoria_feriados").select("data").execute()
        # A conversão entra no try junto da leitura: uma data malformada não
        # pode derrubar o painel inteiro, que é o que a promessa acima diz.
        return frozenset(dt.date.fromisoformat(str(row["data"])) for row in (result.data or []) if row.get("data"))
    except Exception:
        logger.warning("Falha ao carregar feriados: o calendário útil vai contar sem eles")
        return frozenset()


def _instante(bruto) -> dt.datetime | None:
    """O timestamp que o PostgREST devolve como texto, ou None quando vazio."""
    return dt.datetime.fromisoformat(str(bruto)) if bruto else None


def _projetar_prazo(row: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> dict:
    """Traduz o que está persistido no caso nos números que a tela mostra: o
    prazo e os dois indicadores que saem dele. O prazo é lido, nunca
    recalculado: caso já despachado mantém o que o setor recebeu.

    `minutos_uteis_restantes` sai daqui porque o destaque visual precisa da
    mesma régua do rótulo: medir a proximidade em dias corridos no navegador
    apagaria o alerta justo quando o vencimento atravessa fim de semana.

    Caso parado aguardando o manifestante mede tudo no instante em que parou,
    não em `agora` (issue #335). O vencimento só é empurrado na retomada, então
    medir contra o relógio de parede faria um caso parado atravessar o próprio
    vencimento e aparecer estourado, com `cumprimento` carimbando falha contra
    a área por uma espera que não é dela. A escada de cobrança escapa disso
    porque filtra o status; esta projeção precisa da guarda própria."""
    vencimento = _instante(row.get("prazo_area_em"))
    medido_em = _instante(row.get("pausada_em")) or agora
    estourado = esta_vencido(vencimento, medido_em)
    if vencimento is None or estourado:
        restantes = None if vencimento is None else 0
    else:
        restantes = minutos_uteis_entre(medido_em, vencimento, feriados)
    return {
        "rotulo_prazo": rotular_vencimento(vencimento, medido_em, feriados),
        "prazo_estourado": estourado,
        "minutos_uteis_restantes": restantes,
        # O indicador de prazo da área (PRD #318, história 5). A régua é o
        # vencimento vigente, então prorrogação aprovada conta como cumprido
        # sem nenhum caso especial aqui. `area_estourou_em` é a memória do
        # estouro que a área já consumou num ciclo anterior: sem ela, a
        # devolução por insuficiência (que limpa o marco T2 e empurra o prazo)
        # fazia quem respondeu ATRASADO voltar a ler `em_prazo` (issue #374).
        "cumprimento": cumprimento_da_area(
            vencimento,
            _instante(row.get("respondida_em")),
            medido_em,
            estouro_consumado_em=_instante(row.get("area_estourou_em")),
        ),
        # O indicador de resolução (PRD #318, história 12). Caso encerrado por
        # "sem retorno do manifestante" fica de fora: ninguém apurou, e contá-lo
        # de qualquer um dos lados mentiria sobre o número (issue #335).
        "conta_no_indicador_de_resolucao": entra_no_indicador_de_resolucao(row.get("desfecho")),
    }


@router.get("/protocolos")
@limiter.limit("60/minute")
async def listar_protocolos(
    request: Request,
    me: dict = Depends(require_acesso_painel),
    supabase=Depends(get_supabase_client),
):
    """Todos os protocolos, mais recentes primeiro, com prazo e status.

    Índice, não Dossiê: agora que a tabela guarda relato e identificação
    (ADR 0034), a resposta é fechada no índice campo a campo, e não no que o
    select devolveu."""
    # A resposta segue fechada em _CAMPOS_INDICE, campo a campo. O select não
    # precisa mais pedir `sigilo_reforcado` à parte: a coluna entrou no índice.
    query = supabase.table("ouvidoria_protocolos").select(_CAMPOS_INDICE).order("numero", desc=True)
    # Sigilo reforçado (RN-40): o resumo de uma denúncia já identifica quem
    # relatou, então a sigilosa não entra nem no índice de quem está fora da
    # Ouvidoria, super admin incluído. O filtro vive na query (a linha nem sai
    # do banco) e de novo em Python, caso a coluna volte nula por engano.
    if not tem_perfil_ouvidoria(me):
        query = query.eq("sigilo_reforcado", False)
    result = query.execute()
    linhas = result.data or []
    if not tem_perfil_ouvidoria(me):
        linhas = [row for row in linhas if not row.get("sigilo_reforcado")]

    # O rótulo é calculado no servidor, uma vez por carga, com o mesmo motor
    # que o email do setor usa: painel e email nunca dizem prazos diferentes.
    # O calendário só é lido se houver prazo para contar.
    feriados = carregar_feriados(supabase) if any(row.get("prazo_area_em") for row in linhas) else frozenset()
    # Pelo relógio do módulo, como o resto do painel: rótulo de prazo e
    # indicador de cumprimento saem da MESMA leitura do relógio em toda rota.
    agora = agora_utc()
    return {
        "protocolos": [
            {campo: row.get(campo) for campo in _CAMPOS_INDICE_TUPLA} | _projetar_prazo(row, agora, feriados)
            for row in linhas
        ]
    }


# Dossiê completo (ADR 0034, decisão 1): o índice mais o que só ouvidor e
# diretoria executiva podem ler.
_CAMPOS_DOSSIE_TUPLA = _CAMPOS_PROTOCOLO_TUPLA + (
    # O tipo entra porque toda regra de sigilo o lê (issue #372), e a leitura
    # não é só de tela: a reabertura por reincidência carrega o caso por esta
    # tupla e decide o sigilo pelo tipo. Sem a coluna aqui, ela leria None em
    # todo caso, e `nasce_sigilosa(None)` é fail-closed: uma reclamação
    # reaberta sumiria do painel de quem está fora da Ouvidoria.
    "tipo_manifestacao",
    "relato_integral",
    "manifestante_nome",
    "manifestante_contato",
    "manifestante_vinculo",
    "anonimo",
    "sigilo_reforcado",
    "dados_incompletos",
    "classificacao_ia",
    "desfecho",
    "desfecho_descricao",
    "canal",
    "contato_em",
    "gravidade",
    "prazo_area_em",
    "prazo_rompido_em",
    "validada_em",
    "validada_por",
    "respondida_em",
    "resposta_da_area",
    "respondida_por_nome",
    "encerrada_em",
    # Pausa aguardando o manifestante e reincidência (issue #335).
    "pausada_em",
    "minutos_pausados",
    "reincidencia",
    "reaberta_em",
    # Memória do estouro consumado pela área (issue #374).
    "area_estourou_em",
)
_CAMPOS_DOSSIE = ", ".join(_CAMPOS_DOSSIE_TUPLA)

PERFIS_OUVIDORIA = ("ouvidor", "diretoria_executiva")


def tem_perfil_ouvidoria(participante: dict | None) -> bool:
    """Quem lê o Dossiê (ADR 0034, decisão 8): só os dois perfis do contexto
    Ouvidoria. Papel nas Reuniões, inclusive super admin, não concede."""
    return bool(participante) and participante.get("perfil_ouvidoria") in PERFIS_OUVIDORIA


async def require_perfil_ouvidoria(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate do Dossiê. Devolve o participante para a rota decidir sobre sigilo
    e para registrar o log de acesso."""
    me = await get_participante_for_user(current_user, supabase)
    if not tem_perfil_ouvidoria(me):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito à Ouvidoria",
        )
    return me


async def require_diretoria_executiva(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Gate de quem define os parâmetros do prazo (RN-21). Mais estreito que o
    da Ouvidoria de propósito: o ouvidor trabalha com o prazo, quem o define é
    a Diretoria Executiva."""
    me = await get_participante_for_user(current_user, supabase)
    if not me or me.get("perfil_ouvidoria") != "diretoria_executiva":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Só a Diretoria Executiva altera os parâmetros da Ouvidoria",
        )
    return me


def registrar_acesso(supabase, me: dict, manifestacao_id: str, acao: str) -> None:
    """Grava o log de acesso. Falha aqui não derruba a leitura: a trilha é
    importante, mas deixar o ouvidor sem o Dossiê por causa dela seria pior.
    O timestamp é do banco (`ocorrido_em` tem default now())."""
    try:
        supabase.table("ouvidoria_acessos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "ator_id": me["id"],
                "ator_nome": me.get("nome_completo") or me["id"],
                "acao": acao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao registrar acesso à manifestação %s", manifestacao_id)


class RegistroManual(BaseModel):
    """Manifestação digitada pelo ouvidor (issue #321).

    `contato_em` é o T0: a data e hora em que a manifestação chegou ao
    hospital, não o momento do clique. Sem fuso na entrada, vale o horário de
    Brasília, que é como o ouvidor pensa a hora do telefonema."""

    canal: Literal["telefone", "presencial", "email"]
    contato_em: datetime
    tipo_manifestacao: TipoManifestacao
    categoria: str | None = None
    setor: str
    resumo: str
    relato_integral: str
    manifestante_nome: str | None = None
    manifestante_contato: str | None = None
    manifestante_vinculo: Literal["paciente", "acompanhante", "colaborador", "terceiro", "outro"] | None = None
    anonimo: bool = False
    sigilo_reforcado: bool = False

    @field_validator("setor", "resumo", "relato_integral")
    @classmethod
    def campo_critico_nao_vazio(cls, valor: str) -> str:
        # Tipografia sanitizada antes da validação (ADR 0013): o texto aparece
        # no painel e nos emails ao setor.
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo crítico não pode ser vazio")
        return valor

    @field_validator("categoria")
    @classmethod
    def rotulo_limpo(cls, valor: str | None) -> str | None:
        # O rótulo é opcional desde a issue #372: quem diz o que o caso é passou
        # a ser o tipo. Vazio vira ausente, e a rota preenche com o nome do
        # tipo, porque a coluna é NOT NULL e o painel a mostra.
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None

    @field_validator("manifestante_nome", "manifestante_contato")
    @classmethod
    def identificacao_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = sanitizar_travessao(valor).strip()
        return valor or None

    @field_validator("contato_em")
    @classmethod
    def contato_nao_pode_ser_no_futuro(cls, valor: datetime) -> datetime:
        # Retroativo é o caso normal; futuro seria erro de digitação que
        # empurraria o prazo do setor para frente sem ninguém perceber.
        #
        # A folga existe porque o campo já vem preenchido com o relógio do
        # navegador: uns minutos adiantados no computador do balcão não podem
        # recusar o valor que a própria tela sugeriu.
        instante = valor.replace(tzinfo=FUSO_HOSPITAL) if valor.tzinfo is None else valor
        if instante > datetime.now(tz=FUSO_HOSPITAL) + TOLERANCIA_RELOGIO:
            raise ValueError("a data e hora do contato não podem estar no futuro")
        return instante


@router.post("/manifestacoes", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
async def registrar_manifestacao(
    request: Request,
    registro: RegistroManual,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação que chegou por telefone, balcão ou email.

    A abertura acompanha o T0 informado (e não o dia da digitação), então o
    protocolo e o prazo saem do momento real do contato. O número `ANO-NNNN` é
    do banco, como sempre: a aplicação nunca o compõe."""
    anonimo = registro.anonimo
    # Anônimo é escolha de quem manifesta, e ela vale contra o que veio no
    # corpo: nome e contato não são gravados, ponto.
    nome = None if anonimo else registro.manifestante_nome
    contato = None if anonimo else registro.manifestante_contato

    linha = {
        "canal": registro.canal,
        "contato_em": registro.contato_em.isoformat(),
        "data_abertura": registro.contato_em.astimezone(FUSO_HOSPITAL).date().isoformat(),
        "tipo_manifestacao": registro.tipo_manifestacao,
        "categoria": registro.categoria or ROTULO_TIPO[registro.tipo_manifestacao],
        "setor": registro.setor,
        "resumo": registro.resumo,
        "relato_integral": registro.relato_integral,
        "manifestante_nome": nome,
        "manifestante_contato": contato,
        "manifestante_vinculo": None if anonimo else registro.manifestante_vinculo,
        "anonimo": anonimo,
        "sigilo_reforcado": registro.sigilo_reforcado or nasce_sigilosa(registro.tipo_manifestacao),
        # O ouvidor preencheu o formulário inteiro: só fica incompleta a que se
        # identificou pela metade (dá nome mas não deixa como responder).
        "dados_incompletos": not anonimo and not (nome and contato),
        "registrado_por": me["id"],
    }

    try:
        result = supabase.table("ouvidoria_protocolos").insert(linha).execute()
    except APIError as exc:
        logger.error("Falha ao registrar manifestação manual (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar a manifestação",
        ) from exc
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao registrar a manifestação",
        )

    row = result.data[0]
    registrar_movimento_de_abertura(supabase, me, row, registro.canal)
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


def registrar_movimento_de_abertura(supabase, me: dict, row: dict, canal: str) -> None:
    """Abre a trilha do caso: o primeiro movimento é o nascimento dele.

    Falha aqui não desfaz o registro (o protocolo já foi dito a quem
    manifestou), mas fica no log para conferência."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": row["id"],
                "estado_anterior": None,
                "estado_novo": row.get("status") or "em_classificacao",
                "autor_id": me["id"],
                "autor_nome": me.get("nome_completo") or me["id"],
                "observacao": f"Registro manual da ouvidoria (canal: {canal})",
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de abertura da manifestação %s", row.get("id"))


@router.get("/manifestacoes/{manifestacao_id}")
@limiter.limit("60/minute")
async def abrir_manifestacao(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Abre o Dossiê completo de uma manifestação."""
    try:
        result = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    row = result.data[0]
    registrar_acesso(supabase, me, manifestacao_id, "abrir_dossie")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


class PedidoTransicao(BaseModel):
    """Pedido de mudança de estado. `desfecho` e `desfecho_descricao` só fazem
    sentido no encerramento, e lá são obrigatórios."""

    estado: Literal[
        "em_classificacao",
        "aguardando_area",
        "aguardando_manifestante",
        "respondido",
        "encerrado",
    ]
    observacao: str | None = None
    desfecho: str | None = None
    desfecho_descricao: str | None = None


# O que a pausa precisa saber do caso: o vencimento que ela congela e o
# acumulado que ela alimenta (issue #335).
_CAMPOS_DA_PAUSA = "id, status, prazo_area_em, pausada_em, minutos_pausados, reaberta_em"


def efeito_da_pausa(caso: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> dict:
    """O que muda no caso quando o relógio da área para (PRD #318, história 8).

    Só o carimbo de quando parou: o vencimento fica onde está, e é a retomada
    que devolve o tempo. Congelar aqui e recalcular lá seria contar duas vezes.
    Quem lê o prazo enquanto isso mede tudo contra `pausada_em`, não contra o
    relógio de parede (ver `_projetar_prazo`)."""
    return {"pausada_em": agora.isoformat()}


def efeito_de_fechar_pausa(
    caso: dict,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    *,
    religar_jobs: bool,
) -> dict:
    """O que muda no caso em toda saída de `aguardando_manifestante`
    (PRD #318, histórias 9 e 10).

    Duas coisas juntas: o tempo parado entra no acumulado do relato separado (a
    Diretoria precisa ver a espera, não só o desconto) e o vencimento anda para
    frente exatamente esse tanto de expediente. As duas valem tanto para a
    retomada quanto para o encerramento por "sem retorno", que sai justamente
    daqui: sem elas o caso abandonado terminava dizendo que nunca esperou
    ninguém e com estouro na ficha da área por uma espera que não era dela.

    `religar_jobs` separa os dois casos. Na retomada os carimbos dos jobs de
    prazo saem, pelo mesmo motivo da prorrogação e da devolução: prazo novo sem
    carimbo zerado é prazo que nenhum degrau cobra. No encerramento eles ficam,
    porque não há mais degrau a cobrar e os carimbos são o registro do que já
    foi avisado.

    DUAS EXCEÇÕES em que o vencimento não anda:

    1. Prazo que já tinha estourado ANTES da pausa. O estouro é fato consumado:
       a área já falhou e a cobrança já saiu. Empurrar o vencimento zeraria
       `prazo_rompido_em` junto e o estouro sumiria do indicador, o que faria
       de pausar um jeito de limpar a ficha. O tempo parado ainda entra no
       relato separado, que é onde ele deve aparecer.
    2. Pausa inteira fora do expediente (noite, fim de semana, feriado). Não
       houve tempo útil parado, então não há o que devolver.

    Caso sem `pausada_em` só limpa o estado da pausa: inventar desconto ali
    daria prazo de graça à área."""
    parada_bruta = caso.get("pausada_em")
    if not parada_bruta:
        return {"pausada_em": None}

    parada = dt.datetime.fromisoformat(str(parada_bruta))
    parado = minutos_uteis_pausados([(parada, agora)], feriados)
    fechamento = {
        "pausada_em": None,
        "minutos_pausados": int(caso.get("minutos_pausados") or 0) + parado,
    }

    bruto = caso.get("prazo_area_em")
    if not bruto or parado <= 0:
        return fechamento

    vencimento = dt.datetime.fromisoformat(str(bruto))
    if esta_vencido(vencimento, parada):
        return fechamento

    novo = vencimento_apos_retomada(vencimento, parada, agora, feriados)
    fechamento["prazo_area_em"] = novo.isoformat()
    if religar_jobs:
        fechamento |= ouvidoria_prorrogacao.carimbos_a_zerar()
    return fechamento


@router.post("/manifestacoes/{manifestacao_id}/transicoes")
@limiter.limit("60/minute")
async def transicionar_manifestacao(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoTransicao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Porta de entrada única da máquina de estados: valida a regra e grava o
    movimento na mesma transação (RPC `ouvidoria_transicionar`).

    A regra é checada aqui para devolver mensagem útil, e de novo no banco,
    para que contornar a API não contorne a máquina de estados."""
    try:
        atual = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DA_PAUSA).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    caso = atual.data[0]
    estado_atual = caso["status"]

    try:
        validar_transicao(
            estado_atual,
            pedido.estado,
            desfecho=pedido.desfecho,
            desfecho_descricao=pedido.desfecho_descricao,
            motivo_pausa=pedido.observacao,
        )
    except DadosInsuficientesError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Encerrar por abandono exige esforço provado (PRD #318, história 11). A
    # guarda fica aqui, e não em `validar_transicao`, porque depende do
    # histórico de tentativas do caso, que o motor puro não conhece. Mesmo
    # desenho da prorrogação, que também confere histórico na rota.
    if pedido.desfecho == DESFECHO_SEM_RETORNO and not contato_suficiente_para_encerrar(
        tentativas_de_contato(supabase, manifestacao_id, desde=caso.get("reaberta_em")),
        agora_utc(),
        carregar_feriados(supabase),
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Encerrar por sem retorno exige duas tentativas de contato registradas "
                "e cinco dias úteis de espera desde a primeira. Registre as tentativas no caso."
            ),
        )

    try:
        resultado = supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": pedido.estado,
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": pedido.observacao,
                "p_desfecho": pedido.desfecho,
                "p_desfecho_descricao": pedido.desfecho_descricao,
            },
        ).execute()
    except APIError as exc:
        # A regra também vive no banco: check_violation é corrida com outra
        # transição; o resto é falha real e não pode se disfarçar de 409.
        if exc.code == "23514":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transição recusada") from exc
        if exc.code == "P0002":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
        logger.error("Erro na RPC ouvidoria_transicionar (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao transicionar manifestação",
        ) from exc

    row = resultado.data[0] if isinstance(resultado.data, list) else resultado.data

    # Marco T3 (issue #326): o encerramento fica carimbado no caso, no padrão
    # do T1 (validada_em). Falha aqui não desfaz a transição (o movimento é a
    # fonte da verdade do ato); fica no log para conferência.
    agora = agora_utc()
    if pedido.estado == "encerrado":
        try:
            carimbo = {"encerrada_em": agora.isoformat()}
            supabase.table("ouvidoria_protocolos").update(carimbo).eq("id", manifestacao_id).execute()
            row.update(carimbo)
        except APIError:
            logger.error("Falha ao carimbar o T3 da manifestação %s", manifestacao_id)

    # A pausa e a retomada mexem no relógio da área (issue #335). Diferente do
    # T3 acima, uma falha aqui NÃO pode passar em silêncio: sem o carimbo a
    # retomada não teria de onde contar o desconto, e sem o prazo novo a área
    # continuaria devendo resposta num vencimento que já correu durante a espera.
    # Encerrar a partir de `aguardando_manifestante` também fecha a pausa: é o
    # caminho do "sem retorno", e a espera que levou ao abandono é justamente a
    # que o relato separado precisa mostrar.
    efeito = None
    if e_pausa(estado_atual, pedido.estado):
        efeito = efeito_da_pausa(caso, agora, carregar_feriados(supabase))
    elif e_retomada(estado_atual, pedido.estado):
        efeito = efeito_de_fechar_pausa(caso, agora, carregar_feriados(supabase), religar_jobs=True)
    elif pedido.estado == "encerrado" and caso.get("pausada_em"):
        efeito = efeito_de_fechar_pausa(caso, agora, carregar_feriados(supabase), religar_jobs=False)

    if efeito is not None:
        try:
            supabase.table("ouvidoria_protocolos").update(efeito).eq("id", manifestacao_id).execute()
            row.update(efeito)
        except APIError as exc:
            logger.error("Falha ao mover o relógio da manifestação %s (código %s)", manifestacao_id, exc.code)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "O caso mudou de estado, mas o prazo da área não acompanhou. "
                    "Confira a manifestação no painel antes de seguir."
                ),
            ) from exc

    registrar_acesso(supabase, me, manifestacao_id, "transicionar")
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


# =====================================================================
# Reabertura por reincidência (issue #335, PRD #318, história 13)
# =====================================================================


class PedidoReabertura(BaseModel):
    """O que o ouvidor manda para tirar o caso do encerramento. O motivo é
    obrigatório pela mesma razão da devolução: é ele que a área lê no email
    para entender que o problema voltou, e é ele que fica na trilha."""

    motivo: str

    @field_validator("motivo")
    @classmethod
    def _motivo_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not valor:
            raise ValueError("A reabertura exige o motivo")
        return valor


@router.post("/manifestacoes/{manifestacao_id}/reaberturas", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def reabrir_por_reincidencia(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoReabertura,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Devolve à área um caso encerrado que o manifestante voltou a cobrar.

    Mesma ordem da devolução, pelo mesmo motivo: a RPC muda o estado e grava o
    movimento na mesma transação, o prazo é carimbado depois de a transição
    valer, e só então o email sai. O caso NÃO vira protocolo novo: é isso que
    impede a reincidência de inflar o volume de casos novos do PRD 3."""
    try:
        atual = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    caso = atual.data[0]

    if caso.get("status") != "encerrado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só uma manifestação encerrada pode ser reaberta.",
        )

    # Reabrir é despachar para a área, e só o acionamento define para QUEM,
    # com que gravidade, em que prazo e com que extrato. Caso encerrado direto
    # da classificação nunca passou por lá: devolvê-lo à área mandaria ao setor
    # um caso que ele nunca viu, sem nada disso, e sem a elevação de sigilo que
    # a validação aplica (ADR 0034, decisão 8). O caminho ali é registrar
    # manifestação nova, não reabrir.
    if not caso.get("validada_em"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este caso foi encerrado sem nunca ter sido validado e acionado. "
                "Registre uma manifestação nova em vez de reabrir esta."
            ),
        )

    encerrada = caso.get("encerrada_em")
    agora = agora_utc()
    if not encerrada or not dentro_da_janela_de_reincidencia(dt.datetime.fromisoformat(str(encerrada)), agora):
        # Fora da janela o retorno é problema novo, não eco do antigo. Reabrir
        # aqui embaralharia os marcos T0 a T3 do caso velho, que os relatórios
        # do PRD 3 leem como o tempo de UMA tramitação.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Este caso foi encerrado há mais de {JANELA_REINCIDENCIA_DIAS} dias. "
                "Registre uma manifestação nova em vez de reabrir esta."
            ),
        )

    hoje = agora.astimezone(FUSO_HOSPITAL).date()
    destinatario = escolher_destinatario(carregar_responsaveis(supabase, caso.get("setor") or ""), hoje)
    if destinatario is None:
        # Reabrir sem ninguém para receber o caso recomeçaria o relógio contra
        # o vazio, do mesmo jeito que acionar ou devolver sem titular faria.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O setor {caso.get('setor')} não tem titular nem gestor vigente. "
                "Cadastre o responsável antes de reabrir o caso."
            ),
        )

    feriados = carregar_feriados(supabase)
    # Prazo INTEIRO da gravidade, não o resto do antigo: o problema voltou e a
    # área precisa de tempo real para tratá-lo. O relógio velho já foi medido e
    # fechado no encerramento anterior.
    vencimento = calcular_vencimento(agora, carregar_prazo_da_area(supabase, caso.get("gravidade")), feriados)

    # A mesma elevação do acionamento (`validar_e_acionar`), repetida aqui em
    # vez de confiar que ela já foi aplicada: esta rota é a SEGUNDA porta que
    # leva o caso ao setor, e o email dela carrega token do portal, onde o
    # responsável lê a identificação de quem manifestou. Toda porta para o
    # setor reaplica a guarda.
    #
    # Aqui só ELEVA, e por isso não usa `resolver_sigilo`: a reabertura não é
    # ato de classificação (ninguém está dizendo o que o caso é), então ela não
    # tem por que devolver caso nenhum ao índice geral. Caso sem tipo continua
    # sigiloso, que é o fail-closed de sempre.
    sigiloso = bool(caso.get("sigilo_reforcado")) or nasce_sigilosa(caso.get("tipo_manifestacao"))

    try:
        supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": "aguardando_area",
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": f"Caso reaberto por reincidência. Motivo: {pedido.motivo}",
                "p_desfecho": None,
                "p_desfecho_descricao": None,
            },
        ).execute()
    except APIError as exc:
        if exc.code == "23514":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O caso mudou de estado agora mesmo: recarregue o painel antes de reabrir.",
            ) from exc
        logger.error("Erro na RPC ouvidoria_transicionar durante a reabertura (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao reabrir a manifestação",
        ) from exc

    # A marca de reincidência e o prazo novo andam juntos. Os carimbos dos jobs
    # de prazo saem pelo mesmo motivo da devolução: prazo novo sem carimbo
    # zerado é prazo que nenhum degrau da escada cobra. O marco T2 sai também:
    # a resposta do ciclo anterior não vale para o ciclo que começa agora.
    try:
        supabase.table("ouvidoria_protocolos").update(
            {
                "reincidencia": True,
                "reaberta_em": agora.isoformat(),
                "sigilo_reforcado": sigiloso,
                "prazo_area_em": vencimento.isoformat() if vencimento else None,
                # Tudo o que é do ciclo que fechou sai, porque o ciclo que
                # começa tem prazo inteiro novo e ainda não tem nada:
                # - o desfecho, senão o indicador de resolução contaria como
                #   resolvido um caso que ninguém resolveu (a RPC aplica
                #   COALESCE sem olhar o estado, então a limpeza é aqui);
                # - o crédito e o marco da resposta anterior (é o T2 que move
                #   o indicador de cumprimento, e ela não vale para o ciclo
                #   novo). O TEXTO fica: `resposta_da_area` é a resposta
                #   corrente que o ouvidor relê, e a devolução da #334 preserva
                #   o campo pelo mesmo motivo. Desde a #374 o texto não depende
                #   mais dele para sobreviver: o movimento da trilha guarda uma
                #   cópia imutável por ciclo;
                # - o relato de espera, senão o Dossiê diria "este caso já
                #   esperou X, e esse tempo saiu do seu prazo" sobre um prazo
                #   que nasceu agora;
                # - o estouro consumado pela área, porque o ciclo novo tem
                #   prazo INTEIRO novo e a área ainda não deve nada nele. É
                #   aqui que a reincidência se separa da devolução: lá o mesmo
                #   ciclo continua em pé, e o atraso continua contando
                #   (issue #374).
                # `encerrada_em` FICA: é o marco T3 do ciclo anterior, e os
                # relatórios do PRD 3 leem T0 a T3 como o tempo de uma
                # tramitação. Reabrir de novo continua barrado pela guarda de
                # estado logo acima, não por apagar o marco.
                "desfecho": None,
                "desfecho_descricao": None,
                "respondida_em": None,
                "respondida_por_nome": None,
                "area_estourou_em": None,
                "pausada_em": None,
                "minutos_pausados": 0,
            }
            | ouvidoria_prorrogacao.carimbos_a_zerar()
        ).eq("id", manifestacao_id).execute()
    except APIError as exc:
        logger.error("Falha ao gravar a reabertura da manifestação %s (código %s)", manifestacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso saiu do encerramento, mas a reabertura não foi gravada e o setor não foi notificado. "
                "Confira a manifestação no painel."
            ),
        ) from exc

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=ouvidoria_notificacoes.GATILHO_CASO_REABERTO,
        destinatario_nome=destinatario.nome,
        destinatario_email=destinatario.email,
        papel_destinatario=destinatario.papel,
        enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, caso.get("gravidade"), feriados),
        detalhe=pedido.motivo,
    )
    if notificacao is None:
        # Mesma régua do acionamento e da devolução: sem linha na fila não há
        # email, não há registro no caso e não há botão de reenvio, e o ouvidor
        # não pode ler "o setor foi avisado" na tela por cima disso.
        logger.error("Falha ao registrar a reabertura da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso foi reaberto com prazo novo, mas o setor não foi notificado. "
                "Confira a manifestação no painel e reenvie o aviso."
            ),
        )
    ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, feriados)

    if destinatario.alerta_diretoria:
        alertar_diretoria_sem_titular(
            supabase, manifestacao_id, destinatario.nome, caso.get("gravidade") or "", agora, feriados
        )

    registrar_acesso(supabase, me, manifestacao_id, "reabrir_por_reincidencia")
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    row = completo.data[0] if completo.data else caso
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


# =====================================================================
# Tentativa de contato com o manifestante (issue #335, PRD #318)
# =====================================================================

_CAMPOS_TENTATIVA_TUPLA = ("id", "manifestacao_id", "tentada_em", "canal", "observacao", "autor_id", "autor_nome")
_CAMPOS_TENTATIVA = ", ".join(_CAMPOS_TENTATIVA_TUPLA)


class PedidoTentativaDeContato(BaseModel):
    """O registro de uma tentativa de falar com o manifestante. O canal é
    texto livre de propósito: a Ouvidoria liga, manda email, manda mensagem e
    às vezes recado por terceiro, e fechar a lista aqui travaria o ouvidor no
    dia em que aparecer um caminho novo."""

    canal: str
    observacao: str | None = None

    @field_validator("canal")
    @classmethod
    def _canal_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not valor:
            raise ValueError("A tentativa de contato exige o canal usado")
        return valor

    @field_validator("observacao")
    @classmethod
    def _limpar_observacao(cls, valor: str | None) -> str | None:
        return sanitizar_travessao(valor).strip() or None if valor else None


def tentativas_de_contato(supabase, manifestacao_id: str, desde: str | None = None) -> list[dt.datetime]:
    """Quando a Ouvidoria tentou falar com o manifestante NESTE ciclo do caso.

    `desde` é a última reabertura. O recorte existe porque as duas tentativas
    que fecharam o ciclo anterior já satisfaziam a regra dos cinco dias úteis:
    sem ele, um caso reaberto podia ser fechado de novo por "sem retorno" no
    minuto seguinte, sem ninguém ter tentado falar com o manifestante outra vez
    (PRD #318, história 11).

    Falha de leitura devolve lista vazia, e lista vazia recusa o encerramento:
    o erro cai para o lado de não fechar o caso do manifestante por engano."""
    try:
        consulta = (
            supabase.table("ouvidoria_tentativas_contato").select("tentada_em").eq("manifestacao_id", manifestacao_id)
        )
        if desde:
            consulta = consulta.gte("tentada_em", str(desde))
        result = consulta.execute()
        return [dt.datetime.fromisoformat(str(r["tentada_em"])) for r in (result.data or []) if r.get("tentada_em")]
    except Exception:
        logger.warning("Falha ao ler as tentativas de contato da manifestação %s", manifestacao_id)
        return []


@router.post("/manifestacoes/{manifestacao_id}/tentativas-contato", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def registrar_tentativa_de_contato(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoTentativaDeContato,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Grava que a Ouvidoria tentou falar com o manifestante.

    É esta lista que libera (ou não) o encerramento por sem retorno, e é ela
    que o ouvidor lê para saber o que já tentou antes de decidir."""
    carregar_manifestacao(supabase, manifestacao_id)
    linha = {
        "manifestacao_id": manifestacao_id,
        "tentada_em": agora_utc().isoformat(),
        "canal": pedido.canal,
        "observacao": pedido.observacao,
        "autor_id": me["id"],
        "autor_nome": me.get("nome_completo") or me["id"],
    }
    try:
        result = supabase.table("ouvidoria_tentativas_contato").insert(linha).execute()
    except APIError as exc:
        logger.error(
            "Falha ao registrar tentativa de contato da manifestação %s (código %s)", manifestacao_id, exc.code
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao registrar a tentativa de contato",
        ) from exc
    registrar_acesso(supabase, me, manifestacao_id, "registrar_tentativa_de_contato")
    row = result.data[0] if result.data else linha
    return {campo: row.get(campo) for campo in _CAMPOS_TENTATIVA_TUPLA}


@router.get("/manifestacoes/{manifestacao_id}/tentativas-contato")
@limiter.limit("60/minute")
async def listar_tentativas_de_contato(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O que já se tentou NESTE ciclo do caso, em ordem cronológica.

    O recorte é o mesmo da regra que libera o encerramento: a tela conta estas
    tentativas para dizer ao ouvidor se ele já pode encerrar, e mostrar as do
    ciclo anterior faria a conta da tela divergir da conta do servidor. O que
    ficou para trás continua na tabela e na trilha do caso."""
    caso = carregar_manifestacao(supabase, manifestacao_id, campos="id, reaberta_em")
    try:
        consulta = (
            supabase.table("ouvidoria_tentativas_contato")
            .select(_CAMPOS_TENTATIVA)
            .eq("manifestacao_id", manifestacao_id)
        )
        if caso.get("reaberta_em"):
            consulta = consulta.gte("tentada_em", str(caso["reaberta_em"]))
        result = consulta.order("tentada_em").execute()
    except APIError as exc:
        logger.error("Falha ao listar tentativas de contato (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar as tentativas de contato",
        ) from exc
    return {"tentativas": [{campo: r.get(campo) for campo in _CAMPOS_TENTATIVA_TUPLA} for r in (result.data or [])]}


@router.get("/manifestacoes/{manifestacao_id}/respostas")
@limiter.limit("60/minute")
async def listar_respostas_da_area(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O histórico de respostas do caso, um ciclo por resposta da área.

    O Dossiê mostra a resposta CORRENTE, que é a única que a coluna do caso
    guarda: o portal do setor sobrescreve `resposta_da_area` a cada resposta
    nova. Depois de uma devolução por insuficiência, é aqui que o ouvidor relê
    o que recusou e compara com o que veio depois (issue #374, PRD #318,
    histórias 5 e 22).

    A lista vem da trilha imutável, e por isso não tem como encolher. Ao
    contrário das tentativas de contato, ela NÃO é recortada pelo ciclo: o
    ponto do histórico é justamente enxergar as rodadas anteriores.
    """
    # Só existe histórico de caso que existe, e ler o caso primeiro é o que faz
    # manifestação inexistente responder 404 em vez de uma lista vazia.
    carregar_manifestacao(supabase, manifestacao_id, campos="id")
    registrar_acesso(supabase, me, manifestacao_id, "listar_respostas")
    return {"respostas": ouvidoria_respostas.historico(supabase, manifestacao_id)}


# =====================================================================
# Devolução por insuficiência (issue #334, PRD #318, ADR 0034 decisão 12)
# =====================================================================


class PedidoDevolucao(BaseModel):
    """O que o ouvidor manda para devolver uma resposta insuficiente. O motivo
    é obrigatório: é ele que diferencia justificativa de solução, e é ele que a
    área lê no email para saber o que refazer (PRD #318, história 6)."""

    motivo: str

    @field_validator("motivo")
    @classmethod
    def _motivo_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not valor:
            raise ValueError("A devolução exige o motivo da insuficiência")
        return valor


@router.post("/manifestacoes/{manifestacao_id}/devolucoes", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def devolver_por_insuficiencia(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoDevolucao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Devolve ao setor a resposta que não resolve, com meio prazo novo.

    Mesmo desenho do acionamento logo abaixo: a RPC muda o estado e grava o
    movimento na mesma transação, o prazo é carimbado depois de a transição
    valer, e só então o email sai. A ordem existe para que uma falha no meio
    nunca deixe a área avisada de um prazo que o painel não mostra."""
    try:
        atual = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    caso = atual.data[0]

    # A origem tem que ser uma das duas de onde a devolução sai. A checagem
    # vem ANTES de `validar_transicao` porque o grafo ganhou outra aresta para
    # `aguardando_area` desde a issue #335 (a reabertura, saindo de
    # `encerrado`): sem esta guarda, devolver um caso encerrado bateria na
    # exigência de motivo DA REABERTURA e o ouvidor leria uma mensagem sobre um
    # ato que ele não pediu.
    if caso["status"] not in ORIGENS_DA_DEVOLUCAO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não é possível devolver a resposta de um caso em {caso['status']}.",
        )

    try:
        validar_transicao(caso["status"], "aguardando_area", motivo_devolucao=pedido.motivo)
    except DadosInsuficientesError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Só se devolve resposta que existe e que ainda não foi devolvida. O marco
    # T2 é a prova disso: ele nasce quando o setor responde e é apagado logo
    # abaixo, na própria devolução. Sem esta guarda o grafo deixaria passar
    # duas coisas que não são devolução:
    #
    # 1. `em_classificacao -> aguardando_area`, que é o ACIONAMENTO. Devolver
    #    por ali pularia a validação inteira: o caso ficaria com a área sem
    #    gravidade, sem prazo e sem extrato, e o setor leria "sua resposta foi
    #    devolvida" de um caso que nunca viu.
    # 2. A segunda devolução seguida, pelo laço `aguardando_area ->
    #    aguardando_area`. Cada chamada empurraria o vencimento meio prazo
    #    adiante, contornando as duas regras da prorrogação (uma só por caso e
    #    teto de 30 dias úteis da entrada).
    if not caso.get("respondida_em"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este caso não tem resposta do setor esperando análise. "
                "A devolução por insuficiência só existe para recusar uma resposta recebida."
            ),
        )

    agora = agora_utc()
    hoje = agora.astimezone(FUSO_HOSPITAL).date()
    destinatario = escolher_destinatario(carregar_responsaveis(supabase, caso.get("setor") or ""), hoje)
    if destinatario is None:
        # Devolver sem ninguém para receber a devolução recomeçaria o relógio
        # contra o vazio, do mesmo jeito que acionar sem titular faria.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O setor {caso.get('setor')} não tem titular nem gestor vigente. "
                "Cadastre o responsável antes de devolver a resposta."
            ),
        )

    feriados = carregar_feriados(supabase)
    vencimento = vencimento_apos_devolucao(agora, carregar_prazo_da_area(supabase, caso.get("gravidade")), feriados)

    try:
        supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": "aguardando_area",
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": f"Resposta devolvida por insuficiência. Motivo: {pedido.motivo}",
                "p_desfecho": None,
                "p_desfecho_descricao": None,
            },
        ).execute()
    except APIError as exc:
        if exc.code == "23514":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O caso mudou de estado agora mesmo: recarregue o painel antes de devolver.",
            ) from exc
        logger.error("Erro na RPC ouvidoria_transicionar durante a devolução (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao devolver a resposta",
        ) from exc

    # O prazo novo e a limpeza do marco T2 andam juntos: a resposta devolvida
    # deixou de valer como resposta. Sem apagar `respondida_em`, o indicador de
    # cumprimento leria a primeira resposta e diria "cumprido" para um caso que
    # ainda deve resposta.
    #
    # `resposta_da_area` continua gravado: é a resposta corrente, e o ouvidor a
    # relê enquanto espera a refeita. O TEXTO dela não depende mais desse campo
    # para sobreviver, porque o movimento da trilha guarda a sua cópia
    # imutável, uma por ciclo (issue #374, `ouvidoria_respostas`).
    #
    # O que NÃO sai é o estouro consumado: ele é carimbado aqui, com o
    # vencimento e a resposta que valiam antes de o prazo novo entrar. É o que
    # impede a devolução de apagar o atraso do ciclo que acabou, e com ele a
    # leitura honesta do indicador (issue #374, PRD #318 história 5).
    #
    # Os carimbos dos jobs de prazo saem junto, pelo mesmo motivo da
    # prorrogação: prazo novo sem carimbo zerado é prazo que nenhum degrau
    # cobra. A função mora lá porque nasceu lá; a regra é a mesma.
    estourou = estouro_consumado(
        _instante(caso.get("prazo_area_em")),
        _instante(caso.get("respondida_em")),
        agora,
        _instante(caso.get("area_estourou_em")),
    )
    try:
        supabase.table("ouvidoria_protocolos").update(
            {
                "prazo_area_em": vencimento.isoformat() if vencimento else None,
                "respondida_em": None,
                "respondida_por_nome": None,
                "area_estourou_em": estourou.isoformat() if estourou else None,
            }
            | ouvidoria_prorrogacao.carimbos_a_zerar()
        ).eq("id", manifestacao_id).execute()
    except APIError as exc:
        logger.error("Falha ao gravar o prazo da devolução da manifestação %s (código %s)", manifestacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso voltou para a área, mas o prazo novo não foi gravado e o setor não foi notificado. "
                "Confira a manifestação no painel."
            ),
        ) from exc

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=ouvidoria_notificacoes.GATILHO_RESPOSTA_DEVOLVIDA,
        destinatario_nome=destinatario.nome,
        destinatario_email=destinatario.email,
        papel_destinatario=destinatario.papel,
        enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, caso.get("gravidade"), feriados),
        detalhe=pedido.motivo,
    )
    if notificacao is None:
        # Mesma régua do acionamento: sem linha na fila não há email, não há
        # registro no caso e não há botão de reenvio. O prazo já foi encurtado
        # contra um setor que ninguém avisou, e o ouvidor não pode ler "o setor
        # foi avisado" na tela por cima disso.
        logger.error("Falha ao registrar a devolução da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso voltou para a área com o prazo novo, mas o setor não foi notificado. "
                "Confira a manifestação no painel e reenvie o aviso."
            ),
        )
    ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, feriados)

    # Devolver para setor sem titular vigente recomeça o relógio contra um
    # buraco de cadastro. A Diretoria é avisada, como no acionamento
    # (ADR 0034, decisão 5).
    if destinatario.alerta_diretoria:
        alertar_diretoria_sem_titular(
            supabase, manifestacao_id, destinatario.nome, caso.get("gravidade") or "", agora, feriados
        )

    registrar_acesso(supabase, me, manifestacao_id, "devolver_por_insuficiencia")
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    row = completo.data[0] if completo.data else caso
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


# =====================================================================
# Validação e acionamento da área (issue #325, ADR 0034 decisões 3, 5 e 7)
# =====================================================================

_CAMPOS_RESPONSAVEL_TUPLA = ("id", "setor", "papel", "nome", "email", "vigencia_inicio", "vigencia_fim")
_CAMPOS_RESPONSAVEL = ", ".join(_CAMPOS_RESPONSAVEL_TUPLA)


class PedidoValidacao(BaseModel):
    """O que o ouvidor confere antes de qualquer setor ser acionado: tipo,
    área e gravidade. Nada disso vem da IA: a sugestão da Ana vive em
    `classificacao_ia` e nunca chega aqui sozinha (ADR 0034, decisão 10).

    `extrato_para_o_setor` é o texto que vai por email ao responsável, escrito
    pelo ouvidor. Obrigatório em todo acionamento: o campo é opcional no schema
    só para a rota poder recusar com uma mensagem que explica o porquê, em vez
    do erro genérico do pydantic."""

    tipo_manifestacao: TipoManifestacao
    categoria: str | None = None
    sigilo_reforcado: bool | None = None
    setor: str
    gravidade: Literal["critico", "alto", "medio", "baixo"]
    observacao: str | None = None
    extrato_para_o_setor: str | None = None

    @field_validator("setor")
    @classmethod
    def _classificacao_nao_vazia(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo da classificação não pode ser vazio")
        return valor

    @field_validator("categoria")
    @classmethod
    def _rotulo_limpo(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None

    @field_validator("observacao", "extrato_para_o_setor")
    @classmethod
    def _observacao_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None


def extrato_do_acionamento(escrito_pelo_ouvidor: str | None) -> str:
    """O texto que o responsável do setor vai ler no email.

    Obrigatório em todo acionamento, sem exceção (decisão de 25/08). Nem o
    `resumo` nem o relato servem de padrão: os dois carregam a palavra de quem
    manifestou (no canal aberto, o que o cidadão digitou; no canal da Ana, texto
    gerado a partir da conversa com ele), e o responsável do setor é gente de
    fora da Ouvidoria, sem login no app. Uma regra só, sem caso especial para
    alguém lembrar: todo email que sai da Ouvidoria leva texto escrito pela
    Ouvidoria (ADR 0034, decisão 8)."""
    if escrito_pelo_ouvidor:
        return escrito_pelo_ouvidor
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            "O acionamento exige o extrato para o setor. "
            "Escreva com as suas palavras o que a área precisa resolver: o relato original não sai da Ouvidoria."
        ),
    )


def carregar_prazo_da_area(supabase, gravidade: str) -> Prazo:
    """A célula da tabela de prazos que vale para a resposta do setor.

    Célula ausente vira prazo indefinido em vez de erro: a Diretoria pode ter
    esvaziado a linha, e travar a validação por isso deixaria o caso parado na
    fila da ouvidoria, que é pior do que acionar sem contagem regressiva."""
    try:
        result = (
            supabase.table("ouvidoria_prazos")
            .select("valor, unidade")
            .eq("gravidade", gravidade)
            .eq("marco", "area_resposta")
            .execute()
        )
    except Exception:
        logger.warning("Falha ao ler o prazo de %s: o acionamento segue sem vencimento", gravidade)
        return Prazo(valor=None)
    if not result.data:
        return Prazo(valor=None)
    linha = result.data[0]
    return Prazo(valor=linha.get("valor"), unidade=linha.get("unidade") or "dias_uteis")


def carregar_responsaveis(supabase, setor: str) -> list[dict]:
    """O cadastro de quem responde pelo setor. A vigência é filtrada em
    Python, pela função pura, e não na query: a regra de quem responde hoje é
    domínio, não detalhe de SQL."""
    result = supabase.table("ouvidoria_setor_responsaveis").select(_CAMPOS_RESPONSAVEL).eq("setor", setor).execute()
    return result.data or []


def alertar_diretoria_sem_titular(
    supabase,
    manifestacao_id: str,
    gestor_nome: str,
    gravidade: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> None:
    """Setor acionado sem titular vigente sobe ao gestor E avisa a Diretoria
    (ADR 0034, decisão 5): o alerta é o que impede o buraco no cadastro de
    virar rotina silenciosa."""
    diretores = ouvidoria_notificacoes.carregar_diretoria_executiva(supabase)
    if not diretores:
        logger.warning("Setor sem titular na manifestação %s e sem Diretoria com email cadastrado", manifestacao_id)
        return

    for diretor in diretores:
        alerta = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=ouvidoria_notificacoes.GATILHO_ALERTA_SEM_TITULAR,
            destinatario_nome=diretor.get("nome_completo") or diretor["email"],
            destinatario_email=diretor["email"],
            papel_destinatario="diretoria_executiva",
            # A janela comercial vale para toda notificação da leva, não só
            # para o acionamento: setor sem titular não é urgência que
            # justifique acordar a Diretoria de madrugada. Caso crítico é a
            # exceção, e é a mesma regra do email ao setor.
            enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, gravidade, feriados),
            detalhe=gestor_nome,
        )
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, alerta, agora, feriados)


class PedidoResponsavel(BaseModel):
    """Quem passa a responder pelo setor. `vigencia_fim` vazio é o caso comum:
    o titular de hoje, sem data de saída marcada."""

    setor: str
    papel: Literal["titular", "substituto", "gestor"]
    nome: str
    email: EmailStr
    vigencia_inicio: dt.date | None = None
    vigencia_fim: dt.date | None = None

    @field_validator("setor", "nome")
    @classmethod
    def _texto_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("campo obrigatório do cadastro não pode ser vazio")
        return valor

    @model_validator(mode="after")
    def _vigencia_coerente(self) -> "PedidoResponsavel":
        inicio = self.vigencia_inicio or dt.date.today()
        if self.vigencia_fim and self.vigencia_fim < inicio:
            raise ValueError("a vigência não pode terminar antes de começar")
        return self


class EdicaoResponsavel(BaseModel):
    """Edição do cadastro. É por aqui que a vigência do titular se encerra
    quando ele sai do papel."""

    nome: str
    email: EmailStr
    vigencia_inicio: dt.date | None = None
    vigencia_fim: dt.date | None = None

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not re.search(r"\w", valor):
            raise ValueError("o nome do responsável não pode ser vazio")
        return valor

    @model_validator(mode="after")
    def _vigencia_coerente(self) -> "EdicaoResponsavel":
        if self.vigencia_fim and self.vigencia_inicio and self.vigencia_fim < self.vigencia_inicio:
            raise ValueError("a vigência não pode terminar antes de começar")
        return self


def exigir_setor_da_taxonomia(supabase, setor: str) -> None:
    """Responsável só entra em setor que existe na taxonomia da casa (tabela
    `setores`, migration 027).

    Sem isso o cadastro viraria uma lista de nomes livres que nunca casaria com
    o setor da manifestação, e o acionamento cairia sempre no gestor."""
    try:
        result = supabase.table("setores").select("nome").eq("nome", setor).eq("ativo", True).execute()
    except Exception:
        logger.warning("Falha ao conferir o setor %s na taxonomia", setor)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível conferir o setor agora. Tente de novo em instantes.",
        ) from None
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"O setor {setor} não existe na lista de setores ativos do hospital",
        )


@router.get("/responsaveis")
@limiter.limit("60/minute")
async def listar_responsaveis(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Quem responde por cada setor. O ouvidor precisa enxergar o cadastro para
    saber por que uma demanda subiu ao gestor."""
    result = supabase.table("ouvidoria_setor_responsaveis").select(_CAMPOS_RESPONSAVEL).order("setor").execute()
    return {
        "responsaveis": [{campo: row.get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA} for row in (result.data or [])]
    }


@router.post("/responsaveis", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def cadastrar_responsavel(
    request: Request,
    pedido: PedidoResponsavel,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Cadastra titular, substituto ou gestor de um setor."""
    exigir_setor_da_taxonomia(supabase, pedido.setor)
    linha = {
        "setor": pedido.setor,
        "papel": pedido.papel,
        "nome": pedido.nome,
        "email": str(pedido.email),
        "vigencia_inicio": (pedido.vigencia_inicio or agora_utc().astimezone(FUSO_HOSPITAL).date()).isoformat(),
        "vigencia_fim": pedido.vigencia_fim.isoformat() if pedido.vigencia_fim else None,
    }
    try:
        result = supabase.table("ouvidoria_setor_responsaveis").insert(linha).execute()
    except APIError as exc:
        logger.error("Falha ao cadastrar responsável do setor (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível cadastrar o responsável",
        ) from exc
    row = result.data[0] if result.data else linha
    _destravar_se_o_cadastro_melhorou(supabase, row)
    return {campo: row.get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA}


def _destravar_se_o_cadastro_melhorou(supabase, responsavel: dict) -> None:
    """Devolve à varredura os casos do setor, quando o ato deu à escada alguém
    a quem falar, agora ou em breve (issue #373).

    Duas condições, e as duas importam:

    - o papel tem que ser um dos que ESTA escada consulta. O substituto, mesmo
      vigente, não é destinatário de degrau nenhum daqui: quem fala com ele é o
      degrau do vencimento, que mora em `ouvidoria_cobranca`.
    - a vigência não pode estar ENCERRADA. Encerrar é o caminho documentado de
      entregar um setor, e ele piora o cadastro.

    Vigência que só começa amanhã destrava: nada roda quando ela entra em vigor,
    então esperar deixaria o caso preso mesmo depois de o setor voltar a ter
    titular. O custo é uma rodada que re-carimba e manda um alerta a mais, o que
    é bem melhor que um caso sem cobrança para sempre.

    Destravar fora disso devolveria os protocolos à varredura só para serem
    re-carimbados, com alerta novo ao admin a cada edição de responsável."""
    if responsavel.get("papel") not in ouvidoria_escalonamento.PAPEIS_DA_ESCADA:
        return
    fim = responsavel.get("vigencia_fim")
    if fim and dt.date.fromisoformat(str(fim)) < agora_utc().astimezone(FUSO_HOSPITAL).date():
        return
    ouvidoria_escalonamento.destravar_setor(supabase, responsavel.get("setor") or "")


@router.put("/responsaveis/{responsavel_id}")
@limiter.limit("30/minute")
async def editar_responsavel(
    request: Request,
    responsavel_id: str,
    pedido: EdicaoResponsavel,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Edita o cadastro. Encerrar a vigência aqui é o que faz a próxima demanda
    do setor subir ao gestor, sem programador no meio."""
    mudanca: dict = {
        "nome": pedido.nome,
        "email": str(pedido.email),
        "vigencia_fim": pedido.vigencia_fim.isoformat() if pedido.vigencia_fim else None,
    }
    if pedido.vigencia_inicio:
        mudanca["vigencia_inicio"] = pedido.vigencia_inicio.isoformat()

    try:
        result = supabase.table("ouvidoria_setor_responsaveis").update(mudanca).eq("id", responsavel_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado")
    # Reabrir uma vigência encerrada por engano é o outro caminho de corrigir o
    # cadastro, e destrava os casos do setor do mesmo jeito (issue #373).
    _destravar_se_o_cadastro_melhorou(supabase, result.data[0])
    return {campo: result.data[0].get(campo) for campo in _CAMPOS_RESPONSAVEL_TUPLA}


@router.delete("/responsaveis/{responsavel_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def remover_responsavel(
    request: Request,
    responsavel_id: str,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Tira a pessoa do cadastro. Para guardar a história de quem respondeu
    quando, o caminho é encerrar a vigência, não remover."""
    supabase.table("ouvidoria_setor_responsaveis").delete().eq("id", responsavel_id).execute()


class PedidoClassificacao(BaseModel):
    """O ato de classificar, que é também a única porta do sigilo (issue #372,
    decisão 5).

    `categoria` é o rótulo humano do caso, com as palavras de quem classificou;
    quem decide o sigilo é o `tipo_manifestacao`, que é lista fechada.
    `sigilo_reforcado` ausente mantém o sigilo de hoje: descer é ato
    consciente, não efeito colateral de classificar."""

    tipo_manifestacao: TipoManifestacao
    categoria: str | None = None
    sigilo_reforcado: bool | None = None

    @field_validator("categoria")
    @classmethod
    def _rotulo_limpo(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None


def registrar_movimento_de_classificacao(supabase, me: dict, caso: dict, observacao: str) -> None:
    """A classificação entra na trilha imutável do caso.

    Não é transição de estado (classificar não move o caso na máquina), então o
    insert é direto, no molde do movimento de abertura. Melhor esforço: a
    trilha não pode derrubar o ato que ela registra."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": caso["id"],
                "estado_anterior": caso.get("status"),
                "estado_novo": caso.get("status"),
                "autor_id": me["id"],
                "autor_nome": me.get("nome_completo") or me["id"],
                "observacao": observacao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de classificação da manifestação %s", caso.get("id"))


@router.post("/manifestacoes/{manifestacao_id}/classificacao")
@limiter.limit("30/minute")
async def classificar_manifestacao(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoClassificacao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Classifica a manifestação e, no mesmo ato, resolve o sigilo dela.

    A porta é uma só, para sobe e desce: o caso que chegou pela Ana e virou
    denúncia sobe, e o do canal aberto, que nasce fail-closed sem categoria
    nenhuma, desce quando o ouvidor diz o que ele é. Vale em qualquer estado do
    caso, porque um caso já com a área também pode ter sido mal classificado."""
    try:
        atual = (
            supabase.table("ouvidoria_protocolos")
            .select("id, status, sigilo_reforcado, tipo_manifestacao, categoria")
            .eq("id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")

    caso = atual.data[0]
    try:
        sigiloso = resolver_sigilo(
            pedido.tipo_manifestacao,
            sigilo_atual=bool(caso.get("sigilo_reforcado")),
            sigilo_pedido=pedido.sigilo_reforcado,
        )
    except SigiloTravadoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    classificacao = {"tipo_manifestacao": pedido.tipo_manifestacao, "sigilo_reforcado": sigiloso}
    if pedido.categoria:
        classificacao["categoria"] = pedido.categoria
    atualizada = supabase.table("ouvidoria_protocolos").update(classificacao).eq("id", manifestacao_id).execute()

    if not atualizada.data:
        # Antes de gravar a trilha, e não depois: a trilha é imutável, e um
        # movimento dizendo "Sigilo reforçado retirado" para uma mudança que
        # nunca chegou à tabela seria mentira que ninguém pode apagar. A tela
        # também lê o Dossiê desta resposta, e um dicionário vazio apagaria
        # dela o caso que o ouvidor está lendo.
        logger.error("Classificação não encontrou a manifestação %s no update", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível gravar a classificação",
        )

    registrar_movimento_de_classificacao(supabase, me, caso, _observacao_da_classificacao(pedido, caso, sigiloso))
    registrar_acesso(supabase, me, manifestacao_id, "classificacao")

    row = atualizada.data[0]
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA}


def _observacao_da_classificacao(pedido: PedidoClassificacao, caso: dict, sigiloso: bool) -> str:
    """O que a trilha conta: o que o caso virou e o que aconteceu com o sigilo.

    A mudança de sigilo é dita com todas as letras, e só quando MUDA: é o que
    permite auditar depois quem tirou um caso da vista de todos, e quem o
    devolveu."""
    observacao = f"Classificada como {ROTULO_TIPO[pedido.tipo_manifestacao]}"
    if pedido.categoria:
        observacao = f"{observacao} ({pedido.categoria})"
    antes = bool(caso.get("sigilo_reforcado"))
    if sigiloso and not antes:
        observacao = f"{observacao}. Sigilo reforçado aplicado."
    elif antes and not sigiloso:
        observacao = f"{observacao}. Sigilo reforçado retirado: o caso volta ao índice geral."
    return observacao


@router.post("/manifestacoes/{manifestacao_id}/validar")
@limiter.limit("30/minute")
async def validar_e_acionar(
    request: Request,
    manifestacao_id: str,
    pedido: PedidoValidacao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Valida a manifestação e aciona a área na mesma ação.

    É a única porta do despacho: nenhum processo automático acorda um setor
    (ADR 0034, decisão 3). O vencimento é calculado aqui e PERSISTIDO: mudar a
    tabela de prazos depois não move o prazo que o setor recebeu por email."""
    try:
        atual = (
            supabase.table("ouvidoria_protocolos")
            .select("id, status, sigilo_reforcado, tipo_manifestacao")
            .eq("id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")

    caso = atual.data[0]
    # Acionar é ir de `em_classificacao` para `aguardando_area`. Chegar aqui
    # vindo de `respondido` ou de `aguardando_area` seria DEVOLUÇÃO, que tem
    # porta própria e regra própria (motivo obrigatório, meio prazo). O grafo
    # sozinho não separa mais os dois desde a issue #334, então quem separa é
    # esta guarda: sem ela, revalidar acordaria o setor de novo pelo mesmo
    # motivo e ainda daria prazo cheio a quem respondeu mal.
    if e_devolucao(caso["status"], "aguardando_area"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Este caso já está com a área. Para recusar a resposta recebida, use a devolução por "
                "insuficiência, que exige o motivo e recalcula o prazo."
            ),
        )
    try:
        validar_transicao(caso["status"], "aguardando_area")
    except TransicaoInvalidaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # A validação é onde o tipo é DECIDIDO, então é aqui que a regra do sigilo
    # vale de novo, pela mesma função da rota de classificação: caso que chegou
    # pela Ana nasce sem tipo (logo, sigiloso) e vira denúncia ou elogio na mão
    # do ouvidor. Sem reavaliar, o email da denúncia iria ao setor denunciado
    # com o nome de quem manifestou e sem o selo, porque `_identificacao` só
    # olha estas colunas.
    #
    # Sobe e desce, como na rota de classificação: o caso do canal aberto que
    # se revela um elogio volta ao índice de todos aqui mesmo, sem o ouvidor
    # precisar de uma segunda tela. Descer continua sendo ato explícito.
    try:
        sigiloso = resolver_sigilo(
            pedido.tipo_manifestacao,
            sigilo_atual=bool(caso.get("sigilo_reforcado")),
            sigilo_pedido=pedido.sigilo_reforcado,
        )
    except SigiloTravadoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    extrato = extrato_do_acionamento(pedido.extrato_para_o_setor)

    agora = agora_utc()
    hoje = agora.astimezone(FUSO_HOSPITAL).date()
    destinatario = escolher_destinatario(carregar_responsaveis(supabase, pedido.setor), hoje)
    if destinatario is None:
        # Sem titular e sem gestor não há para quem despachar. Recusar é a
        # única saída honesta: acionar assim mandaria a demanda para o vazio e
        # o prazo correria contra ninguém.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"O setor {pedido.setor} não tem titular nem gestor vigente. "
                "Cadastre o responsável antes de acionar a área."
            ),
        )

    feriados = carregar_feriados(supabase)
    vencimento = calcular_vencimento(agora, carregar_prazo_da_area(supabase, pedido.gravidade), feriados)

    # A classificação que o ouvidor digitou é gravada antes da transição: se a
    # corrida com outra transição recusar o passo, o que sobra no caso é o
    # trabalho de classificação, que não faz mal a ninguém. O extrato entra
    # junto pelo mesmo motivo, e porque o email é montado a partir do caso: o
    # que o setor lê tem que estar gravado antes de o email sair.
    #
    # O marco T1 e o prazo da área NÃO entram aqui: eles descrevem um
    # acionamento que aconteceu, e carimbá-los antes da RPC deixaria um caso
    # recusado com hora de validação e vencimento de um despacho que nunca
    # existiu. Vão logo depois da transição valer.
    classificacao = {
        "tipo_manifestacao": pedido.tipo_manifestacao,
        "sigilo_reforcado": sigiloso,
        "setor": pedido.setor,
        "gravidade": pedido.gravidade,
        "extrato_para_o_setor": extrato,
    }
    if pedido.categoria:
        classificacao["categoria"] = pedido.categoria
    supabase.table("ouvidoria_protocolos").update(classificacao).eq("id", manifestacao_id).execute()

    observacao = f"Validada e acionada: setor {pedido.setor}, gravidade {pedido.gravidade}"
    if pedido.observacao:
        observacao = f"{observacao}. {pedido.observacao}"
    try:
        resultado = supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": manifestacao_id,
                "p_estado_novo": "aguardando_area",
                "p_autor_id": me["id"],
                "p_autor_nome": me.get("nome_completo") or me["id"],
                "p_observacao": observacao,
                "p_desfecho": None,
                "p_desfecho_descricao": None,
            },
        ).execute()
    except APIError as exc:
        if exc.code == "23514":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transição recusada") from exc
        logger.error("Erro na RPC ouvidoria_transicionar durante a validação (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao acionar a área",
        ) from exc

    # Agora a transição existe: o marco e o vencimento podem ser carimbados.
    # Falha aqui é falha de infraestrutura e não pode passar em silêncio, senão
    # o setor recebe um email com prazo que o painel não mostra.
    #
    # `dados_incompletos` fica de fora: ele marca identificação pela metade
    # (nome sem contato, migration 064), e a validação classifica tipo, área e
    # gravidade sem pedir nem completar dado de quem manifestou. Zerar aqui
    # apagaria a sinalização do caso pela metade sem ninguém ter completado nada.
    try:
        supabase.table("ouvidoria_protocolos").update(
            {
                "prazo_area_em": vencimento.isoformat() if vencimento else None,
                "validada_em": agora.isoformat(),
                "validada_por": me["id"],
            }
        ).eq("id", manifestacao_id).execute()
    except APIError as exc:
        logger.error("Falha ao gravar o marco T1 da manifestação %s (código %s)", manifestacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso mudou de estado, mas o prazo não foi gravado e o setor não foi notificado. "
                "Confira a manifestação no painel."
            ),
        ) from exc

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
        destinatario_nome=destinatario.nome,
        destinatario_email=destinatario.email,
        papel_destinatario=destinatario.papel,
        enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, pedido.gravidade, feriados),
    )
    if notificacao is None:
        # Sem linha na fila não há email, não há registro no caso e não há botão
        # de reenvio: o prazo correria contra um setor que ninguém avisou. Mesma
        # régua da gravação do marco T1 acima, o caso não pode mentir ao ouvidor.
        logger.error("Falha ao registrar o acionamento da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "O caso mudou de estado, mas o setor não foi notificado e o acionamento não ficou registrado. "
                "Confira a manifestação no painel."
            ),
        )
    ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, feriados)

    if destinatario.alerta_diretoria:
        alertar_diretoria_sem_titular(supabase, manifestacao_id, destinatario.nome, pedido.gravidade, agora, feriados)

    if pedido.gravidade == "critico":
        # Caso crítico não espera degrau nenhum da escada: a Diretoria
        # Executiva sabe no momento da validação (PRD #318, história 18).
        ouvidoria_escalonamento.alertar_diretoria_caso_critico(supabase, manifestacao_id, agora, feriados)

    registrar_acesso(supabase, me, manifestacao_id, "validar_e_acionar")
    row = resultado.data[0] if isinstance(resultado.data, list) else resultado.data
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    if completo.data:
        row = completo.data[0]
    return {campo: row.get(campo) for campo in _CAMPOS_DOSSIE_TUPLA} | _projetar_prazo(row, agora, feriados)


@router.get("/manifestacoes/{manifestacao_id}/notificacoes")
@limiter.limit("60/minute")
async def listar_notificacoes(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Toda notificação que o caso já gerou, da mais recente para a mais antiga.

    É o que prova a cobrança (ADR 0034, decisão 7) e o que alimenta o botão de
    reenvio."""
    carregar_manifestacao(supabase, manifestacao_id)
    result = (
        supabase.table("ouvidoria_notificacoes")
        .select(ouvidoria_notificacoes.CAMPOS_NOTIFICACAO)
        .eq("manifestacao_id", manifestacao_id)
        .order("criada_em", desc=True)
        .execute()
    )
    return {
        "notificacoes": [
            {campo: row.get(campo) for campo in ouvidoria_notificacoes.CAMPOS_NOTIFICACAO_TUPLA}
            for row in (result.data or [])
        ]
    }


@router.post("/manifestacoes/{manifestacao_id}/notificacoes/{notificacao_id}/reenviar", status_code=201)
@limiter.limit("30/minute")
async def reenviar_notificacao(
    request: Request,
    manifestacao_id: str,
    notificacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Manda a mesma notificação de novo, quando o setor diz que não recebeu.

    O reenvio nasce como registro próprio em vez de reescrever o original: a
    data do primeiro envio é o que prova quando a cobrança começou.

    Sai na hora, mesmo fora do expediente: a janela comercial existe para o
    disparo automático não acordar ninguém de madrugada, e aqui há uma pessoa
    da Ouvidoria decidindo mandar."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .select(ouvidoria_notificacoes.CAMPOS_NOTIFICACAO)
            .eq("id", notificacao_id)
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificação não encontrada")

    anterior = result.data[0]
    agora = agora_utc()
    copia = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=manifestacao_id,
        gatilho=anterior["gatilho"],
        destinatario_nome=anterior["destinatario_nome"],
        destinatario_email=anterior["destinatario_email"],
        papel_destinatario=anterior.get("papel_destinatario"),
        enviar_a_partir_de=agora,
        detalhe=anterior.get("detalhe"),
    )
    if copia is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar o reenvio",
        )

    entregue = ouvidoria_notificacoes.despachar(supabase, copia, agora, carregar_feriados(supabase))
    registrar_acesso(supabase, me, manifestacao_id, "reenviar_notificacao")
    return {"id": copia["id"], "gatilho": copia["gatilho"], "entregue": entregue}


# =====================================================================
# Prorrogação de prazo (issue #333, PRD #318, ADR 0034 decisão 12)
# =====================================================================


class DecisaoDeProrrogacao(BaseModel):
    """A decisão do ouvidor sobre o pedido da área. A justificativa é
    opcional, mas vai por email a quem pediu quando existir."""

    aprovada: bool
    justificativa: str | None = None

    @field_validator("justificativa")
    @classmethod
    def _justificativa_limpa(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return sanitizar_travessao(valor).strip() or None


@router.get("/manifestacoes/{manifestacao_id}/prorrogacoes")
@limiter.limit("60/minute")
async def listar_prorrogacoes(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O pedido de prorrogação do caso, quando existe. É uma lista de zero ou
    um: a regra da casa permite um pedido por manifestação.

    Cada pedido pendente vem com o veredito da aprovação já calculado, para a
    tela avisar o ouvidor ANTES de ele confirmar em vez de deixá-lo levar o 409
    de surpresa (issue #373)."""
    # Os campos do cálculo, não o `id, protocolo` do default: sem entrada e sem
    # prazo vigente não há prazo novo a propor, e o aviso diria "teto alcançado"
    # em todo caso.
    caso = carregar_manifestacao(
        supabase, manifestacao_id, "id, protocolo, status, contato_em, data_abertura, prazo_area_em"
    )
    pedido = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    if not pedido:
        return {"prorrogacoes": []}
    resumo = ouvidoria_prorrogacao.resumo_da_aprovacao(caso, pedido, agora_utc(), carregar_feriados(supabase))
    return {"prorrogacoes": [pedido | resumo]}


def _devolver_claim_da_prorrogacao(supabase, prorrogacao_id: str) -> None:
    """Solta o claim da decisão quando o efeito seguinte falhou.

    `prazo_novo` NÃO entra aqui: ele nasce no insert do portal, não na
    decisão. Zerá-lo deixaria o pedido de volta em pendente sem a proposta que
    a área fez, e o reenvio do email de "prorrogação solicitada" diria "prazo
    proposto: sem prazo definido". A aprovação seguinte recalcula o valor de
    qualquer jeito.

    Melhor esforço: se nem isto passar, o pedido fica decidido com o prazo
    antigo, e o log é o rastro para a Ouvidoria refazer na mão."""
    try:
        (
            supabase.table("ouvidoria_prorrogacoes")
            .update(
                {
                    "status": ouvidoria_prorrogacao.PENDENTE,
                    "decidida_em": None,
                    "decidida_por": None,
                    "decidida_por_nome": None,
                    "decisao_justificativa": None,
                }
            )
            .eq("id", prorrogacao_id)
            .execute()
        )
    except Exception:
        logger.error(
            "Falha ao devolver o claim da prorrogação %s: decidir de novo exige a mão da Ouvidoria",
            prorrogacao_id,
        )


@router.post("/manifestacoes/{manifestacao_id}/prorrogacoes/{prorrogacao_id}/decidir")
@limiter.limit("30/minute")
async def decidir_prorrogacao(
    request: Request,
    manifestacao_id: str,
    prorrogacao_id: str,
    decisao: DecisaoDeProrrogacao,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """O ouvidor aprova ou nega o pedido da área (PRD #318, história 3).

    Aprovar move o vencimento do caso; negar deixa o prazo onde estava. Nos
    dois caminhos o ato vira movimento na trilha e email registrado a quem
    pediu. O prazo novo é recalculado aqui, e não copiado do pedido: entre o
    pedido e a decisão o teto de 30 dias úteis da entrada pode ter ficado mais
    perto, e quem manda é ele."""
    # O Dossiê inteiro, não só o `id`: a decisão precisa de estado, entrada,
    # prazo e gravidade, e o email é montado a partir do caso.
    encontrado = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    if not encontrado.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    caso = encontrado.data[0]
    pedido = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    if pedido is None or pedido["id"] != prorrogacao_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido de prorrogação não encontrado")
    if pedido["status"] != ouvidoria_prorrogacao.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido de prorrogação já foi decidido.",
        )
    if caso.get("status") != ouvidoria_prorrogacao.AGUARDANDO_AREA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ouvidoria_prorrogacao.CASO_JA_ANDOU,
        )

    agora = agora_utc()
    feriados = carregar_feriados(supabase)
    mudanca = {
        "status": ouvidoria_prorrogacao.APROVADA if decisao.aprovada else ouvidoria_prorrogacao.NEGADA,
        "decidida_em": agora.isoformat(),
        "decidida_por": me["id"],
        "decidida_por_nome": me.get("nome_completo") or me["id"],
        "decisao_justificativa": decisao.justificativa,
    }

    prazo_novo = None
    if decisao.aprovada:
        # A MESMA regra que o painel já mostrou ao ouvidor, e o mesmo texto: a
        # tela e a recusa não podem discordar. Calcular o prazo por fora daqui
        # era o que fazia uma data ilegível virar 500 em vez de 409.
        recusa = ouvidoria_prorrogacao.motivo_para_nao_aprovar(caso, pedido, agora, feriados)
        if recusa:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=recusa)
        prazo_novo = ouvidoria_prorrogacao.prazo_novo_proposto(caso, pedido, feriados)
        mudanca["prazo_novo"] = prazo_novo.isoformat()

    # A decisão é gravada com CLAIM: o update carrega a condição
    # `status = pendente`, então de dois ouvidores decidindo ao mesmo tempo só
    # o primeiro acha linha para atualizar. O check em Python lá em cima dá a
    # mensagem boa no caso comum, mas não serve de trava: entre ele e este
    # update há uma viagem ao banco, e é nela que a corrida acontece. Mesmo
    # idioma de `ouvidoria_notificacoes._reivindicar` e
    # `ouvidoria_cobranca._reivindicar_caso`.
    #
    # Tudo que tem efeito visível (mover o prazo, trilha, email) vem DEPOIS
    # daqui: duas linhas na trilha imutável e dois emails de decisão não têm
    # como ser desfeitos.
    try:
        claim = (
            supabase.table("ouvidoria_prorrogacoes")
            .update(mudanca)
            .eq("id", prorrogacao_id)
            .eq("status", ouvidoria_prorrogacao.PENDENTE)
            .execute()
        )
    except APIError as exc:
        logger.error("Falha ao gravar a decisão da prorrogação %s (código %s)", prorrogacao_id, exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar a decisão agora. Tente de novo.",
        ) from exc
    if not claim.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este pedido de prorrogação já foi decidido.",
        )

    # O prazo novo passa a valer, e os carimbos dos jobs de prazo saem junto.
    #
    # Carimbo é o que tira o caso da fila de cada job: mover o vencimento para
    # frente e deixar os carimbos do prazo VELHO faria nenhum degrau do prazo
    # novo acontecer (a véspera não avisa, a cobrança não sai, a escada não
    # sobe), e ainda deixaria a trilha dizendo duas coisas contrárias, prazo em
    # setembro com rompido em agosto. Zerar aqui é seguro porque a regra
    # permite um pedido por manifestação: não existe carimbo de outro ciclo
    # para apagar sem querer. Negar não passa por aqui, então a cobrança que já
    # saiu continua valendo.
    #
    # O update repete a condição do pré-check (`status = aguardando_area`):
    # entre a leitura do caso e esta escrita o setor pode ter respondido, e
    # mover o prazo de um caso já respondido reabriria a cobrança dele.
    if prazo_novo is not None:
        try:
            movido = (
                supabase.table("ouvidoria_protocolos")
                .update({"prazo_area_em": prazo_novo.isoformat()} | ouvidoria_prorrogacao.carimbos_a_zerar())
                .eq("id", manifestacao_id)
                .eq("status", ouvidoria_prorrogacao.AGUARDANDO_AREA)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            # Largo de propósito: timeout e erro de conexão do httpx são a
            # falha transitória mais provável aqui, e são justamente os que
            # `APIError` não pega. Devolver o claim é o que impede o pedido de
            # ficar aprovado com o prazo antigo, sem ninguém poder decidir de
            # novo (mesmo desenho de `ouvidoria_setor_tokens.devolver`).
            _devolver_claim_da_prorrogacao(supabase, prorrogacao_id)
            logger.error("Falha ao mover o prazo da manifestação %s: %s", manifestacao_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Não foi possível mover o prazo agora. Tente de novo.",
            ) from exc
        if not movido.data:
            _devolver_claim_da_prorrogacao(supabase, prorrogacao_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O caso saiu de aguardando a área agora mesmo: recarregue o painel antes de decidir.",
            )

    veredito = "aprovada" if decisao.aprovada else "negada"
    observacao = f"Prorrogação {veredito} pela Ouvidoria"
    if prazo_novo is not None:
        quando = prazo_novo.astimezone(FUSO_HOSPITAL).strftime("%d/%m/%Y às %Hh%M")
        observacao = f"{observacao}. Prazo novo: {quando}"
    if decisao.justificativa:
        observacao = f"{observacao}. {decisao.justificativa}"
    ouvidoria_prorrogacao.registrar_movimento(
        supabase,
        manifestacao_id,
        autor_id=me["id"],
        autor_nome=me.get("nome_completo") or me["id"],
        observacao=observacao,
    )

    if (pedido.get("solicitante_email") or "").strip():
        aviso = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=ouvidoria_notificacoes.GATILHO_PRORROGACAO_DECIDIDA,
            destinatario_nome=pedido["solicitante_nome"],
            destinatario_email=pedido["solicitante_email"],
            papel_destinatario="setor",
            enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, caso.get("gravidade"), feriados),
        )
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, aviso, agora, feriados)
    else:
        logger.warning("Prorrogação %s decidida sem email do solicitante para avisar", prorrogacao_id)

    registrar_acesso(supabase, me, manifestacao_id, "decidir_prorrogacao")
    atualizado = ouvidoria_prorrogacao.carregar_pedido(supabase, manifestacao_id)
    completo = supabase.table("ouvidoria_protocolos").select(_CAMPOS_DOSSIE).eq("id", manifestacao_id).execute()
    row = completo.data[0] if completo.data else caso
    return {"prorrogacao": atualizado} | _projetar_prazo(row, agora, feriados)


# Anexos da Manifestação (issue #321): metadados no banco, binário no storage,
# leitura por URL assinada (ADR 0034).
_CAMPOS_ANEXO_TUPLA = ("id", "filename", "content_type", "tamanho_bytes", "enviado_por_nome", "created_at")

# Meia hora: o ouvidor abre o anexo, lê e fecha. Link colado em conversa alheia
# expira antes de virar acesso permanente à evidência.
EXPIRACAO_URL_ANEXO_SEGUNDOS = 1800


def carregar_manifestacao(supabase, manifestacao_id: str, campos: str = "id, protocolo") -> dict:
    """Confirma que a manifestação existe antes de qualquer efeito colateral.
    Levanta 404 quando não existe."""
    try:
        result = supabase.table("ouvidoria_protocolos").select(campos).eq("id", manifestacao_id).execute()
    except APIError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifestação não encontrada")
    return result.data[0]


def _recusa_de_anexo(exc: AnexoRecusadoError) -> HTTPException:
    """Traduz a recusa do módulo de anexo para o status HTTP certo, mantendo a
    mensagem que o ouvidor lê na tela."""
    if isinstance(exc, TipoNaoPermitidoError):
        codigo = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    elif isinstance(exc, AnexoGrandeDemaisError):
        codigo = status.HTTP_413_CONTENT_TOO_LARGE
    else:
        codigo = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=codigo, detail=str(exc))


@router.post("/manifestacoes/{manifestacao_id}/anexos", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def anexar_arquivo(
    request: Request,
    manifestacao_id: str,
    file: UploadFile = File(...),
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Guarda a evidência junto do caso: foto, PDF, áudio ou documento.

    O binário vai ao storage privado e só os metadados ficam no banco. Arquivo
    recusado não deixa rastro: a validação vem antes do upload."""
    manifestacao = carregar_manifestacao(supabase, manifestacao_id)

    # `file.size` vem do Content-Length da parte multipart: recusar por ele
    # evita puxar 200 MB para a memória só para depois dizer não.
    try:
        extensao, content_type = validar_anexo(file.filename or "", file.size or 0)
    except AnexoRecusadoError as exc:
        raise _recusa_de_anexo(exc) from exc

    conteudo = await file.read()
    # O tamanho real manda: o Content-Length é do cliente e pode não bater com
    # o que veio no corpo.
    try:
        validar_anexo(file.filename or "", len(conteudo))
    except AnexoRecusadoError as exc:
        raise _recusa_de_anexo(exc) from exc

    # Caminho sorteado: o nome original é dado da manifestação (pode conter o
    # nome de quem reclamou) e não vira parte de caminho no storage.
    path = f"manifestacao-{manifestacao_id}/{uuid.uuid4().hex}{extensao}"
    subiu = storage.upload_private(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=path,
        content=conteudo,
        content_type=content_type,
    )
    if not subiu:
        # Sem binário não existe anexo: melhor recusar do que registrar
        # metadado que aponta para o vazio.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível guardar o anexo agora. Tente de novo em instantes.",
        )

    try:
        inserido = (
            supabase.table("ouvidoria_anexos")
            .insert(
                {
                    "manifestacao_id": manifestacao["id"],
                    "filename": file.filename,
                    "content_type": content_type,
                    "tamanho_bytes": len(conteudo),
                    "storage_path": path,
                    "enviado_por": me["id"],
                    "enviado_por_nome": me.get("nome_completo") or me["id"],
                }
            )
            .execute()
        )
        row = inserido.data[0]
    except (APIError, IndexError) as exc:
        # Sem a linha no banco, o binário no bucket vira órfão que ninguém
        # alcança e nada recolhe (ON DELETE RESTRICT não ajuda aqui). Limpar
        # agora é a única chance.
        storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, path)
        logger.error("Falha ao registrar o anexo da manifestação %s", manifestacao_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível guardar o anexo. Tente de novo.",
        ) from exc

    registrar_acesso(supabase, me, manifestacao_id, "anexar_arquivo")
    return {campo: row.get(campo) for campo in _CAMPOS_ANEXO_TUPLA}


@router.get("/manifestacoes/{manifestacao_id}/anexos")
@limiter.limit("60/minute")
async def listar_anexos(
    request: Request,
    manifestacao_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Anexos do caso, sem o caminho no storage: o acesso ao binário é sempre
    pela rota que assina a URL."""
    carregar_manifestacao(supabase, manifestacao_id)
    result = (
        supabase.table("ouvidoria_anexos")
        .select(", ".join(_CAMPOS_ANEXO_TUPLA))
        .eq("manifestacao_id", manifestacao_id)
        .order("created_at")
        .execute()
    )
    # O nome original do arquivo pode identificar quem manifestou, então ler a
    # lista já é acesso a dado do caso e entra na trilha.
    registrar_acesso(supabase, me, manifestacao_id, "listar_anexos")
    return {"anexos": [{campo: row.get(campo) for campo in _CAMPOS_ANEXO_TUPLA} for row in (result.data or [])]}


@router.get("/manifestacoes/{manifestacao_id}/anexos/{anexo_id}/url")
@limiter.limit("60/minute")
async def abrir_anexo(
    request: Request,
    manifestacao_id: str,
    anexo_id: str,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """URL assinada, com expiração, para abrir o anexo.

    O anexo precisa ser DESTE caso: sem esse casamento, o id de um anexo viraria
    caminho lateral para a evidência de outra manifestação."""
    try:
        result = (
            supabase.table("ouvidoria_anexos")
            .select("id, storage_path, manifestacao_id, filename")
            .eq("id", anexo_id)
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except APIError as exc:
        # Id que não é UUID faz o PostgREST recusar o filtro (22P02). Do lado
        # de fora isso é o mesmo que anexo inexistente.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado") from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anexo não encontrado")

    url = storage.signed_url(
        supabase,
        bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
        path=result.data[0]["storage_path"],
        expires_in=EXPIRACAO_URL_ANEXO_SEGUNDOS,
    )
    if url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível abrir o anexo agora. Tente de novo em instantes.",
        )
    registrar_acesso(supabase, me, manifestacao_id, "abrir_anexo")
    return {
        "url": url,
        "filename": result.data[0]["filename"],
        "expira_em_segundos": EXPIRACAO_URL_ANEXO_SEGUNDOS,
    }


# =====================================================================
# Parâmetros do motor de prazos (issue #322, RN-21 e RN-22)
# =====================================================================

_CAMPOS_PRAZO_TUPLA = ("gravidade", "marco", "valor", "unidade")
_CAMPOS_PRAZO = ", ".join(_CAMPOS_PRAZO_TUPLA)
_CAMPOS_FERIADO_TUPLA = ("data", "nome", "abrangencia")
_CAMPOS_FERIADO = ", ".join(_CAMPOS_FERIADO_TUPLA)
# Teto de sanidade do prazo. A spec limita a prorrogação a 30 dias úteis de
# T0; 365 dá folga de sobra e ainda impede que um valor absurdo faça o motor
# caminhar milhões de dias pelo calendário.
TETO_DO_PRAZO = 365
_CAMPOS_HISTORICO_PRAZO_TUPLA = (
    "id",
    "gravidade",
    "marco",
    "valor_anterior",
    "unidade_anterior",
    "valor_novo",
    "unidade_nova",
    "autor_nome",
    "ocorrido_em",
)
_CAMPOS_HISTORICO_PRAZO = ", ".join(_CAMPOS_HISTORICO_PRAZO_TUPLA)


@router.get("/prazos")
@limiter.limit("60/minute")
async def listar_prazos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """A tabela de prazos por gravidade que alimenta o motor. Leitura para
    quem trabalha na Ouvidoria; edição só para a Diretoria Executiva."""
    result = supabase.table("ouvidoria_prazos").select(_CAMPOS_PRAZO).execute()
    linhas = result.data or []
    return {"prazos": [{campo: row.get(campo) for campo in _CAMPOS_PRAZO_TUPLA} for row in linhas]}


class PedidoPrazo(BaseModel):
    """Uma célula da tabela. `valor` nulo significa sem prazo (crítico não tem
    conclusiva fixa; baixo não passa pela área)."""

    valor: int | None = None
    unidade: Literal["horas_uteis", "dias_uteis"]


@router.put("/prazos/{gravidade}/{marco}")
@limiter.limit("30/minute")
async def editar_prazo(
    request: Request,
    gravidade: Literal["critico", "alto", "medio", "baixo"],
    marco: Literal["triagem", "area_resposta", "conclusiva"],
    pedido: PedidoPrazo,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Edita um prazo (RN-21). A mudança vale para validação nova: nenhum caso
    já despachado é recalculado, porque o vencimento deles está congelado em
    `prazo_area_em` desde o acionamento."""
    if pedido.valor is not None and not (0 <= pedido.valor <= TETO_DO_PRAZO):
        # O teto não é burocracia: o motor caminha dia a dia pelo calendário, e
        # valor sem limite vira request travado na hora de validar o caso.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Prazo precisa estar entre 0 e {TETO_DO_PRAZO}",
        )

    atual = (
        supabase.table("ouvidoria_prazos").select(_CAMPOS_PRAZO).eq("gravidade", gravidade).eq("marco", marco).execute()
    )
    if not atual.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prazo não encontrado")
    anterior = atual.data[0]

    if anterior.get("valor") == pedido.valor and anterior.get("unidade") == pedido.unidade:
        # Salvar o que já estava lá não é alteração. O histórico é append-only
        # e não se limpa depois: passar pelas células sem mudar nada não pode
        # encher de "mudou de 2 para 2" o que a Diretoria vai ler amanhã.
        return {"gravidade": gravidade, "marco": marco, "valor": pedido.valor, "unidade": pedido.unidade}

    supabase.table("ouvidoria_prazos").update({"valor": pedido.valor, "unidade": pedido.unidade}).eq(
        "gravidade", gravidade
    ).eq("marco", marco).execute()

    # O histórico é o que prova quem mudou o prazo e quando (RN-21). Escrito
    # depois da mudança valer, para não registrar edição que não aconteceu.
    supabase.table("ouvidoria_prazos_historico").insert(
        {
            "gravidade": gravidade,
            "marco": marco,
            "valor_anterior": anterior.get("valor"),
            "unidade_anterior": anterior.get("unidade"),
            "valor_novo": pedido.valor,
            "unidade_nova": pedido.unidade,
            "autor_id": me["id"],
            "autor_nome": me.get("nome_completo") or me["id"],
        }
    ).execute()

    return {"gravidade": gravidade, "marco": marco, "valor": pedido.valor, "unidade": pedido.unidade}


@router.get("/prazos/historico")
@limiter.limit("60/minute")
async def listar_historico_de_prazos(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Quem mudou qual prazo, quando, de quanto para quanto."""
    result = (
        supabase.table("ouvidoria_prazos_historico")
        .select(_CAMPOS_HISTORICO_PRAZO)
        .order("ocorrido_em", desc=True)
        .execute()
    )
    # Projetada campo a campo como as demais rotas do módulo: coluna nova na
    # tabela não vira campo novo na resposta sem alguém decidir isso.
    return {
        "historico": [{campo: row.get(campo) for campo in _CAMPOS_HISTORICO_PRAZO_TUPLA} for row in (result.data or [])]
    }


@router.get("/feriados")
@limiter.limit("60/minute")
async def listar_feriados(
    request: Request,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os dias que saem do calendário útil (RN-22)."""
    result = supabase.table("ouvidoria_feriados").select(_CAMPOS_FERIADO).order("data").execute()
    linhas = result.data or []
    return {"feriados": [{campo: row.get(campo) for campo in _CAMPOS_FERIADO_TUPLA} for row in linhas]}


class PedidoFeriado(BaseModel):
    data: dt.date
    nome: str
    abrangencia: Literal["nacional", "estadual_rj", "municipal_rio"]

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Feriado sem nome não é administrável")
        return v.strip()


@router.post("/feriados", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def cadastrar_feriado(
    request: Request,
    pedido: PedidoFeriado,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Cadastra um feriado. A partir daqui o motor deixa de contar esse dia."""
    try:
        supabase.table("ouvidoria_feriados").insert(
            {"data": pedido.data.isoformat(), "nome": pedido.nome, "abrangencia": pedido.abrangencia}
        ).execute()
    except APIError as exc:
        if exc.code == "23505":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feriado já cadastrado") from exc
        raise
    return {"data": pedido.data.isoformat(), "nome": pedido.nome, "abrangencia": pedido.abrangencia}


@router.delete("/feriados/{data}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def remover_feriado(
    request: Request,
    data: dt.date,
    me: dict = Depends(require_diretoria_executiva),
    supabase=Depends(get_supabase_client),
):
    """Remove um feriado: o dia volta a contar no calendário útil."""
    supabase.table("ouvidoria_feriados").delete().eq("data", data.isoformat()).execute()


@router.get("/metricas")
@limiter.limit("60/minute")
async def metricas_do_periodo(
    request: Request,
    inicio: dt.date | None = None,
    fim: dt.date | None = None,
    me: dict = Depends(require_perfil_ouvidoria),
    supabase=Depends(get_supabase_client),
):
    """Os números da Ouvidoria no período (PRD #319, fatia I1).

    A porta única do módulo de métricas: o painel e os relatórios leem daqui, e
    é por isso que não conseguem divergir. Restrita aos dois perfis da
    Ouvidoria, sem bypass de super admin, porque a agregação enxerga também o
    caso sigiloso (ADR 0034, decisão 8).

    Sem intervalo, o período é o mês corrente até hoje, no fuso do hospital: é
    o retrato que o painel abre pedindo."""
    agora = agora_utc()
    hoje = agora.astimezone(FUSO_HOSPITAL).date()
    periodo_inicio = inicio or hoje.replace(day=1)
    periodo_fim = fim or hoje
    if periodo_fim < periodo_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O fim do período não pode ser anterior ao início.",
        )
    dias = (periodo_fim - periodo_inicio).days + 1
    if dias > ouvidoria_metricas.MAX_DIAS_DO_PERIODO:
        # Sem teto, um pedido de dez anos varre a tabela inteira duas vezes por
        # requisição, e a rota aceita 60 por minuto.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O período não pode passar de {ouvidoria_metricas.MAX_DIAS_DO_PERIODO} dias.",
        )
    if periodo_inicio <= dt.date.min + dt.timedelta(days=dias):
        # `Periodo.anterior()` recua uma janela inteira: perto do início do
        # calendário isso estoura, e o erro sairia como 500 em cima de um
        # parâmetro do cliente.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data de início fora do calendário suportado.",
        )
    return ouvidoria_metricas.metricas_do_periodo(
        supabase,
        ouvidoria_metricas.Periodo(inicio=periodo_inicio, fim=periodo_fim),
        agora,
    )
