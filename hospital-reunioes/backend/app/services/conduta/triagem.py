"""O que o Comitê faz na triagem e nos ritos (issue #1824; especificação,
seções 5, 6.1 e 6.2).

A coordenação confirma a triagem (dentro, fora ou misto, a categoria, o rito
e o destino do que é de fora). O segundo leitor confere ou contesta, e a
contestação vai à decisão dos três votantes. O Encaminhamento encerra o caso
como "Encaminhado" num clique, depois da conferência. O Completo prorroga uma
vez, com justificativa. Prazo vencido fica registrado para sempre.

Toda ação grava a sua linha na trilha antes de mudar o caso: sem a linha, a
ação não acontece. A mudança do caso confere a etapa de antes, para duas
pessoas não agirem sobre o mesmo passo.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from app.services.conduta import cifra, trilha
from app.services.conduta.acesso import _atribuicoes_e_citacoes, papel_no_caso
from app.services.conduta.portao import CasoAberto, NoComite
from app.services.conduta.ritos import (
    CATEGORIAS,
    ETAPA_DO_RITO,
    Olhar,
    acao_pendente,
    agora_utc,
    chave_de_urgencia,
    data_do_envio,
    erro_da_triagem,
    orientacao_do_encaminhamento,
    pode_prorrogar,
    prazo_do_rito,
    prazo_venceu,
    resultado_da_contestacao,
    situacao,
    votante,
)
from app.services.feriados import FALHAS_DE_LEITURA_DO_CALENDARIO, feriados_entre

logger = logging.getLogger(__name__)

NOMES_DOS_RITOS = {"encaminhamento": "Encaminhamento", "rapido": "Rápido", "completo": "Completo"}
_TAMANHO_DO_MOTIVO = 500
_TAMANHO_DA_JUSTIFICATIVA = 2000


class AcaoRecusadaError(Exception):
    """A ação não pode acontecer agora. `status` vai para a resposta, e a
    mensagem diz o motivo numa linha."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


# ── Leituras ────────────────────────────────────────────────────────────────


def _contestacoes(supabase, caso_ids: list[str]) -> dict[str, dict]:
    if not caso_ids:
        return {}
    linhas = supabase.table("conduta_contestacoes").select("*").in_("caso_id", caso_ids).execute().data or []
    return {linha["caso_id"]: linha for linha in linhas}


def _votos(supabase, contestacao_id: str) -> list[dict]:
    return (
        supabase.table("conduta_contestacao_votos").select("*").eq("contestacao_id", contestacao_id).execute().data
        or []
    )


def _olhar(supabase, pessoa_id: str, papel: str | None, atribuicoes, contestacao: dict | None) -> Olhar:
    ja_votou = bool(contestacao) and any(
        v.get("participante_id") == pessoa_id for v in _votos(supabase, contestacao["id"])
    )
    return Olhar(
        papel=papel,
        votante=votante(papel, atribuicoes),
        contestacao=contestacao,
        ja_votou_na_contestacao=ja_votou,
    )


def olhar_do_caso(supabase, aberto: CasoAberto) -> Olhar:
    contestacao = _contestacoes(supabase, [aberto.caso["id"]]).get(aberto.caso["id"])
    return _olhar(supabase, aberto.autor_id, aberto.pessoa.papel, aberto.atribuicoes, contestacao)


def registrar_vencidos(supabase, casos: list[dict], hoje: date) -> set[str]:
    """Grava o prazo que venceu (uma vez por prazo) e devolve os casos com
    algum prazo vencido registrado, de agora ou de antes. A prorrogação não
    apaga o vencido de antes."""
    ids = [caso["id"] for caso in casos]
    if not ids:
        return set()
    ja = supabase.table("conduta_prazos_vencidos").select("caso_id, prazo_em").in_("caso_id", ids).execute().data or []
    registrados = {(linha["caso_id"], str(linha["prazo_em"])[:10]) for linha in ja}
    for caso in casos:
        if not prazo_venceu(caso, hoje) or (caso["id"], str(caso["prazo_em"])[:10]) in registrados:
            continue
        prazo = str(caso["prazo_em"])[:10]
        trilha.registrar(supabase, caso["id"], None, "prazo_vencido", f"prazo do rito venceu em {prazo}")
        supabase.table("conduta_prazos_vencidos").insert(
            {"caso_id": caso["id"], "rito": caso.get("rito") or "", "prazo_em": prazo}
        ).execute()
        registrados.add((caso["id"], prazo))
    return {caso_id for caso_id, _ in registrados}


