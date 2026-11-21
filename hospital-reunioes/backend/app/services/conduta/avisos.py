"""Os avisos por e-mail do Canal de Conduta (issue #1840; especificação,
seção 12 e regra C6).

O e-mail vai ao endereço profissional do membro e não diz nada do caso: "Há
uma tarefa no Canal de Conduta.", com o link para MINHA VEZ. Nem protocolo,
nem nome, nem rito, nem trecho de relato, no assunto, no corpo ou no link.

Dois motivos de aviso, cada um gravado em `conduta_avisos` antes de sair:

- a tarefa nova: depois de toda mudança no caso (entrada, triagem,
  conferência, contestação, decisão), quem passou a ter uma ação pendente na
  MINHA VEZ ganha o aviso. A regra de quem tem ação é a mesma da MINHA VEZ
  (`ritos.o_que_fazer_agora`), com o portão de quem abre o caso
  (`acesso.pode_abrir`): o Citado e o impedido nunca são avisados;
- o lembrete a cinco dias e a um dia do prazo do rito, a quem tem tarefa no
  caso. Ninguém com tarefa (a apuração, que ainda não tem botão no
  aplicativo), vai a quem conduz o rito: a coordenação, o apurador e o grupo
  da Rota Especial. De cada prazo sai só o marco mais adiantado, e a
  prorrogação, que muda o prazo, recomeça os lembretes.

Caso do rito Completo ou da Rota Especial avisa na hora: o job de minuto em
minuto (`despachar(..., so_na_hora=True)`) entrega. Os outros avisos saem na
rodada diária (`rodada_do_dia`), que também cria os lembretes. Um e-mail por
pessoa e por rodada, por mais tarefas que ela tenha. Antes de sair, a tarefa
é conferida de novo: quem já não tem a ação não recebe.

Quem relatou nunca recebe aviso: o caso não guarda contato de quem relatou, e
os destinatários saem só do Comitê e das atribuições do caso. Nada aqui
decifra o caso nem chama IA.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from postgrest.exceptions import APIError

from app.config import settings
from app.services.conduta.acesso import CAMPOS_DA_LISTA, hoje_em_sao_paulo, pessoa_no_comite, pode_abrir
from app.services.conduta.membros import ids_dos_membros_vigentes
from app.services.conduta.ritos import ACOES_DA_MINHA_VEZ, Olhar, o_que_fazer_agora, votante
from app.services.email_service import _enviar_email, jinja_env

logger = logging.getLogger(__name__)

TABELA = "conduta_avisos"
FRASE = "Há uma tarefa no Canal de Conduta."
TAREFA = "tarefa"
# Do mais adiantado para o primeiro: o primeiro que a contagem alcança é o do dia.
MARCOS_DO_PRAZO = (("lembrete_1", 1), ("lembrete_5", 5))
# Quem conduz o rito, além da coordenação: recebe o lembrete quando ninguém
# tem tarefa no caso.
CONDUZEM = ("apurador", "grupo_especial")


def link_da_minha_vez() -> str:
    return f"{settings.frontend_url}/comite-de-conduta"


def avisa_na_hora(caso: dict[str, Any]) -> bool:
    return caso.get("rito") == "completo" or caso.get("rota") == "especial"


# ── Quem tem tarefa no caso ─────────────────────────────────────────────────


def _caso(supabase, caso_id: str) -> dict | None:
    linhas = supabase.table("conduta_casos").select(", ".join(CAMPOS_DA_LISTA)).eq("id", caso_id).execute().data
    return linhas[0] if linhas else None


def _quem_abre(supabase, caso: dict, hoje: date) -> list[tuple[str, Olhar, list[dict]]]:
    """Cada pessoa que abre o caso, com o olhar dela (o mesmo da MINHA VEZ) e
    as atribuições dela no caso."""
    atribuicoes = supabase.table("conduta_atribuicoes").select("*").eq("caso_id", caso["id"]).execute().data or []
    citacoes = supabase.table("conduta_citados").select("participante_id").eq("caso_id", caso["id"]).execute()
    citados = {linha.get("participante_id") for linha in citacoes.data or []}
    contestacao, votaram = None, set()
    if caso.get("etapa") == "contestada":
        linhas = supabase.table("conduta_contestacoes").select("*").eq("caso_id", caso["id"]).execute().data or []
        contestacao = linhas[0] if linhas else None
    if contestacao:
        votos = (
            supabase.table("conduta_contestacao_votos").select("*").eq("contestacao_id", contestacao["id"]).execute()
        ).data or []
        votaram = {v.get("participante_id") for v in votos}
    candidatos = set(ids_dos_membros_vigentes(supabase, hoje)) | {a["participante_id"] for a in atribuicoes}
    saida = []
    for pid in sorted(candidatos):
        pessoa = pessoa_no_comite(supabase, pid, hoje)
        das = [a for a in atribuicoes if a["participante_id"] == pid]
        if not pode_abrir(caso, pessoa, das, pid in citados):
            continue
        olhar = Olhar(
            papel=pessoa.papel,
            votante=votante(pessoa.papel, das),
            contestacao=contestacao,
            ja_votou_na_contestacao=pid in votaram,
        )
        saida.append((pid, olhar, das))
    return saida


def _acao(caso: dict, olhar: Olhar) -> str | None:
    caixa = o_que_fazer_agora(caso, olhar)
    return caixa["acao"] if caixa["acao"] in ACOES_DA_MINHA_VEZ and caixa["bloqueio"] is None else None


def tarefas_do_caso(supabase, caso: dict, hoje: date) -> dict[str, str]:
    """Quem tem ação pendente no caso agora, e qual."""
    tarefas = {}
    for pid, olhar, _ in _quem_abre(supabase, caso, hoje):
        acao = _acao(caso, olhar)
        if acao:
            tarefas[pid] = acao
    return tarefas


def _quem_conduz(supabase, caso: dict, hoje: date) -> set[str]:
    return {
        pid
        for pid, olhar, das in _quem_abre(supabase, caso, hoje)
        if olhar.papel == "coordenacao" or any(a.get("motivo") in CONDUZEM and not a.get("revogada_em") for a in das)
    }


# ── O registro do aviso ─────────────────────────────────────────────────────


def _gravar(supabase, caso: dict, pid: str, motivo: str, referencia: str) -> bool:
    ja = (
        supabase.table(TABELA)
        .select("id")
        .eq("caso_id", caso["id"])
        .eq("participante_id", pid)
        .eq("motivo", motivo)
        .eq("referencia", referencia)
        .execute()
        .data
    )
    if ja:
        return False
    try:
        supabase.table(TABELA).insert(
            {
                "caso_id": caso["id"],
                "participante_id": pid,
                "motivo": motivo,
                "referencia": referencia,
                "na_hora": avisa_na_hora(caso),
                "situacao": "pendente",
            }
        ).execute()
    except APIError as erro:
        if getattr(erro, "code", None) == "23505":  # outra rodada gravou antes
            return False
        raise
    return True


def tarefas_antes(supabase, caso_id: str) -> dict[str, str] | None:
    """A foto de quem tem tarefa no caso antes de uma ação. None quando não deu
    para ler: aí a ação segue e o aviso fica para a próxima mudança."""
    try:
        caso = _caso(supabase, caso_id)
        return tarefas_do_caso(supabase, caso, hoje_em_sao_paulo()) if caso else {}
    except Exception:  # noqa: BLE001 (o aviso nunca impede a ação)
        logger.warning("[conduta_avisos] Tarefas do caso não lidas antes da ação", exc_info=True)
        return None


def avisar_tarefas_novas(supabase, caso_id: str, antes: dict[str, str] | None) -> list[str]:
    """Grava o aviso de quem passou a ter uma ação pendente no caso. Devolve
    quem ganhou aviso. Best-effort: falha aqui não desfaz a ação."""
    if antes is None:
        return []
    try:
        caso = _caso(supabase, caso_id)
        if not caso:
            return []
        avisados = []
        for pid, acao in tarefas_do_caso(supabase, caso, hoje_em_sao_paulo()).items():
            if antes.get(pid) == acao:
                continue
            if _gravar(supabase, caso, pid, TAREFA, acao):
                avisados.append(pid)
        return avisados
    except Exception:  # noqa: BLE001
        logger.warning("[conduta_avisos] Aviso da tarefa nova não gravado", exc_info=True)
        return []


# ── Os lembretes do prazo ───────────────────────────────────────────────────


def _marco(prazo: date, hoje: date) -> str | None:
    faltam = (prazo - hoje).days
    if faltam < 0:
        return None
    for marco, dias in MARCOS_DO_PRAZO:
        if faltam <= dias:
            return marco
    return None


def lembrar_prazos(supabase, hoje: date) -> int:
    """Grava o lembrete do marco do dia de cada caso aberto com prazo. Devolve
    quantos gravou."""
    casos = (
        supabase.table("conduta_casos").select(", ".join(CAMPOS_DA_LISTA)).is_("encerrado_em", "null").execute().data
        or []
    )
    gravados = 0
    for caso in casos:
        if not caso.get("prazo_em"):
            continue
        prazo = date.fromisoformat(str(caso["prazo_em"])[:10])
        marco = _marco(prazo, hoje)
        if marco is None:
            continue
        ja = supabase.table(TABELA).select("motivo").eq("caso_id", caso["id"]).eq("referencia", prazo.isoformat())
        ja_marcos = {linha["motivo"] for linha in ja.execute().data or []}
        # O job parado uns dias não manda o de cinco dias depois do de um.
        if marco in ja_marcos or (marco == "lembrete_5" and "lembrete_1" in ja_marcos):
            continue
        destinatarios = set(tarefas_do_caso(supabase, caso, hoje)) or _quem_conduz(supabase, caso, hoje)
        for pid in sorted(destinatarios):
            gravados += _gravar(supabase, caso, pid, marco, prazo.isoformat())
    return gravados


# ── A entrega ───────────────────────────────────────────────────────────────


def _montar() -> tuple[str, str]:
    from app.services.email_constants import get_logo_data_uri

    link = link_da_minha_vez()
    html = jinja_env.get_template("email_conduta_aviso.html").render(
        frase=FRASE, link=link, logo_base64=get_logo_data_uri()
    )
    return html, f"{FRASE}\n\nPara ver: {link}\n"


def _marcar(supabase, ids: list[str], situacao: str) -> None:
    if ids:
        campos: dict[str, Any] = {"situacao": situacao}
        if situacao == "enviado":
            campos["enviado_em"] = datetime.now(tz=ZoneInfo("UTC")).isoformat()
        supabase.table(TABELA).update(campos).in_("id", ids).execute()


def despachar(supabase, hoje: date, *, so_na_hora: bool = False) -> dict[str, int]:
    """Entrega os avisos pendentes: um e-mail por pessoa. A tarefa que a
    pessoa já não tem fica dispensada. Quem não recebeu (sem e-mail, provedor
    fora do ar) fica pendente para a próxima rodada."""
    consulta = supabase.table(TABELA).select("*").eq("situacao", "pendente")
    if so_na_hora:
        consulta = consulta.eq("na_hora", True)
    pendentes = consulta.execute().data or []
    if not pendentes:
        return {"enviados": 0, "falhas": 0}

    tarefas_por_caso: dict[str, dict[str, str]] = {}
    dispensados, por_pessoa = [], defaultdict(list)
    for aviso in pendentes:
        if aviso["motivo"] == TAREFA:
            caso_id = aviso["caso_id"]
            if caso_id not in tarefas_por_caso:
                caso = _caso(supabase, caso_id)
                tarefas_por_caso[caso_id] = tarefas_do_caso(supabase, caso, hoje) if caso else {}
            if tarefas_por_caso[caso_id].get(aviso["participante_id"]) != aviso["referencia"]:
                dispensados.append(aviso["id"])
                continue
        por_pessoa[aviso["participante_id"]].append(aviso["id"])
    _marcar(supabase, dispensados, "dispensado")
    if not por_pessoa:
        return {"enviados": 0, "falhas": 0}

    html, texto = _montar()
    enderecos = {
        linha["id"]: linha.get("email")
        for linha in supabase.table("participantes").select("id, email").in_("id", sorted(por_pessoa)).execute().data
        or []
    }
    enviados = falhas = 0
    for pid, ids in sorted(por_pessoa.items()):
        if not enderecos.get(pid):
            falhas += 1
            logger.warning("[conduta_avisos] Membro %s sem e-mail: o aviso fica pendente", pid)
            continue
        try:
            saiu = _enviar_email(enderecos[pid], FRASE, html, texto, endereco_fora_do_log=True)
        except Exception:  # noqa: BLE001 (um aviso que falha não para os outros)
            logger.warning("[conduta_avisos] Aviso para %s não saiu", pid, exc_info=True)
            saiu = False
        if saiu:
            enviados += 1
            _marcar(supabase, ids, "enviado")
        else:
            falhas += 1
    return {"enviados": enviados, "falhas": falhas}


def rodada_do_dia(supabase, hoje: date) -> dict[str, int]:
    """A rodada das 08:00: cria os lembretes do dia e entrega todo aviso
    pendente, o da tarefa de caso comum inclusive."""
    lembrar_prazos(supabase, hoje)
    return despachar(supabase, hoje)
