"""Impedimento, suplente convocado e Citado (issue #1828; especificação, 3.3 e
6.9; ADR 0097, decisões 4 e 5).

Quem fica impedido num caso ganha a marca na atribuição dele ao caso, e o
portão (`acesso.pode_abrir`) passa a recusá-lo na hora. Se o impedido tinha
papel de membro votante no caso, um suplente vigente é convocado no lugar e
passa a ver só aquele caso, com o papel do substituído.

Toda declaração, decisão e convocação grava a sua linha na trilha antes de
mudar o banco: sem a linha, nada acontece.
"""

from __future__ import annotations

import logging
import re

from app.services.conduta import cifra, membros, trilha
from app.services.conduta.acesso import hoje_em_sao_paulo, papel_no_caso, pessoa_no_comite
from app.services.conduta.portao import CasoAberto
from app.services.conduta.ritos import PAPEIS_VOTANTES, agora_utc
from app.services.conduta.triagem import AcaoRecusadaError

logger = logging.getLogger(__name__)

MOTIVOS = {
    "parte": "parte no caso",
    "chefia_direta": "chefia direta de envolvido",
    "parentesco": "parentesco",
    "relacao_pessoal": "relação pessoal",
    "interesse": "interesse no resultado",
}


def _impedir(supabase, caso_id: str, pessoa_id: str, motivo: str) -> None:
    """Marca a pessoa impedida no caso. A Participação no Comitê não tem linha
    de atribuição: o impedimento cria a dele."""
    campos = {"impedido_em": agora_utc().isoformat(), "impedimento_motivo": motivo}
    abertas = (
        supabase.table("conduta_atribuicoes")
        .update(campos)
        .eq("caso_id", caso_id)
        .eq("participante_id", pessoa_id)
        .is_("impedido_em", "null")
        .execute()
        .data
    )
    if not abertas:
        supabase.table("conduta_atribuicoes").insert(
            {"caso_id": caso_id, "participante_id": pessoa_id, "motivo": "membro_do_comite", **campos}
        ).execute()


def _suplente_livre(supabase, caso_id: str) -> str | None:
    """O primeiro suplente vigente, com o Termo assinado, que ainda não tem
    nada no caso (convocação, impedimento) e não é Citado nele."""
    comite_id = membros.id_do_comite(supabase)
    if not comite_id:
        return None
    hoje = hoje_em_sao_paulo()
    candidatos = sorted(
        (
            p
            for p in membros.participacoes(supabase, comite_id)
            if p["papel"] == "suplente" and p.get("termo_assinado_em") and membros.vigente_em(p, hoje)
        ),
        key=lambda p: (str(p["vigencia_inicio"]), p["participante_id"]),
    )
    no_caso = supabase.table("conduta_atribuicoes").select("participante_id").eq("caso_id", caso_id).execute().data
    citados = supabase.table("conduta_citados").select("participante_id").eq("caso_id", caso_id).execute().data
    ocupados = {linha["participante_id"] for linha in (no_caso or []) + (citados or [])}
    return next((p["participante_id"] for p in candidatos if p["participante_id"] not in ocupados), None)


def _avisar_o_suplente(supabase, suplente_id: str) -> None:
    """Sino, sem protocolo nem conteúdo. O aviso não desfaz a convocação."""
    try:
        supabase.table("notificacoes").insert(
            {
                "destinatario_id": suplente_id,
                "tipo": membros.TIPO_DO_AVISO,
                "titulo": "Convocação no Comitê de Conduta",
                "mensagem": "Você foi convocado como suplente para um caso. Veja em Casos, no Canal de Conduta.",
            }
        ).execute()
    except Exception as erro:  # noqa: BLE001
        logger.error("[conduta_impedimento] Aviso da convocação não gravado no sino: %s", erro)


def _convocar_no_lugar(supabase, caso_id: str, impedido_id: str, papel: str | None) -> None:
    """Quem ficou impedido votava no caso: um suplente entra no lugar, com o
    papel do substituído. Sem suplente livre, a trilha diz isso."""
    if papel not in PAPEIS_VOTANTES:
        return
    suplente = _suplente_livre(supabase, caso_id)
    if suplente is None:
        trilha.registrar(supabase, caso_id, None, "sem_suplente", "nenhum suplente livre para convocar")
        return
    trilha.registrar(supabase, caso_id, None, "convocacao", "convocou um suplente no lugar de quem ficou impedido")
    supabase.table("conduta_atribuicoes").insert(
        {
            "caso_id": caso_id,
            "participante_id": suplente,
            "motivo": "suplente_convocado",
            "substitui_id": impedido_id,
            "substitui_papel": papel,
        }
    ).execute()
    _avisar_o_suplente(supabase, suplente)


