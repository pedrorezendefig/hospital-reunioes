"""O texto da memória gerado do banco (issue #1130, PRD #1128).

É o texto que vai para a IA, no formato do arquivo de importação: o cabeçalho
YAML com os parâmetros da versão e as tabelas de regras por seção, uma regra
por linha. Sai do banco, e não do arquivo guardado na importação: a regra
mudada depois (a edição pela tela, PRD #1129) vai para a IA como está agora.

Ida e volta sem perda: `ler_memoria(gerar_texto_memoria(...))` devolve a
mesma operadora, versão, situação, parâmetros e regras do arquivo importado.
O texto solto do arquivo do diretor (introdução, "Responder:", comentários do
cabeçalho) não é guardado em lugar nenhum e não volta; um arquivo escrito no
formato gerado volta igual, letra por letra.

O formato é estável (as chaves do cabeçalho na ordem do modelo do diretor, as
de dentro em ordem alfabética, as regras por seção e por ID) para o mesmo
banco dar sempre o mesmo texto: é o que deixa o cache de prompt valer entre
as contas da operadora.
"""

from __future__ import annotations

from typing import Any

import yaml

__all__ = ["gerar_texto_memoria", "orientacoes_de_leitura"]

# As seções do MODELO-MEMORIA-OPERADORA.md, pelo prefixo do ID da regra.
SECOES = {
    "PRI": "1. PRINCÍPIOS",
    "PRC": "2. PREÇOS E TABELAS",
    "DIA": "3. DIÁRIAS",
    "PAC": "4. PACOTES",
    "TAX": "5. TAXAS E ALUGUÉIS",
    "CC": "6. CENTRO CIRÚRGICO",
    "HON": "7. HONORÁRIOS",
    "INS": "8. QUANTIDADES E INSUMOS POR TEMPO",
    "MED": "9. MEDICAMENTOS",
}
SECAO_SEM_PREFIXO = "OUTRAS REGRAS"

# A ordem das chaves do cabeçalho no modelo do diretor. Chave fora da lista
# vem depois, em ordem alfabética.
ORDEM_DO_CABECALHO = (
    "operadora",
    "nome",
    "versao_memoria",
    "data",
    "origem",
    "situacao",
    "contrato",
    "tabelas",
    "colunas_de_preco",
    "diaria",
    "tetos_por_dia",
    "precos",
    "pacote_uti_adulto",
    "fora_da_conta_do_hospital",
    "transicao",
)

COLUNAS = ("ID", "Regra", "Tipo", "Origem", "Status", "Data")


def _em_ordem(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {chave: _em_ordem(valor[chave]) for chave in sorted(valor)}
    if isinstance(valor, list):
        return [_em_ordem(item) for item in valor]
    return valor


def _cabecalho(parametros: dict[str, Any], sigla: str, versao: str) -> str:
    valores = {**parametros, "operadora": sigla, "versao_memoria": versao}

    def posicao(chave: str) -> tuple[int, str]:
        return (ORDEM_DO_CABECALHO.index(chave) if chave in ORDEM_DO_CABECALHO else len(ORDEM_DO_CABECALHO), chave)

    ordenado = {chave: _em_ordem(valores[chave]) for chave in sorted(valores, key=posicao)}
    return yaml.safe_dump(ordenado, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6)


def _celula(valor: Any) -> str:
    """O valor numa célula de tabela: a barra escapada e a quebra de linha
    como `<br>`, que a leitura da memória desfaz."""
    return str(valor or "").replace("|", "\\|").replace("\n", "<br>")


def _data(validado_em: str | None) -> str:
    """`2026-09-23` (ou o timestamp do banco) como a memória escreve: 23/09/2026."""
    if not validado_em:
        return ""
    ano, mes, dia = str(validado_em)[:10].split("-")
    return f"{dia}/{mes}/{ano}"


def _linha(celulas: list[str]) -> str:
    return "| " + " | ".join(celulas) + " |"


def _tabela(regras: list[dict[str, Any]]) -> list[str]:
    linhas = [_linha(list(COLUNAS)), "|" + "---|" * len(COLUNAS)]
    for regra in regras:
        linhas.append(
            _linha(
                [
                    _celula(regra["codigo"]),
                    _celula(regra.get("texto")),
                    _celula(regra.get("tipo")),
                    _celula(regra.get("origem")),
                    _celula(regra.get("status")),
                    _data(regra.get("validado_em")),
                ]
            )
        )
    return linhas


def gerar_texto_memoria(supabase, operadora_id: str, versao_id: str | None = None) -> str:
    """O texto da memória da operadora no formato do arquivo: a versão pedida
    ou, sem ela, a vigente. Só as regras ativas entram."""
    operadoras = supabase.table("cm_operadora").select("sigla, nome").eq("id", operadora_id).execute().data or []
    consulta = (
        supabase.table("cm_memoria_versao").select("id, versao, parametros_json").eq("operadora_id", operadora_id)
    )
    consulta = consulta.eq("id", versao_id) if versao_id else consulta.eq("vigente", True)
    versoes = consulta.execute().data or []
    if not operadoras or not versoes:
        raise LookupError("A operadora não tem esta versão da memória.")
    operadora, versao = operadoras[0], versoes[0]
    regras = (
        supabase.table("cm_regra")
        .select("codigo, secao, texto, tipo, origem, status, validado_em")
        .eq("memoria_versao_id", versao["id"])
        .eq("ativa", True)
        .order("codigo")
        .execute()
        .data
        or []
    )

    por_secao: dict[str, list[dict[str, Any]]] = {}
    for regra in regras:
        por_secao.setdefault(SECOES.get(regra.get("secao") or "", SECAO_SEM_PREFIXO), []).append(regra)
    ordem = [*SECOES.values(), SECAO_SEM_PREFIXO]

    partes = [
        "---\n" + _cabecalho(versao.get("parametros_json") or {}, operadora["sigla"], versao["versao"]) + "---",
        f"# MEMÓRIA DA OPERADORA: {operadora['nome']}",
    ]
    for secao in sorted(por_secao, key=ordem.index):
        partes.append(f"## {secao}")
        partes.append("\n".join(_tabela(por_secao[secao])))
    return "\n\n".join(partes) + "\n"


# O que orienta a leitura do prontuário no passo A (spec 9.2): princípios,
# diárias e quantidades por tempo. O resto da memória é do passo B.
SECOES_DA_LEITURA = ("PRI", "DIA", "INS")


def orientacoes_de_leitura(regras: list[dict[str, Any]]) -> str:
    """As seções 1, 3 e 8 da memória, no mesmo formato de tabela do texto
    inteiro. `regras` são as ativas da versão, como `memoria_vigente` lê."""
    partes = []
    for prefixo in SECOES_DA_LEITURA:
        da_secao = sorted((r for r in regras if r.get("secao") == prefixo), key=lambda r: r["codigo"])
        if da_secao:
            partes += [f"## {SECOES[prefixo]}", "\n".join(_tabela(da_secao))]
    return "\n\n".join(partes) + "\n" if partes else "(a memória não tem orientações de leitura)\n"
