"""A tela de triagem do Núcleo (issue #1992, PRD #1979, ADR 0095 e 0107).

O agente sugere (`agente_de_triagem`) e a Presidência decide aqui. Três peças:

- a fila: as notificações sem triagem confirmada, da mais antiga para a mais
  nova, com a faixa e o assunto sugeridos. Nada do relato nem de quem
  notificou: o assunto do agente já sai sem nome de pessoa;
- a tela de um caso: a notificação, a sugestão (ou nenhuma, quando ficou para
  classificar manualmente), a regra de conferência e o que o sistema calcula
  (recorrência, casos parecidos, frequência e prioridade pela matriz do Anexo
  A, seção 7.2);
- a decisão: confirmar a sugestão como veio, ou ajustar. Grava a linha da
  pessoa em `nsp_triagens` ao lado da sugestão, que fica como está, com as
  divergências campo a campo, e leva o caso a Classificada, ou a Em análise
  agregada na faixa E e na D sem dano.

Nas faixas A e B, com menção a morte, com evento da lista "possível" ou quando
quem notificou marcou grave e o agente sugeriu menos, confirmar exige cada
campo conferido: não existe "aceitar tudo". O banco guarda uma decisão de
pessoa por notificação (migration 194).
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from postgrest.exceptions import APIError

from app.services.seguranca_do_paciente import notificacoes
from app.services.seguranca_do_paciente.triagem_do_agente import (
    CANAIS,
    CATEGORIAS,
    GRAUS_DE_DANO,
    ITENS_DA_LISTA,
    NATUREZAS,
    PROTOCOLOS_BASICOS,
    SITUACOES_DA_LISTA,
    faixa_esperada,
    menciona_morte,
)

LOTE_DE_IDS = notificacoes.LOTE_DE_IDS
TAMANHO_DA_PAGINA = notificacoes.TAMANHO_DA_PAGINA

ESTADOS_DA_FILA = ("recebida", "em_triagem")
CLASSIFICADA = "classificada"
EM_ANALISE_AGREGADA = "em_analise_agregada"

# Os campos que a Presidência confere um a um quando a revisão é campo a campo.
CAMPOS_DA_CONFERENCIA = (
    "assunto",
    "natureza",
    "grau_de_dano",
    "categoria",
    "incidente",
    "evento",
    "iras",
    "risco_de_imagem",
    "protocolo_basico",
    "canais",
    "faixa",
)

# Por que a revisão é campo a campo.
MOTIVO_FAIXA = "faixa"
MOTIVO_MORTE = "morte"
MOTIVO_EVENTO_POSSIVEL = "evento_possivel"
MOTIVO_GRAVE_MARCADO = "grave_marcado"
MOTIVO_AGENTE = "agente"

# A recorrência da tela: "3ª ocorrência desta categoria neste setor em 60 dias".
JANELA_DA_RECORRENCIA_DIAS = 60

# Os cortes de frequência (Configuração), com a sugestão da issue #2005 como
# padrão: em 12 meses, nenhuma anterior = remoto, 1 = incomum, 2 ou 3 =
# ocasional, 4 ou mais = frequente.
CORTES_PADRAO = {"janela_meses": 12, "incomum_a_partir": 1, "ocasional_a_partir": 2, "frequente_a_partir": 4}
_CAMPOS_DOS_CORTES = tuple(CORTES_PADRAO)

# A matriz de prioridade do Anexo A, seção 7.2: gravidade por frequência.
_MATRIZ = {
    "frequente": {"catastrofico": "alta", "grave": "alta", "moderado": "moderada", "leve": "baixa"},
    "ocasional": {"catastrofico": "alta", "grave": "moderada", "moderado": "baixa", "leve": "baixa"},
    "incomum": {"catastrofico": "alta", "grave": "moderada", "moderado": "baixa", "leve": "baixa"},
    "remoto": {"catastrofico": "alta", "grave": "moderada", "moderado": "baixa", "leve": "baixa"},
}
# A gravidade da matriz pela faixa: A é óbito ou evento que nunca deveria
# ocorrer (catastrófico), B dano grave, C moderado, D e E leve ou sem dano.
_GRAVIDADE_DA_FAIXA = {"A": "catastrofico", "B": "grave", "C": "moderado", "D": "leve", "E": "leve"}

_SEM_DANO = ("circunstancia_de_risco", "quase_erro", "incidente_sem_dano")
_DANO_DE_EVENTO_ADVERSO = ("leve", "moderado", "grave", "obito")
_TAMANHO_DO_ASSUNTO = 300


class TriagemRecusadaError(Exception):
    """A decisão não pode ser gravada; a mensagem vai para a tela."""


class CasoNaoEncontradoError(TriagemRecusadaError):
    pass


class JaConfirmadaError(TriagemRecusadaError):
    pass


class ConferenciaIncompletaError(TriagemRecusadaError):
    pass


class ClassificacaoInvalidaError(TriagemRecusadaError):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Leituras
# ═══════════════════════════════════════════════════════════════════════════


def _paginas(consulta: Callable[[], Any]) -> list[dict[str, Any]]:
    """Toda linha da consulta, página a página, abaixo do teto do PostgREST.
    O id descarta a repetição de uma linha que mudou de lugar no meio."""
    linhas: list[dict[str, Any]] = []
    vistas: set[str] = set()
    inicio = 0
    while True:
        pagina = consulta().range(inicio, inicio + TAMANHO_DA_PAGINA - 1).execute().data or []
        for linha in pagina:
            if linha["id"] not in vistas:
                vistas.add(linha["id"])
                linhas.append(linha)
        if len(pagina) < TAMANHO_DA_PAGINA:
            return linhas
        inicio += TAMANHO_DA_PAGINA


def _triagens_por_notificacao(supabase, notificacao_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """As linhas de triagem de cada notificação, lidas em lotes de ids."""
    por_notificacao: dict[str, list[dict[str, Any]]] = {}
    for inicio in range(0, len(notificacao_ids), LOTE_DE_IDS):
        lote = notificacao_ids[inicio : inicio + LOTE_DE_IDS]
        for linha in supabase.table("nsp_triagens").select("*").in_("notificacao_id", lote).execute().data or []:
            por_notificacao.setdefault(linha["notificacao_id"], []).append(linha)
    return por_notificacao


def _sugestao(linhas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A última rodada do agente."""
    do_agente = [linha for linha in linhas if linha.get("autor_tipo") == "agente"]
    return max(do_agente, key=lambda linha: linha["versao"]) if do_agente else None