def membros_do_caso(supabase, caso: dict) -> dict[str, str]:
    """Quem vota no caso hoje, e com que papel: a Participação votante com o
    Termo (fila comum) e o suplente convocado. Sem impedidos e sem Citados."""
    caso_id = caso["id"]
    atribuicoes = supabase.table("conduta_atribuicoes").select("*").eq("caso_id", caso_id).execute().data or []
    citados = supabase.table("conduta_citados").select("participante_id").eq("caso_id", caso_id).execute().data
    fora = {a["participante_id"] for a in atribuicoes if a.get("impedido_em")}
    fora |= {linha["participante_id"] for linha in citados or [] if linha.get("participante_id")}
    papeis: dict[str, str] = {}
    comite_id = membros.id_do_comite(supabase)
    if caso.get("rota") == "comum" and comite_id:
        hoje = hoje_em_sao_paulo()
        for p in membros.participacoes(supabase, comite_id):
            if p["papel"] in PAPEIS_VOTANTES and p.get("termo_assinado_em") and membros.vigente_em(p, hoje):
                papeis[p["participante_id"]] = p["papel"]
    for a in atribuicoes:
        papel = papel_no_caso(None, [a])
        if papel:
            papeis[a["participante_id"]] = papel
    return {pid: papel for pid, papel in papeis.items() if pid not in fora}


def _contestacoes(supabase, caso_id: str) -> list[dict]:
    linhas = (
        supabase.table("conduta_contestacoes_de_participacao").select("*").eq("caso_id", caso_id).execute().data
    ) or []
    return sorted(linhas, key=lambda x: str(x.get("created_at") or ""))


def _votos(supabase, contestacao_id: str) -> list[dict]:
    return (
        supabase.table("conduta_participacao_votos").select("*").eq("contestacao_id", contestacao_id).execute().data
        or []
    )


def resultado_da_contestacao(votos: list[dict], decisores: set[str]) -> str | None:
    """`confirmada` com a maioria dos demais membros, `rejeitada` quando a
    maioria já não é alcançável, None enquanto falta voto."""
    maioria = len(decisores) // 2 + 1
    contam = [v for v in votos if v["participante_id"] in decisores]
    if sum(1 for v in contam if v["escolha"] == "confirmar") >= maioria:
        return "confirmada"
    if sum(1 for v in contam if v["escolha"] == "manter") > len(decisores) - maioria:
        return "rejeitada"
    return None


def _resolver(supabase, caso_id: str, contestacao: dict, quem: dict[str, str]) -> dict:
    contestado = contestacao["contestado_id"]
    resultado = resultado_da_contestacao(_votos(supabase, contestacao["id"]), set(quem) - {contestado})
    if resultado is None:
        return contestacao
    trilha.registrar(
        supabase, caso_id, None, "participacao_decidida", f"contestação da participação {resultado} pelos demais"
    )
    decidida = (
        supabase.table("conduta_contestacoes_de_participacao")
        .update({"resultado": resultado, "decidida_em": agora_utc().isoformat()})
        .eq("id", contestacao["id"])
        .execute()
        .data
    )
    if resultado == "confirmada":
        _impedir(supabase, caso_id, contestado, contestacao["motivo"])
        _convocar_no_lugar(supabase, caso_id, contestado, quem.get(contestado))
    return decidida[0] if decidida else contestacao


