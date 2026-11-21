"""A fonte de Rotinas do Início (issue #1874; ADR 0098, decisão 9).

Uma linha por ciclo em aberto das Rotinas de que a pessoa é responsável: o
ciclo de agora e os que fecharam sem marcação. O ciclo vem da data, nada é
gravado para ele existir. O prazo é o último dia do ciclo, então o ciclo que
fechou cai em "Passou do prazo" sozinho. Realizada é um clique, ali mesmo;
Não realizada pede anotação e fica na tela das Rotinas. O sigilo do Núcleo
segue o das Pendências.

A Rotina sem frequência (o fluxo contínuo antigo convertido, issue #1877) não
tem ciclo: ela entra na fila do Facilitador da Reunião, sem prazo, até ele
escolher a frequência.

O trilho mostra as Rotinas do ciclo de agora do responsável, e a revisão de
90 dias de cada Rotina entra na fila do Facilitador (issue #1944).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.dependencies import reunioes_ocultas, tem_acesso_reunioes
from app.services import rotina_service
from app.services.inicio.regras import FUSO

ROTULO = "as Rotinas"

_FREQUENCIA = {"SEMANAL": "semanal", "QUINZENAL": "quinzenal", "MENSAL": "mensal"}


def _origem(rotina: dict, reuniao: dict | None) -> str:
    frequencia = _FREQUENCIA.get(rotina.get("frequencia") or "", "")
    titulo = ((reuniao or {}).get("titulo") or "").strip()
    rotina_de = f"Rotina {frequencia}".strip()
    return f"{rotina_de} da {titulo}." if titulo else f"{rotina_de}."


def _dia_em_brasilia(quando) -> date | None:
    if not quando:
        return None
    return datetime.fromisoformat(str(quando).replace("Z", "+00:00")).astimezone(FUSO).date()


def _do_responsavel(supabase, me: dict) -> list[dict]:
    """As Rotinas de que a pessoa é a responsável, sem as do Núcleo oculto. Só
    o responsável vê a Rotina no Início: o Facilitador marca por ele na tela
    das Rotinas, não aqui."""
    if not tem_acesso_reunioes(me):
        return []
    rotinas = supabase.table("rotinas").select("*").eq("responsavel_id", me["id"]).execute().data or []
    if not rotinas:
        return []
    ocultas = set(reunioes_ocultas(supabase, me))
    return [r for r in rotinas if r["id_reuniao"] not in ocultas]


def _destino(rotina: dict) -> str:
    return f"/rotinas#rotina-{rotina['id']}"


def do_ciclo(supabase, me: dict, hoje: date) -> list[dict]:
    """O trilho (issue #1944): as Rotinas com um ciclo que contém hoje, e a
    Verificação desse ciclo quando já foi marcada. A que ainda não começou ou
    foi encerrada não tem ciclo corrente e fica de fora."""
    rotinas = _do_responsavel(supabase, me)
    if not rotinas:
        return []
    marcadas = rotina_service.verificacoes_de(supabase, [r["id"] for r in rotinas])
    saida: list[dict] = []
    for rotina in rotinas:
        corrente = next((c for c in rotina_service.devidos(rotina, hoje) if c.inicio <= hoje <= c.fim), None)
        if corrente is None:
            continue
        verificacao = next(
            (
                v
                for v in marcadas.get(rotina["id"], [])
                if str(v.get("ciclo_inicio"))[:10] == corrente.inicio.isoformat()
            ),
            None,
        )
        saida.append(
            {
                "id": rotina["id"],
                "titulo": rotina.get("descricao") or "Rotina sem descrição",
                "ciclo_inicio": corrente.inicio,
                "ciclo_fim": corrente.fim,
                "verificacao": (verificacao or {}).get("resultado"),
                "destino": _destino(rotina),
            }
        )
    saida.sort(key=lambda r: (r["ciclo_fim"], r["titulo"].lower()))
    return saida


def itens(supabase, me: dict, agora: datetime | None = None) -> list[dict]:
    """Os itens da fonte, no formato comum do Início, sem grupo: as
    Verificações em aberto do responsável e as Rotinas a revisar do
    Facilitador."""
    if not tem_acesso_reunioes(me):
        return []
    hoje = (agora or datetime.now(FUSO)).astimezone(FUSO).date()
    return _verificacoes(supabase, me, hoje) + _frequencias_a_escolher(supabase, me) + _a_revisar(supabase, me)


def _frequencias_a_escolher(supabase, me: dict) -> list[dict]:
    """As Rotinas ativas e sem frequência das Reuniões que a pessoa facilita."""
    facilitadas = {
        r["id_reuniao"]: r
        for r in supabase.table("reunioes").select("id_reuniao, titulo").eq("facilitador_id", me["id"]).execute().data
        or []
    }
    if not facilitadas:
        return []
    ocultas = set(reunioes_ocultas(supabase, me))
    rotinas = (
        supabase.table("rotinas")
        .select("*")
        .in_("id_reuniao", sorted(facilitadas))
        .is_("frequencia", "null")
        .eq("status", rotina_service.ATIVA)
        .execute()
        .data
        or []
    )
    return [
        {
            "tipo": "frequencia_da_rotina",
            "id": rotina["id"],
            "titulo": rotina.get("descricao") or "Rotina sem descrição",
            "origem": _origem(rotina, facilitadas.get(rotina["id_reuniao"])),
            "chegou_em": _dia_em_brasilia(rotina.get("created_at")),
            "sem_prazo_no_modulo": True,
            "area": "Reuniões",
            "acao": "Escolher a frequência",
            "destino": "/rotinas",
            "contexto": (
                "Era fluxo contínuo e virou Rotina. Escolha se é semanal, quinzenal ou mensal; "
                "até lá, nenhum ciclo é cobrado do responsável."
            ),
        }
        for rotina in rotinas
        if rotina["id_reuniao"] not in ocultas
    ]


def _a_revisar(supabase, me: dict) -> list[dict]:
    """A revisão de 90 dias (decisão 72 da #1757): a Rotina ativa das Reuniões
    que a pessoa conduz, com o prazo no dia em que a revisão vence. Manter é um
    clique; encerrar pede anotação, na tela das Rotinas."""
    reunioes = {
        r["id_reuniao"]: r
        for r in supabase.table("reunioes").select("id_reuniao, titulo").eq("facilitador_id", me["id"]).execute().data
        or []
    }
    for oculta in reunioes_ocultas(supabase, me) if reunioes else []:
        reunioes.pop(oculta, None)
    if not reunioes:
        return []
    rotinas = (
        supabase.table("rotinas")
        .select("*")
        .in_("id_reuniao", sorted(reunioes))
        .eq("status", rotina_service.ATIVA)
        .execute()
        .data
        or []
    )
    saida: list[dict] = []
    for rotina in rotinas:
        # A sem frequência espera a escolha (issue #1877), não a revisão.
        prazo = rotina_service.revisao_em(rotina) if rotina.get("frequencia") else None
        if prazo is None:
            continue
        saida.append(
            {
                "tipo": "rotina_a_revisar",
                "id": rotina["id"],
                "titulo": rotina.get("descricao") or "Rotina sem descrição",
                "origem": f"Revisão de 90 dias. {_origem(rotina, reunioes.get(rotina['id_reuniao']))}",
                "prazo": prazo,
                "chegou_em": prazo - timedelta(days=rotina_service.DIAS_ATE_A_REVISAO),
                "area": "Reuniões",
                "acao": "Revisar a Rotina",
                "destino": _destino(rotina),
                "contexto": (
                    f"Responsável: {rotina.get('responsavel_nome') or 'sem nome'}. "
                    "Sem revisão, a Rotina continua. Encerrar pede uma anotação, na tela das Rotinas."
                ),
                "acao_de_um_clique": {"rotulo": "Manter", "endpoint": f"/api/rotinas/{rotina['id']}/manter"},
                "acao_secundaria": {"rotulo": "Encerrar", "destino": _destino(rotina)},
            }
        )
    return saida


def _verificacoes(supabase, me: dict, hoje: date) -> list[dict]:
    """Os ciclos em aberto das Rotinas de que a pessoa é responsável."""
    rotinas = _do_responsavel(supabase, me)
    if not rotinas:
        return []
    marcadas = rotina_service.verificacoes_de(supabase, [r["id"] for r in rotinas])
    ids_reunioes = sorted({r["id_reuniao"] for r in rotinas})
    reunioes = {
        r["id_reuniao"]: r
        for r in supabase.table("reunioes").select("id_reuniao, titulo").in_("id_reuniao", ids_reunioes).execute().data
        or []
    }
    saida: list[dict] = []
    for rotina in rotinas:
        origem = _origem(rotina, reunioes.get(rotina["id_reuniao"]))
        for ciclo in rotina_service.ciclos_em_aberto(rotina, marcadas.get(rotina["id"], []), hoje):
            inicio = ciclo.inicio.isoformat()
            saida.append(
                {
                    "tipo": "verificacao_da_rotina",
                    "id": f"{rotina['id']}:{inicio}",
                    "titulo": rotina.get("descricao") or "Rotina sem descrição",
                    "origem": origem,
                    "prazo": ciclo.fim,
                    "chegou_em": ciclo.inicio,
                    "area": "Reuniões",
                    "acao": "Abrir as Rotinas",
                    "destino": "/rotinas",
                    "contexto": (
                        f"Ciclo de {ciclo.inicio.strftime('%d/%m')} a {ciclo.fim.strftime('%d/%m')}. "
                        "Se não foi feita, marque Não realizada na tela das Rotinas, com uma anotação."
                    ),
                    "acao_de_um_clique": {
                        "rotulo": "Realizada",
                        "endpoint": f"/api/rotinas/{rotina['id']}/ciclos/{inicio}/realizada",
                    },
                    "acao_secundaria": {"rotulo": "Não realizada", "destino": _destino(rotina)},
                }
            )
    return saida