def _no_dia(hoje: date, caso: dict) -> dict:
    prazo = caso.get("prazo_em")
    faltam = (date.fromisoformat(str(prazo)[:10]) - hoje).days if prazo else None
    return {"faltam_dias": faltam}


def minha_vez(supabase, comite: NoComite, hoje: date) -> list[dict]:
    """Só o que depende da pessoa, do mais urgente ao menos urgente."""
    vencidos = registrar_vencidos(supabase, comite.casos, hoje)
    atribuicoes, _ = _atribuicoes_e_citacoes(supabase, comite.pessoa)
    contestacoes = _contestacoes(supabase, [c["id"] for c in comite.casos if c.get("etapa") == "contestada"])
    itens = []
    for caso in comite.casos:
        do_caso = atribuicoes.get(caso["id"], [])
        olhar = _olhar(
            supabase,
            comite.autor_id,
            papel_no_caso(comite.pessoa.papel, do_caso),
            do_caso,
            contestacoes.get(caso["id"]),
        )
        acao = acao_pendente(caso, olhar)
        if acao is None:
            continue
        itens.append(
            {
                "id": caso["id"],
                "protocolo": caso["protocolo"],
                "etapa": caso.get("etapa"),
                "rito": caso.get("rito"),
                "acao": acao,
                "prazo_em": caso.get("prazo_em"),
                "prazo_vencido": caso["id"] in vencidos,
                **_no_dia(hoje, caso),
                "_urgencia": chave_de_urgencia(caso),
            }
        )
    itens.sort(key=lambda item: item.pop("_urgencia"))
    return itens


def lista_de_casos(supabase, comite: NoComite, hoje: date, *, situacao_pedida: str | None, rito: str | None):
    vencidos = registrar_vencidos(supabase, comite.casos, hoje)
    saida = []
    for caso in comite.casos:
        if situacao_pedida and situacao(caso) != situacao_pedida:
            continue
        if rito and (caso.get("rito") or "sem_rito") != rito:
            continue
        saida.append(
            {**caso, "situacao": situacao(caso), "prazo_vencido": caso["id"] in vencidos, **_no_dia(hoje, caso)}
        )
    return saida


def contestacao_para_a_tela(supabase, caso_id: str) -> dict | None:
    contestacao = _contestacoes(supabase, [caso_id]).get(caso_id)
    if contestacao is None:
        return None
    return {
        "escopo": contestacao["escopo"],
        "categoria": contestacao["categoria"],
        "rito": contestacao["rito"],
        "destino": contestacao.get("destino"),
        "motivo": cifra.decifrar_texto(contestacao["motivo_cifrado"]),
        "votos": len(_votos(supabase, contestacao["id"])),
        "resultado": contestacao.get("resultado"),
    }


# ── Ações ───────────────────────────────────────────────────────────────────


def _feriados(supabase, recebido_em) -> frozenset[date]:
    """Os feriados das semanas do Encaminhamento. Sem o calendário, conta sem
    feriado: o prazo sai mais cedo, nunca mais tarde."""
    envio = data_do_envio(recebido_em)
    try:
        return feriados_entre(supabase, envio, envio + timedelta(days=30))
    except FALHAS_DE_LEITURA_DO_CALENDARIO:
        logger.warning("Feriados fora do ar: o prazo do Encaminhamento conta sem eles", exc_info=True)
        return frozenset()


def _prazo(supabase, caso: dict, rito: str, *, prorrogado: bool = False) -> str:
    feriados = _feriados(supabase, caso["recebido_em"]) if rito == "encaminhamento" else frozenset()
    return prazo_do_rito(rito, caso["recebido_em"], prorrogado=prorrogado, feriados=feriados).isoformat()


def _mudar(supabase, caso: dict, etapa_de_antes: str, campos: dict[str, Any]) -> dict:
    linhas = (
        supabase.table("conduta_casos").update(campos).eq("id", caso["id"]).eq("etapa", etapa_de_antes).execute().data
        or []
    )
    if not linhas:
        raise AcaoRecusadaError(409, "O caso mudou enquanto você agia. Abra de novo.")
    return linhas[0]