def contestar_participacao(supabase, aberto: CasoAberto, *, contestado_id: str, motivo: str) -> dict:
    caso_id = aberto.caso["id"]
    if motivo not in MOTIVOS:
        raise AcaoRecusadaError(422, "Escolha o motivo da contestação.")
    quem = membros_do_caso(supabase, aberto.caso)
    if aberto.autor_id not in quem:
        raise AcaoRecusadaError(403, "Só os membros do caso contestam a participação de outro.")
    if contestado_id == aberto.autor_id or contestado_id not in quem:
        raise AcaoRecusadaError(422, "Escolha outro membro deste caso.")
    if any(c["contestado_id"] == contestado_id and not c.get("decidida_em") for c in _contestacoes(supabase, caso_id)):
        raise AcaoRecusadaError(409, "A participação desse membro já está em contestação.")
    trilha.registrar(
        supabase,
        caso_id,
        aberto.autor_id,
        "contestacao_de_participacao",
        f"contestou a participação de outro membro: {MOTIVOS[motivo]}",
    )
    contestacao = (
        supabase.table("conduta_contestacoes_de_participacao")
        .insert({"caso_id": caso_id, "contestado_id": contestado_id, "autor_id": aberto.autor_id, "motivo": motivo})
        .execute()
        .data[0]
    )
    # Quem contesta já é um voto para confirmar.
    supabase.table("conduta_participacao_votos").insert(
        {"contestacao_id": contestacao["id"], "participante_id": aberto.autor_id, "escolha": "confirmar"}
    ).execute()
    return _resolver(supabase, caso_id, contestacao, quem)


def decidir_participacao(supabase, aberto: CasoAberto, *, contestacao_id: str, escolha: str) -> dict:
    caso_id = aberto.caso["id"]
    if escolha not in ("confirmar", "manter"):
        raise AcaoRecusadaError(422, "Escolha confirmar o impedimento ou manter o membro no caso.")
    contestacao = next((c for c in _contestacoes(supabase, caso_id) if c["id"] == contestacao_id), None)
    if contestacao is None:
        raise AcaoRecusadaError(404, "Contestação não encontrada neste caso.")
    if contestacao["contestado_id"] == aberto.autor_id:
        raise AcaoRecusadaError(403, "Quem teve a participação contestada não decide.")
    quem = membros_do_caso(supabase, aberto.caso)
    if aberto.autor_id not in quem:
        raise AcaoRecusadaError(403, "Só os membros do caso decidem a contestação.")
    if contestacao.get("decidida_em"):
        raise AcaoRecusadaError(409, "Esta contestação já foi decidida.")
    if any(v["participante_id"] == aberto.autor_id for v in _votos(supabase, contestacao_id)):
        raise AcaoRecusadaError(409, "Você já decidiu esta contestação.")
    trilha.registrar(
        supabase, caso_id, aberto.autor_id, "decisao_de_participacao", "decidiu a contestação da participação"
    )
    supabase.table("conduta_participacao_votos").insert(
        {"contestacao_id": contestacao_id, "participante_id": aberto.autor_id, "escolha": escolha}
    ).execute()
    return _resolver(supabase, caso_id, contestacao, quem)


def contestacoes_para_a_tela(supabase, caso_id: str, pessoa_id: str, quem: dict[str, str]) -> list[dict]:
    linhas = _contestacoes(supabase, caso_id)
    nome_de = membros.nomes(supabase, [c["contestado_id"] for c in linhas])
    saida = []
    for c in linhas:
        votos = _votos(supabase, c["id"])
        saida.append(
            {
                "id": c["id"],
                "contestado": nome_de.get(c["contestado_id"]),
                "motivo": MOTIVOS.get(c["motivo"], c["motivo"]),
                "votos": len(votos),
                "resultado": c.get("resultado"),
                "pode_decidir": not c.get("decidida_em")
                and pessoa_id in quem
                and pessoa_id != c["contestado_id"]
                and all(v["participante_id"] != pessoa_id for v in votos),
            }
        )
    return saida


# ── Citado ──────────────────────────────────────────────────────────────────

_TAMANHO_DO_NOME = 200
_LIMITE_DA_BUSCA = 8


def buscar_no_cadastro(supabase, busca: str) -> list[dict]:
    """Quem está no cadastro com esse trecho no nome, para ligar o Citado. Só
    id e nome. Curinga digitado não vale."""
    trecho = re.sub(r"[%_,()*\\]", " ", busca or "").strip()
    if len(trecho) < 3:
        return []
    linhas = (
        supabase.table("participantes")
        .select("id, nome_completo")
        .eq("ativo", True)
        .ilike("nome_completo", f"%{trecho}%")
        .order("nome_completo")
        .limit(_LIMITE_DA_BUSCA)
        .execute()
        .data
    ) or []
    return [{"id": linha["id"], "nome": linha.get("nome_completo")} for linha in linhas]


