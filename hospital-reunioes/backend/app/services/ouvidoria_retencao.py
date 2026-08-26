"""Retenção da Ouvidoria: anonimização após cinco anos (issue #343, ADR 0034).

A manifestação encerrada há mais de cinco anos perde o Dossiê e vira estatística.
O que sai é o que identifica ou narra o caso; o que fica é o que os relatórios
contam. A separação é explícita de propósito: uma anonimização por lista de
exclusão erra sempre que uma coluna nova nasce, então aqui a lista é a das
colunas que SAEM, e cada coluna nova precisa de uma decisão consciente.

O Dossiê não mora só na manifestação. O relato e a resposta da área se
espalham por quatro lugares, e a retenção varre os quatro:

  1. `ouvidoria_protocolos`, as colunas de texto e identificação;
  2. `ouvidoria_anexos`, metadados aqui e binário no bucket privado;
  3. `ouvidoria_movimentos.observacao`, que carrega a resposta INTEIRA da área
     (issue #374) e é servida pela rota do histórico de respostas;
  4. `ouvidoria_tentativas_contato.observacao` e as duas justificativas de
     `ouvidoria_prorrogacoes`, texto livre sobre o caso.

Ordem das operações: o movimento da trilha vem PRIMEIRO, e o carimbo por
ÚLTIMO. Tudo o que destrói fica no meio, entre os dois. O motivo está em
`_anonimizar_caso`.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio; aqui
vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.config import settings
from app.services import storage

logger = logging.getLogger(__name__)

ENCERRADO = "encerrado"

# O prazo de retenção da ADR 0034: cinco anos contados do encerramento (T3).
# O mesmo prazo está escrito na guarda de UPDATE da trilha (migration 079).
# Mudar aqui exige mudar lá.
ANOS_DE_RETENCAO = 5

# Teto de casos por rodada. O job roda uma vez por dia e nasce dormindo (nenhum
# caso tem cinco anos ainda), mas o dia em que a fila acumular não pode virar
# uma varredura infinita segurando o scheduler.
LOTE_POR_RODADA = 100

# Quem assina o movimento da retenção. É por este nome que a rodada seguinte
# reconhece um movimento já gravado e não grava outro.
AUTOR_DA_RETENCAO = "Sistema (retenção)"

# O Dossiê na manifestação: o que a retenção apaga. Cada campo é texto livre
# sobre o caso ou identificação de quem manifestou.
CAMPOS_DO_DOSSIE: dict[str, str | None] = {
    "relato_integral": None,
    "manifestante_nome": None,
    "manifestante_contato": None,
    # Cópias e derivados do relato, espalhados pela tramitação.
    "extrato_para_o_setor": None,
    "resposta_da_area": None,
    "desfecho_descricao": None,
    "classificacao_ia": None,
    # Ponte para a conversa da Ana, onde o relato original continua inteiro.
    "conversa_id": "",
}

# `resumo` é NOT NULL com CHECK anti-vazio desde a migration 063: não pode ir a
# NULL, então vira marcador. O texto some do mesmo jeito. Mesma história para
# `justificativa` da prorrogação (migration 073).
MARCADOR_ANONIMIZADO = "[anonimizado pela retenção]"

# O que fica, e por quê: é disto que o módulo de métricas tira volume, prazo
# cumprido, ranking por área e reincidência. A lista não é usada pelo código
# (o update só toca no Dossiê); ela existe para o teste de retenção afirmar,
# campo a campo, o que a anonimização não pode ter mexido.
CAMPOS_ESTATISTICOS: tuple[str, ...] = (
    "numero",
    "protocolo",
    "status",
    "data_abertura",
    "contato_em",
    "validada_em",
    "respondida_em",
    "encerrada_em",
    "prazo_area_em",
    "tipo_manifestacao",
    "categoria",
    "setor",
    "gravidade",
    "canal",
    "desfecho",
    "minutos_pausados",
    "reincidencia",
    "anonimo",
    "sigilo_reforcado",
    "manifestante_vinculo",
)

# O que o job precisa do caso para decidir e anonimizar.
_CAMPOS_DA_RETENCAO = "id, status, encerrada_em, anonimizada_em"


def data_de_corte(agora: dt.datetime) -> dt.datetime:
    """O instante a partir do qual o encerramento ainda está dentro da retenção.

    Encerramento anterior ou igual ao corte já passou dos cinco anos. Feito por
    subtração de ano (não por 365 dias) para o aniversário cair no mesmo dia;
    29 de fevereiro recua para 28."""
    try:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO)
    except ValueError:
        return agora.replace(year=agora.year - ANOS_DE_RETENCAO, day=28)


def anonimizar_encerradas_antigas(supabase, agora: dt.datetime) -> int:
    """Anonimiza as manifestações encerradas há mais de cinco anos.

    Devolve quantas foram anonimizadas nesta rodada. Com o freio puxado
    (`OUVIDORIA_RETENCAO_ATIVA=false`), devolve 0 sem tocar em nada."""
    if not settings.ouvidoria_retencao_ativa:
        logger.info("[Ouvidoria] Retenção desligada por configuração; nenhum caso será anonimizado.")
        return 0

    corte = data_de_corte(agora)
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DA_RETENCAO)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            # Caso com `encerrada_em` nulo (encerrado antes do marco T3 existir,
            # ou vindo do import histórico do NocoDB) fica de fora: sem saber
            # quando fechou, não dá para dizer que os cinco anos passaram.
            .lte("encerrada_em", corte.isoformat())
            .order("encerrada_em")
            .limit(LOTE_POR_RODADA)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos encerrados para a retenção")
        return 0

    anonimizadas = 0
    for caso in result.data or []:
        if _anonimizar_caso(supabase, caso, agora):
            anonimizadas += 1
    return anonimizadas


def _anonimizar_caso(supabase, caso: dict, agora: dt.datetime) -> bool:
    """Anonimiza um caso inteiro, na ordem que sobrevive a uma falha no meio.

    O movimento da trilha vem PRIMEIRO: ele é o registro que prova a
    legalidade do ato, e gravá-lo depois do carimbo significaria que uma falha
    ali destruiria o Dossiê sem deixar rastro, para sempre, porque nenhuma
    rodada seguinte volta em caso carimbado. Gravado antes, o pior caso é um
    movimento em pé com o Dossiê ainda inteiro, e a rodada seguinte termina o
    serviço reaproveitando o mesmo movimento.

    O carimbo vem por ÚLTIMO pelo mesmo motivo, do outro lado: enquanto ele não
    existe, o caso volta na varredura e a limpeza recomeça. Cada passo é
    idempotente, então recomeçar não custa nada.

    Qualquer passo que falhe interrompe o caso e devolve False: um caso
    contado como anonimizado com metade do Dossiê em pé seria pior que um caso
    que voltou para a fila."""
    movimento_id = _garantir_movimento(supabase, caso["id"])
    if movimento_id is None:
        return False
    if not _limpar_observacoes_da_trilha(supabase, caso["id"], exceto=movimento_id):
        return False
    if not _limpar_tentativas_de_contato(supabase, caso["id"]):
        return False
    if not _limpar_prorrogacoes(supabase, caso["id"]):
        return False
    if not _apagar_anexos(supabase, caso["id"]):
        return False
    return _apagar_dossie(supabase, caso["id"], agora)


def _garantir_movimento(supabase, manifestacao_id: str) -> str | None:
    """O ato entra na trilha do caso, uma vez só. Devolve o id do movimento, ou
    None quando não foi possível garantir que ele existe.

    Não é transição de estado (o caso segue encerrado), então o insert é
    direto, no molde do movimento de prazo rompido. A idempotência não vem do
    carimbo da manifestação (que ainda não existe neste ponto) e sim da
    assinatura: um movimento da retenção já gravado é reaproveitado.

    A observação não cita nada do Dossiê: este é o único movimento do caso que
    sobrevive à limpeza de observações, e um nome escrito aqui seria dado
    pessoal que a retenção nunca mais apagaria."""
    try:
        existentes = (
            supabase.table("ouvidoria_movimentos")
            .select("id")
            .eq("manifestacao_id", manifestacao_id)
            .eq("autor_nome", AUTOR_DA_RETENCAO)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao conferir o movimento de anonimização do caso %s", manifestacao_id)
        return None
    if existentes.data:
        return str(existentes.data[0]["id"])

    try:
        gravado = (
            supabase.table("ouvidoria_movimentos")
            .insert(
                {
                    "manifestacao_id": manifestacao_id,
                    "estado_anterior": ENCERRADO,
                    "estado_novo": ENCERRADO,
                    "autor_id": None,
                    "autor_nome": AUTOR_DA_RETENCAO,
                    "observacao": (
                        f"Manifestação anonimizada pela política de retenção de {ANOS_DE_RETENCAO} anos: "
                        "relato, identificação do manifestante, anexos e o conteúdo dos demais "
                        "registros do caso apagados. Os campos estatísticos foram preservados."
                    ),
                }
            )
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao gravar o movimento de anonimização do caso %s", manifestacao_id)
        return None
    if not gravado.data:
        logger.error("[Ouvidoria] Movimento de anonimização do caso %s não gravou", manifestacao_id)
        return None
    return str(gravado.data[0]["id"])


def _limpar_observacoes_da_trilha(supabase, manifestacao_id: str, exceto: str) -> bool:
    """Zera a `observacao` dos movimentos do caso, menos a do movimento da
    própria retenção.

    É aqui que o texto da resposta da área morre de verdade: o portal do setor
    grava a resposta INTEIRA na trilha (issue #374), e a rota do histórico de
    respostas serve esse texto sem olhar a anonimização. Apagar
    `resposta_da_area` sem apagar isto não anonimizaria nada.

    O resto do movimento (quem, quando, de que estado para qual) fica: a trilha
    continua provando o que aconteceu. Quem permite este único UPDATE é a
    guarda da migration 079, que confere na própria linha do caso que a
    política de cinco anos o cobre."""
    try:
        (
            supabase.table("ouvidoria_movimentos")
            .update({"observacao": None})
            .eq("manifestacao_id", manifestacao_id)
            .neq("id", exceto)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as observações da trilha do caso %s", manifestacao_id)
        return False
    return True


def _limpar_tentativas_de_contato(supabase, manifestacao_id: str) -> bool:
    """Zera a `observacao` das tentativas de contato do caso.

    É o que o ouvidor escreveu ao tentar falar com quem manifestou, tipicamente
    o telefone discado e o que foi dito. As linhas ficam, e com elas `canal` e
    `tentada_em`: quantas vezes e por onde a Ouvidoria tentou é estatística do
    encerramento por sem retorno, não relato de ninguém."""
    try:
        (
            supabase.table("ouvidoria_tentativas_contato")
            .update({"observacao": None})
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as tentativas de contato do caso %s", manifestacao_id)
        return False
    return True


def _limpar_prorrogacoes(supabase, manifestacao_id: str) -> bool:
    """Zera as duas justificativas da prorrogação do caso.

    `justificativa` é NOT NULL com CHECK anti-vazio (migration 073), então vira
    marcador. Dias pedidos, prazos e o status da decisão ficam: é deles que sai
    a taxa de prorrogação por área do PRD #319."""
    try:
        (
            supabase.table("ouvidoria_prorrogacoes")
            .update({"justificativa": MARCADOR_ANONIMIZADO, "decisao_justificativa": None})
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao limpar as prorrogações do caso %s", manifestacao_id)
        return False
    return True


def _apagar_anexos(supabase, manifestacao_id: str) -> bool:
    """Remove o binário do bucket e depois os metadados do caso.

    Binário primeiro: a linha é o único ponteiro para o arquivo, e apagá-la
    antes deixaria o arquivo órfão no bucket para sempre. Se alguma remoção
    falhar, nada é apagado do banco e a rodada seguinte tenta de novo."""
    try:
        result = (
            supabase.table("ouvidoria_anexos")
            .select("id, storage_path")
            .eq("manifestacao_id", manifestacao_id)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao listar os anexos do caso %s para a retenção", manifestacao_id)
        return False

    anexos = result.data or []
    for anexo in anexos:
        caminho = anexo.get("storage_path")
        if not caminho:
            continue
        if not storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, caminho):
            logger.error("[Ouvidoria] Falha ao remover o anexo %s do bucket; retenção adiada", caminho)
            return False

    if not anexos:
        return True
    try:
        supabase.table("ouvidoria_anexos").delete().eq("manifestacao_id", manifestacao_id).execute()
    except Exception:
        logger.error("[Ouvidoria] Falha ao apagar os metadados dos anexos do caso %s", manifestacao_id)
        return False
    return True


def _apagar_dossie(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    """Zera o Dossiê da manifestação e carimba a anonimização no mesmo update.

    O update é condicional (`status = 'encerrado'` e `anonimizada_em IS NULL`):
    a segunda rodada do job, uma rodada concorrente, ou um caso que reabriu
    entre a varredura e a gravação não acham o que anonimizar."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update(dict(CAMPOS_DO_DOSSIE) | {"resumo": MARCADOR_ANONIMIZADO, "anonimizada_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", ENCERRADO)
            .is_("anonimizada_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao apagar o Dossiê do caso %s", manifestacao_id)
        return False
    return bool(result.data)
