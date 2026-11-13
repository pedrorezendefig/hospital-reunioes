"""Regras puras da aba Tecnologia (PRD #634, ADR 0050).

Sem I/O: quem fala com o Supabase e o router e os servicos ao lado. Desde a ADR
0077 a aba e o chat do agente, e o que sobrou aqui e o que o chat, a
sincronizacao da Etapa e o Anexo ainda leem (issue #1386).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.dependencies import is_super_admin
from app.services.github_client import FATO_ASSIGNEE, PROJETO_ANA, PROJETO_HOSPITAL
from app.services.tecnologia_vinculo import (
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPA_REGISTRADA,
)

# As tabelas da aba. Moram aqui, e nao no router, porque quem escreve nelas nao
# e so o router: o webhook do GitHub e o job de reconciliacao escrevem pelo
# `tecnologia_sincronizacao`, e um nome de tabela repetido em tres arquivos e
# uma renomeacao que passa em dois deles.
TABELA_DEMANDAS = "tecnologia_demandas"
TABELA_PRODUTOS = "tecnologia_produtos"
# A Conversa da Demanda (issue #1537, ADR 0083, decisao 8): mensagens de gente,
# separadas da conversa com o agente, que mora em `tecnologia_planejamentos`.
TABELA_CONVERSA_DA_DEMANDA = "tecnologia_conversa_da_demanda"

# O estado da Demanda de antes da ADR 0077, congelado na coluna ate o drop. A
# sincronizacao e o apagamento dos prints ainda o leem: a Demanda Concluida ou
# Cancelada a mao, no Quadro de antes, nao volta a ser tocada. Os dois grupos
# sao o COMPLEMENTO um do outro sobre o CHECK da migration 102, e o teste cobra
# isso (`test_admin_tecnologia.py`).
ESTADOS_ABERTOS: tuple[str, ...] = ("nova", "em_andamento", "aguardando")
ESTADOS_FECHADOS: tuple[str, ...] = ("concluida", "cancelada")

# Quem abriu o card (ADR 0084, decisao 4; CHECK da migration 130): o diretor,
# pelo chat da aba, ou a Vitta, pela issue-raiz do app aberta no terminal.
ORIGEM_DIRETOR = "diretor"
ORIGEM_VITTA = "vitta"
ORIGENS: tuple[str, ...] = (ORIGEM_DIRETOR, ORIGEM_VITTA)

# O nome que a issue do bug leva quando a Demanda nao tem Produto.
SEM_PRODUTO = "(sem Produto)"

# O rotulo que a gente le de cada Tipo. O banco guarda o valor sem acento
# (CHECK da migration 102); o PRD do diretor escreve "Novo".
TIPO_ROTULO: dict[str, str] = {
    "decisao": "Decisão",
    "informacao": "Informação",
    "terceiro": "Terceiro",
    "ajuste": "Ajuste",
    "novo": "Novo",
    "defeito": "Defeito",
    "consultoria": "Consultoria",
}

RECUO_DA_CONTINUACAO = "    "


def instante_do_banco(valor: str | None) -> datetime | None:
    """O `TIMESTAMPTZ` do PostgREST como `datetime` consciente de fuso.

    Devolve `None` quando nao da para ler, e nunca "agora": um carimbo quebrado
    que virasse o instante atual seria uma janela (a da criacao do card, o
    prazo do print) aberta em cima de dado corrompido.

    Data sem fuso conta como UTC porque comparar um `datetime` ingenuo com um
    consciente estoura `TypeError`, e a janela viraria 500.
    """
    if not valor:
        return None
    try:
        lido = datetime.fromisoformat(str(valor))
    except ValueError:
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=UTC)


def recuar_continuacao(bloco: str) -> str:
    r"""As linhas depois da primeira entram recuadas.

    E o que impede um texto de varias linhas de derramar no nivel de cima e
    passar por moldura do prompt: a segunda linha de uma fala que diga
    "--- fim do kit ---" sai com quatro espacos na frente, e a marca que fecha
    a cerca continua sendo a unica que comeca na coluna zero.

    **Linha e o que o `splitlines()` diz que e linha** (issue #770). Com
    `split("\n")`, um `\r`, `\x0c` ou `\u2028` no corpo de uma issue nao virava
    linha aqui e escapava do recuo, mas virava linha para quem LE o prompt, e
    a marca de fim voltava para a coluna zero. O criterio e o proprio
    `splitlines()`, e nao uma tabela de caracteres: tabela e enumeracao, e foi
    enumeracao que divergiu do detector no PR #751. A saida so tem `\n`.

    A normalizacao mora AQUI, e nao em quem chama, porque esta funcao e o
    gargalo de todas as cercas do prompt (o `_cercar` do assistente, o kit e a
    conversa do chat). O `splitlines()` descarta a linha vazia final de um
    `"a\n"`, que o `split` mantinha como uma linha so de recuo.

    Docstring cru (prefixo `r`) de proposito: os separadores citados aqui nao
    podem virar quebra de verdade dentro dele.
    """
    primeira, *resto = bloco.splitlines() or [""]
    return "\n".join([primeira, *(f"{RECUO_DA_CONTINUACAO}{linha}" for linha in resto)])


def versao_da_entrega(demanda: dict[str, Any]) -> str | None:
    """A versao do app em que a Demanda subiu, so quando a Etapa e Em producao.

    A coluna pode guardar a versao de uma subida anterior com a Etapa que voltou
    atras (a issue reaberta para um ajuste): mostrar "v0.160.0" ao lado de
    "Entregue" diria que ja esta no ar o que ainda nao esta.
    """
    if demanda.get("etapa") != ETAPA_EM_PRODUCAO:
        return None
    return demanda.get("versao_em_producao") or None


def em_producao_desde(demanda: dict[str, Any]) -> str | None:
    """A data em que a Demanda entrou Em producao, so com a Etapa la (issue
    #1552, ADR 0084, decisao 8). A mesma guarda da versao: a coluna guarda a
    data de uma subida anterior quando a issue reabre."""
    if demanda.get("etapa") != ETAPA_EM_PRODUCAO:
        return None
    return demanda.get("em_producao_em") or None


def entregue_na_data(demanda: dict[str, Any]) -> str | None:
    """A data de entrega do Documento do card: o fechamento da issue-raiz, lido
    na sincronizacao (issue #1552). So com a Etapa Entregue ou Em producao: a
    issue fechada como nao planejada tambem tem data, e nao e entrega."""
    if demanda.get("etapa") not in (ETAPA_ENTREGUE, ETAPA_EM_PRODUCAO):
        return None
    foto = demanda.get("github_foto")
    return (foto.get("fechada_em") or None) if isinstance(foto, dict) else None


def e_desenvolvedor(pessoa: dict[str, Any] | None) -> bool:
    """O Super admin com login do GitHub no cadastro (ADR 0083, decisao 2).

    Nao e perfil nem permissao propria: e o cadastro que diz. Login so de
    espacos conta como sem login.
    """
    return is_super_admin(pessoa) and bool(str((pessoa or {}).get("github_login") or "").strip())


def origem_da_demanda(demanda: dict[str, Any]) -> str:
    """A Origem da Demanda; a linha de antes da coluna (migration 130) e do diretor."""
    return ORIGEM_VITTA if demanda.get("origem") == ORIGEM_VITTA else ORIGEM_DIRETOR


def projeto_da_demanda(demanda: dict[str, Any]) -> str:
    """O Projeto da Demanda (issue #1713, ADR 0093, decisao 2), que diz de qual
    repositorio e a issue dela. A linha de antes da coluna (migration 145) e do
    Hospital, como o default que a migration da as Demandas de hoje."""
    return PROJETO_ANA if demanda.get("projeto") == PROJETO_ANA else PROJETO_HOSPITAL


def pode_ver(pessoa: dict[str, Any], demanda: dict[str, Any]) -> bool:
    """Quem ve uma Demanda: o autor, o Desenvolvedor, que ve todas (ADR 0083),
    e todo Super admin no card de Origem Vitta, aberto pelo terminal (ADR 0084,
    decisao 4). A conversa de outro diretor continua fechada.

    A regra e uma so, e a lista e a leitura da conversa leem daqui.
    """
    return (
        demanda.get("autor_id") == pessoa.get("id")
        or e_desenvolvedor(pessoa)
        or origem_da_demanda(demanda) == ORIGEM_VITTA
    )


# Ate onde a Demanda se apaga (ADR 0084, decisao 2): ate Planejada. Em
# desenvolvimento ja existe PR aberto, e dali em diante o app recusa. Nao sera
# feita tambem se apaga (issue #1637): ninguem vai fazer o pedido, e sem isto o
# card fechado pelo GitHub ficava na lista para sempre.
ETAPAS_QUE_SE_APAGAM: tuple[str, ...] = (ETAPA_REGISTRADA, ETAPA_EM_ANALISE, ETAPA_PLANEJADA, ETAPA_NAO_SERA_FEITA)

MOTIVO_APAGAR_SO_O_AUTOR = "Só quem começou esta conversa pode apagá-la."
MOTIVO_APAGAR_SO_O_DESENVOLVEDOR = "Pedido que já virou card, só a Vitta apaga. Peça na Conversa da Demanda."
MOTIVO_APAGAR_JA_COMECOU = "Este pedido já começou a ser feito e não pode mais ser apagado."


def recusa_de_apagar(pessoa: dict[str, Any], demanda: dict[str, Any]) -> tuple[int, str] | None:
    """Por que esta pessoa nao apaga esta Demanda, ou `None` se apaga (ADR 0084,
    decisao 2). A recusa vem com o status HTTP e a frase da tela.

    A conversa que nao virou card, quem apaga e o autor ou o Desenvolvedor
    (issue #1637: a conversa velha de outra pessoa nao fica na lista para
    sempre). O card criado, so o Desenvolvedor, ate Planejada ou em Nao sera
    feita. Quem nao pode apagar e 403 antes de a Etapa ser olhada. A lista le
    daqui para mostrar o botao so a quem pode.
    """
    if not demanda.get("github_issue_numero"):
        if demanda.get("autor_id") != pessoa.get("id") and not e_desenvolvedor(pessoa):
            return 403, MOTIVO_APAGAR_SO_O_AUTOR
        return None
    if not e_desenvolvedor(pessoa):
        return 403, MOTIVO_APAGAR_SO_O_DESENVOLVEDOR
    if demanda.get("etapa") not in ETAPAS_QUE_SE_APAGAM:
        return 409, MOTIVO_APAGAR_JA_COMECOU
    return None


# A Revisao com o codigo de hoje (ADR 0084, decisao 3): so no card Em analise
# ou Planejada, e enquanto nenhuma parte esta em desenvolvimento.
ETAPAS_QUE_SE_REVISAM: tuple[str, ...] = (ETAPA_EM_ANALISE, ETAPA_PLANEJADA)

MOTIVO_REVISAR_SO_O_CARD_DA_MELHORIA = "Só a melhoria que já virou card se revisa com o código de hoje."
MOTIVO_REVISAR_SO_O_AUTOR = "Só quem pediu e a Vitta revisam este pedido."
MOTIVO_REVISAR_JA_COMECOU = "Este pedido já começou a ser feito e não pode mais ser revisado."


def recusa_de_revisar(pessoa: dict[str, Any], demanda: dict[str, Any]) -> tuple[int, str] | None:
    """Por que esta pessoa nao revisa esta Demanda, ou `None` se revisa (ADR
    0084, decisao 3). A recusa vem com o status HTTP e a frase da tela.

    Revisa-se a melhoria do chat que virou card: o bug e o card da Vitta nao
    tem planejamento para retomar. Clicam o autor e o Desenvolvedor. A Etapa
    tem de ser Em analise ou Planejada, sem parte Em desenvolvimento. A lista
    le daqui para mostrar o botao so a quem pode.
    """
    if (
        not demanda.get("github_issue_numero")
        or demanda.get("tipo") != "novo"
        or origem_da_demanda(demanda) == ORIGEM_VITTA
    ):
        return 409, MOTIVO_REVISAR_SO_O_CARD_DA_MELHORIA
    if demanda.get("autor_id") != pessoa.get("id") and not e_desenvolvedor(pessoa):
        return 403, MOTIVO_REVISAR_SO_O_AUTOR
    partes = demanda.get("partes") if isinstance(demanda.get("partes"), list) else []
    em_desenvolvimento = any(
        isinstance(parte, dict) and parte.get("situacao") == ETAPA_EM_DESENVOLVIMENTO for parte in partes
    )
    if demanda.get("etapa") not in ETAPAS_QUE_SE_REVISAM or em_desenvolvimento:
        return 409, MOTIVO_REVISAR_JA_COMECOU
    return None


def responsavel_da_demanda(demanda: dict[str, Any]) -> str | None:
    """O id do Responsavel, que so existe depois do "Criar o card" (ADR 0083,
    decisao 5).

    A conversa sem card nao tem Responsavel, mesmo com a coluna preenchida: a
    Demanda de antes desta versao nascia com o dono do Produto ali, e ninguem o
    escolheu.
    """
    if not demanda.get("github_issue_numero"):
        return None
    return demanda.get("responsavel_id") or None


def quem_avisar(
    demanda: dict[str, Any], *, autor_id: str, mencoes: list[str], ja_escreveram: Sequence[str] = ()
) -> list[str]:
    """Quem a mensagem da Conversa da Demanda avisa no sino (ADR 0083, decisao 8).

    Mencao avisa o mencionado, e so ele. Sem mencao, a mensagem do autor da
    Demanda avisa o Responsavel, e a de qualquer outro (o Desenvolvedor, unico
    que alem do autor escreve ali) avisa o autor. No card de Origem Vitta, que
    toda a diretoria le e escreve (ADR 0084, decisao 4), avisa tambem quem ja
    escreveu na conversa: o autor ali e o proprio Desenvolvedor, e sem isso a
    resposta nunca chega ao diretor que perguntou. Ninguem e avisado da
    propria mensagem.
    """
    if mencoes:
        destino = list(mencoes)
    elif autor_id == demanda.get("autor_id"):
        destino = [responsavel_da_demanda(demanda)]
    else:
        destino = [demanda.get("autor_id")]
    if not mencoes and origem_da_demanda(demanda) == ORIGEM_VITTA:
        destino += list(ja_escreveram)
    return sorted({str(d) for d in destino if d and d != autor_id})


def login_do_responsavel(demanda: dict[str, Any]) -> str | None:
    """O login do dono da issue, como a foto o guardou, ou `None`.

    E o que a tela mostra quando o dono do GitHub nao e usuario do app (issue
    #1534, ADR 0083, decisao 6): sem `responsavel_id`, o Responsavel aparece
    pelo login. A conversa sem card nao tem dono, como em
    `responsavel_da_demanda`.
    """
    if not demanda.get("github_issue_numero"):
        return None
    foto = demanda.get("github_foto")
    login = foto.get(FATO_ASSIGNEE) if isinstance(foto, dict) else None
    return login if isinstance(login, str) and login else None
