"""Quem responde a você (issue #1943, ADR 0104 decisão 9).

O bloco do Início de quem acompanha outras pessoas, em pedido separado do
resto do Início: a falha dele não derruba a Minha Fila. Até o organograma
chegar (#1910), quem aparece segue o vínculo da ADR 0098, decisão 7, sem
hierarquia e sem `role`: o Super admin vê todas as pessoas com Pendência
aberta, e o Facilitador vê os responsáveis e co-responsáveis das Pendências
das Reuniões que conduziu. Quem não é nenhum dos dois não recebe o bloco.

O sigilo do Núcleo vale para todos, o Super admin incluído (ADR 0095): a
Pendência de Reunião do Núcleo que quem pede não alcança fica fora, e o
lembrete da Agenda regulatória só entra para quem alcança a agenda. O último
acesso (Registro de acesso, decisão 10) só é lido para as pessoas da lista,
que são justamente as que têm algum item visível a quem pede.

As entregas de 90 dias de cada pessoa (issue #1946) são a mesma conta que
ela vê no Início dela (`entregas`), com o sigilo do Núcleo de quem pede. As
Rotinas do ciclo entram em outra fatia.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.dependencies import is_super_admin, recursos_nsp_da_pessoa, reunioes_ocultas, tem_acesso_reunioes
from app.services.inicio import entregas
from app.services.inicio.fonte_pendencias import STATUS_ABERTOS
from app.services.inicio.registro_de_acesso import TABELA as TABELA_DO_REGISTRO
from app.services.inicio.regras import FUSO, dias_de_atraso
from app.services.paginacao import ler_tudo
from app.services.pendencia_service import e_lembrete_do_nucleo

_COLUNAS = "id_acao, descricao_acao, prazo, id_reuniao, responsavel_id, co_responsavel_id"


class ItemVencido(BaseModel):
    id: str
    titulo: str
    origem: str
    prazo: date
    dias_de_atraso: int


class PessoaQueResponde(BaseModel):
    id: str
    nome: str
    cargo: str | None = None
    vencidos: int
    em_aberto: int
    ultimo_acesso: str
    entregas_90_dias: entregas.Numeros
    itens_vencidos: list[ItemVencido]


class QuemRespondeAVoce(BaseModel):
    pessoas: list[PessoaQueResponde]


def _data(valor: Any) -> date | None:
    return date.fromisoformat(str(valor)[:10]) if valor else None


def texto_do_ultimo_acesso(dia: date | None, hoje: date) -> str:
    """O texto do último acesso: "hoje", "há N dias" ou "nunca entrou". O
    Registro guarda 90 dias, então quem não abre o Início há mais tempo que
    isso também lê "nunca entrou"."""
    if dia is None:
        return "nunca entrou"
    dias = max((hoje - dia).days, 0)
    if dias == 0:
        return "hoje"
    return "há 1 dia" if dias == 1 else f"há {dias} dias"


def _reunioes_que_conduziu(supabase, me: dict) -> dict[str, dict]:
    resultado = (
        supabase.table("reunioes")
        .select("id_reuniao, titulo, data")
        .eq("facilitador_id", me["id"])
        .is_("deleted_at", "null")
        .execute()
    )
    return {linha["id_reuniao"]: linha for linha in resultado.data or []}


def _reunioes(supabase, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    resultado = supabase.table("reunioes").select("id_reuniao, titulo, data").in_("id_reuniao", ids).execute()
    return {linha["id_reuniao"]: linha for linha in resultado.data or []}


def _abertas(supabase, reunioes: list[str] | None) -> list[dict]:
    """As Pendências abertas, de todas as Reuniões (None) ou só destas."""

    def consulta():
        q = supabase.table("pendencias").select(_COLUNAS).in_("status", list(STATUS_ABERTOS)).is_("deleted_at", "null")
        if reunioes is not None:
            q = q.in_("id_reuniao", reunioes)
        return q.order("id_acao")

    return ler_tudo(consulta, rotulo="pendências de Quem responde a você")


def _origem(linha: dict, reunioes: dict[str, dict]) -> str:
    if e_lembrete_do_nucleo(linha):
        return "Lembrete da Agenda regulatória do Núcleo."
    reuniao = reunioes.get(linha["id_reuniao"])
    if not reuniao:
        return "Pendência de Reunião."
    titulo = (reuniao.get("titulo") or "Reunião").strip()
    quando = _data(reuniao.get("data"))
    return f"{titulo}, de {quando.strftime('%d/%m/%Y')}." if quando else f"{titulo}."


def _visiveis(supabase, me: dict) -> tuple[list[dict], dict[str, dict], set[str]] | None:
    """As Pendências abertas que quem pede acompanha, com as Reuniões delas e
    as Reuniões do Núcleo que quem pede não alcança. None quando a pessoa não
    acompanha ninguém e não recebe o bloco."""
    if not tem_acesso_reunioes(me):
        return None
    ocultas = set(reunioes_ocultas(supabase, me))
    if is_super_admin(me):
        linhas = _abertas(supabase, None)
        com_agenda = "agenda" in recursos_nsp_da_pessoa(supabase, me)
        linhas = [
            linha
            for linha in linhas
            if (com_agenda if e_lembrete_do_nucleo(linha) else linha["id_reuniao"] not in ocultas)
        ]
        reunioes = _reunioes(supabase, sorted({linha["id_reuniao"] for linha in linhas if linha.get("id_reuniao")}))
        return linhas, reunioes, ocultas
    conduzidas = {rid: r for rid, r in _reunioes_que_conduziu(supabase, me).items() if rid not in ocultas}
    if not conduzidas:
        return None
    return _abertas(supabase, sorted(conduzidas)), conduzidas, ocultas


def _ultimos_acessos(supabase, ids: list[str]) -> dict[str, date]:
    """Até 90 marcas por pessoa: a lista do Super admin passa fácil do teto
    de linhas do PostgREST, que corta em silêncio. Por isso lê em páginas,
    ordenado pela chave da tabela."""
    if not ids:
        return {}

    def consulta():
        return (
            supabase.table(TABELA_DO_REGISTRO)
            .select("participante_id, dia")
            .in_("participante_id", ids)
            .order("participante_id")
            .order("dia")
        )

    ultimos: dict[str, date] = {}
    for linha in ler_tudo(consulta, rotulo="último acesso de Quem responde a você"):
        dia = _data(linha.get("dia"))
        if dia and (linha["participante_id"] not in ultimos or dia > ultimos[linha["participante_id"]]):
            ultimos[linha["participante_id"]] = dia
    return ultimos


def montar(supabase, me: dict | None, agora: datetime) -> QuemRespondeAVoce | None:
    if not me:
        return None
    visiveis = _visiveis(supabase, me)
    if visiveis is None:
        return None
    linhas, reunioes, ocultas = visiveis
    hoje = agora.astimezone(FUSO).date()

    por_pessoa: dict[str, list[dict]] = {}
    for linha in linhas:
        for pessoa_id in {linha.get("responsavel_id"), linha.get("co_responsavel_id")} - {None, me["id"]}:
            por_pessoa.setdefault(pessoa_id, []).append(linha)

    ids = sorted(por_pessoa)
    cadastro = {}
    if ids:
        resultado = supabase.table("participantes").select("id, nome_completo, cargo").in_("id", ids).execute()
        cadastro = {linha["id"]: linha for linha in resultado.data or []}
    acessos = _ultimos_acessos(supabase, ids)
    entregues = entregas.ler(supabase, ids, ocultas, hoje)

    pessoas: list[PessoaQueResponde] = []
    for pessoa_id in ids:
        itens = por_pessoa[pessoa_id]
        vencidos = []
        for linha in itens:
            atraso = dias_de_atraso(_data(linha.get("prazo")), agora)
            if atraso:
                vencidos.append(
                    ItemVencido(
                        id=linha["id_acao"],
                        titulo=linha.get("descricao_acao") or "Pendência sem descrição",
                        origem=_origem(linha, reunioes),
                        prazo=_data(linha["prazo"]),
                        dias_de_atraso=atraso,
                    )
                )
        vencidos.sort(key=lambda item: (-item.dias_de_atraso, item.id))
        pessoa = cadastro.get(pessoa_id) or {}
        pessoas.append(
            PessoaQueResponde(
                id=pessoa_id,
                nome=(pessoa.get("nome_completo") or "Pessoa sem cadastro").strip(),
                cargo=pessoa.get("cargo"),
                vencidos=len(vencidos),
                em_aberto=len(itens),
                ultimo_acesso=texto_do_ultimo_acesso(acessos.get(pessoa_id), hoje),
                entregas_90_dias=entregas.numeros(entregues.get(pessoa_id, [])),
                itens_vencidos=vencidos,
            )
        )
    pessoas.sort(key=lambda p: (-p.vencidos, -p.em_aberto, p.nome))
    return QuemRespondeAVoce(pessoas=pessoas)