def _exigir_etapa(caso: dict, *etapas: str) -> str:
    etapa = caso.get("etapa") or "triagem"
    if etapa not in etapas or caso.get("encerrado_em"):
        raise AcaoRecusadaError(409, "Este passo já foi feito ou ainda não chegou.")
    return etapa


def _exigir_triagem_valida(escopo, categoria, rito, destino) -> None:
    erro = erro_da_triagem(escopo, categoria, rito, destino)
    if erro:
        raise AcaoRecusadaError(422, erro)


def _descricao(escopo: str, categoria: str, rito: str) -> str:
    return f"{escopo}, categoria {categoria} ({CATEGORIAS[categoria]}), rito {NOMES_DOS_RITOS[rito]}"


def confirmar_triagem(supabase, aberto: CasoAberto, *, escopo, categoria, rito, destino) -> dict:
    caso = aberto.caso
    if aberto.pessoa.papel != "coordenacao":
        raise AcaoRecusadaError(403, "Só a coordenação confirma a triagem.")
    etapa = _exigir_etapa(caso, "triagem")
    _exigir_triagem_valida(escopo, categoria, rito, destino)
    trilha.registrar(
        supabase, caso["id"], aberto.autor_id, "triagem", f"confirmou: {_descricao(escopo, categoria, rito)}"
    )
    return _mudar(
        supabase,
        caso,
        etapa,
        {
            "escopo": escopo,
            "categoria": categoria,
            "rito": rito,
            "destino": destino or None,
            "triagem_por": aberto.autor_id,
            "triagem_em": agora_utc().isoformat(),
            "prazo_em": _prazo(supabase, caso, rito),
            "etapa": ETAPA_DO_RITO[rito],
        },
    )


def _exigir_segundo_leitor_a_conferir(supabase, aberto: CasoAberto) -> str:
    caso = aberto.caso
    if aberto.pessoa.papel != "segundo_leitor":
        raise AcaoRecusadaError(403, "Só o segundo leitor confere ou contesta a triagem.")
    if not caso.get("triagem_em") or caso.get("conferida_em") or caso.get("encerrado_em"):
        raise AcaoRecusadaError(409, "Não há triagem a conferir neste caso.")
    if _contestacoes(supabase, [caso["id"]]):
        raise AcaoRecusadaError(409, "A triagem deste caso já foi contestada.")
    return caso.get("etapa") or "triagem"


def conferir_triagem(supabase, aberto: CasoAberto) -> dict:
    etapa = _exigir_segundo_leitor_a_conferir(supabase, aberto)
    trilha.registrar(supabase, aberto.caso["id"], aberto.autor_id, "conferencia", "conferiu a triagem")
    return _mudar(
        supabase,
        aberto.caso,
        etapa,
        {"conferida_por": aberto.autor_id, "conferida_em": agora_utc().isoformat()},
    )


def contestar_triagem(supabase, aberto: CasoAberto, *, motivo, escopo, categoria, rito, destino) -> dict:
    etapa = _exigir_segundo_leitor_a_conferir(supabase, aberto)
    motivo = (motivo or "").strip()
    if not motivo:
        raise AcaoRecusadaError(422, "Escreva o motivo da contestação em uma linha.")
    if len(motivo) > _TAMANHO_DO_MOTIVO:
        raise AcaoRecusadaError(422, "O motivo cabe em uma linha.")
    _exigir_triagem_valida(escopo, categoria, rito, destino)
    caso = aberto.caso
    trilha.registrar(
        supabase,
        caso["id"],
        aberto.autor_id,
        "contestacao",
        f"contestou a triagem: {_descricao(escopo, categoria, rito)}",
    )
    supabase.table("conduta_contestacoes").insert(
        {
            "caso_id": caso["id"],
            "autor_id": aberto.autor_id,
            "motivo_cifrado": cifra.cifrar_texto(motivo),
            "escopo": escopo,
            "categoria": categoria,
            "rito": rito,
            "destino": destino or None,
        }
    ).execute()
    return _mudar(supabase, caso, etapa, {"etapa": "contestada"})


