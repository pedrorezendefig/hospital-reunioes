"""O comando de ação da Pendência (ADR 0098, decisão 5; issues #1862 e #1866).

A única porta que muda estado e prazo da Pendência: decide pela regra pura de
`pendencia_ciclo` e grava pela função `registrar_acao_da_pendencia` do
Postgres (migration 169), que atualiza a Pendência e insere o evento no
histórico na mesma transação. Passam por aqui a rota `POST /pendencias/{id}/acoes`
e os lembretes do Núcleo (Agenda regulatória), que são Pendência sem Reunião.

O ajuste da Contestação pode trocar o responsável (issue #1870): só por uma
pessoa ativa do cadastro, com o nome e o cargo dela, como no nascimento.

Recusa da regra sobe como `AcaoRecusada`; o estado mudado no meio sobe como
`APIError` de código `PT409` (e `PT404` se a Pendência sumiu).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.services.pendencia_ciclo import AcaoRecusada, Comando, Mudanca, Papel, decidir
from app.services.pendencias_consulta import as_data


def agir(
    supabase,
    pendencia: dict,
    comando: Comando,
    papeis: Iterable[Papel],
    *,
    anotacao: str | None,
    autor_id: str | None,
    autor_nome: str,
    hoje: date,
    prazo_novo: date | None = None,
    responsavel_novo: str | None = None,
    ata_em_assinatura: bool = False,
    contestada: bool = False,
) -> Mudanca:
    prazo_atual = as_data(pendencia.get("prazo"))
    mudanca = decidir(
        comando,
        papeis,
        status=pendencia["status"],
        prazo=prazo_atual,
        hoje=hoje,
        anotacao=anotacao,
        prazo_novo=prazo_novo,
        responsavel_novo=responsavel_novo,
        ata_em_assinatura=ata_em_assinatura,
        contestada=contestada,
    )
    troca = {}
    if mudanca.responsavel_id and mudanca.responsavel_id != pendencia.get("responsavel_id"):
        pessoa = _pessoa_ativa(supabase, mudanca.responsavel_id)
        troca = {
            "p_responsavel_id": pessoa["id"],
            "p_responsavel_nome": pessoa.get("nome_completo") or "",
            "p_cargo": (pessoa.get("cargo") or "").strip() or None,
        }
    supabase.rpc(
        "registrar_acao_da_pendencia",
        {
            "p_id_acao": pendencia["id_acao"],
            "p_comando": comando.value,
            "p_anotacao": anotacao,
            "p_autor_id": autor_id,
            "p_autor_nome": autor_nome,
            "p_status_esperado": pendencia["status"],
            "p_status_novo": mudanca.status,
            "p_prazo_novo": mudanca.prazo.isoformat() if mudanca.prazo and mudanca.prazo != prazo_atual else None,
            "p_concluida": mudanca.concluida,
            "p_conta_atraso": mudanca.conta_atraso,
            **troca,
        },
    ).execute()
    return mudanca


def _pessoa_ativa(supabase, participante_id: str) -> dict:
    linhas = (
        supabase.table("participantes")
        .select("id, nome_completo, cargo")
        .eq("id", participante_id)
        .eq("ativo", True)
        .execute()
        .data
    )
    if not linhas:
        raise AcaoRecusada("dados", "Escolha para responsável uma pessoa ativa do cadastro.")
    return linhas[0]
