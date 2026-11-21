"""O Início de cada pessoa (ADR 0104): a Minha Fila de todos os módulos.

O endpoint chama uma função por módulo, a fonte. Toda fonte devolve itens no
mesmo formato (tipo, título, origem, prazo ou a data em que o item chegou,
área, rótulo da ação, destino interno e, quando couber, a ação de um clique),
já recortados para quem pede. Aqui o grupo e o atraso de cada item saem da
data, a fila é ordenada e a frase é escrita. Fonte que lança erro não derruba
a resposta: ela some com um aviso (decisão 4). Módulo novo entra como fonte
nova em `FONTES`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel

from app.services.inicio import (
    fonte_contas_medicas,
    fonte_contestacoes,
    fonte_nucleo,
    fonte_ouvidoria,
    fonte_pendencias,
    fonte_pops,
    fonte_reunioes,
    fonte_rotinas,
)
from app.services.inicio.regras import (
    ATE_48_HORAS,
    FUSO,
    GRUPOS,
    PASSOU_DO_PRAZO,
    PROXIMOS_7_DIAS,
    SEM_PRAZO,
    dias_de_atraso,
    dias_esperando,
    frase_do_inicio,
    grupo_do_item,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fonte:
    nome: str
    rotulo: str
    # (supabase, quem pede, agora) -> itens no formato comum, sem grupo.
    itens: Callable[..., list[dict]]
    # (supabase, quem pede, hoje) -> as Rotinas do ciclo, no trilho (issue #1944).
    do_ciclo: Callable[..., list[dict]] | None = None


FONTES: tuple[Fonte, ...] = (
    Fonte("pendencias", fonte_pendencias.ROTULO, fonte_pendencias.itens),
    Fonte("contestacoes", fonte_contestacoes.ROTULO, fonte_contestacoes.itens),
    Fonte("atas", fonte_reunioes.ROTULO, fonte_reunioes.itens),
    Fonte("rotinas", fonte_rotinas.ROTULO, fonte_rotinas.itens, fonte_rotinas.do_ciclo),
    Fonte("ouvidoria", fonte_ouvidoria.ROTULO, fonte_ouvidoria.itens),
    Fonte("pops", fonte_pops.ROTULO, fonte_pops.itens),
    Fonte("contas_medicas", fonte_contas_medicas.ROTULO, fonte_contas_medicas.itens),
    Fonte("nucleo", fonte_nucleo.ROTULO, fonte_nucleo.itens),
)

# A Fila do papel (ADR 0104, decisão 6): a fila sem responsável nomeado, uma
# linha de resumo para quem a enxerga pelo perfil. Mesmo formato de fonte; cada
# uma devolve as linhas de `FilaDoPapel` que cabem a quem pede.
FILAS_DO_PAPEL: tuple[Fonte, ...] = (
    Fonte("fila_da_ouvidoria", fonte_ouvidoria.ROTULO_DA_FILA, fonte_ouvidoria.fila_do_papel),
    Fonte("fila_de_contas", fonte_contas_medicas.ROTULO_DA_FILA, fonte_contas_medicas.fila_do_papel),
)


class AcaoDeUmClique(BaseModel):
    rotulo: str
    endpoint: str


class AcaoSecundaria(BaseModel):
    """O caminho ao lado do botão de um clique, para a outra saída do item que
    pede tela própria (a Não realizada da Rotina, que pede Anotação)."""

    rotulo: str
    destino: str


class ItemDoInicio(BaseModel):
    tipo: str
    id: str
    titulo: str
    origem: str
    prazo: date | None = None
    chegou_em: date | None = None
    area: str
    acao: str
    destino: str
    # A linha de contexto (issue #1935): aparece no hover, no foco e sempre na
    # tela de toque. Fonte que não tem o que dizer deixa vazia.
    contexto: str | None = None
    acao_de_um_clique: AcaoDeUmClique | None = None
    acao_secundaria: AcaoSecundaria | None = None
    # O módulo de origem não dá prazo ao item: ele fica em Sem prazo, e só
    # sai de lá se o `prazo` que a fonte calculou vencer.
    sem_prazo_no_modulo: bool = False
    grupo: str | None = None
    dias_de_atraso: int | None = None
    dias_esperando: int | None = None


class Frase(BaseModel):
    titulo: str
    apoio: str


class Contadores(BaseModel):
    passou_do_prazo: int = 0
    ate_48_horas: int = 0
    proximos_7_dias: int = 0


class AvisoDeFonte(BaseModel):
    fonte: str
    mensagem: str


class ItemDoTrilho(BaseModel):
    tipo: str
    id: str
    titulo: str
    data: date
    hora: str | None = None
    papel: str
    destino: str


class RotinaDoCiclo(BaseModel):
    """Uma Rotina no trilho (issue #1944): o ciclo de agora e a Verificação
    dele, quando já marcada (REALIZADA ou NAO_REALIZADA)."""

    id: str
    titulo: str
    ciclo_inicio: date
    ciclo_fim: date
    verificacao: str | None = None
    destino: str


class FilaDoPapel(BaseModel):
    fila: str
    titulo: str
    esperam: int
    vencidas: int
    resumo: str
    destino: str


class Inicio(BaseModel):
    hoje: date
    frase: Frase
    contadores: Contadores
    itens: list[ItemDoInicio]
    avisos: list[AvisoDeFonte]
    # O trilho, ao lado da fila: as próximas Reuniões e as Rotinas do ciclo
    # (issue #1944). Fora da fila e da contagem da frase.
    trilho: list[ItemDoTrilho] = []
    rotinas_do_ciclo: list[RotinaDoCiclo] = []
    filas_do_papel: list[FilaDoPapel] = []


def _primeiro_nome(me: dict | None) -> str | None:
    nome = ((me or {}).get("nome_completo") or "").strip()
    return nome.split()[0] if nome else None


def _ordem(item: ItemDoInicio) -> tuple:
    # O mais atrasado primeiro, o mais distante por último; no fim, o grupo
    # Sem prazo, do que espera há mais tempo para o mais recente.
    if item.grupo == SEM_PRAZO:
        return (True, item.chegou_em or date.max, item.id)
    return (False, item.prazo or date.max, item.id)


def _aviso(nome: str, rotulo: str, me: dict) -> AvisoDeFonte:
    logger.exception("[Início] A fonte %s falhou para %s", nome, me.get("id"))
    return AvisoDeFonte(fonte=nome, mensagem=f"Não foi possível carregar {rotulo} agora. Tente de novo em instantes.")


def _ler(fonte: Fonte, supabase, me: dict, agora: datetime, avisos: list[AvisoDeFonte]) -> list[dict]:
    """O que a fonte devolve, ou nada e um aviso quando ela falha (decisão 4)."""
    try:
        return fonte.itens(supabase, me, agora)
    except Exception:
        avisos.append(_aviso(fonte.nome, fonte.rotulo, me))
        return []


def montar_inicio(
    supabase,
    me: dict | None,
    agora: datetime,
    fontes: tuple[Fonte, ...] = FONTES,
    filas_do_papel: tuple[Fonte, ...] = FILAS_DO_PAPEL,
) -> Inicio:
    itens: list[ItemDoInicio] = []
    filas: list[FilaDoPapel] = []
    avisos: list[AvisoDeFonte] = []
    trilho: list[ItemDoTrilho] = []
    rotinas_do_ciclo: list[RotinaDoCiclo] = []
    hoje = agora.astimezone(FUSO).date()
    if me:
        for fonte in fontes:
            for bruto in _ler(fonte, supabase, me, agora, avisos):
                item = ItemDoInicio(**bruto)
                item.grupo = grupo_do_item(item.prazo, item.sem_prazo_no_modulo, agora)
                item.dias_de_atraso = dias_de_atraso(item.prazo, agora) if item.grupo == PASSOU_DO_PRAZO else None
                item.dias_esperando = dias_esperando(item.chegou_em, agora) if item.grupo == SEM_PRAZO else None
                itens.append(item)
            if fonte.do_ciclo is not None:
                try:
                    rotinas_do_ciclo.extend(RotinaDoCiclo(**bruto) for bruto in fonte.do_ciclo(supabase, me, hoje))
                except Exception:
                    avisos.append(_aviso(f"{fonte.nome}_do_ciclo", f"{fonte.rotulo} do ciclo", me))
        try:
            trilho = [ItemDoTrilho(**bruto) for bruto in fonte_reunioes.proximas(supabase, me, hoje)]
        except Exception:
            avisos.append(_aviso("trilho", fonte_reunioes.ROTULO_DO_TRILHO, me))
        # A Fila do papel fica fora da frase e dos contadores (decisão 6).
        for fila in filas_do_papel:
            filas.extend(FilaDoPapel(**bruto) for bruto in _ler(fila, supabase, me, agora, avisos))
    itens.sort(key=_ordem)

    por_grupo = {grupo: [item for item in itens if item.grupo == grupo] for grupo in GRUPOS}
    vencidos = por_grupo[PASSOU_DO_PRAZO]
    futuros = [
        item.prazo for item in itens if item.grupo != SEM_PRAZO and item.prazo is not None and item.prazo >= hoje
    ]
    titulo, apoio = frase_do_inicio(
        nome=_primeiro_nome(me),
        vencidos=len(vencidos),
        maior_atraso=max((item.dias_de_atraso or 0 for item in vencidos), default=0),
        em_48_horas=len(por_grupo[ATE_48_HORAS]),
        proximo_prazo=min(futuros, default=None),
    )
    return Inicio(
        hoje=hoje,
        frase=Frase(titulo=titulo, apoio=apoio),
        contadores=Contadores(
            passou_do_prazo=len(vencidos),
            ate_48_horas=len(por_grupo[ATE_48_HORAS]),
            proximos_7_dias=len(por_grupo[PROXIMOS_7_DIAS]),
        ),
        itens=itens,
        avisos=avisos,
        trilho=trilho,
        rotinas_do_ciclo=rotinas_do_ciclo,
        filas_do_papel=filas,
    )