def _decisao(linhas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A linha da pessoa: a triagem confirmada."""
    return next((linha for linha in linhas if linha.get("autor_tipo") == "pessoa"), None)


def _vigente(linhas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """O que vale para o caso: a decisão, ou a sugestão enquanto não há decisão."""
    return _decisao(linhas) or _sugestao(linhas)


def _nomes_dos_setores(supabase, setor_ids: set[str]) -> dict[str, str]:
    if not setor_ids:
        return {}
    linhas = supabase.table("setores").select("id, nome").in_("id", sorted(setor_ids)).execute().data or []
    return {linha["id"]: linha["nome"] for linha in linhas}


# ═══════════════════════════════════════════════════════════════════════════
# A fila
# ═══════════════════════════════════════════════════════════════════════════

_CAMPOS_DA_FILA = (
    "id, protocolo, numero, criado_em, setor_id, data_ocorrencia, grave_ou_morte, "
    "classificar_manualmente, motivo_classificar_manualmente"
)


def fila(supabase) -> list[dict[str, Any]]:
    """As notificações sem triagem confirmada, da mais antiga para a mais nova.
    Sem relato e sem quem notificou: a fila mostra o protocolo, o setor, a data,
    a faixa e o assunto sugeridos."""
    linhas = _paginas(
        lambda: (
            supabase.table("nsp_notificacoes")
            .select(_CAMPOS_DA_FILA)
            .in_("estado", list(ESTADOS_DA_FILA))
            .order("criado_em")
        )
    )
    linhas.sort(key=lambda linha: (str(linha.get("criado_em")), linha.get("numero") or 0))
    triagens = _triagens_por_notificacao(supabase, [linha["id"] for linha in linhas])
    setores = _nomes_dos_setores(supabase, {linha["setor_id"] for linha in linhas if linha.get("setor_id")})
    itens = []
    for linha in linhas:
        das_linhas = triagens.get(linha["id"], [])
        if _decisao(das_linhas):
            continue
        sugestao = _sugestao(das_linhas)
        itens.append(
            {
                "id": linha["id"],
                "protocolo": linha["protocolo"],
                "criado_em": linha.get("criado_em"),
                "data_ocorrencia": linha.get("data_ocorrencia"),
                "setor": setores.get(linha.get("setor_id")),
                "grave_ou_morte": linha.get("grave_ou_morte"),
                "faixa": sugestao["faixa"] if sugestao else None,
                "assunto": sugestao["assunto"] if sugestao else None,
                "classificar_manualmente": bool(linha.get("classificar_manualmente")),
            }
        )
    return itens


# ═══════════════════════════════════════════════════════════════════════════
# O cálculo: recorrência, casos parecidos, frequência e prioridade
# ═══════════════════════════════════════════════════════════════════════════


def frequencia(anteriores: int, cortes: dict[str, int]) -> str:
    """A frequência pela contagem das ocorrências anteriores na janela."""
    if anteriores >= cortes["frequente_a_partir"]:
        return "frequente"
    if anteriores >= cortes["ocasional_a_partir"]:
        return "ocasional"
    if anteriores >= cortes["incomum_a_partir"]:
        return "incomum"
    return "remoto"


def prioridade(faixa: str | None, freq: str | None) -> str | None:
    """A prioridade pela matriz do Anexo A, seção 7.2. Sem faixa do Núcleo
    (não é do NSP ou indeterminada), sem prioridade."""
    gravidade = _GRAVIDADE_DA_FAIXA.get(faixa or "")
    if gravidade is None or freq is None:
        return None
    return _MATRIZ[freq][gravidade]


def _meses_antes(dia: date, meses: int) -> date:
    anos, mes = divmod(dia.month - 1 - meses, 12)
    ano = dia.year + anos
    return date(ano, mes + 1, min(dia.day, calendar.monthrange(ano, mes + 1)[1]))


def cortes_de_frequencia(supabase) -> dict[str, int]:
    """Os cortes da Configuração, ou o padrão enquanto a migration 194 não
    rodou."""
    try:
        linhas = (
            supabase.table("nsp_cortes_de_frequencia").select(", ".join(_CAMPOS_DOS_CORTES)).limit(1).execute().data
        )
    except APIError:
        linhas = None
    if not linhas:
        return dict(CORTES_PADRAO)
    return {campo: int(linhas[0][campo]) for campo in _CAMPOS_DOS_CORTES}


def salvar_cortes_de_frequencia(supabase, cortes: dict[str, int], *, autor_id: str) -> dict[str, int]:
    """Grava os cortes, em ordem crescente e com o incomum a partir de uma
    ocorrência. Vale para o que for calculado daqui para a frente; a decisão
    já gravada guarda a frequência do dia dela."""
    novos = {campo: cortes[campo] for campo in _CAMPOS_DOS_CORTES}
    if not 1 <= novos["janela_meses"] <= 60:
        raise ClassificacaoInvalidaError("A janela vai de 1 a 60 meses.")
    if not 1 <= novos["incomum_a_partir"] < novos["ocasional_a_partir"] < novos["frequente_a_partir"]:
        raise ClassificacaoInvalidaError(
            "Os cortes crescem: incomum a partir de 1 ocorrência, ocasional depois do incomum, "
            "frequente depois do ocasional."
        )
    linha = {**novos, "atualizado_por": autor_id, "atualizado_em": datetime.now(UTC).isoformat()}
    gravadas = supabase.table("nsp_cortes_de_frequencia").update(linha).eq("id", True).execute().data
    if not gravadas:
        supabase.table("nsp_cortes_de_frequencia").insert({"id": True, **linha}).execute()
    return novos


def contexto(supabase, notificacao: dict[str, Any], categoria: str | None, faixa: str | None) -> dict[str, Any]:
    """O que o sistema calcula para o caso, na categoria e na faixa dadas:
    a recorrência e os casos parecidos (mesmo setor e categoria, 60 dias até
    a data do incidente), a frequência (ocorrências anteriores na janela dos
    cortes) e a prioridade. A categoria de cada outro caso é a da triagem
    confirmada, ou a sugerida enquanto não há confirmação."""
    cortes = cortes_de_frequencia(supabase)
    vazio = {
        "recorrencia": None,
        "janela_da_recorrencia_dias": JANELA_DA_RECORRENCIA_DIAS,
        "parecidos": [],
        "anteriores": None,
        "frequencia": None,
        "prioridade": None,
        "cortes": cortes,
    }
    setor_id, quando = notificacao.get("setor_id"), notificacao.get("data_ocorrencia")
    if not setor_id or not quando or categoria not in CATEGORIAS:
        return vazio
    dia = date.fromisoformat(str(quando)[:10])
    inicio_da_recorrencia = dia - timedelta(days=JANELA_DA_RECORRENCIA_DIAS)
    inicio_da_frequencia = _meses_antes(dia, cortes["janela_meses"])
    outros = [
        linha
        for linha in _paginas(
            lambda: (
                supabase.table("nsp_notificacoes")
                .select("id, protocolo, estado, data_ocorrencia")
                .eq("setor_id", setor_id)
                .gte("data_ocorrencia", min(inicio_da_recorrencia, inicio_da_frequencia).isoformat())
                .lte("data_ocorrencia", dia.isoformat())
                .order("data_ocorrencia")
            )
        )
        if linha["id"] != notificacao["id"]
    ]
    triagens = _triagens_por_notificacao(supabase, [linha["id"] for linha in outros])
    mesmas = []
    for linha in outros:
        vigente = _vigente(triagens.get(linha["id"], []))
        if vigente and vigente.get("categoria") == categoria:
            mesmas.append({**linha, "assunto": vigente.get("assunto")})
    parecidos = sorted(
        (m for m in mesmas if str(m["data_ocorrencia"])[:10] >= inicio_da_recorrencia.isoformat()),
        key=lambda m: (str(m["data_ocorrencia"]), m["protocolo"]),
        reverse=True,
    )
    anteriores = sum(1 for m in mesmas if str(m["data_ocorrencia"])[:10] >= inicio_da_frequencia.isoformat())
    freq = frequencia(anteriores, cortes)
    return {
        **vazio,
        "recorrencia": len(parecidos) + 1,
        "parecidos": [
            {
                "id": m["id"],
                "protocolo": m["protocolo"],
                "data_ocorrencia": m["data_ocorrencia"],
                "estado": m["estado"],
                "assunto": m["assunto"],
            }
            for m in parecidos
        ],
        "anteriores": anteriores,
        "frequencia": freq,
        "prioridade": prioridade(faixa, freq),
    }


# ═══════════════════════════════════════════════════════════════════════════
# A tela de um caso
# ═══════════════════════════════════════════════════════════════════════════

_CAMPOS_DA_TRIAGEM = (
    "assunto",
    "natureza",
    "grau_de_dano",
    "categoria",
    "incidente",
    "iras",
    "risco_de_imagem",
    "protocolo_basico",
    "canais",
    "motivo_do_encaminhamento",
    "faixa",
    "revisao",
    "justificativa",
    "confianca",
    "motivo_da_confianca",
    "alertas",
    "perguntas_ao_notificante",
    "divergencias",
    "frequencia",
    "prioridade",
    "criado_em",
)


def _apresentar(linha: dict[str, Any] | None) -> dict[str, Any] | None:
    if linha is None:
        return None
    apresentada = {campo: linha.get(campo) for campo in _CAMPOS_DA_TRIAGEM}
    apresentada["evento"] = {
        "situacao": linha.get("evento_situacao"),
        "item": linha.get("evento_item"),
        "motivo": linha.get("evento_motivo"),
    }
    return apresentada


def motivos_da_conferencia(notificacao: dict[str, Any], sugestao: dict[str, Any] | None) -> list[str]:
    """Por que a confirmação é campo a campo; lista vazia quando é um clique.
    Faixa A ou B, menção a morte no relato, evento da lista "possível", quem
    notificou marcou grave e a sugestão ficou abaixo de B, ou o próprio agente
    pediu a revisão campo a campo."""
    faixa = sugestao.get("faixa") if sugestao else None
    motivos = []
    if faixa in ("A", "B"):
        motivos.append(MOTIVO_FAIXA)
    if menciona_morte(notificacao.get("relato")):
        motivos.append(MOTIVO_MORTE)
    if sugestao and sugestao.get("evento_situacao") == "possivel":
        motivos.append(MOTIVO_EVENTO_POSSIVEL)
    if notificacao.get("grave_ou_morte") is True and faixa not in ("A", "B"):
        motivos.append(MOTIVO_GRAVE_MARCADO)
    if sugestao and sugestao.get("revisao") == "campo_a_campo" and not motivos:
        motivos.append(MOTIVO_AGENTE)
    return motivos


_CAMPOS_DA_NOTIFICACAO = (
    "id, estado, relato, setor_id, data_ocorrencia, grave_ou_morte, classificar_manualmente, "
    "motivo_classificar_manualmente"
)


def _notificacao(supabase, notificacao_id: str) -> dict[str, Any] | None:
    linhas = (
        supabase.table("nsp_notificacoes")
        .select(_CAMPOS_DA_NOTIFICACAO)
        .eq("id", notificacao_id)
        .limit(1)
        .execute()
        .data
    )
    return linhas[0] if linhas else None


def _opcoes(supabase) -> dict[str, list[dict[str, Any]]]:
    """As 19 categorias e os 30 eventos da lista, da configuração do banco
    (migration 188), para a pessoa escolher ao ajustar."""
    categorias = supabase.table("nsp_categorias").select("codigo, nome, ordem").order("ordem").execute().data or []
    eventos = (
        supabase.table("nsp_eventos_que_nunca_deveriam_ocorrer").select("item, evento").order("item").execute().data
        or []
    )
    categorias.sort(key=lambda c: c.get("ordem") or 0)
    eventos.sort(key=lambda e: e["item"])
    return {
        "categorias": [{"codigo": c["codigo"], "nome": c["nome"]} for c in categorias],
        "eventos": [{"item": e["item"], "evento": e["evento"]} for e in eventos],
    }


def abrir(supabase, notificacao_id: str, *, com_identidade: bool) -> dict[str, Any] | None:
    """A tela de triagem de um caso, ou None quando ele não existe."""
    notificacao = _notificacao(supabase, notificacao_id)
    if notificacao is None:
        return None
    caso = notificacoes.abrir(supabase, notificacao_id, com_identidade=com_identidade)
    if caso is None:
        return None
    linhas = _triagens_por_notificacao(supabase, [notificacao_id]).get(notificacao_id, [])
    sugestao, decisao = _sugestao(linhas), _decisao(linhas)
    motivos = motivos_da_conferencia(notificacao, sugestao)
    vigente = decisao or sugestao
    return {
        "caso": caso,
        "sugestao": _apresentar(sugestao),
        "decisao": _apresentar(decisao),
        "pendente": decisao is None and notificacao.get("estado") in ESTADOS_DA_FILA,
        "classificar_manualmente": bool(notificacao.get("classificar_manualmente")),
        "motivo_classificar_manualmente": notificacao.get("motivo_classificar_manualmente"),
        "conferencia": {
            "campo_a_campo": bool(motivos),
            "motivos": motivos,
            "campos": list(CAMPOS_DA_CONFERENCIA),
        },
        "contexto": contexto(
            supabase,
            notificacao,
            vigente.get("categoria") if vigente else None,
            vigente.get("faixa") if vigente else None,
        ),
        "opcoes": _opcoes(supabase),
    }


def contexto_do_caso(supabase, notificacao_id: str, categoria: str | None, faixa: str | None) -> dict | None:
    """O cálculo de novo, para a categoria e a faixa que a pessoa escolheu."""
    notificacao = _notificacao(supabase, notificacao_id)
    if notificacao is None:
        return None
    return contexto(supabase, notificacao, categoria, faixa)


# ═══════════════════════════════════════════════════════════════════════════
# A decisão: confirmar ou ajustar
# ═══════════════════════════════════════════════════════════════════════════

# O que a linha da pessoa copia da sugestão ao confirmar como veio.
_CAMPOS_DA_CLASSIFICACAO = (
    "assunto",
    "natureza",
    "grau_de_dano",
    "categoria",
    "incidente",
    "evento_situacao",
    "evento_item",
    "evento_motivo",
    "iras",
    "risco_de_imagem",
    "protocolo_basico",
    "canais",
    "motivo_do_encaminhamento",
    "faixa",
)

# Cada campo conferido e as colunas que ele compara com a sugestão.
_COLUNAS_DO_CAMPO = {
    "assunto": ("assunto",),
    "natureza": ("natureza",),
    "grau_de_dano": ("grau_de_dano",),
    "categoria": ("categoria",),
    "incidente": ("incidente",),
    "evento": ("evento_situacao", "evento_item"),
    "iras": ("iras",),
    "risco_de_imagem": ("risco_de_imagem",),
    "protocolo_basico": ("protocolo_basico",),
    "canais": ("canais",),
    "faixa": ("faixa",),
}


def _comparavel(coluna: str, valor):
    if coluna == "canais":
        return sorted(valor or [])
    if isinstance(valor, str):
        return " ".join(valor.split()) or None
    return valor


def divergencias(sugestao: dict[str, Any], decisao: dict[str, Any]) -> list[str]:
    """Os campos em que a decisão da pessoa difere da sugestão do agente."""
    return [
        campo
        for campo, colunas in _COLUNAS_DO_CAMPO.items()
        if any(_comparavel(c, sugestao.get(c)) != _comparavel(c, decisao.get(c)) for c in colunas)
    ]


def _texto(valor) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ClassificacaoInvalidaError("Preencha a classificação com texto.")
    return " ".join(valor.split()) or None


def _validar(classificacao: dict[str, Any]) -> dict[str, Any]:
    """A classificação da pessoa, conferida pelas mesmas regras que valem para
    o agente (Anexo B). A faixa sai da natureza, do dano e da lista."""
    assunto = _texto(classificacao.get("assunto"))
    if not assunto:
        raise ClassificacaoInvalidaError("Escreva o assunto em uma linha.")
    if len(assunto) > _TAMANHO_DO_ASSUNTO:
        raise ClassificacaoInvalidaError(f"O assunto cabe em {_TAMANHO_DO_ASSUNTO} caracteres.")
    natureza, dano = classificacao.get("natureza"), classificacao.get("grau_de_dano")
    if natureza not in NATUREZAS:
        raise ClassificacaoInvalidaError("Escolha a natureza na lista.")
    if dano not in GRAUS_DE_DANO:
        raise ClassificacaoInvalidaError("Escolha o grau de dano na lista.")
    if (natureza in _SEM_DANO and dano != "nenhum") or (
        natureza == "evento_adverso" and dano not in _DANO_DE_EVENTO_ADVERSO
    ):
        raise ClassificacaoInvalidaError(
            "Circunstância de risco, quase erro e incidente sem dano não têm dano; "
            "evento adverso tem dano de leve a óbito."
        )
    if classificacao.get("categoria") not in CATEGORIAS:
        raise ClassificacaoInvalidaError("Escolha a categoria na lista.")
    situacao, item = classificacao.get("evento_situacao"), classificacao.get("evento_item")
    if situacao not in SITUACOES_DA_LISTA:
        raise ClassificacaoInvalidaError("Diga se é evento que nunca deveria ocorrer.")
    if situacao == "nao":
        if item is not None:
            raise ClassificacaoInvalidaError("O item da lista só vale quando é evento que nunca deveria ocorrer.")
    elif isinstance(item, bool) or not isinstance(item, int) or item not in ITENS_DA_LISTA:
        raise ClassificacaoInvalidaError("Escolha o item da lista dos eventos que nunca deveriam ocorrer.")
    if classificacao.get("protocolo_basico") not in PROTOCOLOS_BASICOS:
        raise ClassificacaoInvalidaError("Escolha o protocolo básico na lista.")
    for marcador in ("iras", "risco_de_imagem"):
        if not isinstance(classificacao.get(marcador), bool):
            raise ClassificacaoInvalidaError("Marque IRAS e risco de imagem com sim ou não.")
    canais = classificacao.get("canais")
    if not isinstance(canais, list) or not canais or any(canal not in CANAIS for canal in canais):
        raise ClassificacaoInvalidaError("Escolha ao menos um canal na lista.")
    if natureza != "nao_e_do_nsp" and "NSP" not in canais:
        raise ClassificacaoInvalidaError("O caso do Núcleo tem o canal NSP.")
    return {
        "assunto": assunto,
        "natureza": natureza,
        "grau_de_dano": dano,
        "categoria": classificacao["categoria"],
        "incidente": _texto(classificacao.get("incidente")),
        "evento_situacao": situacao,
        "evento_item": None if situacao == "nao" else item,
        "evento_motivo": _texto(classificacao.get("evento_motivo")),
        "iras": classificacao["iras"],
        "risco_de_imagem": classificacao["risco_de_imagem"],
        "protocolo_basico": classificacao["protocolo_basico"],
        "canais": list(dict.fromkeys(canais)),
        "motivo_do_encaminhamento": _texto(classificacao.get("motivo_do_encaminhamento")),
        "faixa": faixa_esperada(natureza, dano, situacao),
    }


def estado_depois_da_triagem(faixa: str, grau_de_dano: str) -> str:
    """Classificada, ou Em análise agregada na faixa E e na D sem dano."""
    if faixa == "E" or (faixa == "D" and grau_de_dano == "nenhum"):
        return EM_ANALISE_AGREGADA
    return CLASSIFICADA


def decidir(
    supabase,
    notificacao_id: str,
    *,
    autor_id: str,
    classificacao: dict[str, Any] | None,
    conferidos: list[str],
) -> dict[str, Any]:
    """Confirma a sugestão como veio (`classificacao` None) ou grava o ajuste
    da pessoa. Devolve o estado novo do caso e a linha gravada."""
    notificacao = _notificacao(supabase, notificacao_id)
    if notificacao is None:
        raise CasoNaoEncontradoError("Caso não encontrado.")
    linhas = _triagens_por_notificacao(supabase, [notificacao_id]).get(notificacao_id, [])
    sugestao = _sugestao(linhas)
    if notificacao.get("estado") not in ESTADOS_DA_FILA:
        raise JaConfirmadaError("A triagem deste caso já foi confirmada.")
    gravada = _decisao(linhas)
    if gravada:
        # A decisão ficou gravada e a mudança de estado falhou: a nova
        # tentativa conclui com o que foi gravado, sem gravar outra linha.
        return _concluir(supabase, notificacao_id, gravada, autor_id)
    motivos = motivos_da_conferencia(notificacao, sugestao)
    if motivos and not set(CAMPOS_DA_CONFERENCIA) <= set(conferidos or []):
        raise ConferenciaIncompletaError(
            "Confira cada campo antes de confirmar: este caso não aceita confirmação direta."
        )
    if classificacao is None:
        if sugestao is None:
            raise ClassificacaoInvalidaError("Este caso não tem sugestão: preencha a classificação.")
        campos = {campo: sugestao.get(campo) for campo in _CAMPOS_DA_CLASSIFICACAO}
        divergentes: list[str] | None = []
    else:
        campos = _validar(classificacao)
        divergentes = divergencias(sugestao, campos) if sugestao else None
    calculo = contexto(supabase, notificacao, campos["categoria"], campos["faixa"])
    linha = {
        "notificacao_id": notificacao_id,
        "autor_tipo": "pessoa",
        "autor_id": autor_id,
        **campos,
        "revisao": "campo_a_campo" if motivos else "confirmacao_simples",
        "alertas": [],
        "perguntas_ao_notificante": [],
        "divergencias": divergentes,
        "frequencia": calculo["frequencia"],
        "prioridade": calculo["prioridade"],
    }
    try:
        gravada = supabase.table("nsp_triagens").insert(linha).execute().data[0]
    except APIError as erro:
        if erro.code == "23505":
            raise JaConfirmadaError("A triagem deste caso já foi confirmada.") from erro
        raise
    return _concluir(supabase, notificacao_id, gravada, autor_id)


def _concluir(supabase, notificacao_id: str, decisao: dict[str, Any], autor_id: str) -> dict[str, Any]:
    """Leva o caso ao estado que a decisão gravada pede."""
    estado = estado_depois_da_triagem(decisao["faixa"], decisao["grau_de_dano"])
    supabase.table("nsp_notificacoes").update({"estado": estado, "editado_por": autor_id}).eq("id", notificacao_id).in_(
        "estado", list(ESTADOS_DA_FILA)
    ).execute()
    return {"estado": estado, "triagem": _apresentar(decisao)}
