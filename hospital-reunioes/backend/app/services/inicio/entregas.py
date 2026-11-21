"""As entregas de cada pessoa (issue #1946, ADR 0104 decisões 7 e 9).

Os próprios números dos últimos 90 dias (entregas no prazo e fora), que cada
pessoa vê no Início, e a mesma conta por pessoa no bloco Quem responde a você.
Quem está em dia vê também o que entregou nos últimos 7 dias.

A régua é a do ranking do painel de Reuniões (`painel_reunioes`):

- a data de conclusão sai do Histórico da Pendência, então só conta a
  conclusão feita depois que o ciclo novo entrou (a Pendência concluída antes
  dele não tem evento `concluir`);
- a entrega conta para o responsável pela Pendência (decisão 61);
- a entrega é fora do prazo quando a conclusão veio depois do prazo que valia
  nela, ou quando, antes dela, houve uma Repactuação feita com o prazo já
  vencido, que o ranking também conta como atraso; a Repactuação feita antes
  do vencimento não pesa;
- a Pendência cancelada e o lembrete da Agenda regulatória (Pendência sem
  Reunião) ficam fora, e a Reunião do Núcleo que quem pede não alcança também.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from app.dependencies import reunioes_ocultas, tem_acesso_reunioes
from app.services.inicio.regras import FUSO
from app.services.paginacao import ler_tudo

# Hoje e os 89 dias antes, como o ranking (decisão 62 do diretor).
DIAS_DOS_NUMEROS = 90
# Hoje e os 6 dias antes.
DIAS_DO_ENTREGUE = 7
# O tamanho de cada `in` na consulta: a lista de quem acompanha passa disso.
_LOTE = 200


class Numeros(BaseModel):
    no_prazo: int = 0
    fora_do_prazo: int = 0


class Entrega(BaseModel):
    id: str
    titulo: str
    concluida_em: date
    no_prazo: bool


class MeusNumeros(BaseModel):
    numeros_90_dias: Numeros
    # Do mais recente para o mais antigo.
    entregues_7_dias: list[Entrega]


def _dia_em_brasilia(valor) -> date | None:
    if not valor:
        return None
    momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(FUSO).date()


def _prazo(valor) -> date | None:
    return date.fromisoformat(str(valor)[:10]) if valor else None


def calcular(pendencias: Iterable[dict], historico: Iterable[dict], hoje: date) -> dict[str, list[Entrega]]:
    """As entregas dos últimos 90 dias de cada responsável, sem banco."""
    inicio = hoje - timedelta(days=DIAS_DOS_NUMEROS - 1)
    por_id = {
        p["id_acao"]: p
        for p in pendencias
        if p.get("status") != "CANCELADO" and p.get("responsavel_id") and p.get("id_reuniao")
    }
    por_pendencia: dict[str, list[dict]] = {}
    for evento in historico:
        if evento.get("id_acao") in por_id:
            por_pendencia.setdefault(evento["id_acao"], []).append(evento)

    saida: dict[str, list[Entrega]] = {}
    for id_acao, eventos in por_pendencia.items():
        p = por_id[id_acao]
        repactuou_vencida = False
        for evento in sorted(eventos, key=lambda e: (str(e.get("criado_em")), e.get("id") or 0)):
            if evento.get("comando") == "repactuar":
                repactuou_vencida = repactuou_vencida or bool(evento.get("conta_atraso"))
                continue
            if evento.get("comando") != "concluir":
                continue
            dia = _dia_em_brasilia(evento.get("criado_em"))
            prazo = _prazo(evento.get("prazo_antes"))
            no_prazo = not repactuou_vencida and not (prazo is not None and dia > prazo)
            # A Repactuação vencida pesa na entrega que veio depois dela, não
            # na seguinte, depois de uma Reabertura.
            repactuou_vencida = False
            if dia is None or not inicio <= dia <= hoje:
                continue
            saida.setdefault(p["responsavel_id"], []).append(
                Entrega(
                    id=id_acao,
                    titulo=p.get("descricao_acao") or "Pendência sem descrição",
                    concluida_em=dia,
                    no_prazo=no_prazo,
                )
            )
    for lista in saida.values():
        lista.sort(key=lambda e: (e.concluida_em, e.id), reverse=True)
    return saida


def numeros(lista: Iterable[Entrega]) -> Numeros:
    resultado = Numeros()
    for entrega in lista:
        if entrega.no_prazo:
            resultado.no_prazo += 1
        else:
            resultado.fora_do_prazo += 1
    return resultado


def _lotes(ids: list[str]) -> list[list[str]]:
    return [ids[i : i + _LOTE] for i in range(0, len(ids), _LOTE)]


def ler(supabase, responsaveis: Iterable[str], ocultas: Iterable[str], hoje: date) -> dict[str, list[Entrega]]:
    """As entregas de 90 dias destes responsáveis, lidas em páginas. O
    histórico vem inteiro, sem a janela: a Repactuação vencida de antes dos 90
    dias ainda pesa na entrega que caiu dentro deles."""
    ids = sorted(set(responsaveis))
    if not ids:
        return {}
    escondidas = set(ocultas)
    pendencias: list[dict] = []
    for lote in _lotes(ids):
        linhas = ler_tudo(
            lambda lote=lote: (
                supabase.table("pendencias")
                .select("id_acao, descricao_acao, status, responsavel_id, id_reuniao")
                .in_("responsavel_id", lote)
                .is_("deleted_at", "null")
                .order("id_acao")
            ),
            rotulo="pendências das entregas",
        )
        pendencias.extend(linha for linha in linhas if linha.get("id_reuniao") not in escondidas)
    historico: list[dict] = []
    for lote in _lotes(sorted({p["id_acao"] for p in pendencias if p.get("id_reuniao")})):
        historico.extend(
            ler_tudo(
                lambda lote=lote: (
                    supabase.table("pendencia_historico")
                    .select("id, id_acao, comando, criado_em, conta_atraso, prazo_antes")
                    .in_("comando", ["concluir", "repactuar"])
                    .in_("id_acao", lote)
                    .order("id")
                ),
                rotulo="histórico das entregas",
            )
        )
    return calcular(pendencias, historico, hoje)


def meus_numeros(supabase, me: dict | None, agora: datetime) -> MeusNumeros | None:
    """Os próprios números de quem pede. None para quem não tem papel nas
    Reuniões, que não tem Pendência."""
    if not me or not tem_acesso_reunioes(me):
        return None
    hoje = agora.astimezone(FUSO).date()
    minhas = ler(supabase, [me["id"]], reunioes_ocultas(supabase, me), hoje).get(me["id"], [])
    desde = hoje - timedelta(days=DIAS_DO_ENTREGUE - 1)
    return MeusNumeros(
        numeros_90_dias=numeros(minhas),
        entregues_7_dias=[e for e in minhas if e.concluida_em >= desde],
    )