def _citados(supabase, caso_id: str) -> list[dict]:
    linhas = supabase.table("conduta_citados").select("*").eq("caso_id", caso_id).execute().data or []
    return sorted(linhas, key=lambda x: str(x.get("created_at") or ""))


def marcar_citado(supabase, aberto: CasoAberto, *, participante_id: str | None, nome: str | None) -> dict:
    """Qualquer membro do caso, em qualquer etapa. Ligado ao cadastro, o portão
    barra a pessoa; se ela é do Comitê, fica impedida na hora, sem ato de
    ninguém. Nome sem cadastro fica como texto, cifrado."""
    caso_id = aberto.caso["id"]
    nome = (nome or "").strip()
    if participante_id:
        pessoa = supabase.table("participantes").select("id").eq("id", participante_id).limit(1).execute().data
        if not pessoa:
            raise AcaoRecusadaError(422, "Essa pessoa não está no cadastro.")
        if any(c.get("participante_id") == participante_id for c in _citados(supabase, caso_id)):
            raise AcaoRecusadaError(409, "Essa pessoa já é Citada neste caso.")
        quem = membros_do_caso(supabase, aberto.caso)
        trilha.registrar(supabase, caso_id, aberto.autor_id, "citado", "marcou um Citado ligado ao cadastro")
        supabase.table("conduta_citados").insert({"caso_id": caso_id, "participante_id": participante_id}).execute()
        if participante_id in quem or pessoa_no_comite(supabase, participante_id).papel:
            trilha.registrar(supabase, caso_id, None, "impedimento", "impedimento automático: membro Citado no caso")
            _impedir(supabase, caso_id, participante_id, "citado")
            _convocar_no_lugar(supabase, caso_id, participante_id, quem.get(participante_id))
        return aberto.caso
    if not nome:
        raise AcaoRecusadaError(422, "Escreva o nome ou escolha a pessoa no cadastro.")
    if len(nome) > _TAMANHO_DO_NOME:
        raise AcaoRecusadaError(422, "O nome passou do tamanho que cabe.")
    trilha.registrar(supabase, caso_id, aberto.autor_id, "citado", "marcou um Citado sem cadastro")
    supabase.table("conduta_citados").insert({"caso_id": caso_id, "nome_cifrado": cifra.cifrar_texto(nome)}).execute()
    return aberto.caso


def citados_para_a_tela(supabase, caso_id: str) -> list[dict]:
    linhas = _citados(supabase, caso_id)
    nome_de = membros.nomes(supabase, [c["participante_id"] for c in linhas if c.get("participante_id")])
    return [
        {
            "id": c["id"],
            "nome": nome_de.get(c["participante_id"])
            if c.get("participante_id")
            else cifra.decifrar_texto(c["nome_cifrado"]),
            "ligado": bool(c.get("participante_id")),
        }
        for c in linhas
    ]


def para_a_tela(supabase, caso_id: str, pessoa_id: str, quem: dict[str, str]) -> dict:
    """O que a tela do caso mostra desta fatia: os outros membros do caso (para
    a contestação) e as contestações de participação."""
    nome_de = membros.nomes(supabase, list(quem))
    return {
        "membros_do_caso": sorted(
            ({"id": pid, "nome": nome_de.get(pid), "papel": papel} for pid, papel in quem.items() if pid != pessoa_id),
            key=lambda m: (m["nome"] or "").lower(),
        ),
        "pode_contestar_participacao": pessoa_id in quem and len(quem) > 1,
        "contestacoes_de_participacao": contestacoes_para_a_tela(supabase, caso_id, pessoa_id, quem),
        "citados": citados_para_a_tela(supabase, caso_id),
    }


def declarar_impedimento(supabase, aberto: CasoAberto, *, motivo: str) -> dict:
    if motivo not in MOTIVOS:
        raise AcaoRecusadaError(422, "Escolha o motivo do impedimento.")
    caso_id = aberto.caso["id"]
    trilha.registrar(supabase, caso_id, aberto.autor_id, "impedimento", f"declarou impedimento: {MOTIVOS[motivo]}")
    _impedir(supabase, caso_id, aberto.autor_id, motivo)
    _convocar_no_lugar(supabase, caso_id, aberto.autor_id, aberto.pessoa.papel)
    return aberto.caso
