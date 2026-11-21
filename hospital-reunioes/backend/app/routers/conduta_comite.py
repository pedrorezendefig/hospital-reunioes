"""Canal de Conduta, o lado do Comitê (issues #1820 e #1824, PRD #1786, ADR 0097).

MINHA VEZ, a lista dos casos, a tela do caso e as ações da triagem e dos
ritos. E as configurações do módulo, só da coordenação (issue #1826). A área
logada fica em `/comite-de-conduta`, fora de `/conduta`, que é a rota pública.
Toda rota daqui passa pelo portão (`app.services.conduta.portao`).

As listas levam só metadados: nenhum nome e nenhum trecho de relato.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from supabase import Client

from app.dependencies import get_supabase_client
from app.services.conduta import cifra, configuracoes, impedimento, triagem
from app.services.conduta.acesso import CAMPOS_DA_LISTA, hoje_em_sao_paulo
from app.services.conduta.portao import (
    INDISPONIVEL,
    CasoAberto,
    NoComite,
    portao_da_acao,
    portao_da_coordenacao,
    portao_da_lista,
    portao_da_tela_inicial,
    portao_do_caso,
)
from app.services.conduta.ritos import (
    o_que_fazer_agora,
    orientacao_do_encaminhamento,
    pode_prorrogar,
    situacao,
    trilho,
)

router = APIRouter(prefix="/comite-de-conduta", tags=["canal-de-conduta"])


class Triagem(BaseModel):
    escopo: str
    categoria: str
    rito: str
    destino: str | None = None


class Contestacao(Triagem):
    motivo: str = Field(default="", max_length=2000)


class Decisao(BaseModel):
    escolha: Literal["manter", "acatar"]


class Prorrogacao(BaseModel):
    justificativa: str = Field(default="", max_length=4000)


class Impedimento(BaseModel):
    motivo: str = Field(default="", max_length=40)


class ContestacaoDeParticipacao(Impedimento):
    contestado_id: str = Field(max_length=10)


class Citado(BaseModel):
    participante_id: str | None = Field(default=None, max_length=10)
    nome: str | None = Field(default=None, max_length=400)


class DecisaoDeParticipacao(BaseModel):
    escolha: Literal["confirmar", "manter"]


def _indisponivel(erro: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=INDISPONIVEL)


def _metadados(caso: dict) -> dict:
    return {campo: caso.get(campo) for campo in CAMPOS_DA_LISTA}


@router.get("/minha-vez")
async def minha_vez(
    comite: NoComite = Depends(portao_da_tela_inicial), supabase: Client = Depends(get_supabase_client)
) -> dict:
    """`termo_pendente`: a pessoa está no Comitê e ainda não assinou o Termo
    de Confidencialidade e Posse; a tela diz isso no lugar dos casos."""
    return {
        "itens": triagem.minha_vez(supabase, comite, hoje_em_sao_paulo()),
        "termo_pendente": comite.termo_pendente,
    }


@router.get("/casos")
async def listar_casos(
    comite: NoComite = Depends(portao_da_lista),
    supabase: Client = Depends(get_supabase_client),
    situacao_pedida: Literal["em_triagem", "em_andamento", "encerrado"] | None = Query(None, alias="situacao"),
    rito: Literal["encaminhamento", "rapido", "completo", "sem_rito"] | None = None,
) -> dict:
    casos = triagem.lista_de_casos(supabase, comite, hoje_em_sao_paulo(), situacao_pedida=situacao_pedida, rito=rito)
    return {"casos": casos}


@router.get("/casos/{caso_id}")
async def abrir_caso(aberto: CasoAberto = Depends(portao_do_caso), supabase: Client = Depends(get_supabase_client)):
    caso = aberto.caso
    try:
        relato = cifra.decifrar_texto(caso["relato_cifrado"])
        contestacao = triagem.contestacao_para_a_tela(supabase, caso["id"])
        prorrogacao = cifra.decifrar_texto(caso["prorrogacao_cifrada"]) if caso.get("prorrogacao_cifrada") else None
        orientacao = cifra.decifrar_texto(caso["orientacao_cifrada"]) if caso.get("orientacao_cifrada") else None
        impedimentos = impedimento.para_a_tela(
            supabase, caso["id"], aberto.autor_id, impedimento.membros_do_caso(supabase, caso)
        )
    except cifra.CifraIndisponivelError as erro:
        raise _indisponivel(erro) from erro
    vencidos = triagem.registrar_vencidos(supabase, [caso], hoje_em_sao_paulo())
    olhar = triagem.olhar_do_caso(supabase, aberto)
    if orientacao is None and caso.get("rito") == "encaminhamento" and caso.get("destino"):
        orientacao = orientacao_do_encaminhamento(caso["destino"])
    return {
        **impedimentos,
        **_metadados(caso),
        "relato": relato,
        "situacao": situacao(caso),
        "papel": aberto.pessoa.papel,
        "trilho": trilho(caso),
        "o_que_fazer_agora": o_que_fazer_agora(caso, olhar),
        "prazo_vencido": caso["id"] in vencidos,
        "contestacao": contestacao,
        "pode_contestar": olhar.papel == "segundo_leitor"
        and o_que_fazer_agora(caso, olhar)["acao"] == "conferir_triagem",
        "prorrogacao": {"justificativa": prorrogacao, "bloqueio": pode_prorrogar(caso, olhar)}
        if caso.get("rito") == "completo"
        else None,
        "orientacao": orientacao,
    }


def _executar(funcao, supabase, aberto: CasoAberto, **argumentos):
    try:
        return funcao(supabase, aberto, **argumentos)
    except triagem.AcaoRecusadaError as recusa:
        raise HTTPException(status_code=recusa.status, detail=recusa.mensagem) from recusa
    except cifra.CifraIndisponivelError as erro:
        raise _indisponivel(erro) from erro


def _agir(funcao, supabase, aberto: CasoAberto, **argumentos) -> dict:
    return {"caso": _metadados(_executar(funcao, supabase, aberto, **argumentos))}


@router.post("/casos/{caso_id}/triagem")
async def confirmar_triagem(
    corpo: Triagem, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.confirmar_triagem, supabase, aberto, **corpo.model_dump())


@router.post("/casos/{caso_id}/conferencia")
async def conferir_triagem(
    aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.conferir_triagem, supabase, aberto)


@router.post("/casos/{caso_id}/contestacao")
async def contestar_triagem(
    corpo: Contestacao, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.contestar_triagem, supabase, aberto, **corpo.model_dump())


@router.post("/casos/{caso_id}/contestacao/decisao")
async def decidir_contestacao(
    corpo: Decisao, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.decidir_contestacao, supabase, aberto, escolha=corpo.escolha)


@router.post("/casos/{caso_id}/prorrogacao")
async def prorrogar_prazo(
    corpo: Prorrogacao, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.prorrogar_prazo, supabase, aberto, justificativa=corpo.justificativa, hoje=hoje_em_sao_paulo())


@router.post("/casos/{caso_id}/encaminhamento")
async def enviar_orientacao(
    aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(triagem.enviar_orientacao, supabase, aberto, hoje=hoje_em_sao_paulo())


@router.post("/casos/{caso_id}/impedimento")
async def declarar_impedimento(
    corpo: Impedimento, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(impedimento.declarar_impedimento, supabase, aberto, motivo=corpo.motivo)


@router.get("/casos/{caso_id}/cadastro")
async def buscar_no_cadastro(
    busca: str = Query("", max_length=80),
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    """Para ligar o Citado ao cadastro: só id e nome."""
    return {"pessoas": impedimento.buscar_no_cadastro(supabase, busca)}


@router.post("/casos/{caso_id}/citados")
async def marcar_citado(
    corpo: Citado, aberto: CasoAberto = Depends(portao_da_acao), supabase: Client = Depends(get_supabase_client)
) -> dict:
    return _agir(impedimento.marcar_citado, supabase, aberto, **corpo.model_dump())


def _contestacao(linha: dict) -> dict:
    return {"contestacao": {"id": linha["id"], "resultado": linha.get("resultado")}}


@router.post("/casos/{caso_id}/contestacoes-de-participacao")
async def contestar_participacao(
    corpo: ContestacaoDeParticipacao,
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    linha = _executar(impedimento.contestar_participacao, supabase, aberto, **corpo.model_dump())
    return _contestacao(linha)


@router.post("/casos/{caso_id}/contestacoes-de-participacao/{contestacao_id}/decisao")
async def decidir_participacao(
    contestacao_id: UUID,
    corpo: DecisaoDeParticipacao,
    aberto: CasoAberto = Depends(portao_da_acao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    linha = _executar(
        impedimento.decidir_participacao, supabase, aberto, contestacao_id=str(contestacao_id), escolha=corpo.escolha
    )
    return _contestacao(linha)


class NovaVersao(BaseModel):
    texto: str = Field(min_length=1, max_length=5000)

    @field_validator("texto")
    @classmethod
    def _nao_em_branco(cls, texto: str) -> str:
        # Só espaço cairia no CHECK da migration 186 (500); quebra de linha
        # passaria por ele e viraria versão vigente em branco na tela pública.
        if not texto.strip():
            raise ValueError("O texto não pode ficar em branco")
        return texto


@router.get("/configuracoes")
async def listar_configuracoes(
    _me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    return {"itens": configuracoes.itens_com_historico(supabase)}


@router.post("/configuracoes/{chave}", status_code=status.HTTP_201_CREATED)
async def salvar_configuracao(
    chave: str,
    corpo: NovaVersao,
    me: dict = Depends(portao_da_coordenacao),
    supabase: Client = Depends(get_supabase_client),
) -> dict:
    if chave not in configuracoes.POR_CHAVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item de configuração inexistente")
    return configuracoes.salvar(supabase, chave, corpo.texto, me["id"])