def decidir_contestacao(supabase, aberto: CasoAberto, *, escolha: str) -> dict:
    caso = aberto.caso
    if escolha not in ("manter", "acatar"):
        raise AcaoRecusadaError(422, "Escolha manter a triagem da coordenação ou acatar a contestação.")
    if not votante(aberto.pessoa.papel, aberto.atribuicoes):
        raise AcaoRecusadaError(403, "Só os três membros votantes decidem a contestação.")
    _exigir_etapa(caso, "contestada")
    contestacao = _contestacoes(supabase, [caso["id"]])[caso["id"]]
    if any(v.get("participante_id") == aberto.autor_id for v in _votos(supabase, contestacao["id"])):
        raise AcaoRecusadaError(409, "Você já decidiu esta contestação.")
    trilha.registrar(supabase, caso["id"], aberto.autor_id, "decisao_da_triagem", "decidiu a contestação da triagem")
    supabase.table("conduta_contestacao_votos").insert(
        {"contestacao_id": contestacao["id"], "participante_id": aberto.autor_id, "escolha": escolha}
    ).execute()
    resultado = resultado_da_contestacao(_votos(supabase, contestacao["id"]))
    if resultado is None:
        return caso
    agora = agora_utc().isoformat()
    trilha.registrar(supabase, caso["id"], None, "triagem_decidida", f"contestação {resultado} pelos três")
    supabase.table("conduta_contestacoes").update({"resultado": resultado, "decidida_em": agora}).eq(
        "id", contestacao["id"]
    ).execute()
    vale = contestacao if resultado == "acatada" else caso
    campos = {
        "escopo": vale["escopo"],
        "categoria": vale["categoria"],
        "rito": vale["rito"],
        "destino": vale.get("destino"),
        "prazo_em": _prazo(supabase, caso, vale["rito"]),
        "etapa": ETAPA_DO_RITO[vale["rito"]],
        "conferida_em": agora,
    }
    return _mudar(supabase, caso, "contestada", campos)


def prorrogar_prazo(supabase, aberto: CasoAberto, *, justificativa: str, hoje: date) -> dict:
    caso = aberto.caso
    motivo = pode_prorrogar(caso, Olhar(papel=aberto.pessoa.papel, votante=False))
    if motivo:
        raise AcaoRecusadaError(403 if motivo.startswith("Só a coordenação") else 409, motivo)
    justificativa = (justificativa or "").strip()
    if not justificativa:
        raise AcaoRecusadaError(422, "Escreva a justificativa da prorrogação.")
    if len(justificativa) > _TAMANHO_DA_JUSTIFICATIVA:
        raise AcaoRecusadaError(422, "A justificativa passou do tamanho que cabe.")
    registrar_vencidos(supabase, [caso], hoje)
    trilha.registrar(supabase, caso["id"], aberto.autor_id, "prorrogacao", "prorrogou o prazo por 30 dias")
    return _mudar(
        supabase,
        caso,
        caso.get("etapa") or "triagem",
        {
            "prorrogado_por": aberto.autor_id,
            "prorrogado_em": agora_utc().isoformat(),
            "prorrogacao_cifrada": cifra.cifrar_texto(justificativa),
            "prazo_em": _prazo(supabase, caso, "completo", prorrogado=True),
        },
    )


def enviar_orientacao(supabase, aberto: CasoAberto, *, hoje: date) -> dict:
    caso = aberto.caso
    if aberto.pessoa.papel != "coordenacao":
        raise AcaoRecusadaError(403, "Só a coordenação envia a orientação.")
    etapa = _exigir_etapa(caso, "encaminhamento")
    if not caso.get("conferida_em"):
        raise AcaoRecusadaError(409, "Falta o segundo leitor conferir a triagem.")
    registrar_vencidos(supabase, [caso], hoje)
    trilha.registrar(supabase, caso["id"], aberto.autor_id, "encaminhamento", "enviou a orientação e encerrou")
    return _mudar(
        supabase,
        caso,
        etapa,
        {
            "orientacao_cifrada": cifra.cifrar_texto(orientacao_do_encaminhamento(caso["destino"])),
            "encerrado_em": agora_utc().isoformat(),
            "desfecho": "encaminhado",
            "etapa": "encerrado",
        },
    )
