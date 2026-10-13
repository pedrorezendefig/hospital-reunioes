"""Carga da operadora (issue #1119, PRD #1113, ADR 0070): memória, planos e setores.

A memória entra por arquivo (`memoria.ler_memoria`) e vira uma versão nova em
`cm_memoria_versao`, com as regras em `cm_regra`. Só uma versão é vigente por
operadora; `memoria_vigente` é o que as conferências leem.

A ordem da gravação protege a versão em uso: a nova nasce não vigente, recebe
as regras e só então troca de lugar com a anterior. Uma falha no meio deixa
uma versão órfã fora de uso, nunca uma operadora com metade das regras.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from postgrest.exceptions import APIError

from app.services.contas_medicas.contratos import gravar_contrato_da_memoria
from app.services.contas_medicas.memoria import MemoriaLida, parametros_lidos
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.tabelas import tabelas_por_categoria
from app.services.contas_medicas_conta import chave_do_plano

__all__ = [
    "CadastroRecusadoError",
    "cadastrar_plano",
    "cadastrar_setor",
    "importar_memoria",
    "listar_operadoras",
    "listar_planos",
    "listar_setores",
    "memoria_vigente",
    "reconhecer_plano",
    "texto_da_memoria_vigente",
]


class CadastroRecusadoError(ValueError):
    """O cadastro não entra; `conflito` diz se é por já existir outro igual."""

    def __init__(self, mensagem: str, *, conflito: bool = False):
        super().__init__(mensagem)
        self.conflito = conflito


def _operadora(supabase, memoria: MemoriaLida) -> dict:
    existentes = supabase.table("cm_operadora").select("*").eq("sigla", memoria.sigla).execute().data or []
    if existentes:
        return existentes[0]
    return (
        supabase.table("cm_operadora")
        .insert({"sigla": memoria.sigla, "nome": memoria.nome, "situacao": "SEM_MEMORIA"})
        .execute()
        .data[0]
    )


def importar_memoria(supabase, memoria: MemoriaLida, texto_md: str, autor_id: str | None) -> dict:
    """Grava a memória lida como a versão vigente da operadora e devolve o resumo."""
    operadora = _operadora(supabase, memoria)
    vigentes = sum(1 for r in memoria.regras if r.status == "VIGENTE")
    contagem = {"total": len(memoria.regras), "vigentes": vigentes, "pendentes": len(memoria.regras) - vigentes}

    versao = (
        supabase.table("cm_memoria_versao")
        .insert(
            {
                "operadora_id": operadora["id"],
                "versao": memoria.versao,
                "parametros_json": memoria.parametros,
                "texto_md": texto_md,
                "vigente": False,
                "autor_id": autor_id,
                "resumo": f"{contagem['total']} regras: {vigentes} vigentes e {contagem['pendentes']} pendentes",
            }
        )
        .execute()
        .data[0]
    )
    if memoria.regras:
        supabase.table("cm_regra").insert(
            [
                {
                    "operadora_id": operadora["id"],
                    "memoria_versao_id": versao["id"],
                    "codigo": r.codigo,
                    "secao": r.secao,
                    "texto": r.texto,
                    "tipo": r.tipo,
                    "origem": r.origem,
                    "status": r.status,
                    "validado_em": r.validado_em,
                    "modelo_id": r.modelo_id,
                }
                for r in memoria.regras
            ]
        ).execute()

    supabase.table("cm_memoria_versao").update({"vigente": False}).eq("operadora_id", operadora["id"]).eq(
        "vigente", True
    ).execute()
    supabase.table("cm_memoria_versao").update({"vigente": True}).eq("id", versao["id"]).execute()
    supabase.table("cm_operadora").update({"nome": memoria.nome, "situacao": memoria.situacao}).eq(
        "id", operadora["id"]
    ).execute()
    gravar_contrato_da_memoria(supabase, operadora["id"], memoria.parametros, texto_md)

    return {
        "operadora": memoria.sigla,
        "nome": memoria.nome,
        "situacao": memoria.situacao,
        "versao": memoria.versao,
        "regras": contagem,
        "parametros": parametros_lidos(memoria.parametros),
    }


def listar_operadoras(supabase) -> list[dict[str, Any]]:
    """Cada operadora com a situação, a versão vigente da memória, a contagem de
    regras ativas e cada categoria de tabela de preço com as versões carregadas."""
    operadoras = supabase.table("cm_operadora").select("id, sigla, nome, situacao").order("sigla").execute().data or []
    versoes = {
        v["operadora_id"]: v
        for v in (
            supabase.table("cm_memoria_versao")
            .select("id, operadora_id, versao, parametros_json")
            .eq("vigente", True)
            .execute()
            .data
            or []
        )
    }
    ligacoes = supabase.table("cm_operadora_tabela").select("operadora_id, categoria, tabela_id").execute().data or []
    precos = {}
    if ligacoes:
        precos = {
            t["id"]: t
            for t in supabase.table("cm_tabela_preco")
            .select("id, nome, tipo, versao, vigencia_inicio, vigencia_fim, criado_em")
            .in_("id", [ligacao["tabela_id"] for ligacao in ligacoes])
            .execute()
            .data
            or []
        }
    tabelas: dict[str, list[dict[str, Any]]] = {}
    for ligacao in ligacoes:
        if ligacao["tabela_id"] in precos:
            tabelas.setdefault(ligacao["operadora_id"], []).append(
                {**precos[ligacao["tabela_id"]], "categoria": ligacao["categoria"]}
            )

    lista = []
    for operadora in operadoras:
        versao = versoes.get(operadora["id"])
        status = []
        if versao:
            status = [
                r["status"]
                for r in supabase.table("cm_regra")
                .select("status")
                .eq("memoria_versao_id", versao["id"])
                .eq("ativa", True)
                .execute()
                .data
                or []
            ]
        lista.append(
            {
                "sigla": operadora["sigla"],
                "nome": operadora["nome"],
                "situacao": operadora["situacao"],
                "versao": versao["versao"] if versao else None,
                "regras": {"vigentes": status.count("VIGENTE"), "pendentes": status.count("PENDENTE")},
                "tabelas": tabelas_por_categoria(
                    (versao or {}).get("parametros_json") or {}, tabelas.get(operadora["id"], [])
                ),
            }
        )
    return lista


def memoria_vigente(supabase, operadora_id: str) -> dict | None:
    """A versão vigente da memória da operadora: parâmetros lidos e regras ativas.

    Sem memória carregada, `None`: a operadora está SEM_MEMORIA.
    """
    versoes = (
        supabase.table("cm_memoria_versao")
        .select("id, versao, parametros_json")
        .eq("operadora_id", operadora_id)
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    if not versoes:
        return None
    versao = versoes[0]
    regras = (
        supabase.table("cm_regra")
        .select("codigo, secao, texto, tipo, origem, status")
        .eq("memoria_versao_id", versao["id"])
        .eq("ativa", True)
        .order("codigo")
        .execute()
        .data
        or []
    )
    return {
        "memoria_versao_id": versao["id"],
        "versao": versao["versao"],
        "parametros": parametros_lidos(versao.get("parametros_json") or {}),
        "regras": regras,
    }


def texto_da_memoria_vigente(supabase, sigla: str) -> tuple[str, str] | None:
    """A versão e o texto Markdown da memória vigente para exportar, gerado do
    banco no formato do arquivo de importação: o cabeçalho de `parametros_json`
    com todas as chaves e as regras como estão agora, por seção."""
    operadoras = supabase.table("cm_operadora").select("id").eq("sigla", sigla.strip().upper()).execute().data or []
    if not operadoras:
        return None
    versoes = (
        supabase.table("cm_memoria_versao")
        .select("versao")
        .eq("operadora_id", operadoras[0]["id"])
        .eq("vigente", True)
        .execute()
        .data
        or []
    )
    if not versoes:
        return None
    return versoes[0]["versao"], gerar_texto_memoria(supabase, operadoras[0]["id"])


def reconhecer_plano(nome_na_conta: str, planos: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """O plano cadastrado que corresponde ao nome impresso na conta, ou `None`.

    Mesma comparação da coluna de preço: sem acento, sem diferença de maiúscula
    e ignorando o sufixo de acomodação (ENF, APT).
    """
    chave = chave_do_plano(nome_na_conta)
    return next((p for p in planos if chave_do_plano(p["nome_mv"]) == chave), None)


def _siglas(supabase) -> dict[str, str]:
    linhas = supabase.table("cm_operadora").select("id, sigla").execute().data or []
    return {linha["id"]: linha["sigla"] for linha in linhas}


def listar_planos(supabase) -> list[dict[str, Any]]:
    """Os planos do MV cadastrados, com a sigla da operadora de cada um."""
    siglas = _siglas(supabase)
    linhas = (
        supabase.table("cm_operadora_plano")
        .select("id, nome_mv, operadora_id, coluna_preco")
        .order("nome_mv")
        .execute()
        .data
        or []
    )
    return [{**linha, "operadora": siglas.get(linha["operadora_id"])} for linha in linhas]


def _sem_espacos_sobrando(texto: str | None) -> str:
    return " ".join((texto or "").split())


def cadastrar_plano(supabase, nome_mv: str, sigla: str, coluna_preco: str | None) -> dict[str, Any]:
    """Liga o nome do plano como o MV imprime à operadora e à coluna de preço.

    Recusa o nome que o reconhecimento já acha em outro cadastro: dois planos
    que se confundem deixariam a conta com operadora ou coluna ao acaso.
    """
    nome = _sem_espacos_sobrando(nome_mv)
    if not nome:
        raise CadastroRecusadoError("Informe o nome do plano como o MV imprime.")
    sigla = sigla.strip().upper()
    operadora = next((oid for oid, s in _siglas(supabase).items() if s == sigla), None)
    if operadora is None:
        raise CadastroRecusadoError(f"A operadora {sigla} não está cadastrada. Envie a memória dela antes.")
    ja_existe = reconhecer_plano(nome, listar_planos(supabase))
    if ja_existe:
        raise CadastroRecusadoError(
            f"Este nome já é reconhecido como o plano {ja_existe['nome_mv']} ({ja_existe['operadora']}).",
            conflito=True,
        )
    coluna = _sem_espacos_sobrando(coluna_preco).upper() or None
    try:
        linha = (
            supabase.table("cm_operadora_plano")
            .insert({"nome_mv": nome, "operadora_id": operadora, "coluna_preco": coluna})
            .execute()
            .data[0]
        )
    except APIError as exc:
        if exc.code == "23505":
            raise CadastroRecusadoError("Este plano já está cadastrado.", conflito=True) from None
        raise
    return {**linha, "operadora": sigla}


def listar_setores(supabase) -> list[dict[str, Any]]:
    """Os setores como o MV imprime, cada um com a acomodação."""
    return supabase.table("cm_setor").select("id, nome_mv, acomodacao").order("nome_mv").execute().data or []


def cadastrar_setor(supabase, nome_mv: str, acomodacao: str) -> dict[str, Any]:
    """Liga o nome do setor no MV à acomodação. Não é o Setor dos POPs nem o das Reuniões."""
    nome = _sem_espacos_sobrando(nome_mv)
    if not nome:
        raise CadastroRecusadoError("Informe o nome do setor como o MV imprime.")
    try:
        return supabase.table("cm_setor").insert({"nome_mv": nome, "acomodacao": acomodacao}).execute().data[0]
    except APIError as exc:
        if exc.code == "23505":
            raise CadastroRecusadoError(f"O setor {nome} já está cadastrado.", conflito=True) from None
        raise
